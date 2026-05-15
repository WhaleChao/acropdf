import fitz
import pytest
from core.document import PDFDocument


def _blank_pdf(tmp_path, name="form.pdf"):
    path = tmp_path / name
    doc = fitz.open()
    doc.new_page()
    doc.save(str(path))
    doc.close()
    return str(path)


def test_add_radio_button(tmp_path):
    """Radio button 以 checkbox 實作（無 AcroForm parent 時的相容做法）"""
    pdf = _blank_pdf(tmp_path)
    pdoc = PDFDocument()
    pdoc.open(pdf)
    pdoc.forms.add_radio_button(0, fitz.Rect(100, 100, 120, 120), "gender", "male")
    pdoc.forms.add_radio_button(0, fitz.Rect(100, 130, 120, 150), "gender", "female")
    out = tmp_path / "out.pdf"
    pdoc.save(str(out))

    check = fitz.open(str(out))
    widgets = list(check[0].widgets())
    # 使用 checkbox 模擬，確認有 2 個 widget 即可
    assert len(widgets) >= 2
    check.close()


def test_add_signature_field(tmp_path):
    pdf = _blank_pdf(tmp_path)
    pdoc = PDFDocument()
    pdoc.open(pdf)
    pdoc.forms.add_signature_field(0, fitz.Rect(100, 400, 300, 450), "sig1")
    out = tmp_path / "out.pdf"
    pdoc.save(str(out))

    check = fitz.open(str(out))
    widgets = list(check[0].widgets())
    sig_widgets = [w for w in widgets if w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE]
    assert len(sig_widgets) >= 1
    check.close()


def test_tab_order(tmp_path):
    pdf = _blank_pdf(tmp_path)
    pdoc = PDFDocument()
    pdoc.open(pdf)
    pdoc.forms.add_field(0, fitz.Rect(100, 100, 300, 130), "text", "field_a")
    pdoc.forms.add_field(0, fitz.Rect(100, 150, 300, 180), "text", "field_b")
    pdoc.forms.add_field(0, fitz.Rect(100, 200, 300, 230), "text", "field_c")
    pdoc.forms.set_tab_order(0, ["field_c", "field_a", "field_b"])
    out = tmp_path / "out.pdf"
    pdoc.save(str(out))
    assert out.exists()


def test_get_all_fields(tmp_path):
    pdf = _blank_pdf(tmp_path)
    pdoc = PDFDocument()
    pdoc.open(pdf)
    pdoc.forms.add_field(0, fitz.Rect(100, 100, 300, 130), "text", "myfield")
    fields = pdoc.forms.get_all_fields(0)
    assert any(f["name"] == "myfield" for f in fields)


def test_set_field_properties(tmp_path):
    pdf = _blank_pdf(tmp_path)
    pdoc = PDFDocument()
    pdoc.open(pdf)
    pdoc.forms.add_field(0, fitz.Rect(100, 100, 300, 130), "text", "myfield")
    pdoc.forms.set_field_properties(0, "myfield", {"font_size": 14})
    out = tmp_path / "out.pdf"
    pdoc.save(str(out))
    assert out.exists()
