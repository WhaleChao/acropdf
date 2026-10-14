import pytest
from PyQt6.QtGui import QPageLayout
from PyQt6.QtPrintSupport import QPrinter

from core.print_engine import configure_print_layout


def test_rotated_pages_and_real_print_settings_preserve_content(qapp, tmp_path):
    from ui.print_check import verify_print_orientation
    result = verify_print_orientation(qapp, tmp_path)
    assert result["passed"] and result["original_unchanged"]
    assert len(result["layouts"]) == 8


def test_driver_rejecting_landscape_stops_before_printing(qapp):
    class UnsupportedPrinter:
        def pageLayout(self):
            return QPrinter().pageLayout()

        def setPageLayout(self, layout):
            return False

    with pytest.raises(ValueError, match="不接受"):
        configure_print_layout(UnsupportedPrinter(), (595.276, 841.89), True)


@pytest.mark.parametrize("landscape", [False, True])
def test_paper_layout_is_applied_as_one_request(qapp, landscape):
    printer = QPrinter()
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    configure_print_layout(printer, (595.276, 841.89), landscape)
    assert printer.pageLayout().orientation() == (
        QPageLayout.Orientation.Landscape if landscape else QPageLayout.Orientation.Portrait)


@pytest.mark.parametrize("landscape", [False, True])
def test_annotation_summary_honors_selected_paper_and_orientation(qapp, sample_pdf, tmp_path, monkeypatch, landscape):
    import fitz
    from core.document import PDFDocument
    from ui.dialogs.print_dialog import PrintDialog
    from ui.dialogs.annot_summary import annot_summary_dialog as module
    document = PDFDocument()
    assert document.open(str(sample_pdf))
    target = tmp_path / "summary.pdf"
    def ready_dialog(*args, **kwargs):
        dialog = PrintDialog(*args, **kwargs)
        dialog._paper_combo.setCurrentIndex(2)  # Letter, distinct from A4 default.
        dialog._orientation.setCurrentIndex(int(landscape))
        dialog._pdf_check.setChecked(True)
        dialog._pdf_edit.setText(str(target))
        dialog._accept_settings()
        dialog.exec = lambda: dialog.DialogCode.Accepted
        return dialog
    monkeypatch.setattr(module, "PrintDialog", ready_dialog)
    monkeypatch.setattr(module.QMessageBox, "information", lambda *a: None)
    monkeypatch.setattr(module.QMessageBox, "warning", lambda *a: pytest.fail(str(a)))
    dialog = module.AnnotSummaryDialog(document)
    try:
        dialog._on_print()
        with fitz.open(target) as printed:
            assert all((p.rect.width > p.rect.height) == landscape for p in printed)
            rect = printed[0].rect
            assert sorted((rect.width, rect.height)) == pytest.approx([612, 792], abs=.1)
    finally:
        dialog.close()
        document.close()
