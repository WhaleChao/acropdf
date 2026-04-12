import fitz
import os
import tempfile
import time

import acro_platform
import platform as std_platform
from core.compare_engine import CompareEngine
from core.dependency_manager import DependencyManager
from core.document import PDFDocument
from core.temp_manager import cleanup_temp_files
from ui.dialogs.compare.compare_dialog import CompareDialog
from ui.dialogs.export.export_dialog import ExportDialog
from ui.dialogs.ocr.ocr_dialog import OCRDialog
from ui.dialogs.optimize.optimize_dialog import OptimizeDialog
from ui.dialogs.security.security_dialog import SecurityDialog
from ui.dialogs.signature.sign_dialog import SignDialog
from ui.main_window import MainWindow


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

    dialogs = [
        OCRDialog(doc, window),
        ExportDialog(doc, "txt", window),
        OptimizeDialog(doc, window),
        SecurityDialog(doc, window),
        SignDialog(doc, window),
        CompareDialog(window),
    ]
    for dialog in dialogs:
        assert dialog.windowTitle()


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
