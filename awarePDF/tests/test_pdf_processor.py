# ============================================================
# tests/test_pdf_processor.py
# Run with: pytest tests/
# ============================================================

import pytest
from pathlib import Path


def test_get_pdf_hash_is_consistent():
    """Same file should always produce same hash."""
    from app.utils.file_handler import get_pdf_hash
    tmp = Path("/tmp/test_dummy.pdf")
    tmp.write_bytes(b"%PDF-1.4 dummy content for testing")
    hash1 = get_pdf_hash(str(tmp))
    hash2 = get_pdf_hash(str(tmp))
    assert hash1 == hash2
    assert len(hash1) == 32
    tmp.unlink()


def test_is_highlighted_content_detects_keywords():
    """Should flag textbook important-box content."""
    from app.core.pdf_processor import _is_highlighted_content
    assert _is_highlighted_content("Note: This is important") is True
    assert _is_highlighted_content("Warning: Do not skip this") is True
    assert _is_highlighted_content("Definition: A queue is FIFO") is True
    assert _is_highlighted_content("This is a regular paragraph.") is False


def test_chunk_documents_does_not_split_tables():
    """Tables should never be split regardless of size."""
    from app.core.chunker import chunk_documents
    big_table = {
        "text": "| Col1 | Col2 |\n" + "| data | data |\n" * 100,
        "page_number": 1,
        "content_type": "table",
        "section": "Test",
        "is_important": False,
        "chunk_index": 0,
    }
    result = chunk_documents([big_table])
    assert len(result) == 1
    assert result[0]["content_type"] == "table"


def test_chunk_documents_splits_long_text():
    """Long text chunks should be split into smaller ones."""
    from app.core.chunker import chunk_documents
    long_text = {
        "text": "This is a sentence about data structures. " * 100,
        "page_number": 2,
        "content_type": "text",
        "section": "Test",
        "is_important": False,
        "chunk_index": 1,
    }
    result = chunk_documents([long_text])
    assert len(result) > 1
