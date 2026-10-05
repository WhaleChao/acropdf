# ~/Desktop/acropdf/ui/dialogs/accessibility/accessibility_dialog.py
"""基礎無障礙檢查及文件標題、語言設定；不宣告 PDF/UA 合規。"""

import fitz
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QProgressBar, QGroupBox,
    QFormLayout, QLineEdit, QMessageBox, QComboBox,
    QFileDialog, QAbstractItemView, QDialogButtonBox, QTableWidget, QTableWidgetItem, QHeaderView, QTreeWidget, QTreeWidgetItem, QInputDialog,
)
from PyQt6.QtCore import Qt


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


from ui.widgets.worker_dialog import WorkerDialog


class AccessibilityDialog(WorkerDialog):
    """PDF/UA 無障礙標記對話框。"""

    def __init__(self, doc, parent=None):
        super().__init__(parent)
        self._doc = doc
        self.setWindowTitle("無障礙內容標記與閱讀順序")
        self.resize(720, 700)
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
        self._image_alts = QTableWidget(0, 3)
        self._image_alts.setHorizontalHeaderLabels(["頁面", "圖片編號", "替代文字（描述圖片意義）"])
        self._image_alts.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        images = {}
        for page in self._doc.fitz_doc:
            for image in page.get_images(full=True): images.setdefault(image[0], []).append(str(page.number+1))
        for xref, pages in images.items():
            row = self._image_alts.rowCount(); self._image_alts.insertRow(row)
            for column, text in enumerate([", ".join(pages), str(xref), ""]):
                item = QTableWidgetItem(text)
                if column < 2: item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._image_alts.setItem(row, column, item)
        self._image_alts.setVisible(bool(images)); root.addWidget(self._image_alts)
        self._structure = QTreeWidget(); self._structure.setHeaderLabels(["閱讀結構", "頁面", "替代文字"])
        self._structure.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._structure.itemDoubleClicked.connect(self._edit_tag)
        root.addWidget(self._structure)
        order_row = QHBoxLayout()
        for text, delta in [("標記上移", -1), ("標記下移", 1)]:
            button = QPushButton(text); button.clicked.connect(lambda checked=False, d=delta: self._move_section(d)); order_row.addWidget(button)
        table_button = QPushButton("將所選文字標為表格"); table_button.clicked.connect(self._create_table); order_row.addWidget(table_button)
        hint = QLabel("雙擊文字標記可調整標題層級；圖片標記可編輯替代文字。閱讀順序和語意請逐頁人工審閱。")
        hint.setWordWrap(True); root.addLayout(order_row); root.addWidget(hint)

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

        self._tag_btn = QPushButton("建立內容標記")
        self._tag_btn.setToolTip("建立文字與圖片的 MCID 及 ParentTree；保留既有結構樹。")
        self._tag_btn.clicked.connect(self._run_auto_tag)
        btn_row.addWidget(self._tag_btn)

        self._meta_btn = QPushButton("僅更新中繼資料")
        self._meta_btn.clicked.connect(self._update_metadata_only)
        btn_row.addWidget(self._meta_btn)

        self._ua_btn = QPushButton("驗證並匯出 PDF/UA")
        self._ua_btn.clicked.connect(self._export_ua)
        btn_row.addWidget(self._ua_btn)
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

        from core.accessibility_engine import AccessibilityEngine
        tree = AccessibilityEngine().get_structure_tree(fitz_doc)
        self._tag_btn.setEnabled(tree is None)
        self._structure.clear()
        def populate(node, parent):
            item = QTreeWidgetItem([node.type, str(node.page+1), node.alt_text or ""])
            item.setData(0, Qt.ItemDataRole.UserRole, node.xref)
            parent.addChild(item) if isinstance(parent, QTreeWidgetItem) else parent.addTopLevelItem(item)
            for child in node.children: populate(child, item)
        if tree: populate(tree, self._structure)
        self._structure.expandToDepth(2)
        self._tagged_label.setText("有標記宣告（未驗證完整性）" if is_tagged else "未標記")
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

        from core.accessibility_engine import AccessibilityEngine
        issues = AccessibilityEngine().validate_pdfua(fitz_doc)
        self._report_edit.setPlainText("\n".join(item["message"] for item in issues))

        # 預選語言
        if doc_lang:
            for i in range(self._lang_combo.count()):
                if self._lang_combo.itemData(i) == doc_lang:
                    self._lang_combo.setCurrentIndex(i)
                    break

    # -- 動作 --

    def _run_auto_tag(self):
        from core.accessibility_engine import AccessibilityEngine
        if not self._tag_btn.isEnabled(): return
        alts = {int(self._image_alts.item(row,1).text()): self._image_alts.item(row,2).text() for row in range(self._image_alts.rowCount())}
        try:
            count = AccessibilityEngine().auto_tag(self._doc, self._title_edit.text(), self._lang_combo.currentData(), alts)
            self._check_status()
            QMessageBox.information(self, "內容標記完成", f"已建立 {count} 個內容關聯。請逐頁確認閱讀順序、標題層級與圖片描述。")
        except Exception as exc: QMessageBox.warning(self, "標記未完成", str(exc))

    def _edit_tag(self, item, column):
        from core.accessibility_engine import AccessibilityEngine
        xref = item.data(0, Qt.ItemDataRole.UserRole); kind = item.text(0)
        if kind == "Figure":
            value, ok = QInputDialog.getMultiLineText(self, "圖片替代文字", "描述圖片的意義：", item.text(2))
            if ok:
                with self._doc.edit_transaction("修改替代文字"): AccessibilityEngine().set_alt_text(self._doc.fitz_doc, xref, value)
                self._check_status()
        elif kind in ("TD", "TH"):
            value, ok = QInputDialog.getItem(self, "表格語意", "選擇表格儲存格角色：", ["資料儲存格", "欄表頭", "列表頭", "列與欄表頭"], 0, False)
            if ok:
                with self._doc.edit_transaction("修改表格表頭"):
                    if value == "資料儲存格":
                        self._doc.fitz_doc.xref_set_key(xref,"S","/TD");self._doc.fitz_doc.xref_set_key(xref,"A","null")
                    else: AccessibilityEngine().set_table_header(self._doc.fitz_doc,xref,{"欄表頭":"Column","列表頭":"Row","列與欄表頭":"Both"}[value])
                self._check_status()
        elif kind == "P" or kind.startswith("H"):
            value, ok = QInputDialog.getItem(self, "文字語意", "選擇段落或標題層級：", ["P", "H1", "H2", "H3", "H4", "H5", "H6"], 0, False)
            if ok:
                with self._doc.edit_transaction("修改文字標記"): AccessibilityEngine().set_heading_level(self._doc.fitz_doc, xref, int(value[1:]) if value != "P" else 0)
                self._check_status()

    def _move_section(self, delta):
        from core.accessibility_engine import AccessibilityEngine
        selected = self._structure.currentItem()
        if selected is None: return
        parent = selected.parent()
        if parent is None: return
        index = parent.indexOfChild(selected); target = index+delta
        if not 0 <= target < parent.childCount(): return
        order = list(range(parent.childCount())); order[index],order[target] = order[target],order[index]
        try:
            with self._doc.edit_transaction("調整閱讀順序"):
                AccessibilityEngine().reorder_children(self._doc.fitz_doc,parent.data(0,Qt.ItemDataRole.UserRole),order)
            self._check_status()
        except Exception as exc: QMessageBox.warning(self,"無法重排",str(exc))

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

    def _export_ua(self):
        if self.running_workers(): return
        path, _ = QFileDialog.getSaveFileName(self, "匯出 PDF/UA-1", "accessible.pdf", "PDF (*.pdf)")
        if not path: return
        from core.pdf_standards import PDFStandards
        from ui.widgets.operation_worker import OperationWorker
        self._worker = OperationWorker(self._doc, lambda doc: PDFStandards(doc).export_pdfua(path), self)
        self._ua_btn.setEnabled(False)
        self._worker.succeeded.connect(lambda report: QMessageBox.information(self, "PDF/UA 機器驗證通過", "已通過 veraPDF PDF/UA-1 驗證並儲存。閱讀語意與替代文字適切性仍請人工確認。"))
        self._worker.failed.connect(lambda message: QMessageBox.warning(self, "驗證未通過，沒有匯出", message))
        self._worker.finished.connect(lambda: self._ua_btn.setEnabled(True))
        self._worker.start()

    def _create_table(self):
        from core.accessibility_engine import AccessibilityEngine
        selected = [item for item in self._structure.selectedItems() if item.text(0) == "P"]
        if not selected:
            QMessageBox.information(self,"選擇表格文字","請選取屬於同一表格的段落標記，可按住 Cmd/Ctrl 選取多個。")
            return
        pages = {int(item.text(1))-1 for item in selected}
        if len(pages)!=1:
            QMessageBox.warning(self,"表格範圍","請一次選取同一頁的表格文字。")
            return
        rows, ok = QInputDialog.getInt(self,"表格列数","表格有幾列？",2,1,1000)
        if not ok: return
        max_columns = min(1000, AccessibilityEngine.MAX_TABLE_CELLS // rows)
        columns, ok = QInputDialog.getInt(self,"表格欄數","表格有幾欄？",min(2,max_columns),1,max_columns)
        if not ok: return
        import re
        bounds=None
        for item in selected:
            raw=self._doc.fitz_doc.xref_get_key(item.data(0,Qt.ItemDataRole.UserRole),"AcroBBox")[1]
            values=[float(n) for n in re.findall(r'-?\d+(?:\.\d+)?',raw)]
            if len(values)!=4: continue
            rect=fitz.Rect(values);bounds=rect if bounds is None else bounds|rect
        if bounds is None: return
        try:
            with self._doc.edit_transaction("建立表格標記"):
                page_number = pages.pop()
                table_bounds = (bounds+(-1,-1,1,1)) & self._doc.fitz_doc[page_number].rect
                AccessibilityEngine().add_table_structure(self._doc.fitz_doc,page_number,table_bounds,rows,columns,
                    selected_xrefs=[item.data(0,Qt.ItemDataRole.UserRole) for item in selected])
            self._check_status()
            QMessageBox.information(self,"表格標記完成","請雙擊儲存格標記設定列／欄表頭，並審閱每個儲存格的內容及閱讀順序。")
        except Exception as exc: QMessageBox.warning(self,"表格標記未完成",str(exc))
