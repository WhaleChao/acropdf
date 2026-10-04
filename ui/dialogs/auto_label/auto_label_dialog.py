# ~/Desktop/acropdf/ui/dialogs/auto_label/auto_label_dialog.py
"""
自動標籤對話框。

功能：
  - 三種偵測策略選擇（目錄 / 文字層 / AI Gemma 4）
  - 偵測後以表格預覽文件邊界，可手動修改標題
  - 可設定樣式：橫幅 / 角落；顏色、字體大小
  - 套用前顯示數量確認
  - MarkItDown 選項（需安裝 markitdown）
"""
from __future__ import annotations

import threading
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QComboBox, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QProgressBar,
    QGroupBox, QDialogButtonBox, QAbstractItemView,
    QColorDialog, QSpinBox, QMessageBox, QCheckBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread
from PyQt6.QtGui import QColor, QPalette

from core.auto_label_engine import AutoLabelEngine, DocBoundary


# ────────────────────────────── Worker ───────────────────────────────

class _DetectSignals(QObject):
    progress  = pyqtSignal(int, int)
    result    = pyqtSignal(list)
    error     = pyqtSignal(str)


class _DetectWorker(QThread):
    def __init__(self, doc, strategy: str, signals: _DetectSignals):
        super().__init__()
        self._doc      = doc
        self._strategy = strategy
        self.signals   = signals
        self._keep     = signals

    def run(self):
        try:
            boundaries = AutoLabelEngine.detect(
                self._doc,
                strategy=self._strategy,
                on_progress=lambda c, t: self.signals.progress.emit(c, t),
            )
            self.signals.result.emit(boundaries)
        except Exception as e:
            import traceback; traceback.print_exc()
            self.signals.error.emit(str(e))


# ────────────────────────────── Dialog ───────────────────────────────

from ui.widgets.worker_dialog import WorkerDialog


