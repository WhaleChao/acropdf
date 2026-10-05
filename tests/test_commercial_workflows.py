"""End-to-end commercial workflow checks on outputs, content and failure safety."""
from pathlib import Path
import shutil
import threading
import time
import fitz
import pikepdf
import pytest
from PyQt6.QtCore import QThread, QThreadPool
from PyQt6.QtWidgets import QDialog
from PyQt6.QtTest import QTest
from core.document import PDFDocument
from core.batch_engine import BatchEngine
from core.smart_filing_engine import SmartFilingEngine, FilingRule
from core.security_pikepdf import PikePDFSecurity
from ui.widgets.worker_dialog import WorkerDialog


def opened(path, password=''):
    document = PDFDocument(); assert document.open(str(path), password)
    return document


def test_batch_never_copies_sources_into_destination(sample_pdf, tmp_path):
    out = tmp_path / 'batch'; out.mkdir()
    existing = out / sample_pdf.name; existing.write_bytes(b'previous unrelated file')
    results = BatchEngine().batch_process([str(sample_pdf)], 'watermark', {'output_dir': str(out), 'text': 'BATCH'})
    assert results[0]['ok'] and existing.read_bytes() == b'previous unrelated file'
    with fitz.open(results[0]['output']) as check:
        assert 'BATCH' in check[0].get_text() and 'Sample page 1' in check[0].get_text()


def test_batch_generated_collision_preserves_existing(sample_pdf, tmp_path):
    target = sample_pdf.with_name(sample_pdf.stem + '_watermarked.pdf'); target.write_bytes(b'original destination')
    result = BatchEngine().batch_process([str(sample_pdf)], 'watermark', {'text':'NEW'})[0]
    assert not result['ok'] and target.read_bytes() == b'original destination'
    assert not list(tmp_path.glob('.acropdf_*'))


@pytest.mark.parametrize('count', [0, -1])
def test_invalid_split_does_not_loop_or_publish(sample_pdf, tmp_path, count):
    with pytest.raises(ValueError): BatchEngine().split_pages(sample_pdf, tmp_path / 'parts', count)
    assert not (tmp_path / 'parts').exists()


def test_batch_cancellation_reports_unprocessed_files(sample_pdf):
    results = BatchEngine().batch_process([str(sample_pdf)], 'watermark', {}, is_cancelled=lambda:True)
    assert len(results) == 1 and not results[0]['ok'] and not list(sample_pdf.parent.glob('*watermarked*'))


def test_batch_encryption_uses_supplied_passwords(sample_pdf, tmp_path):
    result = BatchEngine().batch_process([str(sample_pdf)], 'encrypt', {'output_dir':str(tmp_path),'owner_password':'unique owner','user_password':'unique reader'})[0]
    assert result['ok']
    with fitz.open(result['output']) as encrypted:
        assert encrypted.needs_pass and not encrypted.authenticate('owner123')
        assert encrypted.authenticate('unique reader') and 'Sample page 1' in encrypted[0].get_text()


def test_batch_encryption_rejects_missing_owner_password(sample_pdf):
    result = BatchEngine().batch_process([str(sample_pdf)], 'encrypt', {})[0]
    assert not result['ok'] and not list(sample_pdf.parent.glob('*_enc.pdf'))


def test_security_export_keeps_live_document_and_undo_usable(sample_pdf, tmp_path):
    document = opened(sample_pdf)
    document.security.encrypt(str(tmp_path/'protected.pdf'), owner_pw='owner', user_pw='reader')
    with fitz.open('pdf', document._snapshot()) as snapshot:
        assert not snapshot.needs_pass and 'Sample page 1' in snapshot[0].get_text()
    document.pages.rotate([0],90); assert document.undo()
    assert document.fitz_doc[0].rotation == 0
    document.close()


def test_pikepdf_encryption_honours_passwords_and_flags(sample_pdf, tmp_path):
    target=tmp_path/'locked.pdf'
    PikePDFSecurity().encrypt_with_aes256(str(sample_pdf),str(target), user_pw='reader-pass',owner_pw='owner-pass', permissions={'copy':False,'print':True})
    with pikepdf.open(target,password='reader-pass') as check:
        assert check.is_encrypted and not check.allow.extract and check.allow.print_lowres
    assert not PikePDFSecurity().inspect_encryption(str(sample_pdf))['encrypted']


def test_filing_identical_names_preserves_every_document(sample_pdf, tmp_path):
    source=tmp_path/'inputs';source.mkdir(); output=tmp_path/'filed'
    for index in range(2):
        with fitz.open(sample_pdf) as doc:
            doc[0].insert_text((72,150),f'Identity {index}');doc.save(source/f'{index}.pdf')
    rules=[FilingRule('Sample','Documents','same','same.pdf')]
    results=SmartFilingEngine().analyze_and_file(str(source),str(output),rules)
    assert len(results)==2 and len({r['output'] for r in results})==2
    for index,result in enumerate(results):
        with fitz.open(result['output']) as doc: assert f'Identity {index}' in doc[0].get_text()
    again=SmartFilingEngine().analyze_and_file(str(source),str(output),rules)
    assert len(list((output/'same').glob('*.pdf')))==4 and all(r['ok'] for r in again)


def test_filing_rejects_traversal_rule(sample_pdf,tmp_path):
    output=tmp_path/'root';source=tmp_path/'inputs';source.mkdir();shutil.copy2(sample_pdf,source/'sample.pdf')
    result=SmartFilingEngine().analyze_and_file(str(source),str(output),[FilingRule('Sample','Documents','../../escape','stolen.pdf')])[0]
    assert not result['ok'] and not (tmp_path.parent/'escape'/'stolen.pdf').exists()


