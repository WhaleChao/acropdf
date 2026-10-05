"""Regression fixtures for printing, markup, image placement and structure safety."""
import io
import math
from unittest.mock import Mock

import fitz
import pytest
from PIL import Image

from core.accessibility_engine import AccessibilityEngine
from core.document import PDFDocument
from core.image_inspection import inspect_images
from core.print_engine import PrintEngine, render_scale


def opened(path):
    document = PDFDocument()
    assert document.open(str(path))
    return document


@pytest.mark.parametrize('kind', ['underline', 'strikeout'])
@pytest.mark.parametrize('rotation', [0, 90])
def test_markup_covers_each_selected_glyph_and_undo(tmp_path, kind, rotation):
    source = tmp_path / 'multiline.pdf'
    with fitz.open() as pdf:
        page = pdf.new_page()
        if rotation:
            page.insert_text((200, 300), 'Rotated text', rotate=rotation)
        else:
            page.insert_text((72, 72), 'First line\nSecond line')
        pdf.save(source)
    document = opened(source)
    page = document.fitz_doc[0]
    before = page.get_pixmap().samples
    characters = [char for block in page.get_text('rawdict')['blocks']
                  for line in block.get('lines', []) for span in line['spans']
                  for char in span['chars'] if not char['c'].isspace()]
    annot = getattr(document.annotations, 'add_area_' + kind)(0, page.rect)
    assert len(annot.vertices) == len(characters) * 4
    for index, char in enumerate(characters):
        quad = fitz.Quad(annot.vertices[index*4:index*4+4])
        assert quad.rect.intersects(fitz.Rect(char['bbox']))
        if rotation: assert abs(quad.ul.y-quad.ur.y) > 1
    assert page.get_pixmap().samples != before
    assert document.undo()
    assert document.fitz_doc[0].get_pixmap().samples == before
    document.close()


def test_blank_markup_creates_no_history(sample_pdf):
    document = opened(sample_pdf)
    with pytest.raises(ValueError, match='OCR'):
        document.annotations.add_area_underline(0, fitz.Rect(300, 300, 400, 400))
    assert not document.can_undo() and not document.is_modified
    document.close()


def test_image_inspection_checks_all_placements_axes_and_rotation():
    image = io.BytesIO()
    Image.new('RGB', (600, 300), 'red').save(image, format='PNG')
    with fitz.open() as doc:
        page = doc.new_page()
        xref = page.insert_image(fitz.Rect(0, 0, 72, 36), stream=image.getvalue())
        page.insert_image(fitz.Rect(0, 100, 144, 172), xref=xref)
        page.insert_image(fitz.Rect(200, 100, 236, 172), xref=xref, rotate=90)
        page.insert_image(fitz.Rect(300, 100, 444, 244), xref=xref, keep_proportion=False)
        images = inspect_images(doc)
        assert len(images) == 4
        assert [item['dpi'] for item in images] == pytest.approx([600, 300, 600, 150])
        assert images[-1]['dpi_x'] == 300 and images[-1]['dpi_y'] == 150
        from core.preflight_engine import PreflightEngine
        report = PreflightEngine().full_preflight(doc, 'PDF/X-1a 印刷')
        assert any('DPI' in issue.message and '150' in issue.message for issue in report.issues)
        assert any(issue.category == '色彩' for issue in report.issues)


def test_inline_images_and_cancellation_are_not_reported_as_empty():
    with fitz.open() as doc:
        page = doc.new_page()
        stream = doc.get_new_xref()
        doc.update_object(stream, '<< >>')
        doc.update_stream(stream, b'q 72 0 0 72 0 0 cm BI /W 1 /H 1 /CS /RGB /BPC 8 ID \xff\x00\x00 EI Q')
        page.set_contents(stream)
        images = inspect_images(doc)
        assert len(images) == 1 and images[0]['xref'] == 0 and images[0]['dpi'] == 1
        with pytest.raises(InterruptedError): inspect_images(doc, lambda: True)


