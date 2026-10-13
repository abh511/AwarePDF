# ============================================================
# tests/test_retriever.py
# ============================================================

import pytest

import app.core.vector_store as vs
import config.settings as settings
from app.core import hybrid_search, retriever
from app.core.llm import format_context

TOPICS = ["thermodynamics entropy", "fluid viscosity", "beam bending moment", "ohm resistor circuit"]


@pytest.fixture
def pdf_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "CHROMA_PERSIST_DIR", tmp_path)
    vs.reset_runtime_state()
    hybrid_search.clear_bm25_indices()
    chunks = [
        {"text": f"Chapter {i}", "page_number": i * 10, "content_type": "heading",
         "section": f"Chapter {i}", "chunk_index": i * 6}
        for i in range(4)
    ]
    for i, topic in enumerate(TOPICS):
        for j in range(5):
            chunks.append({
                "text": f"Paragraph {j} on {topic} with details and the XJ-{i}{j} identifier.",
                "page_number": i * 10 + j + 1, "content_type": "text",
                "section": f"Chapter {i}", "chunk_index": i * 6 + j + 1,
            })
    vs.index_chunks("retrievaltest", chunks)
    yield "retrievaltest"
    vs.reset_runtime_state()


def test_rrf_rewards_agreement():
    a = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
    b = [{"id": "3"}, {"id": "4"}]
    fused = hybrid_search.reciprocal_rank_fusion([a, b], k=10)
    assert fused[0]["id"] == "3"
    assert {c["id"] for c in fused} == {"1", "2", "3", "4"}


def test_bm25_finds_exact_identifier(pdf_hash):
    collection = vs.get_collection(pdf_hash)
    results = hybrid_search.bm25_search(collection, "XJ-23", k=3)
    assert "XJ-23" in results[0]["text"]
    assert all(r["metadata"]["content_type"] != "heading" for r in results)


def test_retrieve_returns_relevant_chunks(pdf_hash, monkeypatch):
    monkeypatch.setattr(retriever, "USE_RERANKER", False)
    results = retriever.retrieve(pdf_hash, "resistor circuit", k=3)
    assert len(results) == 3
    assert all("ohm resistor circuit" in r["text"] for r in results)


def test_outline_and_even_sample(pdf_hash):
    assert [h["text"] for h in retriever.get_outline(pdf_hash)] == [f"Chapter {i}" for i in range(4)]

    sample = retriever.sample_across_document(pdf_hash, max_chars=600)
    pages = [c["metadata"]["page_number"] for c in sample]
    assert pages == sorted(pages)
    assert pages[0] <= 5 and pages[-1] >= 20  # spans start to end of the book


def test_format_context_cites_page_ranges_and_respects_budget():
    chunks = [
        {"text": "a" * 100, "metadata": {"page_number": 3, "page_end": 4, "section": "S"}},
        {"text": "b" * 100, "metadata": {"page_number": 7}},
    ]
    assert format_context(chunks).startswith("[Pages 3-4 | Section: S]")
    assert "b" * 100 not in format_context(chunks, max_chars=150)


def test_outline_text_drops_subsections_when_too_long(pdf_hash):
    full = retriever.outline_text(pdf_hash)
    assert full.splitlines()[0] == "- Chapter 0 (Page 0)"
    assert len(retriever.outline_text(pdf_hash, max_chars=50)) <= 60


def test_section_pages_follow_numbering(monkeypatch):
    outline = [
        ("ERROR CONTROL", 7), ("2.1 Error Control", 7), ("Simple parity", 8), ("2.5 Hamming Code", 9),
        ("FLOW CONTROL", 10), ("3.1 Delay", 10), ("Window size:", 12), ("3.8 Selective Repeat", 12),
        ("3.9 Comparison", 13), ("IPV4 HEADER", 14), ("4.1 IPv4 Header", 14),
        ("Computer Networks", 8), ("Computer Networks", 11), ("Computer Networks", 15),
    ]
    monkeypatch.setattr(retriever, "get_outline", lambda _h: [
        {"text": t, "metadata": {"page_number": p}} for t, p in outline
    ])
    assert retriever._section_pages("x", "flow control") == (10, 13)
    assert retriever._section_pages("x", "Error Control") == (7, 9)
    assert retriever._section_pages("x", "selective repeat") == (12, 13)
    assert retriever._section_pages("x", "IPv4 header") == (14, 10**9)
    assert retriever._section_pages("x", "computer networks") is None  # running header ignored
    assert retriever._section_pages("x", "quantum") is None
