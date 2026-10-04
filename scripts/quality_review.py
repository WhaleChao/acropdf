#!/usr/bin/env python3
"""Offscreen native Qt review. Writes screenshots and real event-loop evidence.

Run: python scripts/quality_review.py --output work/quality-review
This isolates settings and recovery files from the user's application data.
It does not replace live desktop, assistive technology or cross-reader testing.
"""
import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, default=root / 'work/quality-review')
args = parser.parse_args()
base = args.output.resolve()
base.mkdir(parents=True, exist_ok=True)
workspace = tempfile.TemporaryDirectory(prefix='acropdf_review_')
scratch = Path(workspace.name)
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['ACROPDF_RECOVERY_DIR'] = str(scratch / 'recovery')
import fitz
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSettings,QThreadPool
from app.config import Config
app=QApplication([]);Config()._settings=QSettings(str(scratch/'settings.ini'),QSettings.Format.IniFormat)
Config().set('recent_files',[]);Config().set('window_geometry',None)
from ui.main_window import MainWindow
from ui.dialogs.document_properties_dialog import DocumentPropertiesDialog
from ui.widgets.command_palette import CommandPalette
pdf=scratch/'review.pdf'
with fitz.open() as d:
 for i in range(12):
  p=d.new_page();p.insert_text((52,65),'ACROPDF / DOCUMENT STUDIO',fontsize=10,color=(.08,.4,.36))
  p.insert_text((52,120),'A quieter way to work.',fontsize=27)
  p.insert_text((52,180),'Your documents. Your workspace. Your control.',fontsize=12)
  p.draw_rect(fitz.Rect(52,225,540,227),color=(.08,.4,.36),fill=(.08,.4,.36))
  p.insert_text((52,265),f'REVIEW DOCUMENT / {i+1:02d}',fontsize=10)
  p.insert_textbox(fitz.Rect(52,310,540,720),'A document editor must earn trust through reliable saving,\nclear feedback, consistent controls and careful handling\nof every page.\n\nThis sample checks page navigation, search, annotations,\nzoom, rendering, export and theme consistency.',fontsize=14,lineheight=1.7)
 d.save(pdf)
w=MainWindow();w.resize(1280,900);w.show();app.processEvents()
for theme in ['light','dark']:
 w._switch_theme(theme);app.processEvents();w.grab().save(str(base/f'AcroPDF-{theme}.png'))
w.resize(900,640);app.processEvents();w.grab().save(str(base/'AcroPDF-small-window.png'))
w.resize(1280,900);w.open_file(str(pdf));w._show_thumbnails();app.processEvents();QThreadPool.globalInstance().waitForDone(10000);app.processEvents();w._current_view().fit_page();app.processEvents();QThreadPool.globalInstance().waitForDone(10000);app.processEvents()
for theme in ['light','dark']:
 w._switch_theme(theme);app.processEvents();w.grab().save(str(base/f'AcroPDF-document-{theme}.png'))
dlg=DocumentPropertiesDialog(w._current_doc(),w);dlg.show();app.processEvents();dlg.grab().save(str(base/'AcroPDF-dialog-dark.png'));dlg.close()
palette=CommandPalette(w,[('開啟文件','open pdf',w.open_file_dialog,True),('匯出 Word','docx export',lambda:None,True),('OCR 文字辨識','scan',lambda:None,True),('永久塗黑','redact',lambda:None,True),('夜間模式','dark theme',lambda:None,True)]);palette.show();app.processEvents();palette.grab().save(str(base/'AcroPDF-commands.png'));palette.close()
# Real event-loop regression: repeated rebuilds, not just method-return checks.
view=w._current_view()
for _ in range(12):
 for zoom in (.5,.75,1.0):
  view.set_zoom(zoom);app.processEvents()
 QThreadPool.globalInstance().waitForDone(10000);app.processEvents()
assert len(view._page_widgets)==12
assert view._container_layout.count()==12
assert len(view._pending_signals)==0
assert len(view._cache._cache)<=12
assert view._cache._bytes<=96*1024*1024
big=scratch/'300-pages.pdf'
with fitz.open() as d:
 for i in range(300):d.new_page().insert_text((72,72),f'Page {i+1}')
 d.save(big)
start=time.perf_counter();w.open_file(str(big));app.processEvents();elapsed=time.perf_counter()-start
QThreadPool.globalInstance().waitForDone(10000);app.processEvents();w._current_view().go_to_page(299);app.processEvents();QThreadPool.globalInstance().waitForDone(10000);app.processEvents()
assert w._current_view().current_page()==299
assert any(pw._pixmap for pw in w._current_view()._page_widgets if pw.page_num==299)
(base/'validation.json').write_text(json.dumps({'repeat_zoom_cycles':36,'pending_render_jobs':len(view._pending_signals),'large_pdf_pages':300,'open_to_event_loop_seconds':round(elapsed,3),'last_page_rendered':True},indent=2))
for doc in w._docs:doc._modified=False
w.close();app.processEvents()

QThreadPool.globalInstance().waitForDone(10000)
workspace.cleanup()
print((base / "validation.json").read_text())