def test_table_selection_does_not_absorb_unselected_text(tmp_path):
    source = tmp_path / 'table.pdf'
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), 'Selected cell')
        page.insert_text((72, 95), 'Unselected text inside bounds')
        pdf.save(source)
    document = opened(source)
    engine = AccessibilityEngine()
    engine.auto_tag(document, 'Table')
    section = engine.get_structure_tree(document.fitz_doc).children[0].children[0]
    selected, other = section.children
    before = document.fitz_doc.xref_get_key(other.xref, 'P')
    table = engine.add_table_structure(document.fitz_doc, 0, fitz.Rect(50, 40, 350, 110), 1, 1, [selected.xref])
    assert document.fitz_doc.xref_get_key(other.xref, 'P') == before
    assert document.fitz_doc.xref_get_key(selected.xref, 'P') != before
    assert engine.get_structure_tree(document.fitz_doc).children[0].children[0].children[0].xref == table
    document.close()


def test_table_limit_and_mixed_kids_preserve_original(sample_pdf):
    document = opened(sample_pdf)
    engine = AccessibilityEngine()
    engine.auto_tag(document, 'Table')
    count = document.fitz_doc.xref_length()
    with pytest.raises(ValueError, match='儲存格'):
        engine.add_table_structure(document.fitz_doc, 0, fitz.Rect(50, 40, 300, 100), 1000, 1000)
    assert document.fitz_doc.xref_length() == count
    section = engine.get_structure_tree(document.fitz_doc).children[0].children[0]
    mixed = f'[ {section.children[0].xref} 0 R 5 ]'
    document.fitz_doc.xref_set_key(section.xref, 'K', mixed)
    original = document.fitz_doc.xref_get_key(section.xref, 'K')
    with pytest.raises(ValueError, match='混合'):
        engine.reorder_children(document.fitz_doc, section.xref, [0])
    assert document.fitz_doc.xref_get_key(section.xref, 'K') == original
    document.close()


def test_vector_print_copy_order_copies_forms_and_annotations(sample_pdf, tmp_path):
    document = opened(sample_pdf)
    page = document.fitz_doc[0]
    annotation = page.add_rect_annot(fitz.Rect(50, 100, 100, 150))
    annotation.set_colors(stroke=(1, 0, 0)); annotation.update()
    widget = fitz.Widget(); widget.field_name = 'Print field'; widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    widget.field_value = 'Filled form'; widget.rect = fitz.Rect(72, 180, 250, 210)
    page.add_widget(widget)
    target = tmp_path / 'print.pdf'
    report = PrintEngine(document).export_pdf(target, [2, 0], 2, landscape=True)
    assert report['pages'] == 4 and document.page_count == 3
    with fitz.open(target) as output:
        assert all(p.rect.width > p.rect.height for p in output)
        assert ['Sample page ' + n in output[i].get_text() for i, n in enumerate(['3', '1', '3', '1'])] == [True]*4
        assert 'Filled form' in output[1].get_text()
        assert output[1].get_drawings() and not output[1].get_images()
        assert not list(output[1].annots() or ()) and not list(output[1].widgets() or ())
    assert list(document.fitz_doc[0].annots()) and list(document.fitz_doc[0].widgets())
    document.close()


def test_print_failure_cancel_and_source_protection(sample_pdf, tmp_path):
    document = opened(sample_pdf)
    engine = PrintEngine(document)
    before = sample_pdf.read_bytes()
    with pytest.raises(ValueError, match='來源'):
        engine.export_pdf(sample_pdf, [0], overwrite=True)
    assert sample_pdf.read_bytes() == before
    target = tmp_path / 'print.pdf'
    target.write_bytes(b'Previous output')
    with pytest.raises(InterruptedError):
        engine.export_pdf(target, [0], overwrite=True, interrupted=lambda: True)
    assert target.read_bytes() == b'Previous output' and not list(tmp_path.glob('.acropdf_*'))
    with pytest.raises(FileExistsError): engine.export_pdf(target, [0])
    with pytest.raises(ValueError): engine.export_pdf(tmp_path/'invalid.pdf', [100])
    document.close()


def test_extreme_print_rendering_stays_bounded():
    page = fitz.Rect(0, 0, 14400, 14400)
    scale = render_scale(page, 9600)
    assert math.ceil(page.width * scale) <= 16384
    assert (page.width * scale) * (page.height * scale) <= 24_000_001
    assert render_scale(fitz.Rect(0, 0, 595, 842), 1200) == 300 / 72


def test_checked_pdf_with_missing_path_never_prints_to_device(qapp, monkeypatch):
    from ui.dialogs.print_dialog import PrintDialog
    from PyQt6.QtWidgets import QMessageBox
    warning = Mock(); monkeypatch.setattr(QMessageBox, 'warning', warning)
    dialog = PrintDialog(1, 0)
    dialog._pdf_check.setChecked(True)
    dialog._accept_settings()
    assert warning.called and dialog._settings is None


