# ~/Desktop/acropdf/ui/main_window.py
from __future__ import annotations

import os
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QSplitter, QToolBar,
    QStatusBar, QLabel, QFileDialog, QMessageBox,
    QInputDialog, QWidget, QMenu, QComboBox
)
from pathlib import Path
from PyQt6.QtCore import Qt, QPoint, QSize
from PyQt6.QtGui import QAction, QKeySequence, QShortcut, QIcon


def _load_window_icon() -> "QIcon | None":
    base = Path(__file__).parent.parent / "resources" / "icons"
    for name in ("acropdf.icns", "acropdf.ico", "acropdf_1024.png"):
        p = base / name
        if p.exists():
            icon = QIcon(str(p))
            if not icon.isNull():
                return icon
    return None

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
        # 視窗圖示（Windows / Linux 標題欄；macOS 用 app-level icon）
        _icon = _load_window_icon()
        if _icon:
            self.setWindowIcon(_icon)
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

        self._left_tabs = QTabWidget()
        self._left_tabs.tabBar().setExpanding(False)   # 不撐滿，緊湊顯示
        self._left_tabs.setMaximumWidth(220)
        self._left_tabs.setMinimumWidth(180)
        self._thumbnail_panel = ThumbnailPanel()
        self._bookmark_panel = BookmarkPanel()
        self._left_tabs.addTab(self._thumbnail_panel, "縮圖")
        self._left_tabs.addTab(self._bookmark_panel, "書籤")

        self._doc_tabs = QTabWidget()
        self._doc_tabs.setTabsClosable(True)
        self._doc_tabs.tabBar().setExpanding(False)   # 不撐滿，靠左排列
        self._doc_tabs.tabCloseRequested.connect(self._close_tab)
        self._doc_tabs.currentChanged.connect(self._on_tab_changed)

        splitter.addWidget(self._left_tabs)
        splitter.addWidget(self._doc_tabs)
        splitter.setSizes([220, 1060])
        self.setCentralWidget(splitter)

        self._thumbnail_panel.page_selected.connect(self._goto_page)
        self._thumbnail_panel.pages_reordered.connect(self._reorder_pages)
        self._thumbnail_panel.context_action.connect(self._thumb_context_action)
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
        self._add_action(edit_menu, "取消復原(&Y)", self._redo, "Ctrl+Y")
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
        self._add_action(page_menu, "擷取頁面...", self._extract_pages)
        page_menu.addSeparator()
        self._add_action(page_menu, "插入空白頁", self._insert_blank_page)
        self._add_action(page_menu, "刪除選取頁面", self._delete_pages, "Delete")
        page_menu.addSeparator()
        self._add_action(page_menu, "向右旋轉 90°", lambda: self._rotate(90), "Ctrl+Shift+R")
        self._add_action(page_menu, "向左旋轉 90°", lambda: self._rotate(-90))
        page_menu.addSeparator()
        self._add_action(page_menu, "加浮水印...", self._watermark_dialog)
        self._add_action(page_menu, "加頁首頁尾...", self._header_footer_dialog)

        # 工具
        tools_menu = mb.addMenu("工具(&T)")
        self._add_action(tools_menu, "OCR 文字化...", self._ocr_dialog)
        self._add_action(tools_menu, "表單填寫...", self._form_fill_dialog)
        tools_menu.addSeparator()
        self._add_action(tools_menu, "比較文件...", self._compare_dialog)
        self._add_action(tools_menu, "最佳化 PDF...", self._optimize_dialog)
        self._add_action(tools_menu, "批次處理...", self._batch_dialog)
        tools_menu.addSeparator()
        self._add_action(tools_menu, "套用永久塗黑", self._apply_redactions)
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
        tb.setStyleSheet("""
            QToolBar { spacing: 2px; padding: 2px 4px; }
            QToolButton {
                padding: 3px 7px; border-radius: 4px;
                border: 1px solid transparent;
                font-size: 12px;
            }
            QToolButton:hover { background: rgba(0,0,0,0.08); border-color: rgba(0,0,0,0.12); }
            QToolButton:checked { background: #0078d4; color: white; border-color: #005a9e; }
            QToolButton:pressed { background: rgba(0,0,0,0.12); }
        """)

        def _add(label, mode):
            act = QAction(label, self)
            act.setCheckable(True)
            act.setData(mode)
            act.triggered.connect(lambda checked, m=mode: self._set_tool(m))
            tb.addAction(act)
            self._tool_actions[mode] = act

        # ── 導覽 ─────────────────────────────────────────────────
        _add("手形", ToolMode.HAND)
        _add("選取", ToolMode.SELECT)
        _add("放大", ToolMode.ZOOM)
        tb.addSeparator()

        # ── 文字標記 ─────────────────────────────────────────────
        _add("螢光筆", ToolMode.HIGHLIGHT)
        _add("底線",   ToolMode.UNDERLINE)
        _add("刪除線", ToolMode.STRIKEOUT)
        tb.addSeparator()

        # ── 文字 / 備注 ──────────────────────────────────────────
        _add("便利貼", ToolMode.STICKY_NOTE)
        _add("文字框", ToolMode.TEXT_BOX)
        _add("標注框", ToolMode.CALLOUT)
        tb.addSeparator()

        # ── 手繪 ─────────────────────────────────────────────────
        _add("手繪",   ToolMode.FREEHAND)
        _add("橡皮擦", ToolMode.ERASER)
        tb.addSeparator()

        # ── 圖形 ─────────────────────────────────────────────────
        _add("矩形", ToolMode.SHAPE_RECT)
        _add("圓形", ToolMode.SHAPE_CIRCLE)
        _add("線條", ToolMode.SHAPE_LINE)
        _add("箭頭", ToolMode.SHAPE_ARROW)
        tb.addSeparator()

        # ── 編輯 ─────────────────────────────────────────────────
        _add("圖章", ToolMode.STAMP)
        _add("塗黑", ToolMode.REDACT)
        _add("裁切", ToolMode.CROP)
        tb.addSeparator()

        # ── 測量 ─────────────────────────────────────────────────
        _add("測距", ToolMode.MEASURE_DIST)
        _add("測面積", ToolMode.MEASURE_AREA)
        tb.addSeparator()

        # ── 工具 ─────────────────────────────────────────────────
        _add("連結",   ToolMode.LINK)
        _add("表單欄", ToolMode.FORM_FIELD)
        tb.addSeparator()

        # ── 縮放百分比 ComboBox ──────────────────────────────────────
        self._zoom_combo = QComboBox()
        self._zoom_combo.setEditable(True)
        self._zoom_combo.setFixedWidth(80)
        self._zoom_combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._zoom_combo.addItems([
            "25%", "50%", "75%", "100%", "125%", "150%",
            "175%", "200%", "300%", "400%", "適合頁面", "適合寬度",
        ])
        self._zoom_combo.setCurrentText("100%")
        self._zoom_combo.activated.connect(self._on_zoom_combo_activated)
        self._zoom_combo.lineEdit().returnPressed.connect(self._on_zoom_combo_return)
        tb.addWidget(self._zoom_combo)

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
        view.page_context_requested.connect(self._show_page_context_menu)

        name = doc.display_name
        idx = self._doc_tabs.addTab(view, name)
        self._doc_tabs.setCurrentIndex(idx)
        self._docs.append(doc)

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
        if 0 <= index < len(self._docs):
            doc = self._docs[index]
            self._thumbnail_panel.load_document(doc)
            self._bookmark_panel.load_document(doc)

    def _current_view(self) -> PDFView | None:
        w = self._doc_tabs.currentWidget()
        return w if isinstance(w, PDFView) else None

    def _current_doc(self) -> PDFDocument | None:
        idx = self._doc_tabs.currentIndex()
        return self._docs[idx] if 0 <= idx < len(self._docs) else None

    def _selected_pages(self, fallback_current: bool = True) -> list[int]:
        """縮圖面板選取的頁面；若無選取且 fallback_current=True，回傳目前頁面。"""
        sel = self._thumbnail_panel.selected_page_indices()
        if not sel and fallback_current:
            view = self._current_view()
            if view:
                return [view.current_page()]
        return sel

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

    # ── 右鍵選單 ─────────────────────────────────────────────────
    def _thumb_context_action(self, action_id: str, indices: list[int]):
        doc = self._current_doc()
        if not doc:
            return
        view = self._current_view()

        if action_id == "delete":
            n = len(indices)
            if QMessageBox.question(
                self, "確認刪除", f"確定要刪除第 {', '.join(str(i+1) for i in indices)} 頁（共 {n} 頁）？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) == QMessageBox.StandardButton.Yes:
                doc.pages.delete(indices)

        elif action_id == "extract":
            from ui.dialogs.page_ops.extract_dialog import ExtractDialog
            ExtractDialog(doc, indices, self).exec()

        elif action_id == "split":
            from ui.dialogs.page_ops.split_dialog import SplitDialog
            SplitDialog(doc, indices, self).exec()

        elif action_id == "rotate_cw":
            doc.pages.rotate(indices, 90)

        elif action_id == "rotate_ccw":
            doc.pages.rotate(indices, -90)

        elif action_id == "insert_blank_before":
            doc.pages.insert_blank(indices[0])

        elif action_id == "insert_blank_after":
            doc.pages.insert_blank(indices[-1] + 1)

        elif action_id == "insert_from_file":
            path, _ = QFileDialog.getOpenFileName(
                self, "選擇要插入的 PDF", "", "PDF 檔案 (*.pdf)"
            )
            if path:
                doc.pages.insert_pdf(path, indices[0])

        elif action_id == "replace":
            path, _ = QFileDialog.getOpenFileName(
                self, "選擇取代來源 PDF", "", "PDF 檔案 (*.pdf)"
            )
            if path:
                import fitz
                src = fitz.open(path)
                for i, dest_idx in enumerate(sorted(indices)):
                    if i < src.page_count:
                        doc.fitz_doc[dest_idx].show_pdf_page(
                            doc.fitz_doc[dest_idx].rect, src, i)
                src.close()
                doc._mark_modified()

        elif action_id == "watermark":
            self._watermark_dialog()

        elif action_id == "header_footer":
            self._header_footer_dialog()

        elif action_id == "properties":
            from ui.dialogs.page_ops.page_properties_dialog import PagePropertiesDialog
            PagePropertiesDialog(doc, indices, self).exec()

    def _show_page_context_menu(self, page_num: int, global_pos: QPoint):
        """主視圖右鍵選單（對齊 Adobe Acrobat）"""
        doc = self._current_doc()
        if not doc:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                border: 1px solid rgba(0,0,0,0.15);
                border-radius: 6px;
                padding: 4px;
                background: palette(window);
            }
            QMenu::item { padding: 6px 28px 6px 12px; border-radius: 4px; }
            QMenu::item:selected { background: #0078d4; color: white; }
            QMenu::separator { height: 1px; background: rgba(0,0,0,0.1); margin: 4px 8px; }
        """)

        # ── 標注 ──────────────────────────────────
        menu.addAction("加入螢光筆",
                       lambda: self._set_tool(ToolMode.HIGHLIGHT))
        menu.addAction("加入底線",
                       lambda: self._set_tool(ToolMode.UNDERLINE))
        menu.addAction("加入便利貼...",
                       lambda: self._set_tool(ToolMode.STICKY_NOTE))
        menu.addAction("加入文字框...",
                       lambda: self._set_tool(ToolMode.TEXT_BOX))
        menu.addAction("加入圖章",
                       lambda: self._set_tool(ToolMode.STAMP))
        menu.addAction("標記塗黑",
                       lambda: self._set_tool(ToolMode.REDACT))
        menu.addSeparator()

        # ── 頁面操作 ──────────────────────────────
        page_submenu = menu.addMenu("頁面操作")
        page_submenu.addAction(f"向右旋轉 90°（第 {page_num+1} 頁）",
                               lambda: doc.pages.rotate([page_num], 90))
        page_submenu.addAction(f"向左旋轉 90°（第 {page_num+1} 頁）",
                               lambda: doc.pages.rotate([page_num], -90))
        page_submenu.addSeparator()
        page_submenu.addAction("在此頁前插入空白頁",
                               lambda: doc.pages.insert_blank(page_num))
        page_submenu.addAction("在此頁後插入空白頁",
                               lambda: doc.pages.insert_blank(page_num + 1))
        page_submenu.addSeparator()
        page_submenu.addAction(f"擷取第 {page_num+1} 頁...",
                               lambda: self._thumb_context_action("extract", [page_num]))
        page_submenu.addAction(f"刪除第 {page_num+1} 頁",
                               lambda: self._confirm_delete([page_num]))
        menu.addSeparator()

        # ── 其他 ──────────────────────────────────
        menu.addAction("頁面屬性...",
                       lambda: self._thumb_context_action("properties", [page_num]))

        menu.exec(global_pos)

    # ── 頁面操作 ─────────────────────────────────────────────────
    def _confirm_delete(self, indices: list[int]):
        doc = self._current_doc()
        if not doc:
            return
        n = len(indices)
        if QMessageBox.question(
            self, "確認刪除", f"確定要刪除 {n} 頁嗎？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            doc.pages.delete(indices)

    def _rotate(self, angle: int):
        doc = self._current_doc()
        if not doc:
            return
        indices = self._selected_pages()
        doc.pages.rotate(indices, angle)

    def _delete_pages(self):
        indices = self._selected_pages(fallback_current=False)
        if not indices:
            QMessageBox.information(self, "提示", "請先在縮圖面板 Ctrl/Shift 點選要刪除的頁面")
            return
        self._confirm_delete(indices)

    def _insert_blank_page(self):
        doc = self._current_doc()
        view = self._current_view()
        if doc and view:
            doc.pages.insert_blank(view.current_page())

    def _extract_pages(self):
        doc = self._current_doc()
        if not doc:
            return
        indices = self._selected_pages(fallback_current=False)
        from ui.dialogs.page_ops.extract_dialog import ExtractDialog
        ExtractDialog(doc, indices, self).exec()

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
        indices = self._selected_pages(fallback_current=False)
        from ui.dialogs.page_ops.split_dialog import SplitDialog
        SplitDialog(doc, indices, self).exec()

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
            HeaderFooterDialog(doc, self).exec()

    # ── 導覽 ─────────────────────────────────────────────────────
    def _goto_page(self, page_num: int):
        view = self._current_view()
        if view:
            view.go_to_page(page_num)

    def _goto_page_dialog(self):
        doc = self._current_doc()
        if not doc:
            return
        cur = self._current_view().current_page() + 1 if self._current_view() else 1
        page, ok = QInputDialog.getInt(
            self, "跳至頁面", f"頁碼 (1–{doc.page_count})：",
            value=cur, min=1, max=doc.page_count
        )
        if ok:
            self._goto_page(page - 1)

    def _on_page_changed(self, page_num: int):
        doc = self._current_doc()
        total = doc.page_count if doc else 0
        self._page_label.setText(f"第 {page_num+1} 頁，共 {total} 頁")
        self._thumbnail_panel.setCurrentRow(page_num)

    def _on_zoom_changed(self, zoom: float):
        pct = f"{zoom*100:.0f}%"
        self._zoom_label.setText(pct)
        # 同步更新工具列 ComboBox（暫時斷開訊號防止循環觸發）
        self._zoom_combo.blockSignals(True)
        self._zoom_combo.setCurrentText(pct)
        self._zoom_combo.blockSignals(False)

    def _on_zoom_combo_activated(self, index: int):
        """使用者從下拉選單選擇項目。"""
        text = self._zoom_combo.itemText(index)
        self._apply_zoom_text(text)

    def _on_zoom_combo_return(self):
        """使用者在 ComboBox 文字欄位按 Enter。"""
        self._apply_zoom_text(self._zoom_combo.currentText())

    def _apply_zoom_text(self, text: str):
        view = self._current_view()
        if not view:
            return
        text = text.strip()
        if text == "適合頁面":
            view.fit_page()
        elif text == "適合寬度":
            view.fit_width()
        else:
            # 解析數字，接受「150」或「150%」
            try:
                value = float(text.rstrip("%"))
                view.set_zoom(value / 100.0)
            except ValueError:
                pass

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
        view.set_tool(tool)   # None = 導覽模式（手形 / 選取 / 放大）

    # ── 最近檔案 ─────────────────────────────────────────────────
    def _update_recent_menu(self):
        self._recent_menu.clear()
        for path in self._config.recent_files:
            act = QAction(os.path.basename(path), self)
            act.setToolTip(path)
            act.triggered.connect(lambda checked, p=path: self.open_file(p))
            self._recent_menu.addAction(act)

    # ── Phase 2/3/4 ──────────────────────────────────────────────
    def _ocr_dialog(self):
        from ui.dialogs.ocr.ocr_dialog import OCRDialog
        doc = self._current_doc()
        view = self._current_view()
        if doc:
            cur_page = view.current_page() if view else 0
            OCRDialog(doc, current_page=cur_page, parent=self).exec()

    def _form_fill_dialog(self):
        from ui.dialogs.forms.form_fill_dialog import FormFillDialog
        doc = self._current_doc()
        if doc:
            FormFillDialog(doc, self).exec()

    def _apply_redactions(self):
        doc = self._current_doc()
        if not doc:
            return
        reply = QMessageBox.question(
            self, "套用永久塗黑",
            "確定要永久塗黑所有標記區域？此操作無法復原。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            doc.annotations.apply_redactions()
            view = self._current_view()
            if view:
                view.refresh()

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
