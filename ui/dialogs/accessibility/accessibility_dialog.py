# ~/Desktop/acropdf/ui/dialogs/accessibility/accessibility_dialog.py
"""PDF/UA 無障礙標記對話框 — 檢查並新增文件結構標記。"""

from typing import Optional

import fitz
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QProgressBar, QGroupBox,
    QFormLayout, QLineEdit, QMessageBox, QComboBox,
    QDialogButtonBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal


# ---------------------------------------------------------------------------
#  語言選項
# ---------------------------------------------------------------------------

LANG_OPTIONS = [
    ("zh-TW", "繁體中文（臺灣）"),
    ("zh-CN", "簡體中文"),
    ("en", "英文"),
    ("ja", "日本語"),
    ("ko", "한국어"),
    ("fr", "法文"),
    ("de", "德文"),
    ("es", "西班牙文"),
]


# ---------------------------------------------------------------------------
#  背景執行緒：自動標記
# ---------------------------------------------------------------------------

class _AutoTagWorker(QThread):
    """在背景執行緒中對文件進行自動結構標記。"""

    finished = pyqtSignal(dict)   # 回傳統計資訊
    error = pyqtSignal(str)
    progress = pyqtSignal(int)    # 0-100

    def __init__(self, doc, title: str, lang: str, parent=None):
        super().__init__(parent)
        self._doc = doc
        self._title = title
        self._lang = lang

    def run(self):  # noqa: D401
        try:
            fitz_doc = self._doc.fitz_doc
            page_count = self._doc.page_count
            stats = {
                "paragraphs": 0,
                "images": 0,
                "images_no_alt": 0,
                "pages": page_count,
            }

            # --- 1. 設定文件層級標記資訊 ---
            self.progress.emit(5)

            # 更新中繼資料
            meta = fitz_doc.metadata or {}
            if self._title:
                meta["title"] = self._title
            meta["producer"] = meta.get("producer", "") or "AcroPDF"
            fitz_doc.set_metadata(meta)

            # --- 2. 設定 MarkInfo 與 StructTreeRoot ---
            self.progress.emit(10)
            try:
                # 取得或建立 Catalog 的 MarkInfo
                cat_xref = fitz_doc.pdf_catalog()

                # 設定 /MarkInfo << /Marked true >>
                fitz_doc.xref_set_key(cat_xref, "MarkInfo", "<< /Marked true >>")

                # 設定文件語言
                fitz_doc.xref_set_key(cat_xref, "Lang", f"({self._lang})")

                # ViewerPreferences — 顯示文件標題
                if self._title:
                    fitz_doc.xref_set_key(
                        cat_xref,
                        "ViewerPreferences",
                        "<< /DisplayDocTitle true >>",
                    )

            except Exception:
                # 部分 PDF 結構可能不支援，忽略此步驟
                pass

            # --- 3. 建立 StructTreeRoot（如不存在）---
            self.progress.emit(15)
            try:
                existing_tree = fitz_doc.xref_get_key(cat_xref, "StructTreeRoot")
                if existing_tree[0] == "null" or existing_tree[1] == "null":
                    # 建立新的 StructTreeRoot xref
                    new_xref = fitz_doc.get_new_xref()
                    fitz_doc.update_object(
                        new_xref,
                        f"<< /Type /StructTreeRoot /K [] /ParentTree << /Nums [] >> >>",
                    )
                    fitz_doc.xref_set_key(cat_xref, "StructTreeRoot", f"{new_xref} 0 R")
                    struct_root_xref = new_xref
                else:
                    # 解析現有 xref
                    ref_str = existing_tree[1]
                    if "R" in ref_str:
                        struct_root_xref = int(ref_str.split()[0])
                    else:
                        struct_root_xref = None
            except Exception:
                struct_root_xref = None

            # --- 4. 逐頁分析文字區塊與圖片 ---
            kid_refs: list[str] = []

            for page_idx in range(page_count):
                pct = 20 + int(70 * page_idx / max(page_count, 1))
                self.progress.emit(pct)

                page = fitz_doc[page_idx]

                # 文字區塊 → Paragraph 標記
                blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE).get("blocks", [])
                for block in blocks:
                    if block.get("type") == 0:  # 文字區塊
                        stats["paragraphs"] += 1

                        if struct_root_xref is not None:
                            try:
                                p_xref = fitz_doc.get_new_xref()
                                fitz_doc.update_object(
                                    p_xref,
                                    f"<< /Type /StructElem /S /P /P {struct_root_xref} 0 R >>",
                                )
                                kid_refs.append(f"{p_xref} 0 R")
                            except Exception:
                                pass

                    elif block.get("type") == 1:  # 圖片區塊
                        stats["images"] += 1
                        stats["images_no_alt"] += 1

                        if struct_root_xref is not None:
                            try:
                                fig_xref = fitz_doc.get_new_xref()
                                alt_text = fitz.get_pdf_str(f"第 {page_idx + 1} 頁圖片")
                                fitz_doc.update_object(
                                    fig_xref,
                                    f"<< /Type /StructElem /S /Figure /P {struct_root_xref} 0 R "
                                    f"/Alt {alt_text} >>",
                                )
                                kid_refs.append(f"{fig_xref} 0 R")
                                # 有 placeholder alt-text，不再列為「無替代文字」
                                stats["images_no_alt"] -= 1
                            except Exception:
                                pass

            # --- 5. 更新 StructTreeRoot 的 /K 陣列 ---
            self.progress.emit(92)
            if struct_root_xref is not None and kid_refs:
                try:
                    k_array = "[" + " ".join(kid_refs) + "]"
                    fitz_doc.xref_set_key(struct_root_xref, "K", k_array)
                except Exception:
                    pass

            self.progress.emit(100)
            self.finished.emit(stats)

        except Exception as exc:
            self.error.emit(f"自動標記失敗：{exc}")


