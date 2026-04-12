# ~/Desktop/acropdf/ui/main_window.py
import os
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QSplitter, QToolBar,
    QStatusBar, QLabel, QFileDialog, QMessageBox,
    QInputDialog, QWidget, QTabBar
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QAction, QKeySequence, QIcon

from core.document import PDFDocument
from ui.viewer.pdf_view import PDFView
from ui.panels.thumbnail_panel import ThumbnailPanel
from ui.panels.bookmark_panel import BookmarkPanel
from app.config import Config
from app.constants import ToolMode

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AcroPDF")
        self.resize(1280, 900)
        self._config = Config()
        self._docs: list[PDFDocument] = []
        self._tool_actions: dict[ToolMode, QAction] = {}
        self._setup_ui()
        self._setup_menu()
        self._setup_toolbar()
        self._setup_statusbar()

    # ── UI 建置 ──────────────────────────────────────────────────
    def _setup_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # 左側面板
        self._left_tabs = QTabWidget()
        self._left_tabs.setMaximumWidth(220)
        self._left_tabs.setMinimumWidth(180)
        self._thumbnail_panel = ThumbnailPanel()
        self._bookmark_panel = BookmarkPanel()
        self._left_tabs.addTab(self._thumbnail_panel, "縮圖")
        self._left_tabs.addTab(self._bookmark_panel, "書籤")

        # 文件區（多頁籤）
        self._doc_tabs = QTabWidget()
        self._doc_tabs.setTabsClosable(True)
        self._doc_tabs.tabCloseRequested.connect(self._close_tab)
        self._doc_tabs.currentChanged.connect(self._on_tab_changed)

        splitter.addWidget(self._left_tabs)
        splitter.addWidget(self._doc_tabs)
        splitter.setSizes([220, 1060])
        self.setCentralWidget(splitter)

        # 連接縮圖/書籤到目前文件
        self._thumbnail_panel.page_selected.connect(self._goto_page)
        self._thumbnail_panel.pages_reordered.connect(self._reorder_pages)
        self._bookmark_panel.bookmark_clicked.connect(self._goto_page)

    def _setup_menu(self):
        mb = self.menuBar()

        # 檔案
        file_menu = mb.addMenu("檔案(&F)")
        self._add_action(file_menu, "開啟(&O)...", self.open_file_dialog, "Ctrl+O")
        self._add_action(file_menu, "新增(&N)", self.new_document, "Ctrl+N")
        file_menu.addSeparator()
        self._add_action(file_menu, "儲存(&S)", self.save, "Ctrl+S")
        self._add_action(file_menu, "另存新檔(&A)...", self.save_as, "Ctrl+Shift+S")
        file_menu.addSeparator()
        self._recent_menu = file_menu.addMenu("最近開啟")
        self._update_recent_menu()
        file_menu.addSeparator()
        self._add_action(file_menu, "結束(&Q)", self.close, "Ctrl+Q")

        # 編輯
        edit_menu = mb.addMenu("編輯(&E)")
        self._add_action(edit_menu, "復原(&Z)", self._undo, "Ctrl+Z")
        redo_act = self._add_action(edit_menu, "取消復原(&Y)", self._redo, "Ctrl+Y")
        from PyQt6.QtGui import QKeySequence
        from PyQt6.QtWidgets import QShortcut
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self).activated.connect(self._redo)

        # 檢視
        view_menu = mb.addMenu("檢視(&V)")
        self._add_action(view_menu, "放大", self._zoom_in, "Ctrl+=")
        self._add_action(view_menu, "縮小", self._zoom_out, "Ctrl+-")
        self._add_action(view_menu, "符合頁面", self._fit_page, "Ctrl+0")
        self._add_action(view_menu, "符合寬度", self._fit_width, "Ctrl+2")
        view_menu.addSeparator()
        self._add_action(view_menu, "跳至頁面...", self._goto_page_dialog, "Ctrl+G")

        # 頁面
        page_menu = mb.addMenu("頁面(&P)")
        self._add_action(page_menu, "合併 PDF...", self._merge_pdf)
        self._add_action(page_menu, "分割 PDF...", self._split_pdf)
        self._add_action(page_menu, "插入空白頁", self._insert_blank_page)
        self._add_action(page_menu, "刪除選取頁面", self._delete_pages)
        page_menu.addSeparator()
        self._add_action(page_menu, "向右旋轉 90°", lambda: self._rotate(90), "Ctrl+Shift+R")
        self._add_action(page_menu, "向左旋轉 90°", lambda: self._rotate(-90))
        page_menu.addSeparator()
        self._add_action(page_menu, "加浮水印...", self._watermark_dialog)
        self._add_action(page_menu, "加頁首頁尾...", self._header_footer_dialog)

        # 工具
        tools_menu = mb.addMenu("工具(&T)")
        self._add_action(tools_menu, "OCR 文字化...", self._ocr_dialog)
        self._add_action(tools_menu, "比較文件...", self._compare_dialog)
        self._add_action(tools_menu, "最佳化 PDF...", self._optimize_dialog)
        self._add_action(tools_menu, "批次處理...", self._batch_dialog)
        tools_menu.addSeparator()
        self._add_action(tools_menu, "安全性設定...", self._security_dialog)
        self._add_action(tools_menu, "數位簽章...", self._sign_dialog)

        # 匯出
        export_menu = mb.addMenu("匯出(&X)")
        self._add_action(export_menu, "匯出為 Word (.docx)...", lambda: self._export("docx"))
        self._add_action(export_menu, "匯出為 Excel (.xlsx)...", lambda: self._export("xlsx"))
        self._add_action(export_menu, "匯出為 PowerPoint (.pptx)...", lambda: self._export("pptx"))
        self._add_action(export_menu, "匯出為圖片 (PNG)...", lambda: self._export("png"))
        self._add_action(export_menu, "匯出為純文字...", lambda: self._export("txt"))
        self._add_action(export_menu, "儲存為 PDF/A...", lambda: self._export("pdfa"))

    def _add_action(self, menu, text: str, slot, shortcut: str = None) -> QAction:
        act = QAction(text, self)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        act.triggered.connect(slot)
        menu.addAction(act)
        return act

    def _setup_toolbar(self):
        tb = self.addToolBar("工具列")
        tb.setIconSize(QSize(20, 20))
        tb.setMovable(False)

        # 工具按鈕（簡化版，之後各 tool 可擴充）
        for label, mode in [
            ("手形", ToolMode.HAND),
            ("選取", ToolMode.SELECT),
            ("放大", ToolMode.ZOOM),
            ("螢光筆", ToolMode.HIGHLIGHT),
            ("底線", ToolMode.UNDERLINE),
            ("便利貼", ToolMode.STICKY_NOTE),
            ("文字框", ToolMode.TEXT_BOX),
            ("圖章", ToolMode.STAMP),
            ("塗黑", ToolMode.REDACT),
            ("裁切", ToolMode.CROP),
        ]:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setData(mode)
            act.triggered.connect(lambda checked, m=mode: self._set_tool(m))
            tb.addAction(act)
            self._tool_actions[mode] = act

    def _setup_statusbar(self):
        self._status_bar = self.statusBar()
        self._page_label = QLabel("第 - 頁，共 - 頁")
        self._zoom_label = QLabel("100%")
        self._status_bar.addPermanentWidget(self._page_label)
        self._status_bar.addPermanentWidget(self._zoom_label)

    # ── 文件管理 ─────────────────────────────────────────────────
    def open_file(self, path: str):
        doc = PDFDocument(self)
        if not doc.open(path):
            QMessageBox.warning(self, "錯誤", f"無法開啟：{path}")
            return
        self._add_doc_tab(doc)
        self._config.add_recent_file(path)
        self._update_recent_menu()

    def open_file_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "開啟 PDF", "",
            "PDF 檔案 (*.pdf);;所有檔案 (*)"
        )
        for p in paths:
            self.open_file(p)

    def new_document(self):
        doc = PDFDocument(self)
        doc.new()
        self._add_doc_tab(doc)

    def _add_doc_tab(self, doc: PDFDocument):
        view = PDFView(self)
        view.load_document(doc)
        view.page_changed.connect(self._on_page_changed)
        view.zoom_changed.connect(self._on_zoom_changed)

        name = doc.display_name
        idx = self._doc_tabs.addTab(view, name)
        self._doc_tabs.setCurrentIndex(idx)
        self._docs.append(doc)

        # 更新側邊面板
        self._thumbnail_panel.load_document(doc)
        self._bookmark_panel.load_document(doc)

    def _close_tab(self, index: int):
        doc = self._docs[index] if index < len(self._docs) else None
        if doc and doc.is_modified:
            reply = QMessageBox.question(
                self, "確認關閉",
                "文件已修改，是否在關閉前儲存？",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            if reply == QMessageBox.StandardButton.Save:
                self.save()
        self._doc_tabs.removeTab(index)
        if index < len(self._docs):
            self._docs[index].close()
            self._docs.pop(index)

    def _on_tab_changed(self, index: int):
        if index >= 0 and index < len(self._docs):
            doc = self._docs[index]
            self._thumbnail_panel.load_document(doc)
            self._bookmark_panel.load_document(doc)

    def _current_view(self) -> PDFView | None:
        w = self._doc_tabs.currentWidget()
        return w if isinstance(w, PDFView) else None

    def _current_doc(self) -> PDFDocument | None:
        idx = self._doc_tabs.currentIndex()
        return self._docs[idx] if 0 <= idx < len(self._docs) else None

    # ── 儲存 ─────────────────────────────────────────────────────
    def save(self):
        doc = self._current_doc()
        if doc:
            if doc.path:
                doc.save()
            else:
                self.save_as()

    def save_as(self):
        doc = self._current_doc()
        if not doc:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "另存新檔", "", "PDF 檔案 (*.pdf)"
        )
        if path:
            doc.save(path)
            idx = self._doc_tabs.currentIndex()
            self._doc_tabs.setTabText(idx, doc.display_name)

    # ── 頁面操作 ─────────────────────────────────────────────────
    def _rotate(self, angle: int):
        doc = self._current_doc()
        view = self._current_view()
        if doc and view:
            selected = self._thumbnail_panel.selectedItems()
            if selected:
                indices = [item.data(Qt.ItemDataRole.UserRole) for item in selected]
            else:
                indices = [view.current_page()]
            doc.pages.rotate(indices, angle)

    def _delete_pages(self):
        doc = self._current_doc()
        if not doc:
            return
        selected = self._thumbnail_panel.selectedItems()
        if not selected:
            QMessageBox.information(self, "提示", "請在縮圖面板中選取要刪除的頁面")
            return
        indices = [item.data(Qt.ItemDataRole.UserRole) for item in selected]
        if QMessageBox.question(
            self, "確認刪除", f"確定要刪除 {len(indices)} 頁嗎？"
        ) == QMessageBox.StandardButton.Yes:
            doc.pages.delete(indices)

    def _insert_blank_page(self):
        doc = self._current_doc()
        view = self._current_view()
        if doc and view:
            doc.pages.insert_blank(view.current_page())

    def _merge_pdf(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "選擇要合併的 PDF", "", "PDF 檔案 (*.pdf)"
        )
        if path:
            doc = self._current_doc()
            if doc:
                doc.pages.merge_pdf(path)

    def _split_pdf(self):
        doc = self._current_doc()
        if not doc:
            return
        from ui.dialogs.page_ops.split_dialog import SplitDialog
        d = SplitDialog(doc, self)
        d.exec()

    def _reorder_pages(self, new_order: list[int]):
        doc = self._current_doc()
        if doc:
            doc.pages.reorder(new_order)

    def _watermark_dialog(self):
        text, ok = QInputDialog.getText(self, "加浮水印", "浮水印文字：")
        if ok and text:
            doc = self._current_doc()
            if doc:
                doc.pages.add_watermark(text)

    def _header_footer_dialog(self):
        from ui.dialogs.page_ops.header_footer_dialog import HeaderFooterDialog
        doc = self._current_doc()
        if doc:
            d = HeaderFooterDialog(doc, self)
            d.exec()

    # ── 導覽 ─────────────────────────────────────────────────────
    def _goto_page(self, page_num: int):
        view = self._current_view()
        if view:
            view.go_to_page(page_num)

    def _goto_page_dialog(self):
        doc = self._current_doc()
        if not doc:
            return
        page, ok = QInputDialog.getInt(
            self, "跳至頁面", f"頁碼 (1–{doc.page_count})：",
            value=self._current_view().current_page() + 1 if self._current_view() else 1,
            min=1, max=doc.page_count
        )
        if ok:
            self._goto_page(page - 1)

    def _on_page_changed(self, page_num: int):
        doc = self._current_doc()
        total = doc.page_count if doc else 0
        self._page_label.setText(f"第 {page_num+1} 頁，共 {total} 頁")
        self._thumbnail_panel.setCurrentRow(page_num)

    def _on_zoom_changed(self, zoom: float):
        self._zoom_label.setText(f"{zoom*100:.0f}%")

    # ── 縮放 ─────────────────────────────────────────────────────
    def _zoom_in(self):
        view = self._current_view()
        if view:
            view.zoom_in()

    def _zoom_out(self):
        view = self._current_view()
        if view:
            view.zoom_out()

    def _fit_page(self):
        view = self._current_view()
        if view:
            view.fit_page()

    def _fit_width(self):
        view = self._current_view()
        if view:
            view.fit_width()

    # ── Undo / Redo ───────────────────────────────────────────────
    def _undo(self):
        doc = self._current_doc()
        if doc:
            doc.undo()

    def _redo(self):
        doc = self._current_doc()
        if doc:
            doc.redo()

    # ── 工具選擇 ─────────────────────────────────────────────────
    def _set_tool(self, mode: ToolMode):
        from ui.tools.annotation_tools import ToolFactory

        view = self._current_view()
        doc = self._current_doc()
        if not view or not doc:
            return

        for action_mode, action in self._tool_actions.items():
            action.setChecked(action_mode == mode)

        tool = ToolFactory.create(mode, view, doc)
        if tool is None:
            if mode not in {ToolMode.HAND, ToolMode.SELECT, ToolMode.ZOOM}:
                QMessageBox.information(self, "功能逐步補齊中", "這個工具仍在補強中，先提供核心標注工具。")
            view.set_tool(None)
            return
        view.set_tool(tool)

    # ── 最近檔案 ─────────────────────────────────────────────────
    def _update_recent_menu(self):
        self._recent_menu.clear()
        for path in self._config.recent_files:
            act = QAction(os.path.basename(path), self)
            act.setToolTip(path)
            act.triggered.connect(lambda checked, p=path: self.open_file(p))
            self._recent_menu.addAction(act)

    # ── Phase 2/3/4 預留入口（後續實作）─────────────────────────
    def _ocr_dialog(self):
        from ui.dialogs.ocr.ocr_dialog import OCRDialog
        doc = self._current_doc()
        if doc:
            OCRDialog(doc, self).exec()

    def _compare_dialog(self):
        from ui.dialogs.compare.compare_dialog import CompareDialog
        CompareDialog(self).exec()

    def _optimize_dialog(self):
        from ui.dialogs.optimize.optimize_dialog import OptimizeDialog
        doc = self._current_doc()
        if doc:
            OptimizeDialog(doc, self).exec()

    def _batch_dialog(self):
        from ui.dialogs.batch.batch_dialog import BatchDialog
        BatchDialog(self).exec()

    def _security_dialog(self):
        from ui.dialogs.security.security_dialog import SecurityDialog
        doc = self._current_doc()
        if doc:
            SecurityDialog(doc, self).exec()

    def _sign_dialog(self):
        from ui.dialogs.signature.sign_dialog import SignDialog
        doc = self._current_doc()
        if doc:
            SignDialog(doc, self).exec()

    def _export(self, fmt: str):
        from ui.dialogs.export.export_dialog import ExportDialog
        doc = self._current_doc()
        if doc:
            ExportDialog(doc, fmt, self).exec()