def test_command_arrows_skip_disabled_actions(qapp):
    from ui.widgets.command_palette import CommandPalette
    dialog = CommandPalette(None, [('Open', '', Mock(), True), ('Save', '', Mock(), False),
                                   ('Export', '', Mock(), False), ('Help', '', Mock(), True)])
    dialog._move(1)
    assert dialog._results.currentItem().text() == 'Help'
    dialog._move(1)
    assert dialog._results.currentItem().text() == 'Open'
    dialog._move(-1)
    assert dialog._results.currentItem().text() == 'Help'


def test_print_hardlink_alias_is_protected(sample_pdf, tmp_path):
    import os
    link = tmp_path / 'alias.pdf'
    os.link(sample_pdf, link)
    document = opened(sample_pdf)
    with pytest.raises(ValueError, match='來源'):
        PrintEngine(document).export_pdf(link, [0], overwrite=True)
    document.close()


def test_print_permissions_distinguish_reader_from_owner(sample_pdf, tmp_path):
    encrypted = tmp_path/'protected.pdf'
    with fitz.open(sample_pdf) as source:
        source.save(encrypted, encryption=fitz.PDF_ENCRYPT_AES_256,
                    user_pw='reader', owner_pw='owner', permissions=fitz.PDF_PERM_COPY)
    document = PDFDocument()
    assert document.open(str(encrypted), 'reader')
    with pytest.raises(ValueError, match='列印權限'):
        PrintEngine(document).export_pdf(tmp_path/'reader-print.pdf', [0])
    document.close()
    assert document.open(str(encrypted), 'owner')
    PrintEngine(document).export_pdf(tmp_path/'owner-print.pdf', [0])
    assert (tmp_path/'owner-print.pdf').exists()
    document.close()


def test_physical_print_failure_does_not_leave_false_completion(sample_pdf, qapp, tmp_path):
    from PyQt6.QtPrintSupport import QPrinter
    from core.print_engine import print_to_device
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(tmp_path/'device.pdf'))
    with fitz.open(sample_pdf) as source:
        def fail(_): raise RuntimeError('Injected print failure')
        with pytest.raises(RuntimeError, match='Injected'):
            print_to_device(source, printer, [0, 1], progress=fail)


def test_print_progress_worker_finishes_cleanly(sample_pdf, tmp_path, qapp):
    from PyQt6.QtCore import QEventLoop, QTimer
    from ui.dialogs.print_dialog import PrintSettings
    from ui.dialogs.print_progress_dialog import PrintProgressDialog
    document = opened(sample_pdf)
    settings = PrintSettings('', [0, 2], 1, output_pdf_path=str(tmp_path/'async-print.pdf'))
    dialog = PrintProgressDialog(document, settings)
    loop = QEventLoop()
    dialog.finished.connect(loop.quit)
    timer = QTimer(); timer.setSingleShot(True); timer.timeout.connect(loop.quit); timer.start(5000)
    dialog.show(); loop.exec()
    assert dialog.report and dialog.report['pages'] == 2
    assert not dialog.running_workers()
    document.close()


@pytest.mark.parametrize('kind', ['add_freetext', 'add_callout'])
def test_annotation_text_overflow_is_rolled_back(sample_pdf, kind):
    document = opened(sample_pdf)
    with pytest.raises(ValueError, match='完整顯示'):
        getattr(document.annotations, kind)(0, fitz.Rect(50, 100, 80, 110), 'Long text 中文 that cannot fit in this small box')
    assert not document.can_undo() and not document.is_modified
    assert not list(document.fitz_doc[0].annots() or ())
    annotation = getattr(document.annotations, kind)(0, fitz.Rect(50, 100, 300, 150), '中文標注 Test')
    assert '中文標注 Test' in annotation.get_text()
    assert document.undo() and not list(document.fitz_doc[0].annots() or ())
    document.close()


