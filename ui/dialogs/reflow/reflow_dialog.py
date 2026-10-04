# ~/Desktop/acropdf/ui/dialogs/reflow/reflow_dialog.py
"""
文字重排對話框 — 讓使用者選擇頁面上的文字區塊並重新編輯文字。
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QTextEdit, QPushButton, QSplitter, QMessageBox, QSpinBox
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QImage, QIcon
import fitz


class ReflowDialog(QDialog):
    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc = doc
        self._page_num = 0
        self._blocks = []
        self._selected_block = None
        self.setWindowTitle("文字重排編輯")
        self.resize(860, 600)
        self._setup_ui()
        self._load_page(0)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # 頁面選擇
        page_row = QHBoxLayout()
        page_row.addWidget(QLabel("頁面："))
        self._page_spin = QSpinBox()
        self._page_spin.setRange(1, self._doc.fitz_doc.page_count)
        self._page_spin.valueChanged.connect(lambda v: self._load_page(v - 1))
        page_row.addWidget(self._page_spin)
        page_row.addStretch()
        layout.addLayout(page_row)

        # 主分割區
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左：文字區塊列表
        left = QVBoxLayout()
        left_w = QDialog()
        left_w.setLayout(left)
        left.addWidget(QLabel("頁面文字區塊（點選選取）："))
        self._block_list = QListWidget()
        self._block_list.currentRowChanged.connect(self._on_block_selected)
        left.addWidget(self._block_list)
        splitter.addWidget(left_w)

        # 右：編輯區
        right = QVBoxLayout()
        right_w = QDialog()
        right_w.setLayout(right)
        right.addWidget(QLabel("編輯文字內容："))
        self._text_edit = QTextEdit()
        self._text_edit.setPlaceholderText("選取左側文字區塊後在此編輯…")
        right.addWidget(self._text_edit)

        hint = QLabel("注意：文字重排會先塗黑原區域再插入新文字，請確認後套用。")
        hint.setStyleSheet("color: #8e8e93; font-size: 11px;")
        hint.setWordWrap(True)
        right.addWidget(hint)

        btn_row = QHBoxLayout()
        self._apply_btn = QPushButton("套用重排")
        self._apply_btn.setDefault(True)
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self._apply_reflow)
        cancel_btn = QPushButton("關閉")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(self._apply_btn)
        btn_row.addWidget(cancel_btn)
        right.addLayout(btn_row)
        splitter.addWidget(right_w)

        splitter.setSizes([300, 540])
        layout.addWidget(splitter)

    def _load_page(self, page_num: int):
        self._page_num = page_num
        self._block_list.clear()
        self._selected_block = None
        self._apply_btn.setEnabled(False)
        self._text_edit.clear()

        from core.text_reflow_engine import TextReflowEngine
        engine = TextReflowEngine()
        page = self._doc.fitz_doc[page_num]
        self._blocks = engine.parse_blocks(page)

        for i, blk in enumerate(self._blocks):
            combined = " ".join(s.text for s in blk.spans).strip()
            preview = combined[:60] + ("…" if len(combined) > 60 else "")
            item = QListWidgetItem(f"區塊 {i+1}：{preview}")
            item.setData(Qt.ItemDataRole.UserRole, i)
            self._block_list.addItem(item)

    def _on_block_selected(self, row: int):
        if row < 0 or row >= len(self._blocks):
            return
        self._selected_block = self._blocks[row]
        combined = " ".join(s.text for s in self._selected_block.spans)
        self._text_edit.setPlainText(combined)
        self._apply_btn.setEnabled(True)

    def _apply_reflow(self):
        if self._selected_block is None:
            return
        new_text = self._text_edit.toPlainText()
        if not new_text.strip():
            QMessageBox.warning(self, "提示", "文字內容不可為空")
            return

        from core.text_reflow_engine import TextReflowEngine
        engine = TextReflowEngine()
        try:
            with self._doc.edit_transaction("文字重排"):
                page = self._doc.fitz_doc[self._page_num]
                new_block = engine.reflow(self._selected_block, new_text)
                engine.apply_edit(page, self._selected_block, new_block)
        except Exception as exc:
            QMessageBox.warning(self, "重排未完成", str(exc))
            return

        QMessageBox.information(self, "完成", "文字重排已套用。")
        self._load_page(self._page_num)
        self.accept()
