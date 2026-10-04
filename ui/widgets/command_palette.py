"""Keyboard-first command navigation with document-aware availability."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QShortcut, QKeySequence
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QLabel


class CommandPalette(QDialog):
    def __init__(self, parent, commands):
        super().__init__(parent)
        self.setWindowTitle("快速指令")
        self.resize(540, 420)
        self._commands = commands
        layout = QVBoxLayout(self); layout.setContentsMargins(18, 18, 18, 18); layout.setSpacing(12)
        self._input = QLineEdit(); self._input.setObjectName("commandInput")
        self._input.setPlaceholderText("搜尋工具或動作…"); self._input.setAccessibleName("搜尋快速指令")
        self._input.textChanged.connect(self._filter); layout.addWidget(self._input)
        self._results = QListWidget(); self._results.setObjectName("commandResults")
        self._results.itemActivated.connect(self._activate); self._results.itemClicked.connect(self._activate)
        layout.addWidget(self._results)
        self._hint = QLabel("↑ ↓ 選擇   ·   Enter 執行   ·   Esc 關閉")
        self._hint.setProperty("role", "muted"); layout.addWidget(self._hint)
        self._input.returnPressed.connect(lambda: self._activate(self._results.currentItem()))
        for key, delta in (("Down", 1), ("Up", -1)):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda d=delta: self._move(d))
        self._filter("")
        self._input.setFocus()

    def _move(self, delta):
        count = self._results.count()
        if count: self._results.setCurrentRow((self._results.currentRow() + delta) % count)

    def _filter(self, query):
        self._results.clear()
        tokens = query.casefold().split()
        for index, (label, keywords, callback, enabled) in enumerate(self._commands):
            if not all(token in (label + " " + keywords).casefold() for token in tokens): continue
            item = QListWidgetItem(label + ("  ·  請先開啟文件" if not enabled else ""))
            item.setData(Qt.ItemDataRole.UserRole, index)
            if not enabled: item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self._results.addItem(item)
        for row in range(self._results.count()):
            if self._results.item(row).flags() & Qt.ItemFlag.ItemIsEnabled:
                self._results.setCurrentRow(row); break
        self._hint.setText("↑ ↓ 選擇   ·   Enter 執行   ·   Esc 關閉" if self._results.count() else "找不到指令，試試「匯出」或「OCR」。")

    def _activate(self, item):
        if not item or not item.flags() & Qt.ItemFlag.ItemIsEnabled: return
        callback = self._commands[item.data(Qt.ItemDataRole.UserRole)][2]
        self.accept()
        callback()
