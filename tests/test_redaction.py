import fitz
import pytest
from core.document import PDFDocument


def _make_pdf_with_text(tmp_path, name, text):
    path = tmp_path / name
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((100, 100), text)
    doc.save(str(path))
    doc.close()
    return str(path)


def test_search_and_mark(tmp_path):
    """搜尋文字並標記塗黑"""
    pdf = _make_pdf_with_text(tmp_path, "test.pdf", "機密資料 A123456789 結束")
    pdoc = PDFDocument()
    pdoc.open(pdf)
    results = pdoc.redaction.search_and_mark("A123456789")
    assert len(results) >= 1
    assert pdoc.redaction.get_redact_count() >= 1


def test_pattern_mark(tmp_path):
    """正規表達式模式塗黑"""
    pdf = _make_pdf_with_text(tmp_path, "test.pdf",
                              "聯絡電話 0912345678 身分證 A123456789")
    pdoc = PDFDocument()
    pdoc.open(pdf)
    from core.redaction_engine import RedactionEngine
    results = pdoc.redaction.pattern_mark(RedactionEngine.PATTERNS["手機號碼"])
    assert len(results) >= 1


def test_apply_redactions(tmp_path):
    """套用塗黑後底層文字必須完全移除"""
    pdf = _make_pdf_with_text(tmp_path, "test.pdf", "SECRET_DATA_12345")
    pdoc = PDFDocument()
    pdoc.open(pdf)
    pdoc.redaction.search_and_mark("SECRET_DATA_12345")
    applied = pdoc.redaction.apply_all()
    assert applied >= 1

    out = tmp_path / "redacted.pdf"
    pdoc.save(str(out))

    check = fitz.open(str(out))
    text = check[0].get_text()
    assert "SECRET_DATA_12345" not in text
    check.close()


def test_get_redact_count_zero(tmp_path):
    """無標記時計數為 0"""
    pdf = _make_pdf_with_text(tmp_path, "test.pdf", "一般文字")
    pdoc = PDFDocument()
    pdoc.open(pdf)
    assert pdoc.redaction.get_redact_count() == 0
