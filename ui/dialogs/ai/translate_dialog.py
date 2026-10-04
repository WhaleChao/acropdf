# ~/Desktop/acropdf/ui/dialogs/ai/translate_dialog.py
"""AI 翻譯對話框 — 使用 LLM 翻譯 PDF 文件內容。"""

import io
import json
from typing import Optional

import fitz
import requests
from core.ai_endpoint import confirm_document_transfer
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QProgressBar, QGroupBox,
    QFormLayout, QLineEdit, QMessageBox, QFileDialog,
    QComboBox, QApplication,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal


# ---------------------------------------------------------------------------
#  語言定義
# ---------------------------------------------------------------------------

LANGUAGES = [
    ("繁體中文", "繁體中文（臺灣）"),
    ("簡體中文", "簡體中文"),
    ("英文", "英文"),
    ("日本語", "日文"),
    ("한국어", "韓文"),
    ("法文", "法文"),
    ("德文", "德文"),
    ("西班牙文", "西班牙文"),
]


# ---------------------------------------------------------------------------
#  背景執行緒：呼叫 LLM API
# ---------------------------------------------------------------------------

class _TranslateWorker(QThread):
    """在背景執行緒中呼叫 LLM 端點完成翻譯。"""

    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    CHUNK_SIZE = 6000
    TIMEOUT = 60

    def __init__(
        self,
        pages_text: list[str],
        target_lang: str,
        source_lang: str,
        endpoint: str,
        model: str,
        parent=None,
    ):
        super().__init__(parent)
        self._pages_text = pages_text
        self._target_lang = target_lang
        self._source_lang = source_lang
        self._endpoint = endpoint
        self._model = model

    def _build_system_prompt(self) -> str:
        base = f"你是專業翻譯。請將以下文件翻譯為{self._target_lang}，保持格式。"
        if self._source_lang and self._source_lang != "自動偵測":
            base += f"原文語言為{self._source_lang}。"
        return base

    def _call_llm(self, user_content: str) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": self._build_system_prompt()},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.2,
        }
        resp = requests.post(self._endpoint, json=payload, timeout=self.TIMEOUT, allow_redirects=False)
        if 300 <= resp.status_code < 400:
            raise ValueError("AI 端點重新導向已停止，請使用服務的直接 HTTPS 網址。")
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    @staticmethod
    def _split_text(full_text: str, max_len: int) -> list[str]:
        chunks: list[str] = []
        while full_text:
            if len(full_text) <= max_len:
                chunks.append(full_text)
                break
            cut = full_text.rfind("\n", 0, max_len)
            if cut < max_len // 2:
                cut = max_len
            chunks.append(full_text[:cut])
            full_text = full_text[cut:].lstrip("\n")
        return chunks

    def run(self):  # noqa: D401
        try:
            full_text = "\n\n".join(self._pages_text).strip()
            if not full_text:
                self.error.emit("文件中未偵測到任何文字。")
                return

            chunks = self._split_text(full_text, self.CHUNK_SIZE)
            translated_parts: list[str] = []

            for idx, chunk in enumerate(chunks, 1):
                if self.isInterruptionRequested():
                    self.error.emit("已取消")
                    return
                self.progress.emit(f"正在翻譯第 {idx}/{len(chunks)} 段⋯⋯")
                result = self._call_llm(chunk)
                translated_parts.append(result)

            if self.isInterruptionRequested():
                self.error.emit("已取消")
                return
            self.finished.emit("\n\n".join(translated_parts))

        except requests.exceptions.Timeout:
            self.error.emit("LLM 端點連線逾時，請確認服務是否正常運作。")
        except requests.exceptions.ConnectionError:
            self.error.emit("無法連線至 LLM 端點，請確認端點網址與服務狀態。")
        except Exception as exc:
            self.error.emit(f"翻譯失敗：{exc}")


# ---------------------------------------------------------------------------
#  對話框
# ---------------------------------------------------------------------------

