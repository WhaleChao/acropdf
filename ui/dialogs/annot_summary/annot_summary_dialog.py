# ~/Desktop/acropdf/ui/dialogs/annot_summary/annot_summary_dialog.py
"""
註解摘要對話框。

功能：
  - 收集所有頁面的註解，依頁碼排序
  - 以唯讀 QTextEdit 顯示摘要（頁碼、類型、內容、作者、日期）
  - 匯出為 TXT 或 HTML
  - 列印摘要
"""
from __future__ import annotations

import html
from datetime import datetime
from typing import Optional

import fitz

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit,
    QDialogButtonBox, QFileDialog, QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtPrintSupport import QPrinter
from ui.dialogs.print_dialog import PrintDialog


# ── 註解類型對照表 ──────────────────────────────────────────────────

_ANNOT_TYPE_NAMES: dict[int, str] = {
    fitz.PDF_ANNOT_HIGHLIGHT:   "螢光標記",
    fitz.PDF_ANNOT_UNDERLINE:   "底線",
    fitz.PDF_ANNOT_STRIKE_OUT:  "刪除線",
    fitz.PDF_ANNOT_TEXT:        "文字附註",
    fitz.PDF_ANNOT_FREE_TEXT:   "自由文字",
    fitz.PDF_ANNOT_INK:         "墨跡",
    fitz.PDF_ANNOT_STAMP:       "圖章",
    fitz.PDF_ANNOT_REDACT:      "塗銷",
    fitz.PDF_ANNOT_SQUARE:      "矩形",
    fitz.PDF_ANNOT_CIRCLE:      "圓形",
    fitz.PDF_ANNOT_LINE:        "線條",
}


def _type_label(annot_type: int) -> str:
    return _ANNOT_TYPE_NAMES.get(annot_type, f"其他 ({annot_type})")


def _parse_pdf_date(raw: str) -> str:
    """將 PDF 日期字串 (D:YYYYMMDDHHmmSS) 轉為可讀格式。"""
    if not raw:
        return ""
    cleaned = raw.strip()
    if cleaned.startswith("D:"):
        cleaned = cleaned[2:]
    # 去除時區後綴
    for ch in ("+", "-", "Z"):
        idx = cleaned.find(ch)
        if idx > 0:
            cleaned = cleaned[:idx]
    try:
        dt = datetime.strptime(cleaned[:14], "%Y%m%d%H%M%S")
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, IndexError):
        return raw


# ── 資料收集 ────────────────────────────────────────────────────────

class _AnnotEntry:
    __slots__ = ("page", "type_label", "content", "author", "date")

    def __init__(self, page: int, type_label: str, content: str,
                 author: str, date: str):
        self.page = page
        self.type_label = type_label
        self.content = content
        self.author = author
        self.date = date


def _collect(doc) -> list[_AnnotEntry]:
    """從 PDFDocument 收集所有註解。"""
    fitz_doc = doc.fitz_doc
    if fitz_doc is None:
        return []

    entries: list[_AnnotEntry] = []
    for page_idx in range(fitz_doc.page_count):
        page = fitz_doc.load_page(page_idx)
        annots = page.annots()
        if annots is None:
            continue
        for annot in annots:
            atype = annot.type[0]
            content = (annot.info.get("content") or "").strip()
            author = (annot.info.get("title") or "").strip()
            raw_date = annot.info.get("modDate") or annot.info.get("creationDate") or ""
            entries.append(_AnnotEntry(
                page=page_idx + 1,
                type_label=_type_label(atype),
                content=content,
                author=author,
                date=_parse_pdf_date(raw_date),
            ))
    entries.sort(key=lambda e: e.page)
    return entries


# ── 格式化 ──────────────────────────────────────────────────────────

def _to_plain(entries: list[_AnnotEntry]) -> str:
    lines: list[str] = []
    lines.append(f"註解摘要報告　共 {len(entries)} 筆")
    lines.append("=" * 50)
    for e in entries:
        lines.append(f"頁碼: {e.page}")
        lines.append(f"類型: {e.type_label}")
        if e.author:
            lines.append(f"作者: {e.author}")
        if e.date:
            lines.append(f"日期: {e.date}")
        if e.content:
            lines.append(f"內容: {e.content}")
        lines.append("-" * 40)
    return "\n".join(lines)


