# ============================================================
# tests/test_vector_store.py
# ============================================================

import pytest

import app.core.vector_store as vs
import config.settings as settings

CHUNKS = [
    {"text": "Sorting", "page_number": 4, "content_type": "heading", "section": "Sorting", "chunk_index": 0},
    {
        "text": "Quicksort is a divide and conquer sorting algorithm.",
        "page_number": 5, "page_end": 6, "content_type": "text", "section": "Sorting", "chunk_index": 1,
    },
    {
        "text": "Binary search finds an element in a sorted array in O(log n).",
        "page_number": 8, "content_type": "text", "section": "Searching", "chunk_index": 2,
    },
    {
        "text": "A flowchart of the binary search loop.",
        "page_number": 9, "content_type": "image_description", "section": "Searching",
        "chunk_index": 3, "image_path": "/tmp/page_9_img_0.png",
    },
]


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "CHROMA_PERSIST_DIR", tmp_path)
    vs.reset_runtime_state()
    yield
    vs.reset_runtime_state()


def test_collection_lifecycle():
    pdf_hash = "abc123testhash"
    assert vs.get_collection(pdf_hash) is None
    assert vs.is_indexed(pdf_hash) is False

    vs.index_chunks(pdf_hash, CHUNKS)
    assert vs.is_indexed(pdf_hash) is True
    assert vs.get_chunk_count(pdf_hash) == 4

    vs.delete_collection(pdf_hash)
    assert vs.is_indexed(pdf_hash) is False


def test_search_excludes_headings_and_keeps_metadata():
    collection = vs.index_chunks("searchtest456", CHUNKS)

    results = vs.similarity_search(collection, "how does sorting work?", k=10)
    assert len(results) == 3
    assert "sort" in results[0]["text"].lower()
    assert results[0]["metadata"]["page_end"] == 6

    image = next(r for r in results if r["metadata"]["content_type"] == "image_description")
    assert image["metadata"]["image_path"] == "/tmp/page_9_img_0.png"


def test_get_chunks_returns_document_order():
    collection = vs.index_chunks("ordertest", CHUNKS)
    assert [c["metadata"]["chunk_index"] for c in vs.get_chunks(collection)] == [0, 1, 2, 3]
    assert [c["text"] for c in vs.get_chunks(collection, where={"content_type": "heading"})] == ["Sorting"]


def test_reindex_replaces_partial_collection():
    vs.index_chunks("reindex", CHUNKS[:2])
    vs.index_chunks("reindex", CHUNKS)
    assert vs.get_chunk_count("reindex") == 4


def test_image_chunks_added_incrementally_and_idempotently():
    text_chunks = [c for c in CHUNKS if c["content_type"] != "image_description"]
    vs.index_chunks("imagetest", text_chunks)
    assert vs.images_pending("imagetest") is True

    image = {
        "id": "img_page_8_img_0.png", "text": "Diagram of binary search halving the array.",
        "page_number": 8, "content_type": "image_description", "image_path": "/tmp/page_8_img_0.png",
    }
    vs.add_image_chunks("imagetest", [dict(image)])
    vs.add_image_chunks("imagetest", [dict(image)])  # replayed after a restart
    assert vs.get_chunk_count("imagetest") == len(text_chunks) + 1

    collection = vs.get_collection("imagetest")
    added = vs.get_chunks(collection, where={"content_type": "image_description"})[0]
    assert added["metadata"]["section"] == "Searching"  # inherited from page 8 text
    assert added["metadata"]["chunk_index"] == 2

    vs.mark_images_done("imagetest")
    assert vs.images_pending("imagetest") is False
    assert vs.is_indexed("imagetest") is True
