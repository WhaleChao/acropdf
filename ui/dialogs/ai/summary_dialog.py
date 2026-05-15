# ~/Desktop/acropdf/ui/dialogs/ai/summary_dialog.py
"""AI 文件摘要對話框 — 使用 LLM 產生 PDF 內容摘要。"""

import json
from typing import Optional

import requests
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QProgressBar, QGroupBox,
    QFormLayout, QLineEdit, QMessageBox, QFileDialog,
    QApplication, QToolButton, QWidget,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal


# ---------------------------------------------------------------------------
#  背景執行緒：呼叫 LLM API
# ---------------------------------------------------------------------------

class _SummaryWorker(QThread):
    """在背景執行緒中呼叫 LLM 端點，避免阻塞 UI。"""

    finished = pyqtSignal(str)       # 成功時回傳摘要文字
    error = pyqtSignal(str)          # 失敗時回傳錯誤訊息
    progress = pyqtSignal(str)       # 進度狀態文字

    CHUNK_SIZE = 8000                # 每段最大字元數
    TIMEOUT = 30                     # 單次 API 呼叫逾時（秒）

    def __init__(
        self,
        pages_text: list[str],
        endpoint: str,
        model: str,
        parent=None,
    ):
        super().__init__(parent)
        self._pages_text = pages_text
        self._endpoint = endpoint
        self._model = model

    # -- helpers --

    def _call_llm(self, user_content: str) -> str:
        """向 OpenAI-compatible 端點發送請求並回傳回覆文字。"""
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是文件摘要助手。請用繁體中文對以下文件內容撰寫詳細摘要。",
                },
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.3,
        }
        resp = requests.post(
            self._endpoint,
            json=payload,
            timeout=self.TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    @staticmethod
    def _split_text(full_text: str, max_len: int) -> list[str]:
        """將長文依 max_len 切段，盡可能在換行處切割。"""
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

    # -- main --

    def run(self):  # noqa: D401
        try:
            full_text = "\n\n".join(self._pages_text).strip()
            if not full_text:
                self.error.emit("文件中未偵測到任何文字。")
                return

            if len(full_text) <= self.CHUNK_SIZE:
                self.progress.emit("正在產生摘要⋯⋯")
                result = self._call_llm(full_text)
            else:
                chunks = self._split_text(full_text, self.CHUNK_SIZE)
                partial_summaries: list[str] = []
                for idx, chunk in enumerate(chunks, 1):
                    self.progress.emit(f"正在摘要第 {idx}/{len(chunks)} 段⋯⋯")
                    partial = self._call_llm(chunk)
                    partial_summaries.append(partial)

                self.progress.emit("正在彙整最終摘要⋯⋯")
                combined = "\n\n---\n\n".join(partial_summaries)
                result = self._call_llm(
                    f"以下是同一份文件各段落的分段摘要，請彙整為一份完整摘要：\n\n{combined}"
                )

            self.finished.emit(result)

        except requests.exceptions.Timeout:
            self.error.emit("LLM 端點連線逾時（30 秒），請確認服務是否正常運作。")
        except requests.exceptions.ConnectionError:
            self.error.emit("無法連線至 LLM 端點，請確認端點網址與服務狀態。")
        except Exception as exc:
            self.error.emit(f"摘要產生失敗：{exc}")


# ---------------------------------------------------------------------------
#  對話框
# ---------------------------------------------------------------------------

class SummaryDialog(QDialog):
    """AI 文件摘要對話框。"""

    _DEFAULT_ENDPOINT = "http://localhost:8080/v1/chat/completions"
    _DEFAULT_MODEL = "gemma-4-26b-a4b-it-4bit"

    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc = doc
        self._worker: Optional[_SummaryWorker] = None
        self.setWindowTitle("AI 文件摘要")
        self.resize(640, 520)
        self._setup_ui()

    # -- UI 建構 --

    def _setup_ui(self):
        root = QVBoxLayout(self)

        # --- 設定區（可收合）---
        self._settings_group = QGroupBox("設定")
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
        self._run_btn = QPushButton("產生摘要")
        self._run_btn.clicked.connect(self._run_summary)
        action_row.addWidget(self._run_btn)
        action_row.addStretch()
        root.addLayout(action_row)

        # --- 進度條 ---
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.setTextVisible(True)
        self._progress.setFormat("等待中")
        self._progress.hide()
        root.addWidget(self._progress)

        # --- 結果區 ---
        self._result_edit = QTextEdit()
        self._result_edit.setReadOnly(True)
        self._result_edit.setPlaceholderText("摘要結果將顯示於此⋯⋯")
        root.addWidget(self._result_edit)

        # --- 底部按鈕 ---
        btn_row = QHBoxLayout()
        self._copy_btn = QPushButton("複製")
        self._copy_btn.setEnabled(False)
        self._copy_btn.clicked.connect(self._copy_result)
        btn_row.addWidget(self._copy_btn)

        self._export_btn = QPushButton("匯出")
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._export_result)
        btn_row.addWidget(self._export_btn)

        btn_row.addStretch()

        close_btn = QPushButton("關閉")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)

        root.addLayout(btn_row)

    # -- 動作 --

    def _extract_text(self) -> list[str]:
        """從 PDF 文件各頁提取文字。"""
        fitz_doc = self._doc.fitz_doc
        pages: list[str] = []
        for i in range(self._doc.page_count):
            page = fitz_doc[i]
            text = page.get_text()
            if text.strip():
                pages.append(text)
        return pages

    def _run_summary(self):
        if self._worker and self._worker.isRunning():
            return

        pages_text = self._extract_text()
        if not pages_text:
            QMessageBox.warning(self, "無法摘要", "文件中未偵測到可提取的文字。")
            return

        self._run_btn.setEnabled(False)
        self._progress.show()
        self._result_edit.clear()
        self._copy_btn.setEnabled(False)
        self._export_btn.setEnabled(False)

        endpoint = self._endpoint_edit.text().strip() or self._DEFAULT_ENDPOINT
        model = self._model_edit.text().strip() or self._DEFAULT_MODEL

        self._worker = _SummaryWorker(pages_text, endpoint, model, self)
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
        self._copy_btn.setEnabled(True)
        self._export_btn.setEnabled(True)

    def _on_error(self, msg: str):
        self._progress.hide()
        self._run_btn.setEnabled(True)
        QMessageBox.critical(self, "錯誤", msg)

    def _copy_result(self):
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self._result_edit.toPlainText())
            QMessageBox.information(self, "已複製", "摘要已複製至剪貼簿。")

    def _export_result(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "匯出摘要", "", "純文字 (*.txt)"
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(self._result_edit.toPlainText())
                QMessageBox.information(self, "完成", f"摘要已匯出至\n{path}")
            except OSError as exc:
                QMessageBox.critical(self, "匯出失敗", str(exc))
