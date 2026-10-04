# ~/Desktop/acropdf/ui/widgets/search_bar.py
"""搜尋列元件 — macOS 風格的嵌入式搜尋列。"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLineEdit, QPushButton, QLabel,
)
from PyQt6.QtCore import pyqtSignal, Qt, QEvent
from PyQt6.QtGui import QKeySequence, QShortcut


class SearchBar(QWidget):
    """macOS 風格搜尋列，顯示於文件區上方。"""

    search_requested = pyqtSignal(str)
    next_requested = pyqtSignal()
    prev_requested = pyqtSignal()
    closed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("searchBar")
        self.setFixedHeight(46)
        # 不設 inline stylesheet — 由 QSS 主題檔控制

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(4)

        # 搜尋輸入框
        self._input = QLineEdit()
        self._input.setPlaceholderText("搜尋…")
        self._input.setClearButtonEnabled(True)
        self._input.returnPressed.connect(self._on_return)
        self._input.installEventFilter(self)
        self._input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._input)

        # 結果計數
        self._count_label = QLabel()
        self._count_label.setMinimumWidth(56)
        self._count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._count_label)

        # 上一個 / 下一個（使用符號按鈕）
        self._prev_btn = QPushButton("▲")
        self._prev_btn.setFixedSize(26, 26)
        self._prev_btn.setToolTip("上一筆 (Shift+Enter)")
        self._prev_btn.clicked.connect(self.prev_requested)
        layout.addWidget(self._prev_btn)

        self._next_btn = QPushButton("▼")
        self._next_btn.setFixedSize(26, 26)
        self._next_btn.setToolTip("下一筆 (Enter)")
        self._next_btn.clicked.connect(self.next_requested)
        layout.addWidget(self._next_btn)

        # 關閉
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(26, 26)
        close_btn.setToolTip("關閉 (Esc)")
        close_btn.clicked.connect(self._on_close)
        layout.addWidget(close_btn)

        layout.addStretch()

        # Escape 與 Shift+Enter 快捷鍵
        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        esc.activated.connect(self._on_close)

        self._input.setAccessibleName("搜尋文件文字")
        self._prev_btn.setAccessibleName("上一筆搜尋結果")
        self._next_btn.setAccessibleName("下一筆搜尋結果")
        self.hide()

    def eventFilter(self, watched, event):
        if watched is self._input and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.prev_requested.emit()
                return True
        return super().eventFilter(watched, event)

    # ── public helpers ───────────────────────────────────────────
    def focus_input(self):
        self.show()
        self._input.setFocus()
        self._input.selectAll()

    def set_result_count(self, current: int, total: int):
        self._prev_btn.setEnabled(total > 0)
        self._next_btn.setEnabled(total > 0)
        if total == 0:
            if self._input.text():
                self._count_label.setText("無結果")
            else:
                self._count_label.setText("")
        else:
            self._count_label.setText(f"{current} / {total}")

    def clear_state(self):
        self._input.clear()
        self._count_label.setText("")

    # ── private slots ────────────────────────────────────────────
    def _on_return(self):
        text = self._input.text().strip()
        if text:
            self.next_requested.emit()

    def _on_text_changed(self, text: str):
        text = text.strip()
        self.search_requested.emit(text)
        if not text:
            self._count_label.setText("")

    def _on_close(self):
        self.hide()
        self.closed.emit()
