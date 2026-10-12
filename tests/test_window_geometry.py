"""Regression for the AppKit SF Symbol abort during toolbar repaint."""
import sys

import pytest
from PyQt6.QtCore import QSize, QThreadPool
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QStyleFactory, QToolButton

from ui.widget_style import MacSafeWidgetStyle, install_widget_style
from ui.main_window import MainWindow


def test_windowed_geometry_cli_returns_failure_report_without_error_popup(tmp_path, monkeypatch):
    import json
    import ui.geometry_check as checker
    def fail(*args):
        raise AssertionError("unreadable button")
    monkeypatch.setattr(checker, "run_geometry_check", fail)
    report = tmp_path / "geometry.json"
    assert checker.run_geometry_cli(report, "1.1.5") == 1
    result = json.loads(report.read_text())
    assert not result["passed"] and result["error"] == "unreadable button"
    assert "AssertionError" in result["traceback"]


@pytest.mark.parametrize("standard_icon", list(MacSafeWidgetStyle._glyphs))
def test_small_control_icons_use_pixmaps_at_transient_geometry(qapp, standard_icon):
    style = MacSafeWidgetStyle(QStyleFactory.create("Fusion"))
    image = style.standardIcon(standard_icon)
    # Apple theme engines have no fixed pixmap sizes. This must be our local
    # pixmap engine; tiny requests must not call NSImageSymbolRepProvider.
    assert image.availableSizes()
    for size in (QSize(11, 1), QSize(1, 11), QSize(1, 1), QSize(18, 18)):
        for dpr in (1.0, 1.25, 2.0):
            for mode in QIcon.Mode:
                assert not image.pixmap(size, dpr, mode).isNull()


def test_resize_and_move_keep_documents_and_overflow_controls(qapp, sample_pdf, tmp_path):
    second_pdf = tmp_path / "second.pdf"
    second_pdf.write_bytes(sample_pdf.read_bytes())
    window = MainWindow()
    window.show()
    window.open_file(str(second_pdf))
    window.open_file(str(sample_pdf))
    try:
        extension_images = []
        for theme in ("light", "dark"):
            window._switch_theme(theme)
            if sys.platform == "darwin":
                extension = window.findChild(QToolButton, "qt_toolbar_ext_button")
                extension_images.append(extension.icon().pixmap(QSize(18, 18)).toImage())
            for width, height in ((1280, 900), (640, 480), (880, 640), (400, 320)) * 3:
                window.resize(width, height)
                window.move(30 + width % 100, 40 + height % 100)
                qapp.processEvents()
                window.grab()
                assert window._doc_tabs.count() == 2
                assert all(doc.page_count == 3 and not doc.is_modified for doc in window._docs)
        extensions = window.findChildren(QToolButton, "qt_toolbar_ext_button")
        assert len(extensions) >= 2
        if sys.platform == "darwin":
            assert extension_images[0] != extension_images[1]
            assert all(button.icon().availableSizes() for button in extensions)
            installed = qapp._acro_widget_style
            install_widget_style(qapp)
            assert qapp._acro_widget_style is installed
    finally:
        QThreadPool.globalInstance().waitForDone(10000)
        window.close()
        qapp.processEvents()
