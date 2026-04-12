from pathlib import Path

import fitz

from core.document import PDFDocument


def test_document_open_save_and_page_ops(sample_pdf, tmp_path):
    doc = PDFDocument()
    assert doc.open(str(sample_pdf))
    assert doc.page_count == 3
    assert doc.display_name == sample_pdf.name

    doc.pages.insert_blank(0)
    assert doc.page_count == 4

    doc.pages.rotate([0], 90)
    assert doc.fitz_doc[0].rotation == 90

    doc.pages.delete([3])
    assert doc.page_count == 3

    assert doc.undo()
    assert doc.page_count == 4
    assert doc.redo()
    assert doc.page_count == 3

    out = tmp_path / "saved.pdf"
    assert doc.save(str(out))
    reopened = fitz.open(out)
    try:
        assert reopened.page_count == 3
    finally:
        reopened.close()


def test_document_can_open_image_via_converter(tmp_path):
    image_path = tmp_path / "sample.png"
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 100, 100), False)
    pix.clear_with(255)
    pix.save(image_path)

    doc = PDFDocument()
    assert doc.open(str(image_path))
    assert doc.page_count == 1
    assert doc.path is None
    assert doc.display_name == image_path.name


def test_extract_and_split_pages(sample_pdf, tmp_path):
    doc = PDFDocument()
    assert doc.open(str(sample_pdf))

    extracted = tmp_path / "extracted.pdf"
    doc.pages.extract_pages([0, 2], str(extracted))
    out_doc = fitz.open(extracted)
    try:
        assert out_doc.page_count == 2
    finally:
        out_doc.close()

    outputs = doc.pages.split_by_range([(0, 0), (1, 2)], str(tmp_path))
    assert len(outputs) == 2
    for output in outputs:
        assert Path(output).exists()