def test_linearization_is_real_and_does_not_change_source(sample_pdf,tmp_path):
    document=opened(sample_pdf);target=tmp_path/'linear.pdf';before=sample_pdf.read_bytes()
    document.optimize.linearize(str(target))
    with pikepdf.open(target) as check: assert check.is_linearized
    assert sample_pdf.read_bytes()==before and not document.is_modified
    document.close()


def test_optimization_preserves_annotation_and_removes_only_metadata(sample_pdf,tmp_path):
    document=opened(sample_pdf); document.fitz_doc[0].add_text_annot((100,100),'Keep this review')
    document.fitz_doc.set_metadata({'title':'Private metadata'})
    target=tmp_path/'optimized.pdf';document.optimize.optimize(str(target),remove_metadata=True)
    with fitz.open(target) as check:
        assert not check.metadata['title']
        assert any(a.info['content']=='Keep this review' for a in check[0].annots())
        assert 'Sample page 1' in check[0].get_text()
    assert document.fitz_doc.metadata['title']=='Private metadata'
    document.close()


def test_dialog_waits_for_running_worker_on_escape(qapp):
    release=threading.Event()
    class WaitingThread(QThread):
        def run(self): release.wait(2)
    dialog=WorkerDialog();worker=WaitingThread(dialog);dialog._worker=worker;dialog.show();worker.start()
    while not worker.isRunning(): QTest.qWait(1)
    dialog.reject();assert dialog.isVisible() and worker.isInterruptionRequested()
    release.set()
    import time
    deadline = time.monotonic() + 3
    while dialog.isVisible() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert not dialog.isVisible() and dialog.result()==QDialog.DialogCode.Rejected


def test_font_replace_embeds_program_and_keeps_text(sample_pdf,tmp_path):
    font = fitz.Font(fontname='notos')
    font_path=tmp_path/'NotoSans.ttf';font_path.write_bytes(font.buffer)
    document=opened(sample_pdf);document.fonts.embed_font('Helvetica',str(font_path))
    assert all(f.embedded for f in document.fonts.list_fonts())
    assert 'Sample page 1' in document.fitz_doc[0].get_text().replace('\xa0',' ')
    assert document.undo() and any(not f.embedded for f in document.fonts.list_fonts())
    document.close()


def test_font_subset_keeps_text_and_renders(sample_pdf):
    document=opened(sample_pdf);document.fonts.subset_font(document.fonts.list_fonts()[0].name)
    assert 'Sample page 1' in document.fitz_doc[0].get_text()
    assert document.fitz_doc[0].get_pixmap().width>0
    document.close()


@pytest.mark.skipif(not shutil.which('tesseract'),reason='Tesseract external runtime unavailable')
def test_tesseract_persists_searchable_layer_without_changing_pixels(tmp_path):
    from PIL import Image, ImageDraw, ImageFont
    from acro_platform.common import TesseractOCR
    image=Image.new('RGB',(1400,320),'white');draw=ImageDraw.Draw(image)
    font_path=tmp_path/'NotoSans.ttf';font_path.write_bytes(fitz.Font(fontname='notos').buffer)
    draw.text((50,70),'Searchable document 2026',fill='black',font=ImageFont.truetype(str(font_path),70))
    import io
    stream=io.BytesIO();image.save(stream,format='PNG')
    with fitz.open() as doc:
        page=doc.new_page(width=700,height=160);page.insert_image(page.rect,stream=stream.getvalue())
        before=page.get_pixmap().samples
        TesseractOCR().ocr_page(page,'eng',200)
        target=tmp_path/'ocr.pdf';doc.save(target)
    with fitz.open(target) as result:
        assert 'Searchable' in result[0].get_text() and result[0].search_for('2026')
        assert result[0].get_pixmap().samples==before


def test_ocr_async_uses_unsaved_document_snapshot(qapp,sample_pdf,tmp_path,monkeypatch):
    from core.ocr_engine import OCREngine
    import acro_platform
    class Backend:
        name='Test recognizer'
        def ocr_page(self,page,lang,dpi): page.insert_text((72,180),'Recognized layer',render_mode=3)
    monkeypatch.setattr(acro_platform,'get_ocr_backend',lambda:Backend())
    document=opened(sample_pdf);document.fitz_doc[0].insert_text((72,150),'Unsaved edit');document._modified=True
    target=tmp_path/'ocr.pdf';completed=[];errors=[]
    job=OCREngine.run_async(document,str(target),on_finished=completed.append,on_error=errors.append)
    QThreadPool.globalInstance().waitForDone(10000);qapp.processEvents()
    assert completed==[str(target)] and not errors and not job.isRunning()
    with fitz.open(target) as output:
        assert 'Unsaved edit' in output[0].get_text() and 'Recognized layer' in output[0].get_text()
    document.close()


@pytest.mark.skipif(not shutil.which('gs') or not shutil.which('java'),reason='Offline standards engines unavailable')
@pytest.mark.parametrize('flavour',['1b','2b','3b'])
def test_pdfa_is_independently_verified_and_preserves_pages(sample_pdf,tmp_path,flavour):
    from core.pdf_standards import PDFStandards
    document=opened(sample_pdf);target=tmp_path/f'archive-{flavour}.pdf'
    report=PDFStandards(document).export_pdfa(str(target),flavour)
    result=report['report']['jobs'][0]['validationResult'][0]
    assert result['compliant'] and result['details']['failedChecks']==0
    with fitz.open(target) as check:
        assert len(check)==3 and 'Sample page 1' in check[0].get_text()
    assert not document.is_modified
    document.close()
