"""Section-aware chunking for long textbooks.

Docling yields one element per paragraph/list item, which is far too small for
good retrieval (a 700-page book produces 10k+ fragments of ~100 chars).
This module:
- Merges consecutive paragraphs of the same section up to CHUNK_SIZE chars
- Splits only oversized paragraphs, at sentence boundaries, with overlap
- Splits huge tables by rows, repeating the header row in every part
- Keeps headings as separate chunks (used for the outline, excluded from search)
- Never drops text
"""

import re

from app.utils.logger import get_logger
from config.settings import CHUNK_SIZE, CHUNK_OVERLAP

logger = get_logger(__name__)

_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")


def _hard_split(text: str, size: int) -> list[str]:
    """Split text with no sentence boundaries at word boundaries."""
    pieces: list[str] = []
    current = ""
    for word in text.split(" "):
        if current and len(current) + 1 + len(word) > size:
            pieces.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        pieces.append(current)
    return pieces


def split_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split long text into pieces of at most ~size chars, at sentence boundaries."""
    if len(text) <= size:
        return [text]

    sentences: list[str] = []
    for sentence in _SENTENCE_END_RE.split(text):
        sentences.extend(_hard_split(sentence, size) if len(sentence) > size else [sentence])

    pieces: list[str] = []
    current: list[str] = []
    length = 0
    for sentence in sentences:
        if current and length + len(sentence) + 1 > size:
            pieces.append(" ".join(current))
            # Carry trailing sentences into the next piece as overlap
            carried: list[str] = []
            carried_len = 0
            for prev in reversed(current):
                if carried_len + len(prev) > overlap:
                    break
                carried.insert(0, prev)
                carried_len += len(prev) + 1
            current, length = carried, carried_len
        current.append(sentence)
        length += len(sentence) + 1
    if current:
        pieces.append(" ".join(current))
    return pieces


def split_table(markdown: str, size: int = CHUNK_SIZE) -> list[str]:
    """Split a markdown table into row groups, repeating the header in each part."""
    if len(markdown) <= size * 2:
        return [markdown]
    lines = markdown.splitlines()
    header, rows = lines[:2], lines[2:]
    header_len = sum(len(line) + 1 for line in header)
    parts: list[str] = []
    current: list[str] = []
    length = header_len
    for row in rows:
        if current and length + len(row) + 1 > size * 2:
            parts.append("\n".join(header + current))
            current, length = [], header_len
        current.append(row)
        length += len(row) + 1
    if current:
        parts.append("\n".join(header + current))
    return parts


def chunk_elements(elements: list[dict]) -> list[dict]:
    """
    Turn reading-order elements into retrieval chunks.

    Each element: {"text", "page_number", "content_type" (text|heading|table), "section"}
    Each chunk adds "page_end" (last page it spans) and "chunk_index".
    """
    chunks: list[dict] = []
    buffer: list[str] = []
    buffer_len = 0
    buffer_section = ""
    buffer_pages = (0, 0)

    def add(text: str, content_type: str, section: str, page: int, page_end: int) -> None:
        chunks.append({
            "text": text,
            "page_number": page,
            "page_end": page_end,
            "content_type": content_type,
            "section": section,
            "chunk_index": len(chunks),
        })

    def flush() -> None:
        nonlocal buffer, buffer_len
        if buffer:
            add("\n".join(buffer), "text", buffer_section, *buffer_pages)
        buffer, buffer_len = [], 0

    for element in elements:
        text = (element.get("text") or "").strip()
        if not text:
            continue
        content_type = element.get("content_type", "text")
        section = element.get("section", "")
        page = int(element.get("page_number") or 0)

        if content_type == "heading":
            flush()
            add(text, "heading", section, page, page)
            continue

        if content_type == "table":
            flush()
            for part in split_table(text):
                add(part, "table", section, page, page)
            continue

        if buffer and section != buffer_section:
            flush()

        if len(text) > CHUNK_SIZE:
            flush()
            for piece in split_text(text):
                add(piece, "text", section, page, page)
            continue

        if buffer and buffer_len + len(text) + 1 > CHUNK_SIZE:
            flush()
        if not buffer:
            buffer_section = section
            buffer_pages = (page, page)
        buffer.append(text)
        buffer_len += len(text) + 1
        buffer_pages = (buffer_pages[0], max(buffer_pages[1], page))

    flush()

    text_chunks = [c for c in chunks if c["content_type"] != "heading"]
    logger.info(
        "Chunking: %s elements → %s chunks (%s headings, avg %s chars)",
        len(elements),
        len(chunks),
        len(chunks) - len(text_chunks),
        sum(len(c["text"]) for c in text_chunks) // max(1, len(text_chunks)),
    )
    return chunks
