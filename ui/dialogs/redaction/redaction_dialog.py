# ~/Desktop/acropdf/ui/dialogs/redaction/redaction_dialog.py
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QCheckBox, QProgressBar, QMessageBox, QGroupBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from core.redaction_engine import RedactionEngine


class _WorkerThread(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(int)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        count = self._fn(self.progress.emit)
        self.finished.emit(count)


class RedactionDialog(QDialog):
    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc = doc
        self._engine = RedactionEngine(doc)
        self.setWindowTitle("密文塗銷工具")
        self.resize(560, 480)
        self._setup_ui()

    # ── UI ────────────────────────────────────────────────────────
    def _setup_ui(self):
        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._build_manual_tab(), "手動標記")
        tabs.addTab(self._build_search_tab(), "搜尋塗黑")
        tabs.addTab(self._build_pattern_tab(), "模式塗黑")
        layout.addWidget(tabs)

        # 底部操作列
        bottom = QHBoxLayout()
        self._count_label = QLabel("目前塗黑標記：0")
        self._refresh_count()
        bottom.addWidget(self._count_label)
        bottom.addStretch()

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.hide()
        bottom.addWidget(self._progress)

        apply_btn = QPushButton("套用所有塗黑（不可逆）")
        apply_btn.clicked.connect(self._apply_all)
        bottom.addWidget(apply_btn)

        close_btn = QPushButton("關閉")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)

        layout.addLayout(bottom)

    def _build_manual_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel(
            "在主視窗中，切換到「塗黑」工具模式，直接在頁面上拖曳選取要塗黑的區域。\n"
            "選取後區域會顯示紅框，點擊「套用所有塗黑」後永久移除內容。"
        ))
        layout.addStretch()
        refresh_btn = QPushButton("重新整理計數")
        refresh_btn.clicked.connect(self._refresh_count)
        layout.addWidget(refresh_btn)
        return w

    def _build_search_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        row = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("輸入要塗黑的文字...")
        self._search_input.returnPressed.connect(self._search_mark)
        row.addWidget(self._search_input)
        search_btn = QPushButton("搜尋並標記")
        search_btn.clicked.connect(self._search_mark)
        row.addWidget(search_btn)
        layout.addLayout(row)

        self._search_results = QListWidget()
        layout.addWidget(self._search_results)
        return w

    def _build_pattern_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("選擇要自動掃描並標記的個資類型："))

        box = QGroupBox()
        box_layout = QVBoxLayout(box)
        self._pattern_checks: dict[str, QCheckBox] = {}
        for name in RedactionEngine.PATTERNS:
            cb = QCheckBox(name)
            box_layout.addWidget(cb)
            self._pattern_checks[name] = cb
        layout.addWidget(box)

        scan_btn = QPushButton("掃描並標記")
        scan_btn.clicked.connect(self._pattern_mark)
        layout.addWidget(scan_btn)

        self._pattern_results = QListWidget()
        layout.addWidget(self._pattern_results)
        return w

    # ── 邏輯 ─────────────────────────────────────────────────────
    def _refresh_count(self):
        n = self._engine.get_redact_count()
        self._count_label.setText(f"目前塗黑標記：{n}")

    def _search_mark(self):
        text = self._search_input.text().strip()
        if not text:
            return
        self._search_results.clear()
        results = self._engine.search_and_mark(text)
        for r in results:
            self._search_results.addItem(f"第 {r['page']+1} 頁：{r['text']}")
        self._refresh_count()

    def _pattern_mark(self):
        self._pattern_results.clear()
        for name, cb in self._pattern_checks.items():
            if not cb.isChecked():
                continue
            pattern = RedactionEngine.PATTERNS[name]
            results = self._engine.pattern_mark(pattern)
            for r in results:
                self._pattern_results.addItem(
                    f"[{name}] 第 {r['page']+1} 頁：{r['text']}"
                )
        self._refresh_count()

    def _apply_all(self):
        n = self._engine.get_redact_count()
        if n == 0:
            QMessageBox.information(self, "塗黑", "目前沒有待套用的塗黑標記。")
            return
        ans = QMessageBox.warning(
            self, "確認套用",
            f"即將永久移除 {n} 個塗黑區域的內容，此操作不可復原。\n\n確定要繼續？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return

        self._progress.show()
        applied = self._engine.apply_all()
        self._progress.hide()
        self._refresh_count()
        QMessageBox.information(self, "完成", f"已成功套用 {applied} 個塗黑。")
