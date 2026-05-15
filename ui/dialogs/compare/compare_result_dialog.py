# ~/Desktop/acropdf/ui/dialogs/compare/compare_result_dialog.py
from __future__ import annotations

import fitz
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSplitter, QTextEdit, QWidget,
    QSpinBox, QScrollArea, QFileDialog, QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QPainter, QColor, QImage


def _fitz_page_to_qpixmap(page: fitz.Page, zoom: float = 1.5) -> QPixmap:
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(img)


def _overlay_rects(base_pixmap: QPixmap, rects: list[fitz.Rect],
                   color: QColor, zoom: float = 1.5) -> QPixmap:
    result = QPixmap(base_pixmap)
    painter = QPainter(result)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    color.setAlpha(80)
    painter.setBrush(color)
    painter.setPen(Qt.PenStyle.NoPen)
    for rect in rects:
        x0 = int(rect.x0 * zoom)
        y0 = int(rect.y0 * zoom)
        x1 = int(rect.x1 * zoom)
        y1 = int(rect.y1 * zoom)
        painter.drawRect(x0, y0, x1 - x0, y1 - y0)
    painter.end()
    return result


class CompareResultDialog(QDialog):
    def __init__(self, path_a: str, path_b: str, results: dict, parent=None):
        super().__init__(parent)
        self._path_a = path_a
        self._path_b = path_b
        self._results = results
        self._page_diffs = results.get("page_diffs", [])
        self._diff_nav: list[int] = []  # 有差異的頁碼列表
        self._nav_idx = 0
        self._zoom = 1.5

        self.setWindowTitle("PDF 比較結果")
        self.resize(1000, 720)
        self._setup_ui()

        # 找出有差異的頁面
        for diff in self._page_diffs:
            if diff.visual_rects or diff.text_added or diff.text_removed:
                self._diff_nav.append(diff.page_num)

        self._show_page(self._diff_nav[0] if self._diff_nav else 0)

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 上方：並排頁面
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左側
        left_w = QWidget()
        left_l = QVBoxLayout(left_w)
        left_l.addWidget(QLabel("文件 A（原始）"))
        self._scroll_a = QScrollArea()
        self._lbl_a = QLabel()
        self._lbl_a.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._scroll_a.setWidget(self._lbl_a)
        self._scroll_a.setWidgetResizable(True)
        left_l.addWidget(self._scroll_a)
        splitter.addWidget(left_w)

        # 右側
        right_w = QWidget()
        right_l = QVBoxLayout(right_w)
        right_l.addWidget(QLabel("文件 B（修訂）"))
        self._scroll_b = QScrollArea()
        self._lbl_b = QLabel()
        self._lbl_b.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._scroll_b.setWidget(self._lbl_b)
        self._scroll_b.setWidgetResizable(True)
        right_l.addWidget(self._scroll_b)
        splitter.addWidget(right_w)

        layout.addWidget(splitter, stretch=3)

        # 文字 diff 區
        self._diff_text = QTextEdit()
        self._diff_text.setReadOnly(True)
        self._diff_text.setMaximumHeight(150)
        layout.addWidget(self._diff_text, stretch=1)

        # 下方工具列
        nav_bar = QHBoxLayout()
        prev_btn = QPushButton("← 上一個差異")
        prev_btn.clicked.connect(self._prev_diff)
        nav_bar.addWidget(prev_btn)

        next_btn = QPushButton("下一個差異 →")
        next_btn.clicked.connect(self._next_diff)
        nav_bar.addWidget(next_btn)

        nav_bar.addWidget(QLabel("跳至頁面："))
        self._page_spin = QSpinBox()
        self._page_spin.setMinimum(1)
        self._page_spin.setMaximum(max(len(self._page_diffs), 1))
        self._page_spin.valueChanged.connect(lambda v: self._show_page(v - 1))
        nav_bar.addWidget(self._page_spin)

        self._diff_count_lbl = QLabel()
        nav_bar.addWidget(self._diff_count_lbl)
        nav_bar.addStretch()

        export_btn = QPushButton("匯出比較報告...")
        export_btn.clicked.connect(self._export_report)
        nav_bar.addWidget(export_btn)

        close_btn = QPushButton("關閉")
        close_btn.clicked.connect(self.accept)
        nav_bar.addWidget(close_btn)

        layout.addLayout(nav_bar)

    def _show_page(self, page_num: int):
        if page_num < 0:
            return
        self._page_spin.setValue(page_num + 1)

        try:
            doc_a = fitz.open(self._path_a)
            doc_b = fitz.open(self._path_b)
        except Exception:
            return

        diff = next((d for d in self._page_diffs if d.page_num == page_num), None)

        # 渲染 A
        if page_num < doc_a.page_count:
            pix_a = _fitz_page_to_qpixmap(doc_a[page_num], self._zoom)
            if diff and diff.visual_rects:
                pix_a = _overlay_rects(pix_a, diff.visual_rects,
                                       QColor(255, 0, 0), self._zoom)
            self._lbl_a.setPixmap(pix_a)
            self._lbl_a.resize(pix_a.size())

        # 渲染 B
        if page_num < doc_b.page_count:
            pix_b = _fitz_page_to_qpixmap(doc_b[page_num], self._zoom)
            if diff and diff.visual_rects:
                pix_b = _overlay_rects(pix_b, diff.visual_rects,
                                       QColor(0, 180, 0), self._zoom)
            self._lbl_b.setPixmap(pix_b)
            self._lbl_b.resize(pix_b.size())

        doc_a.close()
        doc_b.close()

        # 文字 diff
        if diff:
            html_lines = []
            for line in diff.text_removed:
                html_lines.append(
                    f'<span style="background:#ffd7d7;color:#c00;">- {line}</span>'
                )
            for line in diff.text_added:
                html_lines.append(
                    f'<span style="background:#d7ffd7;color:#060;">+ {line}</span>'
                )
            self._diff_text.setHtml("<br>".join(html_lines) if html_lines else "（此頁無文字差異）")
        else:
            self._diff_text.setPlainText("（此頁無差異）")

        # 統計
        total_diff = self._results.get("pages_with_diff", 0)
        self._diff_count_lbl.setText(f"共 {total_diff} 頁有差異")

    def _prev_diff(self):
        if not self._diff_nav:
            return
        self._nav_idx = (self._nav_idx - 1) % len(self._diff_nav)
        self._show_page(self._diff_nav[self._nav_idx])

    def _next_diff(self):
        if not self._diff_nav:
            return
        self._nav_idx = (self._nav_idx + 1) % len(self._diff_nav)
        self._show_page(self._diff_nav[self._nav_idx])

    def _export_report(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "匯出比較報告", "compare_report.pdf", "PDF (*.pdf)"
        )
        if not path:
            return
        try:
            from core.compare_engine import CompareEngine
            engine = CompareEngine()
            engine.generate_diff_report(
                self._path_a, self._path_b, path, self._results
            )
            QMessageBox.information(self, "完成", f"報告已儲存至：{path}")
        except Exception as e:
            QMessageBox.critical(self, "匯出失敗", str(e))
