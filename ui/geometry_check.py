"""Opt-in, isolated native window regression for installed packages.

Run AcroPDF --verify-window-geometry REPORT.json. Uses generated PDFs and
temporary settings; does not open the user's files or overwrite preferences.
"""
import hashlib
import json
import platform
import tempfile
from pathlib import Path


def run_geometry_cli(report_path, version):
    """Windowed EXEs have no stderr; return errors as JSON, without a popup."""
    try:
        return run_geometry_check(report_path, version)
    except Exception as error:
        import traceback
        target = Path(report_path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(dict(passed=False, version=version,
                                         error=str(error), traceback=traceback.format_exc()),
                                    ensure_ascii=False, indent=2), encoding="utf-8")
        return 1


def run_geometry_check(report_path, version):
    import os
    import fitz
    from PyQt6.QtCore import QSettings, QSize, QThreadPool, QT_VERSION_STR
    from PyQt6.QtGui import QIcon
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QToolButton
    from app.config import Config
    from ui.main_window import MainWindow
    from ui.widget_style import MacSafeWidgetStyle

    target = Path(report_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    def phase(name):
        target.write_text(json.dumps(dict(passed=False, version=version, phase=name)), encoding="utf-8")
    phase("create-native-window")
    with tempfile.TemporaryDirectory(prefix="acropdf_geometry_") as folder:
        scratch = Path(folder)
        os.environ["ACROPDF_RECOVERY_DIR"] = str(scratch / "recovery")
        os.environ["ACROPDF_APP_DATA_DIR"] = str(scratch / "diagnostics")
        app = QApplication(["AcroPDF geometry verification"])
        Config()._settings = QSettings(str(scratch / "settings.ini"), QSettings.Format.IniFormat)
        sample = scratch / "geometry.pdf"
        with fitz.open() as pdf:
            for i in range(3):
                pdf.new_page().insert_text((72, 72), f"Window geometry verification / page {i + 1}")
            pdf.save(sample)
        digest = hashlib.sha256(sample.read_bytes()).hexdigest()
        second = scratch / "second.pdf"
        second.write_bytes(sample.read_bytes())
        window = MainWindow()
        window.show()
        QTest.qWait(100)
        try:
            phase("small-control-icons")
            icon_requests = 0
            for standard_icon in MacSafeWidgetStyle._glyphs:
                image = app.style().standardIcon(standard_icon)
                if platform.system() == "Darwin":
                    assert image.availableSizes(), "Native SF Symbol engine still in use"
                for size in (QSize(11, 1), QSize(1, 11), QSize(1, 1), QSize(18, 18)):
                    for dpr in (1.0, 1.25, 2.0):
                        for mode in QIcon.Mode:
                            assert not image.pixmap(size, dpr, mode).isNull()
                            icon_requests += 1
            geometry_changes = 0
            overflow_visible = False
            shapes = ((1280, 900), (640, 480), (880, 640), (400, 320), (1100, 700), (900, 550))
            for documents in (False, True):
                if documents:
                    window.open_file(str(sample))
                    window.open_file(str(second))
                for theme in ("light", "dark"):
                    phase(f"window-geometry-{theme}-{'documents' if documents else 'welcome'}")
                    window._switch_theme(theme)
                    for n, (width, height) in enumerate(shapes * 4):
                        window.resize(width, height)
                        window.move(20 + n % 6 * 17, 40 + n % 5 * 13)
                        QTest.qWait(25)
                        assert not window.grab().isNull()
                        buttons = window.findChildren(QToolButton, "qt_toolbar_ext_button")
                        overflow_visible |= any(button.isVisible() for button in buttons)
                        if platform.system() == "Darwin":
                            assert all(button.icon().availableSizes() for button in buttons)
                        if documents:
                            assert window._doc_tabs.count() == 2
                            assert all(doc.page_count == 3 and not doc.is_modified for doc in window._docs)
                        geometry_changes += 1
            assert overflow_visible, "Toolbar overflow repaint was not exercised"
            window.showMaximized(); QTest.qWait(350)
            window.showNormal(); QTest.qWait(350)
            window.showMinimized(); QTest.qWait(350)
            window.showNormal(); QTest.qWait(350)
            QThreadPool.globalInstance().waitForDone(10000)
            app.processEvents()
            assert hashlib.sha256(sample.read_bytes()).hexdigest() == digest
            assert hashlib.sha256(second.read_bytes()).hexdigest() == digest
            assert window._current_view()._page_widgets
            from ui.theme_check import verify_theme_controls, verify_sticky_note_flow
            phase("theme-controls")
            theme_controls = verify_theme_controls(app, target.parent / "theme-screenshots")
            phase("production-sticky-note")
            sticky_note_flow = verify_sticky_note_flow(app, window, target.parent / "theme-screenshots")
            from ui.print_check import verify_print_orientation
            phase("print-orientation")
            print_orientation = verify_print_orientation(app, target.parent / "print-check")
            report = dict(passed=True, version=version, platform=app.platformName(),
                          os=platform.platform(), qt=QT_VERSION_STR,
                          geometry_changes=geometry_changes, icon_requests=icon_requests,
                          overflow_visible=True, source_pdf_unchanged=True,
                          document_tabs=2, themes=["light", "dark"],
                          maximize_restore=True, minimize_restore=True,
                          user_settings_isolated=True, theme_controls=theme_controls,
                          sticky_note_flow=sticky_note_flow, print_orientation=print_orientation)
            target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        finally:
            QThreadPool.globalInstance().waitForDone(10000)
            window.close()
            app.processEvents()
    return 0