class TranslateDialog(QDialog):
    """AI 翻譯對話框。"""

    _DEFAULT_ENDPOINT = "http://localhost:8080/v1/chat/completions"
    _DEFAULT_MODEL = "gemma-4-26b-a4b-it-4bit"

    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc = doc
        self._worker: Optional[_TranslateWorker] = None
        self.setWindowTitle("AI 文件翻譯")
        self.resize(660, 560)
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)

        # --- 語言設定 ---
        lang_group = QGroupBox("翻譯設定")
        lang_form = QFormLayout(lang_group)

        self._source_combo = QComboBox()
        self._source_combo.addItem("自動偵測")
        for prompt_lang, display in LANGUAGES:
            self._source_combo.addItem(display, prompt_lang)
        lang_form.addRow("原文語言：", self._source_combo)

        self._target_combo = QComboBox()
        for prompt_lang, display in LANGUAGES:
            self._target_combo.addItem(display, prompt_lang)
        lang_form.addRow("目標語言：", self._target_combo)

        root.addWidget(lang_group)

        # --- 設定區（可收合）---
        self._settings_group = QGroupBox("進階設定")
        self._settings_group.setCheckable(True)
        self._settings_group.setChecked(False)
        settings_form = QFormLayout(self._settings_group)

        self._endpoint_edit = QLineEdit(self._DEFAULT_ENDPOINT)
        self._endpoint_edit.setPlaceholderText("LLM API 端點")
        settings_form.addRow("API 端點：", self._endpoint_edit)

        self._model_edit = QLineEdit(self._DEFAULT_MODEL)
        self._model_edit.setPlaceholderText("模型名稱")
        settings_form.addRow("模型名稱：", self._model_edit)

        root.addWidget(self._settings_group)

        # --- 動作列 ---
        action_row = QHBoxLayout()
        self._run_btn = QPushButton("開始翻譯")
        self._run_btn.clicked.connect(self._run_translate)
        action_row.addWidget(self._run_btn)
        action_row.addStretch()
        root.addLayout(action_row)

        # --- 進度條 ---
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setTextVisible(True)
        self._progress.setFormat("等待中")
        self._progress.hide()
        root.addWidget(self._progress)

        # --- 結果區 ---
        self._result_edit = QTextEdit()
        self._result_edit.setReadOnly(True)
        self._result_edit.setPlaceholderText("翻譯結果將顯示於此⋯⋯")
        root.addWidget(self._result_edit)

        # --- 底部按鈕 ---
        btn_row = QHBoxLayout()

        self._apply_btn = QPushButton("套用至文件")
        self._apply_btn.setEnabled(False)
        self._apply_btn.setToolTip("在文件尾端新增翻譯後的頁面")
        self._apply_btn.clicked.connect(self._apply_to_doc)
        btn_row.addWidget(self._apply_btn)

        self._export_btn = QPushButton("匯出")
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._export_result)
        btn_row.addWidget(self._export_btn)

        btn_row.addStretch()

        close_btn = QPushButton("關閉")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)

        root.addLayout(btn_row)

    # -- helpers --

    def _extract_text(self) -> list[str]:
        fitz_doc = self._doc.fitz_doc
        pages: list[str] = []
        for i in range(self._doc.page_count):
            page = fitz_doc[i]
            text = page.get_text()
            if text.strip():
                pages.append(text)
        return pages

    # -- 動作 --

    def _run_translate(self):
        if self._worker and self._worker.isRunning():
            return

        pages_text = self._extract_text()
        if not pages_text:
            QMessageBox.warning(self, "無法翻譯", "文件中未偵測到可提取的文字。")
            return

        endpoint = self._endpoint_edit.text().strip() or self._DEFAULT_ENDPOINT
        if not confirm_document_transfer(self, endpoint, len(pages_text)):
            return

        self._run_btn.setEnabled(False)
        self._progress.show()
        self._result_edit.clear()
        self._apply_btn.setEnabled(False)
        self._export_btn.setEnabled(False)

        target_lang = self._target_combo.currentData() or self._target_combo.currentText()
        source_lang = self._source_combo.currentData() or self._source_combo.currentText()
        endpoint = self._endpoint_edit.text().strip() or self._DEFAULT_ENDPOINT
        model = self._model_edit.text().strip() or self._DEFAULT_MODEL

        self._worker = _TranslateWorker(
            pages_text, target_lang, source_lang, endpoint, model, self
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, msg: str):
        self._progress.setFormat(msg)

    def _on_finished(self, text: str):
        self._progress.hide()
        self._run_btn.setEnabled(True)
        self._result_edit.setPlainText(text)
        self._apply_btn.setEnabled(True)
        self._export_btn.setEnabled(True)

    def _on_error(self, msg: str):
        self._progress.hide()
        self._run_btn.setEnabled(True)
        QMessageBox.critical(self, "錯誤", msg)

    def _apply_to_doc(self):
        """使用 reportlab 建立翻譯頁面並插入文件尾端。"""
        translated = self._result_edit.toPlainText().strip()
        if not translated:
            return

        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle
            from reportlab.lib.units import cm
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
        except ImportError:
            QMessageBox.critical(
                self, "缺少套件",
                "需要安裝 reportlab 套件才能將翻譯套用至文件。\n"
                "請執行：pip install reportlab",
            )
            return

        try:
            # 嘗試註冊中文字型（macOS 內建）
            font_name = "Helvetica"
            for font_path in (
                "/System/Library/Fonts/PingFang.ttc",
                "/System/Library/Fonts/STHeiti Medium.ttc",
            ):
                try:
                    pdfmetrics.registerFont(TTFont("PingFang", font_path, subfontIndex=0))
                    font_name = "PingFang"
                    break
                except Exception:
                    continue

            buf = io.BytesIO()
            doc_rl = SimpleDocTemplate(buf, pagesize=A4,
                                       topMargin=2 * cm, bottomMargin=2 * cm,
                                       leftMargin=2 * cm, rightMargin=2 * cm)

            style = ParagraphStyle(
                "TranslatedText",
                fontName=font_name,
                fontSize=11,
                leading=16,
            )

            story = []
            for line in translated.split("\n"):
                if line.strip():
                    # 將 XML 特殊字元跳脫以避免 reportlab 解析錯誤
                    safe = (line.replace("&", "&amp;")
                                .replace("<", "&lt;")
                                .replace(">", "&gt;"))
                    story.append(Paragraph(safe, style))
                else:
                    story.append(Spacer(1, 12))

            if not story:
                return

            doc_rl.build(story)
            buf.seek(0)

            # 將 reportlab 產生的 PDF 頁面插入目前文件尾端
            self._doc.begin_op("套用翻譯")
            try:
                tmp_pdf = fitz.open("pdf", buf.read())
                self._doc.fitz_doc.insert_pdf(tmp_pdf)
                tmp_pdf.close()
                self._doc._mark_modified()
            finally:
                self._doc.end_op()

            QMessageBox.information(
                self, "完成",
                f"已在文件尾端新增 {tmp_pdf.page_count} 頁翻譯內容。",
            )

        except Exception as exc:
            QMessageBox.critical(self, "套用失敗", str(exc))

    def _export_result(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "匯出翻譯", "", "純文字 (*.txt)"
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(self._result_edit.toPlainText())
                QMessageBox.information(self, "完成", f"翻譯已匯出至\n{path}")
            except OSError as exc:
                QMessageBox.critical(self, "匯出失敗", str(exc))

    def reject(self):
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
            self._progress.setFormat("正在停止，等候目前請求完成…")
            return
        super().reject()

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
            self._progress.setFormat("正在停止，等候目前請求完成…")
            event.ignore()
            return
        super().closeEvent(event)