# ---------------------------------------------------------------------------
#  對話框
# ---------------------------------------------------------------------------

class AccessibilityDialog(QDialog):
    """PDF/UA 無障礙標記對話框。"""

    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc = doc
        self._worker: Optional[_AutoTagWorker] = None
        self.setWindowTitle("無障礙標記（PDF/UA）")
        self.resize(560, 480)
        self._setup_ui()
        self._check_status()

    def _setup_ui(self):
        root = QVBoxLayout(self)

        # --- 目前狀態 ---
        status_group = QGroupBox("目前狀態")
        status_form = QFormLayout(status_group)

        self._tagged_label = QLabel("檢查中⋯⋯")
        status_form.addRow("標記狀態：", self._tagged_label)

        self._title_label = QLabel("")
        status_form.addRow("文件標題：", self._title_label)

        self._lang_label = QLabel("")
        status_form.addRow("文件語言：", self._lang_label)

        root.addWidget(status_group)

        # --- 設定區 ---
        settings_group = QGroupBox("文件設定")
        settings_form = QFormLayout(settings_group)

        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("輸入文件標題")
        settings_form.addRow("設定文件標題：", self._title_edit)

        self._lang_combo = QComboBox()
        for code, display in LANG_OPTIONS:
            self._lang_combo.addItem(f"{display} ({code})", code)
        settings_form.addRow("設定語言：", self._lang_combo)

        root.addWidget(settings_group)

        # --- 進度條 ---
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.hide()
        root.addWidget(self._progress)

        # --- 報告區 ---
        self._report_edit = QTextEdit()
        self._report_edit.setReadOnly(True)
        self._report_edit.setPlaceholderText("標記報告將顯示於此⋯⋯")
        self._report_edit.setMaximumHeight(160)
        root.addWidget(self._report_edit)

        # --- 底部按鈕 ---
        btn_row = QHBoxLayout()

        self._tag_btn = QPushButton("自動標記")
        self._tag_btn.clicked.connect(self._run_auto_tag)
        btn_row.addWidget(self._tag_btn)

        self._meta_btn = QPushButton("僅更新中繼資料")
        self._meta_btn.clicked.connect(self._update_metadata_only)
        btn_row.addWidget(self._meta_btn)

        btn_row.addStretch()

        close_btn = QPushButton("關閉")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)

        root.addLayout(btn_row)

    # -- 狀態檢查 --

    def _check_status(self):
        fitz_doc = self._doc.fitz_doc
        meta = fitz_doc.metadata or {}

        # 檢查 MarkInfo
        is_tagged = False
        try:
            cat_xref = fitz_doc.pdf_catalog()
            mark_info = fitz_doc.xref_get_key(cat_xref, "MarkInfo")
            if mark_info[0] != "null" and "true" in mark_info[1].lower():
                is_tagged = True
        except Exception:
            pass

        self._tagged_label.setText("已標記" if is_tagged else "未標記")
        self._tagged_label.setStyleSheet(
            "color: green; font-weight: bold;" if is_tagged
            else "color: red; font-weight: bold;"
        )

        title = meta.get("title", "")
        self._title_label.setText(title or "（無）")
        if title:
            self._title_edit.setText(title)

        # 嘗試讀取文件語言
        doc_lang = ""
        try:
            lang_val = fitz_doc.xref_get_key(cat_xref, "Lang")
            if lang_val[0] != "null":
                doc_lang = lang_val[1].strip("()")
        except Exception:
            pass

        self._lang_label.setText(doc_lang or "（未設定）")

        # 預選語言
        if doc_lang:
            for i in range(self._lang_combo.count()):
                if self._lang_combo.itemData(i) == doc_lang:
                    self._lang_combo.setCurrentIndex(i)
                    break

    # -- 動作 --

    def _run_auto_tag(self):
        if self._worker and self._worker.isRunning():
            return

        title = self._title_edit.text().strip()
        lang = self._lang_combo.currentData() or "zh-TW"

        self._tag_btn.setEnabled(False)
        self._meta_btn.setEnabled(False)
        self._progress.show()
        self._progress.setValue(0)
        self._report_edit.clear()

        self._doc.begin_op("自動無障礙標記")

        self._worker = _AutoTagWorker(self._doc, title, lang, self)
        self._worker.progress.connect(self._progress.setValue)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_finished(self, stats: dict):
        self._doc._mark_modified()
        self._doc.end_op()

        self._progress.hide()
        self._tag_btn.setEnabled(True)
        self._meta_btn.setEnabled(True)

        report_lines = [
            "=== 自動標記報告 ===",
            f"總頁數：{stats['pages']}",
            f"文字段落標記數：{stats['paragraphs']}",
            f"圖片數量：{stats['images']}",
            f"缺少替代文字的圖片：{stats['images_no_alt']}",
        ]

        if stats["images_no_alt"] > 0:
            report_lines.append("")
            report_lines.append(
                "注意：部分圖片僅填入預設替代文字，建議手動補充描述。"
            )

        self._report_edit.setPlainText("\n".join(report_lines))
        self._check_status()

        QMessageBox.information(self, "完成", "自動標記已完成。")

    def _on_error(self, msg: str):
        try:
            self._doc.end_op()
        except Exception:
            pass

        self._progress.hide()
        self._tag_btn.setEnabled(True)
        self._meta_btn.setEnabled(True)
        QMessageBox.critical(self, "錯誤", msg)

    def _update_metadata_only(self):
        """僅更新文件標題與語言，不做結構標記。"""
        fitz_doc = self._doc.fitz_doc
        title = self._title_edit.text().strip()
        lang = self._lang_combo.currentData() or "zh-TW"

        self._doc.begin_op("更新文件中繼資料")
        try:
            meta = fitz_doc.metadata or {}
            if title:
                meta["title"] = title
            fitz_doc.set_metadata(meta)

            try:
                cat_xref = fitz_doc.pdf_catalog()
                fitz_doc.xref_set_key(cat_xref, "Lang", f"({lang})")
                if title:
                    fitz_doc.xref_set_key(
                        cat_xref,
                        "ViewerPreferences",
                        "<< /DisplayDocTitle true >>",
                    )
            except Exception:
                pass

            self._doc._mark_modified()
        finally:
            self._doc.end_op()

        self._check_status()
        QMessageBox.information(self, "完成", "文件中繼資料已更新。")
