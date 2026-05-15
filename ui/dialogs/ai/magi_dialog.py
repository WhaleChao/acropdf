# ~/Desktop/acropdf/ui/dialogs/ai/magi_dialog.py
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QTabWidget, QWidget,
    QLineEdit, QFormLayout, QMessageBox, QGroupBox,
    QListWidget, QListWidgetItem,
)
from PyQt6.QtCore import Qt


class MAGIDialog(QDialog):
    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc = doc
        self.setWindowTitle("MAGI 智慧助理")
        self.resize(680, 560)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        tabs = QTabWidget()

        tabs.addTab(self._build_classify_tab(), "文件分類")
        tabs.addTab(self._build_info_tab(), "關鍵資訊")
        tabs.addTab(self._build_naming_tab(), "智慧命名")
        tabs.addTab(self._build_legal_tab(), "法律分析")
        layout.addWidget(tabs)

        close_btn = QPushButton("關閉")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def _build_classify_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("點擊「分析」讓 MAGI 判斷文件類型："))
        run_btn = QPushButton("分析文件")
        run_btn.clicked.connect(self._classify)
        layout.addWidget(run_btn)
        self._classify_result = QTextEdit()
        self._classify_result.setReadOnly(True)
        layout.addWidget(self._classify_result)
        return w

    def _build_info_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("點擊「擷取」取得結構化資訊（當事人、日期、案號、金額）："))
        run_btn = QPushButton("擷取關鍵資訊")
        run_btn.clicked.connect(self._extract_info)
        layout.addWidget(run_btn)
        self._info_result = QTextEdit()
        self._info_result.setReadOnly(True)
        layout.addWidget(self._info_result)
        return w

    def _build_naming_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("MAGI 將根據文件內容產生建議檔名："))
        run_btn = QPushButton("產生建議檔名")
        run_btn.clicked.connect(self._suggest_name)
        layout.addWidget(run_btn)
        self._name_result = QLineEdit()
        self._name_result.setReadOnly(True)
        layout.addWidget(self._name_result)
        copy_btn = QPushButton("複製檔名")
        copy_btn.clicked.connect(lambda: self._copy_to_clipboard(self._name_result.text()))
        layout.addWidget(copy_btn)
        layout.addStretch()
        return w

    def _build_legal_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("偵測文件中引用的臺灣法條："))
        run_btn = QPushButton("分析法條")
        run_btn.clicked.connect(self._legal_analysis)
        layout.addWidget(run_btn)
        self._legal_result = QTextEdit()
        self._legal_result.setReadOnly(True)
        layout.addWidget(self._legal_result)
        return w

    def _classify(self):
        try:
            doc_type = self._doc.magi.smart_classify(self._doc)
            self._classify_result.setPlainText(f"文件類型：{doc_type}")
        except Exception as e:
            QMessageBox.critical(self, "錯誤", str(e))

    def _extract_info(self):
        try:
            doc_type = self._doc.magi.smart_classify(self._doc)
            info = self._doc.magi.extract_key_info(self._doc, doc_type)
            lines = [f"文件類型：{info.get('doc_type', '')}"]
            for key, val in info.items():
                if key != "doc_type" and val:
                    lines.append(f"{key}：{', '.join(str(v) for v in val)}")
            self._info_result.setPlainText("\n".join(lines))
        except Exception as e:
            QMessageBox.critical(self, "錯誤", str(e))

    def _suggest_name(self):
        try:
            name = self._doc.magi.suggest_filename(self._doc)
            self._name_result.setText(name)
        except Exception as e:
            QMessageBox.critical(self, "錯誤", str(e))

    def _legal_analysis(self):
        try:
            result = self._doc.magi.legal_analysis(self._doc)
            self._legal_result.setPlainText(result)
        except Exception as e:
            QMessageBox.critical(self, "錯誤", str(e))

    def _copy_to_clipboard(self, text: str):
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)