def _to_html(entries: list[_AnnotEntry]) -> str:
    rows: list[str] = []
    for e in entries:
        rows.append(
            f"<tr>"
            f"<td style='padding:4px;border:1px solid #ccc;text-align:center'>{e.page}</td>"
            f"<td style='padding:4px;border:1px solid #ccc'>{html.escape(e.type_label)}</td>"
            f"<td style='padding:4px;border:1px solid #ccc'>{html.escape(e.content)}</td>"
            f"<td style='padding:4px;border:1px solid #ccc'>{html.escape(e.author)}</td>"
            f"<td style='padding:4px;border:1px solid #ccc'>{html.escape(e.date)}</td>"
            f"</tr>"
        )
    table = "\n".join(rows)
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<title>註解摘要報告</title></head><body>"
        f"<h2>註解摘要報告　共 {len(entries)} 筆</h2>"
        "<table style='border-collapse:collapse;width:100%'>"
        "<thead><tr>"
        "<th style='padding:6px;border:1px solid #999;background:#f0f0f0'>頁碼</th>"
        "<th style='padding:6px;border:1px solid #999;background:#f0f0f0'>類型</th>"
        "<th style='padding:6px;border:1px solid #999;background:#f0f0f0'>內容</th>"
        "<th style='padding:6px;border:1px solid #999;background:#f0f0f0'>作者</th>"
        "<th style='padding:6px;border:1px solid #999;background:#f0f0f0'>日期</th>"
        "</tr></thead><tbody>"
        f"{table}"
        "</tbody></table></body></html>"
    )


# ── 對話框 ──────────────────────────────────────────────────────────

class AnnotSummaryDialog(QDialog):
    """註解摘要 / 報告對話框。"""

    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc = doc
        self._entries: list[_AnnotEntry] = []

        self.setWindowTitle("註解摘要")
        self.resize(780, 560)
        self._setup_ui()
        self._load()

    # ── UI 建構 ───────────────────────────────────────────────────
    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 計數標籤
        self._count_label = QLabel("載入中…")
        self._count_label.setStyleSheet("font-size:13px;font-weight:bold;")
        layout.addWidget(self._count_label)

        # 摘要文字區
        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        layout.addWidget(self._text_edit, 1)

        # 按鈕列
        btn_row = QHBoxLayout()

        self._btn_export = QPushButton("匯出")
        self._btn_export.setToolTip("匯出為 TXT 或 HTML 檔案")
        self._btn_export.clicked.connect(self._on_export)
        btn_row.addWidget(self._btn_export)

        self._btn_print = QPushButton("列印")
        self._btn_print.setToolTip("列印註解摘要")
        self._btn_print.clicked.connect(self._on_print)
        btn_row.addWidget(self._btn_print)

        btn_row.addStretch()

        self._btn_close = QPushButton("關閉")
        self._btn_close.clicked.connect(self.reject)
        btn_row.addWidget(self._btn_close)

        layout.addLayout(btn_row)

    # ── 載入資料 ──────────────────────────────────────────────────
    def _load(self):
        self._entries = _collect(self._doc)
        count = len(self._entries)
        self._count_label.setText(f"共 {count} 筆註解")

        if count == 0:
            self._text_edit.setPlainText("此文件無註解。")
            self._btn_export.setEnabled(False)
            self._btn_print.setEnabled(False)
            return

        self._text_edit.setHtml(_to_html(self._entries))

    # ── 匯出 ─────────────────────────────────────────────────────
    def _on_export(self):
        path, chosen = QFileDialog.getSaveFileName(
            self,
            "匯出註解摘要",
            "annotation_summary",
            "純文字檔 (*.txt);;HTML 檔案 (*.html)",
        )
        if not path:
            return

        try:
            if chosen.startswith("HTML") or path.lower().endswith(".html"):
                content = _to_html(self._entries)
            else:
                content = _to_plain(self._entries)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            QMessageBox.information(self, "匯出完成", f"已儲存至：\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "匯出失敗", str(e))

    # ── 列印 ─────────────────────────────────────────────────────
    def _on_print(self):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = PrintDialog(1, 0, self, show_page_range=False)
        dlg.setWindowTitle("列印註解摘要")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        settings = dlg.settings()
        printer.setCopyCount(settings.copies)
        if settings.output_pdf_path:
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(settings.output_pdf_path)
        else:
            printer.setPrinterName(settings.printer_name)
        self._text_edit.print(printer)
        if settings.output_pdf_path:
            QMessageBox.information(self, "列印完成", f"PDF 已輸出至：\n{settings.output_pdf_path}")
