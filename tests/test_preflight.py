import fitz
import pytest


def test_check_fonts(tmp_path):
    from core.preflight_engine import PreflightEngine
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((100, 100), "Hello 測試", fontname="helv")
    doc.save(str(tmp_path / "test.pdf"))

    engine = PreflightEngine()
    fonts = engine.check_fonts(doc)
    assert isinstance(fonts, list)
    assert len(fonts) > 0
    assert "name" in fonts[0]
    assert "embedded" in fonts[0]
    doc.close()


def test_check_images(tmp_path):
    from core.preflight_engine import PreflightEngine
    doc = fitz.open()
    page = doc.new_page()
    img = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 100, 100), 1)
    img.clear_with(255)
    page.insert_image(fitz.Rect(50, 50, 200, 200), pixmap=img)
    doc.save(str(tmp_path / "test.pdf"))

    engine = PreflightEngine()
    images = engine.check_images(doc)
    assert isinstance(images, list)
    doc.close()


def test_full_preflight(tmp_path):
    from core.preflight_engine import PreflightEngine
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((100, 100), "Test")
    doc.save(str(tmp_path / "test.pdf"))

    engine = PreflightEngine()
    report = engine.full_preflight(doc, profile="高品質列印")
    assert hasattr(report, "issues")
    assert hasattr(report, "error_count")
    assert hasattr(report, "warning_count")
    doc.close()


def test_check_color_spaces(tmp_path):
    from core.preflight_engine import PreflightEngine
    doc = fitz.open()
    page = doc.new_page()
    img = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 50, 50), 1)
    img.clear_with(200)
    page.insert_image(fitz.Rect(50, 50, 150, 150), pixmap=img)
    doc.save(str(tmp_path / "test.pdf"))

    engine = PreflightEngine()
    spaces = engine.check_color_spaces(doc)
    assert isinstance(spaces, list)
    doc.close()


def test_preflight_report_counts(tmp_path):
    from core.preflight_engine import PreflightEngine, PreflightIssue, PreflightReport
    report = PreflightReport()
    report.issues.append(PreflightIssue(
        severity="error", category="字型", page=-1,
        message="測試錯誤", auto_fixable=False
    ))
    report.issues.append(PreflightIssue(
        severity="warning", category="圖片", page=0,
        message="測試警告", auto_fixable=True
    ))
    assert report.error_count == 1
    assert report.warning_count == 1
