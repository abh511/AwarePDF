# ============================================================
# tests/test_vector_store.py
# ============================================================

import pytest
import tempfile
import os


def test_collection_lifecycle(tmp_path, monkeypatch):
    """Test create, check exists, and delete collection."""
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path))

    # Reload settings with patched env
    import importlib
    import config.settings as settings
    importlib.reload(settings)

    import app.core.vector_store as vs
    vs._client = None  # Reset singleton

    test_hash = "abc123testhash"

    # Should not exist yet
    assert vs.collection_exists(test_hash) is False

    # Create it
    col = vs.create_or_get_collection(test_hash)
    assert col is not None
    assert vs.collection_exists(test_hash) is True

    # Delete it
    vs.delete_collection(test_hash)
    assert vs.collection_exists(test_hash) is False


def test_add_and_search(tmp_path, monkeypatch):
    """Test adding documents and retrieving them."""
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path))

    import importlib
    import config.settings as settings
    importlib.reload(settings)

    import app.core.vector_store as vs
    vs._client = None

    test_hash = "searchtest456"
    col = vs.create_or_get_collection(test_hash)

    chunks = [
        {
            "text": "Quicksort is a divide and conquer sorting algorithm.",
            "page_number": 5,
            "content_type": "text",
            "section": "Sorting Algorithms",
            "is_important": False,
            "chunk_index": 0,
        },
        {
            "text": "Binary search finds an element in a sorted array in O(log n).",
            "page_number": 8,
            "content_type": "text",
            "section": "Searching",
            "is_important": True,
            "chunk_index": 1,
        },
    ]

    vs.add_documents(col, chunks)
    results = vs.similarity_search(col, "how does sorting work?", k=1)

    assert len(results) == 1
    assert "sort" in results[0]["text"].lower()
