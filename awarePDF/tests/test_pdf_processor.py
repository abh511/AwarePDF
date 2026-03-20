# ============================================================
# tests/test_pdf_processor.py
# Run with: pytest tests/
# ============================================================

import pytest
from pathlib import Path


def test_get_pdf_hash_is_consistent():
    """Same file should always produce same hash (SHA-256 = 64 hex chars)."""
    from app.utils.file_handler import get_pdf_hash
    tmp = Path("/tmp/test_dummy.pdf")
    tmp.write_bytes(b"%PDF-1.4 dummy content for testing")
    hash1 = get_pdf_hash(str(tmp))
    hash2 = get_pdf_hash(str(tmp))
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 produces 64 hex chars
    tmp.unlink()


def test_guess_is_important_detects_headings():
    """Should flag headings as important."""
    from app.core.pdf_processor import _guess_is_important

    class FakeItem:
        style = ""
        type = ""
        category = ""
        is_highlighted = False
        is_boxed = False

    item = FakeItem()
    assert _guess_is_important(item, "heading", "Chapter 1") is True
    assert _guess_is_important(item, "text", "Regular paragraph") is False


def test_chunk_with_metadata_does_not_split_tables():
    """Tables should never be split regardless of size."""
    from app.core.chunker import chunk_with_metadata
    big_table = {
        "text": "| Col1 | Col2 |\n" + "| data | data |\n" * 100,
        "page_number": 1,
        "content_type": "table",
        "section": "Test",
        "is_important": False,
        "chunk_index": 0,
    }
    result = chunk_with_metadata([big_table])
    assert len(result) == 1
    assert result[0]["content_type"] == "table"


def test_chunk_with_metadata_splits_long_text():
    """Long text chunks should be split into smaller ones."""
    from app.core.chunker import chunk_with_metadata
    long_text = {
        "text": "This is a sentence about data structures. " * 100,
        "page_number": 2,
        "content_type": "text",
        "section": "Test",
        "is_important": False,
        "chunk_index": 1,
    }
    result = chunk_with_metadata([long_text])
    assert len(result) > 1
