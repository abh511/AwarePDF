# ============================================================
# tests/test_pdf_processor.py
# ============================================================

import fitz
import pytest

from app.core.pdf_processor import PDFProcessingError, _extract_elements, get_page_count
from app.utils.file_handler import get_pdf_hash


class _Prov:
    def __init__(self, page_no):
        self.page_no = page_no


class _Item:
    def __init__(self, label, text, page):
        self.label = label
        self.text = text
        self.prov = [_Prov(page)]


class _Doc:
    def __init__(self, items):
        self._items = items

    def iterate_items(self):
        return ((item, 0) for item in self._items)


def test_get_pdf_hash_is_consistent(tmp_path):
    pdf = tmp_path / "dummy.pdf"
    pdf.write_bytes(b"%PDF-1.4 dummy content for testing")
    assert get_pdf_hash(str(pdf)) == get_pdf_hash(str(pdf))
    assert len(get_pdf_hash(str(pdf))) == 64


def test_extract_elements_uses_real_page_numbers_and_sections():
    doc = _Doc([
        _Item("page_header", "Chapter 3 | Running header", 40),
        _Item("section_header", "3.1 Beams", 40),
        _Item("text", "A beam resists bending.", 41),
        _Item("caption", "Figure 3-1. A cantilever beam", 41),
        _Item("page_footer", "41", 41),
    ])
    elements, section = _extract_elements(doc, section="Previous")
    assert [e["text"] for e in elements] == [
        "3.1 Beams", "A beam resists bending.", "Figure 3-1. A cantilever beam",
    ]
    assert [e["page_number"] for e in elements] == [40, 41, 41]
    assert elements[0]["content_type"] == "heading"
    assert all(e["section"] == "3.1 Beams" for e in elements)
    assert section == "3.1 Beams"


def test_callouts_and_code_are_not_headings():
    doc = _Doc([
        _Item("section_header", "Bagging and Pasting", 278),
        _Item("section_header", "TIP", 279),
        _Item("section_header", "gbrt.fit(X, y)", 290),
        _Item("section_header", "U", 291),
        _Item("section_header", "Support Vector Machines (SVM)", 292),
    ])
    elements, section = _extract_elements(doc, section="")
    assert [e["content_type"] for e in elements] == ["heading", "text", "text", "text", "heading"]
    assert elements[3]["section"] == "Bagging and Pasting"
    assert section == "Support Vector Machines (SVM)"


def test_table_of_contents_is_kept():
    doc = _Doc([_Item("document_index", "1. Error Control ..... 11.4  2. Flow Control ..... 11.7", 3)])
    elements, _ = _extract_elements(doc, section="")
    assert elements and "Flow Control" in elements[0]["text"]


def test_section_carries_across_batches():
    elements, section = _extract_elements(_Doc([_Item("text", "Continued text.", 81)]), section="3.1 Beams")
    assert elements[0]["section"] == "3.1 Beams"


def test_page_count_and_encrypted_pdf(tmp_path):
    plain, locked = tmp_path / "plain.pdf", tmp_path / "locked.pdf"
    doc = fitz.open()
    for _ in range(3):
        doc.new_page()
    doc.save(str(plain))
    doc.save(str(locked), encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="secret")
    doc.close()

    assert get_page_count(plain) == 3
    with pytest.raises(PDFProcessingError, match="password"):
        get_page_count(locked)
