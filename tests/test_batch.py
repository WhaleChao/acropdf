import fitz
import os
import pytest
from core.batch_engine import BatchEngine


def _make_pdf(tmp_path, name, text, pages=1):
    path = tmp_path / name
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page()
        page.insert_text((100, 100), text)
    doc.save(str(path))
    doc.close()
    return str(path)


def test_add_watermark(tmp_path):
    src = _make_pdf(tmp_path, "src.pdf", "測試文件")
    out = str(tmp_path / "watermarked.pdf")
    engine = BatchEngine()
    engine.add_watermark(src, out, "機密", opacity=0.3, position="center")
    assert os.path.exists(out)
    # 確認輸出是有效 PDF
    doc = fitz.open(out)
    assert doc.page_count >= 1
    doc.close()


def test_add_header_footer(tmp_path):
    src = _make_pdf(tmp_path, "src.pdf", "測試文件", pages=3)
    out = str(tmp_path / "hf.pdf")
    engine = BatchEngine()
    engine.add_header_footer(src, out, header="AcroPDF", footer="第 {page} 頁，共 {total} 頁")
    assert os.path.exists(out)
    doc = fitz.open(out)
    assert doc.page_count == 3
    doc.close()


def test_add_bates_number(tmp_path):
    src = _make_pdf(tmp_path, "src.pdf", "文件", pages=3)
    out = str(tmp_path / "bates.pdf")
    engine = BatchEngine()
    engine.add_bates_number(src, out, prefix="ABC-", start=1, digits=6)
    assert os.path.exists(out)
    doc = fitz.open(out)
    text = doc[0].get_text()
    assert "ABC-" in text
    doc.close()


def test_split_pages(tmp_path):
    src = _make_pdf(tmp_path, "src.pdf", "文件", pages=5)
    out_dir = str(tmp_path / "split")
    engine = BatchEngine()
    parts = engine.split_pages(src, out_dir, pages_per_file=2)
    assert len(parts) == 3  # ceil(5/2)=3
    for p in parts:
        assert os.path.exists(p)


def test_export_to_docx(tmp_path):
    src = _make_pdf(tmp_path, "src.pdf", "Hello World")
    out = str(tmp_path / "out.docx")
    engine = BatchEngine()
    engine.export_to_docx(src, out)
    assert os.path.exists(out)


def test_export_to_html(tmp_path):
    src = _make_pdf(tmp_path, "src.pdf", "HTML test")
    out = str(tmp_path / "out.html")
    engine = BatchEngine()
    engine.export_to_html(src, out)
    assert os.path.exists(out)
    with open(out) as f:
        content = f.read()
    assert "<html>" in content


def test_batch_process_watermark(tmp_path):
    src1 = _make_pdf(tmp_path, "a.pdf", "文件A")
    src2 = _make_pdf(tmp_path, "b.pdf", "文件B")
    engine = BatchEngine()
    results = engine.batch_process(
        [src1, src2], "watermark", {"text": "機密", "opacity": 0.3, "position": "center"}
    )
    assert len(results) == 2
    assert all(r["ok"] for r in results)
