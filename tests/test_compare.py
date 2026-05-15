import fitz
import pytest
from core.compare_engine import CompareEngine


def _make_pdf(tmp_path, name, text):
    path = tmp_path / name
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((100, 100), text)
    doc.save(str(path))
    doc.close()
    return str(path)


def test_text_diff(tmp_path):
    a = _make_pdf(tmp_path, "a.pdf", "Original contract clause one")
    b = _make_pdf(tmp_path, "b.pdf", "Modified contract clause one CHANGED")
    engine = CompareEngine()
    results = engine.compare_text(a, b)
    assert len(results) > 0


def test_visual_diff(tmp_path):
    a = _make_pdf(tmp_path, "a.pdf", "AAAA")
    b = _make_pdf(tmp_path, "b.pdf", "BBBB")
    engine = CompareEngine()
    results = engine.compare_visual(a, b)
    assert any(r.get("diff_ratio", 0) > 0 for r in results)


def test_cluster_diff_regions(tmp_path):
    a = _make_pdf(tmp_path, "a.pdf", "Hello World")
    b = _make_pdf(tmp_path, "b.pdf", "Hello Earth")
    engine = CompareEngine()
    clusters = engine.cluster_diff_regions(a, b, page_num=0)
    assert isinstance(clusters, list)


def test_compare_identical(tmp_path):
    """完全相同的 PDF 應無差異"""
    a = _make_pdf(tmp_path, "a.pdf", "相同內容")
    b = _make_pdf(tmp_path, "b.pdf", "相同內容")
    engine = CompareEngine()
    result = engine.compare(a, b)
    assert result["pages_with_diff"] == 0


def test_generate_diff_report(tmp_path):
    a = _make_pdf(tmp_path, "a.pdf", "原始版本")
    b = _make_pdf(tmp_path, "b.pdf", "修改版本")
    engine = CompareEngine()
    result = engine.compare(a, b)
    out = str(tmp_path / "report.pdf")
    engine.generate_diff_report(a, b, out, result)
    import os
    assert os.path.exists(out)
    assert os.path.getsize(out) > 0
