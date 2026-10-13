# ============================================================
# tests/test_chunker.py
# Run with: pytest tests/
# ============================================================

from app.core.chunker import chunk_elements, split_text, split_table
from config.settings import CHUNK_SIZE


def _el(text, page=1, content_type="text", section="Intro"):
    return {"text": text, "page_number": page, "content_type": content_type, "section": section}


def test_small_paragraphs_are_merged_within_a_section():
    elements = [_el(f"Paragraph {i} about beams.", page=1 + i // 3) for i in range(6)]
    chunks = chunk_elements(elements)
    assert len(chunks) == 1
    assert chunks[0]["page_number"] == 1
    assert chunks[0]["page_end"] == 2
    assert "Paragraph 0" in chunks[0]["text"] and "Paragraph 5" in chunks[0]["text"]


def test_section_change_starts_new_chunk_and_headings_are_kept():
    elements = [
        _el("Stress", content_type="heading", section="Stress"),
        _el("Stress is force per area.", section="Stress"),
        _el("Strain", content_type="heading", section="Strain"),
        _el("Strain is deformation.", section="Strain"),
    ]
    chunks = chunk_elements(elements)
    assert [c["content_type"] for c in chunks] == ["heading", "text", "heading", "text"]
    assert chunks[3]["section"] == "Strain"
    assert [c["chunk_index"] for c in chunks] == [0, 1, 2, 3]


def test_chunks_respect_size_limit():
    elements = [_el("word " * 50) for _ in range(40)]
    chunks = chunk_elements(elements)
    assert len(chunks) > 1
    assert all(len(c["text"]) <= CHUNK_SIZE for c in chunks)


def test_long_paragraph_split_loses_no_sentences():
    sentences = [f"Sentence number {i} explains a concept." for i in range(200)]
    pieces = split_text(" ".join(sentences), size=500, overlap=80)
    joined = " ".join(pieces)
    assert all(s in joined for s in sentences)
    assert all(len(p) <= 500 for p in pieces)


def test_unbroken_text_is_hard_split():
    pieces = split_text("x" * 50 + " " + "y" * 50 + " " + "z" * 50, size=60, overlap=0)
    assert len(pieces) == 3


def test_small_table_kept_whole():
    table = "| A | B |\n| --- | --- |\n| 1 | 2 |"
    chunks = chunk_elements([_el(table, content_type="table")])
    assert len(chunks) == 1 and chunks[0]["content_type"] == "table"


def test_huge_table_split_with_header_repeated():
    table = "| Col1 | Col2 |\n| --- | --- |\n" + "\n".join(f"| r{i} | {i * 2} |" for i in range(400))
    parts = split_table(table, size=500)
    assert len(parts) > 1
    assert all(p.startswith("| Col1 | Col2 |\n| --- | --- |") for p in parts)
    assert sum(p.count("| r") for p in parts) == 400
