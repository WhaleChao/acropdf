import sys, os
sys.path.insert(0, '/Users/ai/Desktop/acropdf')
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

LOG = open('/Users/ai/Desktop/acropdf/diag_out.txt', 'w')
def log(msg): LOG.write(msg + '\n'); LOG.flush()

try:
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    log('QApplication OK')

    from core.document import PDFDocument
    doc = PDFDocument()
    doc.open('/Users/ai/Desktop/.tmp_magi_v2_cleanup/舊文件/MAGI_使用手冊.pdf')
    log(f'doc: {doc.page_count} pages')

    from ui.main_window import MainWindow
    w = MainWindow()
    w._docs.append(doc)
    from ui.viewer.pdf_view import PDFView
    v = PDFView(w)
    v.load_document(doc)
    w._doc_tabs.addTab(v, 'test.pdf')
    w._doc_tabs.setCurrentIndex(0)
    log(f'current_doc: {w._current_doc() is not None}')

    from app.constants import ToolMode
    import traceback

    for name, fn in [
        ('OCR',      lambda: w._ocr_dialog()),
        ('Security', lambda: w._security_dialog()),
        ('Sign',     lambda: w._sign_dialog()),
        ('Export',   lambda: w._export("txt")),
        ('Compare',  lambda: w._compare_dialog()),
        ('Optimize', lambda: w._optimize_dialog()),
        ('Batch',    lambda: w._batch_dialog()),
        ('Split',    lambda: w._split_pdf()),
        ('HdrFtr',   lambda: w._header_footer_dialog()),
        ('Blank',    lambda: w._insert_blank_page()),
        ('Rotate',   lambda: w._rotate(90)),
        ('ToolHL',   lambda: w._set_tool(ToolMode.HIGHLIGHT)),
    ]:
        try:
            fn()
            log(f'OK  {name}')
        except Exception as e:
            log(f'ERR {name}: {type(e).__name__}: {e}')
            log(traceback.format_exc())

    log('=== DONE ===')
except Exception as e:
    import traceback
    log(f'FATAL: {e}\n{traceback.format_exc()}')

LOG.close()
