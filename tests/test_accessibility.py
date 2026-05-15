import fitz
import pytest
from core.accessibility_engine import AccessibilityEngine


def _make_pdf(tmp_path, texts=None):
    path = tmp_path / "test.pdf"
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for text, size in (texts or [("Normal text", 11), ("BIG HEADING", 24)]):
        page.insert_text((72, y), text, fontsize=size)
        y += size + 10
    doc.save(str(path))
    doc.close()
    return str(path), fitz.open(str(path))


def test_auto_detect_headings(tmp_path):
    _, doc = _make_pdf(tmp_path, [("小標題", 11), ("大標題", 24), ("中標題", 16)])
    engine = AccessibilityEngine()
    headings = engine.auto_detect_headings(doc)
    assert isinstance(headings, list)
    # 應至少偵測到大標題
    assert any(h["level"] <= 2 for h in headings)
    doc.close()


def test_validate_pdfua_no_title(tmp_path):
    _, doc = _make_pdf(tmp_path)
    engine = AccessibilityEngine()
    issues = engine.validate_pdfua(doc)
    assert isinstance(issues, list)
    # 未設定標題，應有 UA-001 錯誤
    codes = [i["code"] for i in issues]
    assert "UA-001" in codes
    doc.close()


def test_get_structure_tree(tmp_path):
    _, doc = _make_pdf(tmp_path)
    engine = AccessibilityEngine()
    tree = engine.get_structure_tree(doc)
    # 未標記 PDF 應回傳 None 或有效節點，不能 crash
    doc.close()


def test_reorder_structure(tmp_path):
    _, doc = _make_pdf(tmp_path)
    engine = AccessibilityEngine()
    # 不應 crash
    engine.reorder_structure(doc, [0])
    doc.close()
