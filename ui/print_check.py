"""Opt-in print regression using generated PDFs, never physical print jobs."""
import hashlib
import tempfile
from pathlib import Path

import fitz


def verify_print_orientation(app, output_folder):
    from PyQt6.QtCore import Qt
    from PyQt6.QtPrintSupport import QPrinter, QPrinterInfo
    from PyQt6.QtWidgets import QScrollArea
    from core.document import PDFDocument
    from core.print_engine import configure_print_layout, print_to_device
    from ui.dialogs.print_dialog import PrintDialog
    from ui.dialogs.print_progress_dialog import PrintProgressDialog

    folder = Path(output_folder)
    folder.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix="acropdf_print_check_") as temporary:
        scratch = Path(temporary)
        sample = scratch / "source.pdf"
        colors = ((1, 0, 0), (0, 1, 0), (0, 0, 1), (1, .5, 0))
        with fitz.open() as source:
            for rotation in (0, 90, 180, 270):
                page = source.new_page(width=595.276, height=841.89)
                page.insert_text((60, 75), f"Print orientation {rotation}")
                for rect, color in zip(((45, 100, 75, 130), (520, 100, 550, 130),
                                         (45, 735, 75, 765), (520, 735, 550, 765)), colors):
                    page.draw_rect(fitz.Rect(rect), color=color, fill=color)
                page.set_rotation(rotation)
            source.save(sample)
        original = hashlib.sha256(sample.read_bytes()).hexdigest()
        document = PDFDocument()
        assert document.open(str(sample))
        try:
            for paper in range(4):
                for landscape in (False, True):
                    dialog = PrintDialog(4, 0, page_size=(841.89, 595.276))
                    assert dialog._orientation.currentData() is True
                    dialog.show()
                    app.processEvents()
                    scroll = dialog.findChild(QScrollArea)
                    location = dialog._orientation.mapTo(scroll.viewport(), dialog._orientation.rect().center())
                    assert scroll.viewport().rect().contains(location), "Orientation selector requires scrolling"
                    dialog._pdf_check.setChecked(True)
                    dialog._paper_combo.setCurrentIndex(paper)
                    dialog._orientation.setCurrentIndex(int(landscape))
                    target = scratch / f"vector-{paper}-{landscape}.pdf"
                    dialog._pdf_edit.setText(str(target))
                    dialog._accept_settings()
                    settings = dialog.settings()
                    assert settings.landscape == landscape
                    worker = PrintProgressDialog(document, settings)
                    worker.exec()
                    assert not worker.error and worker.report
                    with fitz.open(target) as printed:
                        assert len(printed) == 4
                        for page in printed:
                            assert (page.rect.width > page.rect.height) == landscape
                            assert "Print orientation" in page.get_text()
                            pixels = page.get_pixmap(colorspace=fitz.csRGB, alpha=False).samples
                            # All four edge markers must survive rotations and fit.
                            for rgb in ((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 127, 0)):
                                assert pixels.count(bytes(rgb)) > 25, (paper, landscape, page.number, rgb)
                    if paper == 0 and landscape:
                        (folder / "vector-landscape.pdf").write_bytes(target.read_bytes())
                        dialog._pdf_check.setChecked(True)
                        dialog.show()
                        app.processEvents()
                        assert dialog.grab().save(str(folder / "print-dialog-landscape.png"))
                    dialog.close()
                    results.append(dict(paper=paper, landscape=landscape, rotated_pages=4,
                                        corner_markers_preserved=True, direction_visible=True))
            backends = []
            for landscape in (False, True):
                printer = QPrinter(QPrinter.PrinterMode.HighResolution)
                target = scratch / f"device-{landscape}.pdf"
                printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
                printer.setOutputFileName(str(target))
                configure_print_layout(printer, (595.276, 841.89), landscape)
                print_to_device(document.fitz_doc, printer, list(range(4)))
                with fitz.open(target) as printed:
                    assert len(printed) == 4
                    assert all((p.rect.width > p.rect.height) == landscape for p in printed)
                backends.append(dict(backend="Qt PDF", landscape=landscape, pages=4))
            # macOS NativeFormat can write to a file through the selected
            # printer driver. Require a nonempty destination before beginning
            # so this never sends a job to the printer queue.
            native_driver = None
            if app.platformName() == "cocoa" and QPrinterInfo.availablePrinterNames():
                printer = QPrinter(QPrinter.PrinterMode.HighResolution)
                printer.setPrinterName(QPrinterInfo.defaultPrinterName())
                target = scratch / "native.pdf"
                printer.setOutputFileName(str(target))
                printer.setOutputFormat(QPrinter.OutputFormat.NativeFormat)
                assert printer.outputFileName() == str(target)
                configure_print_layout(printer, (595.276, 841.89), True)
                print_to_device(document.fitz_doc, printer, list(range(4)))
                with fitz.open(target) as printed:
                    assert all(p.rect.width > p.rect.height for p in printed)
                native_driver = dict(passed=True, backend="macOS NativeFormat", file_destination=True,
                                     physical_job_submitted=False)
            # Exercise the second production printing entry point as well:
            # summary printing previously discarded both paper and orientation.
            from PyQt6.QtCore import QTimer
            from PyQt6.QtWidgets import QMessageBox
            from ui.dialogs.annot_summary.annot_summary_dialog import AnnotSummaryDialog
            summary_target = scratch / "summary.pdf"
            summary = AnnotSummaryDialog(document)
            errors = []
            timer = QTimer()
            def complete_summary():
                modal = app.activeModalWidget()
                try:
                    if isinstance(modal, PrintDialog):
                        modal._pdf_check.setChecked(True)
                        modal._paper_combo.setCurrentIndex(2)
                        modal._orientation.setCurrentIndex(1)
                        modal._pdf_edit.setText(str(summary_target))
                        modal._accept_settings()
                    elif isinstance(modal, QMessageBox):
                        assert modal.icon() == QMessageBox.Icon.Information, modal.text()
                        modal.accept()
                except Exception as error:
                    errors.append(str(error))
                    if modal is not None:
                        modal.reject()
            timer.timeout.connect(complete_summary)
            timer.start(20)
            try:
                summary._on_print()
            finally:
                timer.stop()
                summary.close()
            assert not errors, errors
            with fitz.open(summary_target) as printed:
                assert len(printed) and all(p.rect.width > p.rect.height for p in printed)
                assert abs(printed[0].rect.width - 792) < .1
                assert abs(printed[0].rect.height - 612) < .1
            assert hashlib.sha256(sample.read_bytes()).hexdigest() == original
            assert [p.rotation for p in document.fitz_doc] == [0, 90, 180, 270]
            return dict(passed=True, layouts=results, device_backends=backends,
                        native_driver=native_driver, original_unchanged=True,
                        summary_landscape_letter=True, physical_paper_tested=False)
        finally:
            document.close()
