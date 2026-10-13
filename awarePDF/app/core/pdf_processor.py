"""Docling-based PDF parsing into section-aware chunks (text and tables).

Built for long textbooks (700+ pages):
- Pages are parsed in batches of PAGE_BATCH_SIZE, which bounds memory use
  and gives real progress updates
- OCR is off by default (digital PDFs don't need it and it is the slowest step)
- Page headers/footers are skipped; every element keeps its real page number
- Results are cached by file hash, so a book is only processed once
- Images are saved here; their descriptions are added later in the background
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

from app.core import chunker
from app.core import image_extractor
from app.utils.file_handler import get_pdf_hash
from app.utils.logger import get_logger
import config.settings as settings

logger = get_logger(__name__)

ProgressCallback = Callable[[float, str], None]

# Bump when the chunk format changes so stale caches are ignored
CACHE_VERSION = 3

_HEADING_LABELS = {"section_header", "title"}
_SKIPPED_LABELS = {"picture", "chart", "page_header", "page_footer"}
# Callout boxes and code lines that layout models often mislabel as headings
_CALLOUT_WORDS = {"tip", "note", "warning", "caution", "important", "example", "solution", "exercise"}
_CODE_RE = re.compile(r"\w\(|[=;{}]|^\s*(import|def|class|from)\s")


class PDFProcessingError(Exception):
    """Raised when PDF processing cannot be completed safely."""


def _report_progress(callback: ProgressCallback | None, progress: float, message: str) -> None:
    if callback is None:
        return
    try:
        callback(max(0.0, min(1.0, progress)), message)
    except Exception:
        logger.exception("Progress callback raised an exception.")


def _cache_file_path(pdf_hash: str) -> Path:
    return Path(settings.PROCESSED_DIR) / f"{pdf_hash}.v{CACHE_VERSION}.json"


def _load_cached_chunks(pdf_hash: str) -> list[dict] | None:
    cache_path = _cache_file_path(pdf_hash)
    if not cache_path.exists():
        return None
    try:
        chunks = json.loads(cache_path.read_text(encoding="utf-8"))
        logger.info("Loaded %s cached chunks from %s", len(chunks), cache_path)
        return chunks
    except Exception:
        logger.exception("Failed to load cached chunks from %s", cache_path)
        return None


def _save_cached_chunks(pdf_hash: str, chunks: list[dict]) -> None:
    cache_path = _cache_file_path(pdf_hash)
    try:
        cache_path.write_text(json.dumps(chunks, separators=(",", ":")), encoding="utf-8")
        logger.info("Saved %s chunks to cache: %s", len(chunks), cache_path)
    except Exception:
        logger.exception("Failed to write cache file: %s", cache_path)


def get_page_count(pdf_path: str | Path) -> int:
    """Return the page count, raising PDFProcessingError for unreadable/locked PDFs."""
    import fitz  # PyMuPDF

    try:
        with fitz.open(str(pdf_path)) as doc:
            if doc.needs_pass:
                raise PDFProcessingError(
                    f"PDF '{Path(pdf_path).name}' is password-protected. "
                    "Please provide an unlocked PDF."
                )
            return doc.page_count
    except PDFProcessingError:
        raise
    except Exception as exc:
        raise PDFProcessingError(f"Unable to read PDF '{Path(pdf_path).name}'.") from exc


def _build_converter() -> Any:
    """Build a Docling DocumentConverter tuned for long digital textbooks."""
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as exc:
        raise PDFProcessingError("Docling is not available. Install it with: pip install docling") from exc

    options = PdfPipelineOptions()
    options.do_ocr = settings.ENABLE_OCR
    options.do_table_structure = True
    options.table_structure_options.mode = (
        TableFormerMode.ACCURATE if settings.TABLE_MODE == "accurate" else TableFormerMode.FAST
    )
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


def _clean(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text or "").strip()


def _is_real_heading(text: str) -> bool:
    words = text.strip(" :.").lower()
    return len(words) >= 3 and words not in _CALLOUT_WORDS and not _CODE_RE.search(text)


def _extract_elements(document: Any, section: str) -> tuple[list[dict], str]:
    """
    Walk a Docling document in reading order.

    Returns (elements, last_section) so the section carries across page batches.
    """
    from docling_core.types.doc import TableItem

    elements: list[dict] = []
    for item, _level in document.iterate_items():
        label = str(getattr(item, "label", ""))
        if label in _SKIPPED_LABELS:
            continue

        prov = getattr(item, "prov", None)
        page = prov[0].page_no if prov else 0

        if isinstance(item, TableItem):
            text = item.export_to_markdown(doc=document)
            content_type = "table"
        else:
            text = _clean(getattr(item, "text", ""))
            is_heading = label in _HEADING_LABELS and _is_real_heading(text)
            content_type = "heading" if is_heading else "text"

        if not text:
            continue
        if content_type == "heading":
            section = text[:200]
        elements.append({
            "text": text,
            "page_number": page,
            "content_type": content_type,
            "section": section,
        })
    return elements, section


def process_pdf(
    pdf_path: str,
    progress_callback: ProgressCallback | None = None,
) -> list[dict]:
    """
    Process a PDF into structured chunks (text + tables + diagrams) and cache results.

    Progress: 0.00-0.95 parsing pages, 0.95 saving images, 1.00 done.

    Raises:
        PDFProcessingError: If the file is invalid, encrypted, or processing fails.
    """
    path = Path(pdf_path)
    if not path.is_file():
        raise PDFProcessingError(f"PDF file not found: {pdf_path}")

    _report_progress(progress_callback, 0.0, "Starting PDF processing")
    page_count = get_page_count(path)
    pdf_hash = get_pdf_hash(str(path))

    cached = _load_cached_chunks(pdf_hash)
    if cached is not None:
        _report_progress(progress_callback, 1.0, "Loaded from cache")
        return cached

    try:
        _report_progress(progress_callback, 0.01, "Loading layout models")
        converter = _build_converter()

        elements: list[dict] = []
        section = ""
        batch = max(1, settings.PAGE_BATCH_SIZE)
        for start in range(1, page_count + 1, batch):
            end = min(start + batch - 1, page_count)
            _report_progress(
                progress_callback,
                0.95 * (start - 1) / page_count,
                f"Reading pages {start}-{end} of {page_count}",
            )
            result = converter.convert(str(path), page_range=(start, end), raises_on_error=False)
            if result.document is None:
                logger.warning("Docling could not parse pages %s-%s (%s)", start, end, result.status)
                continue
            batch_elements, section = _extract_elements(result.document, section)
            elements.extend(batch_elements)

        chunks = chunker.chunk_elements(elements)
        if not any(c["content_type"] != "heading" for c in chunks):
            raise PDFProcessingError(
                f"No text found in '{path.name}'. If it is a scanned book, set ENABLE_OCR=True in .env."
            )

        # Image files only; descriptions are generated in the background after indexing
        _report_progress(progress_callback, 0.95, "Extracting images and diagrams")
        try:
            image_extractor.extract_images(str(path), pdf_hash)
        except Exception:
            logger.exception("Image extraction failed (non-fatal), continuing with text only.")

        _save_cached_chunks(pdf_hash, chunks)
        _report_progress(progress_callback, 1.0, "PDF processing complete")
        logger.info("Processed '%s' (%s pages) into %s chunks.", path.name, page_count, len(chunks))
        return chunks

    except PDFProcessingError:
        raise
    except Exception as exc:
        logger.exception("PDF processing failed for %s", pdf_path)
        raise PDFProcessingError(f"Failed to process PDF '{path.name}': {exc}") from exc