def test_selective_flatten_keeps_page_identity_links_and_other_annotations(sample_pdf):
    document = opened(sample_pdf)
    pdf = document.fitz_doc
    page_xrefs = [page.xref for page in pdf]
    pdf.set_toc([[1, 'Page two', 2]])
    pdf[0].insert_link({'kind':fitz.LINK_GOTO, 'from':fitz.Rect(10, 10, 40, 40), 'page':2})
    pdf[1].insert_link({'kind':fitz.LINK_GOTO, 'from':fitz.Rect(10, 10, 40, 40), 'page':0})
    for number in [0, 1]:
        page = pdf[number]; annotation = page.add_rect_annot(fitz.Rect(50, 100, 100, 150))
        annotation.set_colors(stroke=(1, 0, 0)); annotation.update()
    before = [page.get_pixmap().samples for page in pdf]
    document.annotations.flatten([0])
    pdf = document.fitz_doc
    assert [page.xref for page in pdf] == page_xrefs
    assert pdf[0].get_links()[0]['page'] == 2 and pdf[1].get_links()[0]['page'] == 0
    assert pdf.get_toc() == [[1, 'Page two', 2]]
    assert not list(pdf[0].annots() or ()) and len(list(pdf[1].annots() or ())) == 1
    assert [page.get_pixmap().samples for page in pdf] == before
    assert document.undo() and list(document.fitz_doc[0].annots())
    document.close()


def test_preflight_includes_painted_rgb_text_vectors_and_nested_forms():
    from core.preflight_engine import PreflightEngine
    with fitz.open() as doc, fitz.open() as nested:
        source = nested.new_page(); source.insert_text((72, 72), 'Nested RGB', color=(1, 0, 0))
        page = doc.new_page(); page.insert_text((72, 72), 'RGB text', color=(0, 0, 1))
        page.draw_rect(fitz.Rect(72, 100, 200, 150), color=(0, 1, 0))
        second = doc.new_page(); second.show_pdf_page(second.rect, nested)
        report = PreflightEngine().full_preflight(doc, 'PDF/X-1a 印刷')
        assert {issue.page for issue in report.issues if issue.category == '色彩'} == {0, 1}
        assert 'RGB' in PreflightEngine().check_color_spaces(doc)


def test_preflight_unused_rgb_state_does_not_flag_gray_paint():
    from core.color_inspection import painted_color_spaces
    with fitz.open() as doc:
        page = doc.new_page()
        stream = doc.get_new_xref(); doc.update_object(stream, '<< >>')
        doc.update_stream(stream, b'q 1 0 0 rg Q 0 g 20 20 50 50 re f')
        page.set_contents(stream)
        assert painted_color_spaces(doc) == [{'灰階'}]


def test_print_respects_nonprinting_annotation_flags(sample_pdf, tmp_path):
    document = opened(sample_pdf)
    page = document.fitz_doc[0]
    printable = page.add_rect_annot(fitz.Rect(50, 100, 100, 150))
    printable.set_colors(stroke=(1, 0, 0)); printable.update()
    nonprinting = page.add_rect_annot(fitz.Rect(150, 100, 200, 150))
    nonprinting.set_colors(stroke=(0, 0, 1)); nonprinting.set_flags(0); nonprinting.update()
    target = tmp_path/'print-flags.pdf'
    PrintEngine(document).export_pdf(target, [0])
    with fitz.open(target) as check:
        strokes = [item['color'] for item in check[0].get_drawings() if item.get('color')]
        assert any(color == (1, 0, 0) for color in strokes)
        assert not any(color == (0, 0, 1) for color in strokes)
    assert len(list(document.fitz_doc[0].annots())) == 2
    document.close()


def test_textbox_keeps_draft_on_overflow_and_allows_font_adjustment(sample_pdf, qapp, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox, QDialog
    from ui.dialogs.text_box.text_box_dialog import TextBoxDialog
    document = opened(sample_pdf)
    warning = Mock(); monkeypatch.setattr(QMessageBox, 'warning', warning)
    dialog = TextBoxDialog(font_size=12, inserter=lambda text, size:
        document.annotations.add_freetext(0, fitz.Rect(50,100,350,150), text, fontsize=size))
    draft = 'A long annotation sentence with words ' * 8
    dialog._text_edit.setPlainText(draft)
    dialog._insert()
    assert warning.called and dialog.result() != QDialog.DialogCode.Accepted
    assert dialog._text_edit.toPlainText() == draft and not document.can_undo()
    dialog._size_spin.setValue(5); dialog._insert()
    assert dialog.result() == QDialog.DialogCode.Accepted and document.can_undo()
    document.close()
