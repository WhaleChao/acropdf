import fitz
import os
import tempfile
import time
from unittest.mock import patch

import acro_platform
import platform as std_platform
import pytest
from core.compare_engine import CompareEngine
from core.dependency_manager import DependencyManager
from core.document import PDFDocument
from core.temp_manager import cleanup_temp_files
from ui.dialogs.compare.compare_dialog import CompareDialog
from ui.dialogs.export.export_dialog import ExportDialog, default_export_path, ensure_export_suffix
from ui.dialogs.ocr.ocr_dialog import OCRDialog
from ui.dialogs.optimize.optimize_dialog import OptimizeDialog
from ui.dialogs.security.security_dialog import SecurityDialog
from ui.dialogs.signature.sign_dialog import SignDialog
from ui.dialogs.document_properties_dialog import DocumentPropertiesDialog
from ui.dialogs.print_dialog import PrintDialog, _parse_page_ranges
from ui.main_window import MainWindow
from ui.panels.thumbnail_panel import ThumbnailPanel
from rendering.cache import PixmapCache


def test_export_compare_optimize_and_security(sample_pdf, tmp_path):
    doc = PDFDocument()
    assert doc.open(str(sample_pdf))

    txt_out = tmp_path / "sample.txt"
    doc.exports.export(str(txt_out), "txt")
    assert txt_out.exists()
    assert "Sample page 1" in txt_out.read_text(encoding="utf-8")

    img_dir = tmp_path / "images"
    img_dir.mkdir()
    image_paths = doc.exports.export(str(img_dir), "png", dpi=72)
    assert len(image_paths) == 3

    compare_target = tmp_path / "changed.pdf"
    changed = fitz.open(str(sample_pdf))
    try:
        changed[0].insert_text((72, 120), "DIFF")
        changed.save(compare_target)
    finally:
        changed.close()

    result = CompareEngine().compare(str(sample_pdf), str(compare_target))
    assert result["pages_compared"] == 3
    assert result["pages_with_diff"] >= 1

    encrypted = tmp_path / "encrypted.pdf"
    doc.security.encrypt(str(encrypted), owner_pw="owner", user_pw="user")
    encrypted_doc = fitz.open(encrypted)
    try:
        assert encrypted_doc.needs_pass
        assert encrypted_doc.authenticate("user")
    finally:
        encrypted_doc.close()

    optimized = tmp_path / "optimized.pdf"
    doc.optimize.optimize(str(optimized), linearize=True)
    assert optimized.exists()


def test_dependency_manager_scan_does_not_crash():
    manager = DependencyManager()
    deps = manager.scan_all()
    assert len(deps) >= 3
    assert all(dep.name for dep in deps)


def test_platform_module_no_longer_shadows_stdlib():
    assert std_platform.python_implementation()
    backend = acro_platform.get_ocr_backend()
    assert backend is not None
    assert backend.name


def test_temp_cleanup_removes_old_files(tmp_path):
    tmp_dir = tempfile.gettempdir()
    stale = os.path.join(tmp_dir, "acropdf_ocr_stale.png")
    with open(stale, "w", encoding="utf-8") as handle:
        handle.write("x")
    old_time = time.time() - 48 * 3600
    os.utime(stale, (old_time, old_time))
    cleaned = cleanup_temp_files(max_age_hours=24)
    assert cleaned >= 1
    assert not os.path.exists(stale)


def test_main_window_and_dialogs_smoke(qapp, sample_pdf):
    window = MainWindow()
    window.open_file(str(sample_pdf))

    doc = window._current_doc()
    assert doc is not None
    assert window._doc_tabs.count() == 1
    assert window._close_pdf_btn.text() == "關閉 PDF"
    assert window._close_pdf_btn.isEnabled()
    assert [label for label, _ in window._side_pages] == ["案件", "工具", "縮圖", "書籤"]
    assert window._left_panel.minimumWidth() >= 300
    for idx, expected in enumerate(["案件", "工具", "縮圖", "書籤"]):
        button = window._nav_group.button(idx)
        assert button is not None
        assert button.text() == expected

    dialogs = [
        OCRDialog(doc, 0, window),
        ExportDialog(doc, "txt", window),
        OptimizeDialog(doc, window),
        SecurityDialog(doc, window),
        SignDialog(doc, window),
        DocumentPropertiesDialog(doc, window),
        CompareDialog(window),
        PrintDialog(doc.page_count, 0, window),
    ]
    for dialog in dialogs:
        assert dialog.windowTitle()


def test_print_dialog_page_range_parser():
    assert _parse_page_ranges("1-3, 5，7", 8) == [0, 1, 2, 4, 6]
    assert _parse_page_ranges("2,2,3", 4) == [1, 2]


def test_thumbnail_panel_defers_pixmap_rendering(qapp, sample_pdf):
    doc = PDFDocument()
    assert doc.open(str(sample_pdf))
    panel = ThumbnailPanel()
    panel.load_document(doc)

    assert panel.count() == doc.page_count
    assert panel._rendered_pages == set()
    doc.close()


def test_pixmap_cache_respects_byte_budget(qapp):
    from PyQt6.QtGui import QPixmap

    cache = PixmapCache(max_size=20, max_bytes=10_000)
    for page in range(5):
        cache.put(page, 1.0, 0, QPixmap(100, 100))

    assert len(cache._cache) < 5


def test_export_default_path_uses_document_folder(qapp, tmp_path):
    path = tmp_path / "和解書.pdf"
    doc_fitz = fitz.open()
    doc_fitz.new_page().insert_text((72, 72), "settlement")
    doc_fitz.save(path)
    doc_fitz.close()

    doc = PDFDocument()
    assert doc.open(str(path))

    out = default_export_path(doc, "docx")
    assert out == str(tmp_path / "和解書.docx")
    assert out != "/和解書.docx"
    assert ensure_export_suffix(str(tmp_path / "和解書.pdf"), "docx") == str(tmp_path / "和解書.docx")
    doc.close()


def test_export_rejects_unwritable_folder(sample_pdf, tmp_path):
    doc = PDFDocument()
    assert doc.open(str(sample_pdf))

    with patch("core.export_manager.os.access", return_value=False):
        with pytest.raises(PermissionError, match="儲存位置不可寫入"):
            doc.exports.export(str(tmp_path / "out.docx"), "docx")
    doc.close()


def test_main_window_can_open_multiple_documents(qapp, tmp_path):
    window = MainWindow()
    paths = []
    for idx in range(5):
        path = tmp_path / f"bulk_{idx}.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), f"Bulk {idx}")
        doc.save(path)
        doc.close()
        paths.append(path)

    for path in paths:
        window.open_file(str(path))

    assert window._doc_tabs.count() == 5
