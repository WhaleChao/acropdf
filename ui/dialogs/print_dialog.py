from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtPrintSupport import QPrinterInfo
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)


@dataclass(frozen=True)
class PrintSettings:
    printer_name: str
    page_indices: list[int]
    copies: int
    output_pdf_path: str | None = None


class PrintDialog(QDialog):
    """AcroPDF 內建繁中列印對話框，避免系統面板語言退回英文。"""

    def __init__(self, page_count: int, current_page: int, parent=None, show_page_range: bool = True):
        super().__init__(parent)
        self._page_count = max(0, page_count)
        self._current_page = min(max(current_page, 0), max(self._page_count - 1, 0))
        self._show_page_range = show_page_range
        self._settings: PrintSettings | None = None

        self.setWindowTitle("列印")
        self.setMinimumWidth(460)
        self._setup_ui()

    def settings(self) -> PrintSettings:
        if self._settings is None:
            raise RuntimeError("尚未完成列印設定")
        return self._settings

    def _setup_ui(self):
        root = QVBoxLayout(self)

        printer_group = QGroupBox("印表機")
        printer_form = QFormLayout(printer_group)

        self._printer_combo = QComboBox()
        default_name = QPrinterInfo.defaultPrinterName()
        names = QPrinterInfo.availablePrinterNames()
        if names:
            self._printer_combo.addItems(names)
            if default_name in names:
                self._printer_combo.setCurrentText(default_name)
        else:
            self._printer_combo.addItem("未偵測到印表機")
            self._printer_combo.setEnabled(False)
        printer_form.addRow("印表機：", self._printer_combo)

        pdf_row = QHBoxLayout()
        self._pdf_check = QCheckBox("列印至 PDF 檔案")
        self._pdf_edit = QLineEdit()
        self._pdf_edit.setPlaceholderText("選擇輸出位置")
        self._pdf_edit.setEnabled(False)
        browse_btn = QPushButton("選擇…")
        browse_btn.setEnabled(False)
        browse_btn.clicked.connect(self._browse_pdf)
        self._pdf_check.toggled.connect(self._pdf_edit.setEnabled)
        self._pdf_check.toggled.connect(browse_btn.setEnabled)
        if not names:
            self._pdf_check.setChecked(True)
        pdf_row.addWidget(self._pdf_check)
        pdf_row.addWidget(self._pdf_edit, 1)
        pdf_row.addWidget(browse_btn)
        printer_form.addRow("輸出：", pdf_row)
        root.addWidget(printer_group)

        if self._show_page_range:
            page_group = QGroupBox("頁面")
            page_layout = QVBoxLayout(page_group)
            self._range_group = QButtonGroup(self)
            self._all_pages = QRadioButton(f"全部頁面（共 {self._page_count} 頁）")
            self._current = QRadioButton(f"目前頁面（第 {self._current_page + 1} 頁）")
            self._custom = QRadioButton("指定頁面")
            self._all_pages.setChecked(True)
            for btn in (self._all_pages, self._current, self._custom):
                self._range_group.addButton(btn)
                page_layout.addWidget(btn)

            range_row = QHBoxLayout()
            range_row.addSpacing(22)
            self._range_edit = QLineEdit()
            self._range_edit.setPlaceholderText("例如 1-3, 5, 8")
            self._range_edit.setEnabled(False)
            self._custom.toggled.connect(self._range_edit.setEnabled)
            range_row.addWidget(self._range_edit)
            page_layout.addLayout(range_row)
            root.addWidget(page_group)

        copy_group = QGroupBox("份數")
        copy_form = QFormLayout(copy_group)
        self._copies = QSpinBox()
        self._copies.setRange(1, 99)
        self._copies.setValue(1)
        self._copies.setAlignment(Qt.AlignmentFlag.AlignRight)
        copy_form.addRow("列印份數：", self._copies)
        root.addWidget(copy_group)

        root.addWidget(QLabel("頁面會依比例置中並符合可列印範圍。"))

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        print_btn = QPushButton("列印")
        print_btn.setDefault(True)
        cancel_btn = QPushButton("取消")
        print_btn.clicked.connect(self._accept_settings)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(print_btn)
        btn_row.addWidget(cancel_btn)
        root.addLayout(btn_row)

    def _browse_pdf(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "選擇 PDF 輸出位置", "", "PDF 檔案 (*.pdf)"
        )
        if path:
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
            self._pdf_edit.setText(path)

    def _accept_settings(self):
        output_pdf = self._pdf_edit.text().strip() if self._pdf_check.isChecked() else ""
        printer_name = self._printer_combo.currentText().strip() if self._printer_combo.isEnabled() else ""

        if output_pdf:
            if not output_pdf.lower().endswith(".pdf"):
                output_pdf += ".pdf"
            parent = Path(output_pdf).expanduser().parent
            if not parent.exists():
                QMessageBox.warning(self, "無法列印", "PDF 輸出資料夾不存在。")
                return
        elif not printer_name:
            QMessageBox.warning(self, "無法列印", "請選擇印表機或勾選列印至 PDF 檔案。")
            return

        try:
            pages = self._selected_pages()
        except ValueError as exc:
            QMessageBox.warning(self, "頁面範圍錯誤", str(exc))
            return

        self._settings = PrintSettings(
            printer_name=printer_name,
            page_indices=pages,
            copies=self._copies.value(),
            output_pdf_path=output_pdf or None,
        )
        self.accept()

    def _selected_pages(self) -> list[int]:
        if not self._show_page_range:
            return [0]
        if self._page_count <= 0:
            raise ValueError("文件沒有可列印的頁面。")
        if self._current.isChecked():
            return [self._current_page]
        if self._custom.isChecked():
            return _parse_page_ranges(self._range_edit.text(), self._page_count)
        return list(range(self._page_count))


def _parse_page_ranges(text: str, page_count: int) -> list[int]:
    text = text.strip().replace("，", ",")
    if not text:
        raise ValueError("請輸入頁面範圍，例如 1-3, 5。")

    pages: list[int] = []
    seen: set[int] = set()
    for part in (p.strip() for p in text.split(",")):
        if not part:
            continue
        if "-" in part:
            start_text, end_text = [p.strip() for p in part.split("-", 1)]
            if not start_text.isdigit() or not end_text.isdigit():
                raise ValueError("頁面範圍格式不正確。")
            start, end = int(start_text), int(end_text)
            if start > end:
                raise ValueError("頁面範圍起始頁不可大於結束頁。")
            nums = range(start, end + 1)
        else:
            if not part.isdigit():
                raise ValueError("頁面範圍只能包含頁碼、逗號與連字號。")
            nums = (int(part),)

        for num in nums:
            if num < 1 or num > page_count:
                raise ValueError(f"頁碼需介於 1 到 {page_count}。")
            idx = num - 1
            if idx not in seen:
                pages.append(idx)
                seen.add(idx)

    if not pages:
        raise ValueError("請輸入至少一個頁碼。")
    return pages
