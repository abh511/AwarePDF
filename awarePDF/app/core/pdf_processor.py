"""Docling-based PDF parsing and chunk preparation with caching support."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Callable

from pypdf import PdfReader

from app.core import chunker
from app.core import image_extractor
import config.settings as settings

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[float, str], None]


def _get_cache_dir() -> Path:
    return Path(settings.PROCESSED_DIR)


class PDFProcessingError(Exception):
    """Raised when PDF processing cannot be completed safely."""


def _report_progress(callback: ProgressCallback | None, progress: float, message: str) -> None:
    if callback is None:
        return
    try:
        callback(max(0.0, min(1.0, progress)), message)
    except Exception:
        logger.exception("Progress callback raised an exception.")


def _ensure_cache_dir() -> None:
    _get_cache_dir().mkdir(parents=True, exist_ok=True)


def _compute_pdf_hash(pdf_path: Path) -> str:
    digest = hashlib.sha256()
    with pdf_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cache_file_path(pdf_hash: str) -> Path:
    return _get_cache_dir() / f"{pdf_hash}.json"


def _load_cached_chunks(pdf_hash: str) -> list[dict] | None:
    cache_path = _cache_file_path(pdf_hash)
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            logger.info("Loaded %s cached chunks from %s", len(payload), cache_path)
            return payload
        logger.warning("Cache file has invalid format (expected list): %s", cache_path)
        return None
    except Exception:
        logger.exception("Failed to load cached chunks from %s", cache_path)
        return None


def _save_cached_chunks(pdf_hash: str, chunks: list[dict]) -> None:
    """Persist ALL chunks (text + image descriptions) to cache."""
    cache_path = _cache_file_path(pdf_hash)
    try:
        # image_bytes is not JSON-serializable - strip it before saving
        serializable = []
        for chunk in chunks:
            c = {k: v for k, v in chunk.items() if k != "image_bytes"}
            serializable.append(c)
        cache_path.write_text(
            json.dumps(serializable, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        logger.info("Saved %s chunks to cache: %s", len(serializable), cache_path)
    except Exception:
        logger.exception("Failed to write cache file: %s", cache_path)


def _assert_not_encrypted(pdf_path: Path) -> None:
    try:
        reader = PdfReader(str(pdf_path))
        if reader.is_encrypted:
            raise PDFProcessingError(
                f"PDF '{pdf_path.name}' is encrypted and cannot be processed. "
                "Please provide an unencrypted PDF."
            )
    except PDFProcessingError:
        raise
    except Exception as exc:
        logger.exception("Failed to inspect PDF encryption state: %s", pdf_path)
        raise PDFProcessingError(f"Unable to read PDF '{pdf_path.name}'.") from exc


def _import_docling_components() -> tuple[Any, Any]:
    try:
        from docling.document_converter import DocumentConverter, PdfPipelineOptions
        return DocumentConverter, PdfPipelineOptions
    except Exception as exc:
        logger.exception("Failed to import Docling components.")
        raise PDFProcessingError(
            "Docling is not available. Install it with: pip install docling"
        ) from exc


def _build_converter() -> Any:
    DocumentConverter, PdfPipelineOptions = _import_docling_components()
    try:
        options = PdfPipelineOptions(
            do_ocr=True,
            do_table_structure=True,
            do_cell_matching=True,
        )
        try:
            return DocumentConverter(pipeline_options=options)
        except TypeError:
            from docling.document_converter import PdfFormatOption
            return DocumentConverter(
                format_options={"pdf": PdfFormatOption(pipeline_options=options)}
            )
    except Exception as exc:
        logger.exception("Failed to initialize Docling converter.")
        raise PDFProcessingError("Unable to initialize Docling converter.") from exc


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def _guess_is_heading(item: Any, text: str) -> bool:
    label = _safe_text(getattr(item, "label", "")).lower()
    kind = _safe_text(getattr(item, "kind", "")).lower()
    style = _safe_text(getattr(item, "style", "")).lower()
    if any(t in f"{label} {kind} {style}" for t in ("heading", "header", "title", "section")):
        return True
    if not text:
        return False
    if len(text) <= 120 and text == text.upper() and any(ch.isalpha() for ch in text):
        return True
    return bool(re.match(r"^\d+(\.\d+)*\s+[A-Z].+", text))


def _guess_is_important(item: Any, content_type: str, text: str) -> bool:
    if content_type == "heading":
        return True
    marker_blob = " ".join([
        _safe_text(getattr(item, "style", "")),
        _safe_text(getattr(item, "type", "")),
        _safe_text(getattr(item, "category", "")),
    ]).lower()
    if any(t in marker_blob for t in ("highlight", "boxed", "callout", "important")):
        return True
    return bool(
        (getattr(item, "is_highlighted", False) or getattr(item, "is_boxed", False)) and text
    )


def _extract_page_number(item: Any) -> int:
    candidates = [
        getattr(item, "page_number", None),
        getattr(item, "page", None),
    ]
    provenance = getattr(item, "provenance", None)
    if provenance is not None:
        candidates.append(getattr(provenance, "page_number", None))
        candidates.append(getattr(provenance, "page", None))
    for value in candidates:
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return 0


def _extract_text_blocks(document: Any) -> list[Any]:
    blocks: list[Any] = []
    for field in ("texts", "paragraphs", "blocks", "items"):
        value = getattr(document, field, None)
        if isinstance(value, list):
            blocks.extend(value)
    seen: set[int] = set()
    unique: list[Any] = []
    for block in blocks:
        marker = id(block)
        if marker not in seen:
            seen.add(marker)
            unique.append(block)
    return unique


def _extract_tables(document: Any) -> list[Any]:
    tables = getattr(document, "tables", None)
    return tables if isinstance(tables, list) else []


def _extract_figures(document: Any) -> list[Any]:
    figures = getattr(document, "figures", None)
    return figures if isinstance(figures, list) else []


def _table_to_markdown(table: Any) -> str:
    for method_name in ("to_markdown", "export_to_markdown", "as_markdown"):
        method = getattr(table, method_name, None)
        if callable(method):
            try:
                return _safe_text(method())
            except Exception:
                logger.debug("Table markdown conversion failed via %s", method_name, exc_info=True)

    matrix = getattr(table, "cells", None) or getattr(table, "rows", None)
    if not isinstance(matrix, list) or not matrix:
        return ""

    rendered_rows: list[list[str]] = []
    for row in matrix:
        if isinstance(row, list):
            rendered_rows.append([_safe_text(cell) for cell in row])
        else:
            rendered_rows.append([_safe_text(row)])

    if not rendered_rows:
        return ""

    header = rendered_rows[0]
    lines = [
        f"| {' | '.join(header)} |",
        f"| {' | '.join(['---'] * len(header))} |",
    ]
    for row in rendered_rows[1:]:
        padded = row + [""] * max(0, len(header) - len(row))
        lines.append(f"| {' | '.join(padded[:len(header)])} |")
    return "\n".join(lines)


def _caption_from_figure(figure: Any) -> str:
    for attr in ("caption", "text", "title"):
        caption = _safe_text(getattr(figure, attr, None))
        if caption:
            return caption
    return ""


def _append_chunk(
    chunks: list[dict],
    text: str,
    page_number: int,
    content_type: str,
    section: str,
    is_important: bool,
) -> None:
    normalized = _safe_text(text)
    if not normalized:
        return
    chunks.append({
        "text": normalized,
        "page_number": int(page_number),
        "content_type": content_type,
        "section": section,
        "is_important": bool(is_important),
        "chunk_index": len(chunks),
    })


def _extract_structured_chunks(
    document: Any,
    progress_cb: ProgressCallback | None = None,
) -> list[dict]:
    chunks: list[dict] = []
    active_section = ""

    text_blocks = _extract_text_blocks(document)
    tables = _extract_tables(document)
    figures = _extract_figures(document)

    total_steps = max(1, len(text_blocks) + len(tables) + len(figures))
    step = 0

    for block in text_blocks:
        raw_text = _safe_text(
            getattr(block, "text", None)
            or getattr(block, "content", None)
            or block
        )
        if not raw_text:
            continue
        content_type = "heading" if _guess_is_heading(block, raw_text) else "text"
        if content_type == "heading":
            active_section = raw_text
        _append_chunk(
            chunks=chunks,
            text=raw_text,
            page_number=_extract_page_number(block),
            content_type=content_type,
            section=active_section,
            is_important=_guess_is_important(block, content_type, raw_text),
        )
        step += 1
        _report_progress(progress_cb, 0.2 + 0.45 * (step / total_steps), "Extracting text and headings")

    for table in tables:
        markdown = _table_to_markdown(table)
        _append_chunk(
            chunks=chunks,
            text=markdown,
            page_number=_extract_page_number(table),
            content_type="table",
            section=active_section,
            is_important=_guess_is_important(table, "table", markdown),
        )
        step += 1
        _report_progress(progress_cb, 0.2 + 0.45 * (step / total_steps), "Extracting tables")

    for figure in figures:
        caption = _caption_from_figure(figure)
        _append_chunk(
            chunks=chunks,
            text=caption,
            page_number=_extract_page_number(figure),
            content_type="figure_caption",
            section=active_section,
            is_important=_guess_is_important(figure, "figure_caption", caption),
        )
        step += 1
        _report_progress(progress_cb, 0.2 + 0.45 * (step / total_steps), "Extracting figure captions")

    return chunks


def _invoke_chunker(chunks: list[dict]) -> list[dict]:
    for fn_name in ("chunk_with_metadata", "chunk_structured_content", "create_chunks", "chunk_text"):
        fn = getattr(chunker, fn_name, None)
        if not callable(fn):
            continue
        try:
            output = fn(chunks)
            if isinstance(output, list):
                logger.info("Chunker '%s' produced %s chunks.", fn_name, len(output))
                return output
        except Exception:
            logger.debug("Chunker '%s' failed.", fn_name, exc_info=True)
    logger.warning("No compatible chunker function found; returning extracted chunks directly.")
    return chunks


def process_pdf(
    pdf_path: str,
    progress_callback: ProgressCallback | None = None,
) -> list[dict]:
    """
    Process a PDF into structured chunks (text + images) and cache results.

    Progress stages:
      0.00 - start
      0.10 - hash computed
      0.15 - Docling initialised
      0.20 - Docling conversion running
      0.65 - text/table/figure extraction done
      0.75 - chunker done
      0.85 - image extraction done
      1.00 - complete

    Returns:
        List of structured chunks with metadata ready for ChromaDB indexing.

    Raises:
        PDFProcessingError: If the file is invalid, encrypted, or processing fails.
    """
    path = Path(pdf_path)
    _report_progress(progress_callback, 0.0, "Starting PDF processing")

    if not path.exists() or not path.is_file():
        raise PDFProcessingError(f"PDF file not found: {pdf_path}")

    _ensure_cache_dir()

    try:
        _assert_not_encrypted(path)
        _report_progress(progress_callback, 0.1, "Computing PDF hash")
        pdf_hash = _compute_pdf_hash(path)

        # Return cached result if available (includes image chunks)
        cached = _load_cached_chunks(pdf_hash)
        if cached is not None:
            _report_progress(progress_callback, 1.0, "Loaded from cache")
            return cached

        _report_progress(progress_callback, 0.15, "Initializing Docling")
        converter = _build_converter()

        _report_progress(progress_callback, 0.2, "Running Docling conversion (may take a while for large PDFs)")
        conversion_result = converter.convert(str(path))
        document = getattr(conversion_result, "document", conversion_result)

        raw_chunks = _extract_structured_chunks(document, progress_callback)
        _report_progress(progress_callback, 0.65, "Running chunker")
        final_chunks = _invoke_chunker(raw_chunks)

        # Normalise required fields
        for index, chunk in enumerate(final_chunks):
            chunk["chunk_index"] = index
            chunk.setdefault("page_number", 0)
            chunk.setdefault("content_type", "text")
            chunk.setdefault("section", "")
            chunk.setdefault("is_important", False)
            chunk.setdefault("text", "")

        # --- IMAGE EXTRACTION ---
        _report_progress(progress_callback, 0.75, "Extracting images and diagrams")
        try:
            image_chunks = image_extractor.extract_images_as_chunks(
                pdf_path=str(path),
                pdf_hash=pdf_hash,
            )
            if image_chunks:
                base_index = len(final_chunks)
                for i, chunk in enumerate(image_chunks):
                    chunk["chunk_index"] = base_index + i
                    chunk.setdefault("page_number", 0)
                    chunk.setdefault("content_type", "image_description")
                    chunk.setdefault("section", "")
                    chunk.setdefault("is_important", True)
                final_chunks.extend(image_chunks)
                logger.info("Added %s image description chunks.", len(image_chunks))
        except Exception:
            logger.exception("Image extraction failed (non-fatal), continuing with text chunks only.")

        # Cache AFTER image extraction so re-runs don't redo everything
        _report_progress(progress_callback, 0.9, "Saving to cache")
        _save_cached_chunks(pdf_hash, final_chunks)

        _report_progress(progress_callback, 1.0, "PDF processing complete")
        logger.info("Processed '%s' into %s chunks (text + images).", path.name, len(final_chunks))
        return final_chunks

    except PDFProcessingError:
        raise
    except Exception as exc:
        logger.exception("PDF processing failed for %s", pdf_path)
        raise PDFProcessingError(f"Failed to process PDF '{path.name}'.") from exc