class AutoLabelDialog(WorkerDialog):
    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc        = doc
        self._boundaries: list[DocBoundary] = []
        self._bg_color   = AutoLabelEngine.LABEL_COLOR    # (r,g,b) 0-1
        self._text_color = AutoLabelEngine.TEXT_COLOR
        self._worker: Optional[_DetectWorker] = None

        self.setWindowTitle("自動標籤")
        self.resize(700, 560)
        self._setup_ui()
        self._check_markitdown()

    # ── UI 建構 ───────────────────────────────────────────────────
    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # ── 設定群組 ─────────────────────────────────────────────
        cfg_grp = QGroupBox("偵測設定")
        cfg_form = QFormLayout(cfg_grp)

        self._strategy_combo = QComboBox()
        self._strategy_combo.addItems([
            "自動選擇（建議）",
            "目錄 TOC（最快）",
            "文字層解析",
            "MarkItDown",
            "AI 辨識（Gemma 4）",
        ])
        cfg_form.addRow("偵測策略：", self._strategy_combo)

        self._style_combo = QComboBox()
        self._style_combo.addItems(["頁頂橫幅", "右上角標籤"])
        cfg_form.addRow("標籤樣式：", self._style_combo)

        # 字體大小
        self._font_spin = QSpinBox()
        self._font_spin.setRange(7, 20)
        self._font_spin.setValue(AutoLabelEngine.FONT_SIZE)
        cfg_form.addRow("字體大小（pt）：", self._font_spin)

        # 顏色選擇
        color_row = QHBoxLayout()
        self._bg_btn = QPushButton("選擇…")
        self._bg_btn.clicked.connect(self._pick_bg_color)
        self._bg_preview = QLabel("  ")
        self._bg_preview.setAutoFillBackground(True)
        self._refresh_color_preview()
        color_row.addWidget(self._bg_preview)
        color_row.addWidget(self._bg_btn)
        color_row.addStretch()
        cfg_form.addRow("橫幅背景色：", color_row)

        layout.addWidget(cfg_grp)

        # ── 偵測按鈕 + 進度條 ─────────────────────────────────────
        detect_row = QHBoxLayout()
        self._detect_btn = QPushButton("▶ 開始偵測")
        self._detect_btn.setDefault(True)
        self._detect_btn.clicked.connect(self._start_detect)
        detect_row.addWidget(self._detect_btn)

        self._progress = QProgressBar()
        self._progress.setValue(0)
        self._progress.setFormat("%v / %m 頁")
        detect_row.addWidget(self._progress, 1)
        layout.addLayout(detect_row)

        # ── 預覽表格 ──────────────────────────────────────────────
        hint = QLabel("偵測完成後可在「標籤名稱」欄雙擊修改；取消勾選可跳過該頁。")
        hint.setStyleSheet("color: #8e8e93; font-size: 11px;")
        layout.addWidget(hint)

        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["✓", "頁碼", "偵測策略", "標籤名稱"])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        layout.addWidget(self._table)

        # ── 底部按鈕 ──────────────────────────────────────────────
        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        from ui.dialogs._button_helper import make_ok_cancel_row
        row, ok_btn, cancel_btn = make_ok_cancel_row(self, ok_text="套用標籤", cancel_text="取消")
        ok_btn.setEnabled(False)
        ok_btn.clicked.connect(self._apply)
        cancel_btn.clicked.connect(self.reject)
        self._ok_btn = ok_btn
        layout.addLayout(row)

    def _check_markitdown(self):
        """若 markitdown 未安裝，在 combo 標記。"""
        try:
            import markitdown  # noqa
        except ImportError:
            idx = self._strategy_combo.findText("MarkItDown")
            self._strategy_combo.setItemText(idx, "MarkItDown（需 pip install markitdown）")

    # ── 顏色選擇 ──────────────────────────────────────────────────
    def _pick_bg_color(self):
        init = QColor(
            int(self._bg_color[0] * 255),
            int(self._bg_color[1] * 255),
            int(self._bg_color[2] * 255),
        )
        color = QColorDialog.getColor(init, self, "選擇橫幅背景色")
        if color.isValid():
            self._bg_color = (
                color.redF(), color.greenF(), color.blueF()
            )
            self._refresh_color_preview()

    def _refresh_color_preview(self):
        pal = self._bg_preview.palette()
        pal.setColor(
            QPalette.ColorRole.Window,
            QColor(
                int(self._bg_color[0] * 255),
                int(self._bg_color[1] * 255),
                int(self._bg_color[2] * 255),
            ),
        )
        self._bg_preview.setPalette(pal)

    # ── 偵測流程 ──────────────────────────────────────────────────
    def _start_detect(self):
        self._detect_btn.setEnabled(False)
        self._ok_btn.setEnabled(False)
        self._table.setRowCount(0)
        self._progress.setValue(0)
        self._progress.setMaximum(self._doc.page_count)
        self._status_label.setText("偵測中…")

        idx = self._strategy_combo.currentIndex()
        strategy_map = {
            0: "auto",
            1: "toc",
            2: "text",
            3: "markitdown",
            4: "ai",
        }
        strategy = strategy_map.get(idx, "auto")

        signals = _DetectSignals()
        signals.progress.connect(self._on_progress, Qt.ConnectionType.QueuedConnection)
        signals.result.connect(self._on_result, Qt.ConnectionType.QueuedConnection)
        signals.error.connect(self._on_error, Qt.ConnectionType.QueuedConnection)

        self._worker = _DetectWorker(self._doc, strategy, signals)
        self._worker.start()

    def _on_progress(self, current: int, total: int):
        self._progress.setMaximum(total)
        self._progress.setValue(current)
        self._status_label.setText(f"偵測中… {current}/{total} 頁")

    def _on_result(self, boundaries: list):
        self._boundaries = boundaries
        self._populate_table(boundaries)
        n = len(boundaries)
        self._status_label.setText(f"共偵測到 {n} 個文件邊界。")
        self._ok_btn.setEnabled(n > 0)
        self._detect_btn.setEnabled(True)
        self._progress.setValue(self._progress.maximum())

    def _on_error(self, msg: str):
        self._status_label.setText(f"❌ 偵測失敗：{msg}")
        self._detect_btn.setEnabled(True)

    def _populate_table(self, boundaries: list[DocBoundary]):
        self._table.setRowCount(len(boundaries))
        strategy_label = {
            "toc": "目錄 TOC",
            "text": "文字層",
            "markitdown": "MarkItDown",
            "ai": "AI Gemma 4",
        }
        for row, b in enumerate(boundaries):
            # 勾選框
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Checked)
            chk.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 0, chk)

            # 頁碼（1-based）
            pg_item = QTableWidgetItem(str(b.page_num + 1))
            pg_item.setFlags(pg_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            pg_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 1, pg_item)

            # 策略
            st_item = QTableWidgetItem(strategy_label.get(b.strategy, b.strategy))
            st_item.setFlags(st_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            st_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            # 信心度低的標黃
            if b.confidence < 0.6:
                st_item.setBackground(QColor("#fff3cd"))
            self._table.setItem(row, 2, st_item)

            # 標籤名稱（可編輯）
            title_item = QTableWidgetItem(b.title)
            self._table.setItem(row, 3, title_item)

    # ── 套用 ──────────────────────────────────────────────────────
    def _collect_checked(self) -> list[DocBoundary]:
        result = []
        for row in range(self._table.rowCount()):
            chk = self._table.item(row, 0)
            if not chk or chk.checkState() != Qt.CheckState.Checked:
                continue
            title_item = self._table.item(row, 3)
            if row < len(self._boundaries):
                b = self._boundaries[row]
                title = title_item.text().strip() if title_item else b.title
                result.append(DocBoundary(
                    page_num=b.page_num,
                    title=title,
                    strategy=b.strategy,
                    confidence=b.confidence,
                ))
        return result

    def _apply(self):
        checked = self._collect_checked()
        if not checked:
            QMessageBox.warning(self, "無選取", "請至少勾選一個文件邊界。")
            return

        style = "banner" if self._style_combo.currentIndex() == 0 else "corner"

        AutoLabelEngine.apply_labels(
            self._doc,
            checked,
            style=style,
            bg_color=self._bg_color,
            text_color=self._text_color,
            font_size=self._font_spin.value(),
        )

        QMessageBox.information(
            self, "完成",
            f"已為 {len(checked)} 個文件首頁加上標籤。\n"
            "請儲存 PDF 以保留變更。",
        )
        self.accept()
