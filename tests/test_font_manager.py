import fitz
import pytest
from core.document import PDFDocument
from core.font_manager import FontManager


def _make_pdf(tmp_path, name="test.pdf"):
    path = tmp_path / name
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((100, 100), "Hello Font Test", fontname="helv")
    doc.save(str(path))
    doc.close()
    return str(path)


def test_list_fonts(tmp_path):
    pdf = _make_pdf(tmp_path)
    pdoc = PDFDocument()
    pdoc.open(pdf)
    fonts = pdoc.fonts.list_fonts()
    assert isinstance(fonts, list)
    assert len(fonts) >= 1
    assert hasattr(fonts[0], "name")
    assert hasattr(fonts[0], "embedded")


def test_font_info_structure(tmp_path):
    pdf = _make_pdf(tmp_path)
    pdoc = PDFDocument()
    pdoc.open(pdf)
    fonts = pdoc.fonts.list_fonts()
    for f in fonts:
        assert isinstance(f.name, str)
        assert isinstance(f.embedded, bool)
        assert isinstance(f.pages, list)


def test_find_system_fonts():
    fonts = FontManager.find_system_fonts()
    assert isinstance(fonts, list)
    # macOS 應該找到一些字型
    # 在 CI 可能為空，不強制 assert


def test_extract_font_nonexistent(tmp_path):
    pdf = _make_pdf(tmp_path)
    pdoc = PDFDocument()
    pdoc.open(pdf)
    # 嘗試提取不存在的字型，應回傳 False 而非 crash
    result = pdoc.fonts.extract_font("NonExistentFont", str(tmp_path / "out.ttf"))
    assert result is False
