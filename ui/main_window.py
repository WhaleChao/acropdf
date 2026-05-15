# ~/Desktop/acropdf/ui/main_window.py
from __future__ import annotations

import os
import fitz
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QSplitter, QToolBar,
    QStatusBar, QLabel, QFileDialog, QMessageBox,
    QInputDialog, QWidget, QMenu, QComboBox, QVBoxLayout, QHBoxLayout,
    QSlider, QPushButton, QStackedWidget, QFrame, QGridLayout, QSpinBox,
    QScrollArea, QLineEdit, QButtonGroup,
)
from pathlib import Path
from PyQt6.QtCore import Qt, QPoint, QSize, QMarginsF, QTimer
from PyQt6.QtGui import QAction, QKeySequence, QShortcut, QIcon, QPageLayout, QPageSize


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
from ui.panels.file_browser_panel import FileBrowserPanel
from app.config import Config
from app.constants import ToolMode, LayoutMode
from ui.widgets.detachable_tabbar import DetachableTabBar


class WelcomePanel(QWidget):
    """沒有文件時的起始畫面，讓第一步更明確。"""

    def __init__(self, parent: "MainWindow"):
        super().__init__(parent)
        self._main = parent
        self.setObjectName("welcomePanel")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(36, 36, 36, 36)
        outer.setSpacing(18)
        outer.addStretch(1)

        title = QLabel("AcroPDF")
        title.setObjectName("welcomeTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(title)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        open_btn = QPushButton("開啟 PDF")
        open_btn.setDefault(True)
        open_btn.clicked.connect(parent.open_file_dialog)
        new_btn = QPushButton("新增空白 PDF")
        new_btn.clicked.connect(parent.new_document)
        actions.addWidget(open_btn)
        actions.addWidget(new_btn)
        outer.addLayout(actions)

        self._recent_frame = QFrame()
        self._recent_frame.setObjectName("welcomeRecent")
        recent_layout = QVBoxLayout(self._recent_frame)
        recent_layout.setContentsMargins(16, 14, 16, 14)
        recent_layout.setSpacing(8)
        recent_title = QLabel("最近開啟")
        recent_title.setObjectName("welcomeSectionTitle")
        recent_layout.addWidget(recent_title)
        self._recent_grid = QGridLayout()
        self._recent_grid.setContentsMargins(0, 0, 0, 0)
        self._recent_grid.setSpacing(6)
        recent_layout.addLayout(self._recent_grid)
        outer.addWidget(self._recent_frame, alignment=Qt.AlignmentFlag.AlignCenter)

        hint = QLabel("可直接拖曳 PDF、圖片或 Office 文件到視窗")
        hint.setObjectName("welcomeHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(hint)
        outer.addStretch(2)
        self.refresh_recent()

    def refresh_recent(self):
        while self._recent_grid.count():
            item = self._recent_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        recent = [p for p in self._main._config.recent_files if os.path.exists(p)][:6]
        self._recent_frame.setVisible(bool(recent))
        for i, path in enumerate(recent):
            btn = QPushButton(os.path.basename(path))
            btn.setObjectName("recentFileButton")
            btn.setToolTip(path)
            btn.clicked.connect(lambda checked=False, p=path: self._main.open_file(p))
            self._recent_grid.addWidget(btn, i // 2, i % 2)


class AcrobatToolsPanel(QScrollArea):
    """Acrobat 式工具中心，把分散的專業功能收斂成工作流入口。"""

    def __init__(self, parent: "MainWindow"):
        super().__init__(parent)
        self._main = parent
        self.setObjectName("toolsCenter")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        body = QWidget()
        body.setObjectName("toolsCenterBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        heading = QLabel("工具")
        heading.setObjectName("toolsCenterTitle")
        layout.addWidget(heading)

        self._add_group(layout, "建立與整理", [
            ("開啟 / 建立", parent.open_file_dialog),
            ("合併 PDF", parent._merge_pdf),
            ("組織頁面", parent._show_thumbnails),
            ("擷取頁面", parent._extract_pages),
            ("分割 PDF", parent._split_pdf),
        ])
        self._add_group(layout, "編輯 PDF", [
            ("編輯文字", lambda: parent._set_tool(ToolMode.TEXT_EDIT)),
            ("編輯圖片", lambda: parent._set_tool(ToolMode.IMAGE_EDIT)),
            ("加浮水印", parent._watermark_dialog),
            ("頁首頁尾", parent._header_footer_dialog),
        ])
        self._add_group(layout, "註解與標記", [
            ("螢光筆", lambda: parent._set_tool(ToolMode.HIGHLIGHT)),
            ("便利貼", lambda: parent._set_tool(ToolMode.STICKY_NOTE)),
            ("文字框", lambda: parent._set_tool(ToolMode.TEXT_BOX)),
            ("標注摘要", parent._annot_summary_dialog),
        ])
        self._add_group(layout, "表單與簽署", [
            ("填寫表單", parent._form_fill_dialog),
            ("設計表單", parent._form_designer_dialog),
            ("數位簽章", parent._sign_dialog),
            ("管理附件", parent._attachment_dialog),
        ])
        self._add_group(layout, "轉換與最佳化", [
            ("匯出 Word", lambda: parent._export("docx")),
            ("匯出 Excel", lambda: parent._export("xlsx")),
            ("匯出 PowerPoint", lambda: parent._export("pptx")),
            ("匯出圖片", lambda: parent._export("png")),
            ("儲存為 PDF/A", lambda: parent._export("pdfa")),
            ("壓縮 PDF", parent._optimize_dialog),
        ])
        self._add_group(layout, "保護與審查", [
            ("文件屬性", parent._document_properties_dialog),
            ("保護 PDF", parent._security_dialog),
            ("塗黑工具", parent._redaction_dialog),
            ("比較文件", parent._compare_dialog),
            ("預檢", parent._preflight_dialog),
            ("匯出 PDF/X", parent._export_pdfx_dialog),
        ])
        self._add_group(layout, "智慧工具", [
            ("OCR 文字化", parent._ocr_dialog),
            ("AI 摘要", parent._ai_summary_dialog),
            ("AI 翻譯", parent._ai_translate_dialog),
            ("智慧歸檔", parent._filing_dialog),
        ])

        layout.addStretch(1)
        self.setWidget(body)

    def _add_group(self, layout: QVBoxLayout, title: str, actions: list[tuple[str, object]]):
        frame = QFrame()
        frame.setObjectName("toolGroup")
        group_layout = QVBoxLayout(frame)
        group_layout.setContentsMargins(8, 8, 8, 8)
        group_layout.setSpacing(6)
        label = QLabel(title)
        label.setObjectName("toolGroupTitle")
        group_layout.addWidget(label)
        for text, slot in actions:
            btn = QPushButton(text)
            btn.setObjectName("toolCenterButton")
            btn.clicked.connect(slot)
            group_layout.addWidget(btn)
        layout.addWidget(frame)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AcroPDF")
        self.resize(1280, 900)
        self.setAcceptDrops(True)  # 支援拖曳開檔
        # 視窗圖示（Windows / Linux 標題欄；macOS 用 app-level icon）
        _icon = _load_window_icon()
        if _icon:
            self.setWindowIcon(_icon)
        self._config = Config()
        self._docs: list[PDFDocument] = []
        self._tool_actions: dict[ToolMode, QAction] = {}
        self._presentation_view = None
        self._rulers_visible = False
        self._grid_visible = False
        self._setup_ui()
        self._setup_menu()
        self._setup_toolbar()
        self._setup_statusbar()
        # 載入主題
        self._apply_theme(self._config.theme)

    # ── UI 建置 ──────────────────────────────────────────────────
    def _setup_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        self._left_panel = QWidget()
        self._left_panel.setObjectName("leftPanel")
        self._left_panel.setMinimumWidth(300)
        left_layout = QHBoxLayout(self._left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self._side_nav = QFrame()
        self._side_nav.setObjectName("sideNav")
        nav_layout = QVBoxLayout(self._side_nav)
        nav_layout.setContentsMargins(6, 8, 6, 8)
        nav_layout.setSpacing(6)
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._side_stack = QStackedWidget()
        self._side_stack.setObjectName("sideStack")

        self._thumbnail_panel = ThumbnailPanel()
        self._bookmark_panel = BookmarkPanel()
        self._file_browser_panel = FileBrowserPanel(config=self._config)
        self._file_browser_panel.file_open_requested.connect(self.open_file)
        self._tools_panel = AcrobatToolsPanel(self)
        self._side_pages = [
            ("案件", self._file_browser_panel),
            ("工具", self._tools_panel),
            ("縮圖", self._thumbnail_panel),
            ("書籤", self._bookmark_panel),
        ]
        for idx, (label, widget) in enumerate(self._side_pages):
            btn = QPushButton(label)
            btn.setObjectName("sideNavButton")
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked=False, i=idx: self._set_side_page(i))
            self._nav_group.addButton(btn, idx)
            nav_layout.addWidget(btn)
            self._side_stack.addWidget(widget)
            if idx == 0:
                btn.setChecked(True)
        nav_layout.addStretch(1)
        left_layout.addWidget(self._side_nav)
        left_layout.addWidget(self._side_stack, 1)

        self._doc_tabs = QTabWidget()
        self._detachable_bar = DetachableTabBar(self._doc_tabs)
        self._doc_tabs.setTabBar(self._detachable_bar)
        self._doc_tabs.setTabsClosable(True)        # 必須在 setTabBar 之後
        self._doc_tabs.setMovable(True)
        self._detachable_bar.setExpanding(True)
        self._detachable_bar.tab_detach_requested.connect(self._detach_tab)
        self._doc_tabs.tabCloseRequested.connect(self._close_tab)
        self._doc_tabs.currentChanged.connect(self._on_tab_changed)

        # 搜尋列
        from ui.widgets.search_bar import SearchBar
        self._search_bar = SearchBar(self)
        self._search_bar.search_requested.connect(self._on_search)
        self._search_bar.next_requested.connect(self._on_search_next)
        self._search_bar.prev_requested.connect(self._on_search_prev)
        self._search_bar.closed.connect(self._on_search_closed)

        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._search_bar)
        self._welcome_panel = WelcomePanel(self)
        self._workspace_stack = QStackedWidget()
        self._workspace_stack.addWidget(self._welcome_panel)
        self._workspace_stack.addWidget(self._doc_tabs)
        self._workspace_stack.setCurrentWidget(self._welcome_panel)
        right_layout.addWidget(self._workspace_stack)

        splitter.addWidget(self._left_panel)
        splitter.addWidget(right_container)
        splitter.setSizes([300, 980])
        self.setCentralWidget(splitter)

        # 搜尋狀態
        self._search_results: list[tuple[int, object]] = []
        self._search_index: int = -1
        self._search_text: str = ""

        self._thumbnail_panel.page_selected.connect(self._goto_page)
        self._thumbnail_panel.pages_reordered.connect(self._reorder_pages)
        self._thumbnail_panel.context_action.connect(self._thumb_context_action)
        self._bookmark_panel.bookmark_clicked.connect(self._goto_page)
        self._bookmark_panel.add_requested.connect(self._add_bookmark)
        self._bookmark_panel.delete_requested.connect(self._delete_bookmark)
        self._bookmark_panel.rename_requested.connect(self._rename_bookmark)

    def _setup_menu(self):
        mb = self.menuBar()

        # ── 檔案 ──────────────────────────────────
        file_menu = mb.addMenu("檔案(&F)")
        self._add_action(file_menu, "開啟(&O)...", self.open_file_dialog, "Ctrl+O")
        self._add_action(file_menu, "新增(&N)", self.new_document, "Ctrl+N")
        file_menu.addSeparator()
        self._add_action(file_menu, "儲存(&S)", self.save, "Ctrl+S")
        self._add_action(file_menu, "另存新檔(&A)...", self.save_as, "Ctrl+Shift+S")
        self._add_action(file_menu, "關閉目前 PDF(&W)", self._close_current_tab, "Ctrl+W")
        file_menu.addSeparator()
        self._add_action(file_menu, "文件屬性(&I)...", self._document_properties_dialog, "Ctrl+I")
        file_menu.addSeparator()
        self._add_action(file_menu, "列印(&P)...", self._print_document, "Ctrl+P")
        file_menu.addSeparator()
        self._recent_menu = file_menu.addMenu("最近開啟")
        self._update_recent_menu()
        file_menu.addSeparator()
        self._add_action(file_menu, "結束(&Q)", self.close, "Ctrl+Q")

        # ── 編輯 ──────────────────────────────────
        edit_menu = mb.addMenu("編輯(&E)")
        self._add_action(edit_menu, "復原(&Z)", self._undo, "Ctrl+Z")
        self._add_action(edit_menu, "取消復原(&Y)", self._redo, "Ctrl+Y")
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self).activated.connect(self._redo)
        edit_menu.addSeparator()
        self._add_action(edit_menu, "搜尋(&F)...", self._toggle_search, "Ctrl+F")

        # ── 檢視 ──────────────────────────────────
        view_menu = mb.addMenu("檢視(&V)")
        self._add_action(view_menu, "放大", self._zoom_in, "Ctrl+=")
        self._add_action(view_menu, "縮小", self._zoom_out, "Ctrl+-")
        self._add_action(view_menu, "符合頁面", self._fit_page, "Ctrl+0")
        self._add_action(view_menu, "符合寬度", self._fit_width, "Ctrl+2")
        view_menu.addSeparator()
        self._add_action(view_menu, "跳至頁面...", self._goto_page_dialog, "Ctrl+G")
        self._add_action(view_menu, "新增書籤", self._add_bookmark, "Ctrl+D")
        view_menu.addSeparator()

        # 頁面檢視模式
        view_mode_menu = view_menu.addMenu("頁面檢視模式")
        self._view_mode_actions = {}
        for mode, label in [
            (LayoutMode.CONTINUOUS, "連續捲動"),
            (LayoutMode.SINGLE, "單頁"),
            (LayoutMode.DOUBLE, "雙頁"),
        ]:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(mode == LayoutMode.CONTINUOUS)
            act.triggered.connect(lambda checked, m=mode: self._set_layout_mode(m))
            view_mode_menu.addAction(act)
            self._view_mode_actions[mode] = act
        view_menu.addSeparator()

        # 全螢幕簡報
        self._add_action(view_menu, "全螢幕簡報(&F)", self._start_presentation, "F5")
        # 分割檢視
        self._split_action = QAction("分割檢視", self)
        self._split_action.setCheckable(True)
        self._split_action.triggered.connect(self._toggle_split_view)
        view_menu.addAction(self._split_action)
        view_menu.addSeparator()

        # 尺規 & 格線
        self._ruler_action = QAction("顯示尺規", self)
        self._ruler_action.setCheckable(True)
        self._ruler_action.setChecked(self._config.show_rulers)
        self._ruler_action.triggered.connect(self._toggle_rulers)
        view_menu.addAction(self._ruler_action)
        self._grid_action = QAction("顯示格線", self)
        self._grid_action.setCheckable(True)
        self._grid_action.setChecked(self._config.show_grid)
        self._grid_action.triggered.connect(self._toggle_grid)
        view_menu.addAction(self._grid_action)
        view_menu.addSeparator()

        # 深色 / 淺色模式
        theme_menu = view_menu.addMenu("主題")
        self._theme_light_act = QAction("淺色模式", self)
        self._theme_light_act.setCheckable(True)
        self._theme_light_act.setChecked(self._config.theme == "light")
        self._theme_light_act.triggered.connect(lambda: self._switch_theme("light"))
        theme_menu.addAction(self._theme_light_act)
        self._theme_dark_act = QAction("深色模式", self)
        self._theme_dark_act.setCheckable(True)
        self._theme_dark_act.setChecked(self._config.theme == "dark")
        self._theme_dark_act.triggered.connect(lambda: self._switch_theme("dark"))
        theme_menu.addAction(self._theme_dark_act)

        # ── 頁面 ──────────────────────────────────
        page_menu = mb.addMenu("頁面(&P)")
        self._add_action(page_menu, "合併 PDF...", self._merge_pdf)
        self._add_action(page_menu, "分割 PDF...", self._split_pdf)
        self._add_action(page_menu, "擷取頁面...", self._extract_pages)
        page_menu.addSeparator()
        self._add_action(page_menu, "插入空白頁", self._insert_blank_page)
        self._add_action(page_menu, "從檔案插入頁面...", self._insert_from_file)
        self._add_action(page_menu, "刪除選取頁面", self._delete_pages, "Delete")
        page_menu.addSeparator()
        self._add_action(page_menu, "向右旋轉 90°", lambda: self._rotate(90), "Ctrl+Shift+R")
        self._add_action(page_menu, "向左旋轉 90°", lambda: self._rotate(-90), "Ctrl+Shift+L")
        page_menu.addSeparator()
        self._add_action(page_menu, "加浮水印...", self._watermark_dialog)
        self._add_action(page_menu, "加頁首頁尾...", self._header_footer_dialog)
        self._add_action(page_menu, "Bates 編號...", self._bates_dialog)
        self._add_action(page_menu, "頁面背景...", self._background_dialog)

        # ── 工具 ──────────────────────────────────
        tools_menu = mb.addMenu("工具(&T)")
        self._add_action(tools_menu, "編輯文字", lambda: self._set_tool(ToolMode.TEXT_EDIT))
        self._add_action(tools_menu, "編輯圖片", lambda: self._set_tool(ToolMode.IMAGE_EDIT))
        tools_menu.addSeparator()
        self._add_action(tools_menu, "OCR 文字化...", self._ocr_dialog)
        self._add_action(tools_menu, "表單填寫...", self._form_fill_dialog)
        self._add_action(tools_menu, "自動標籤...", self._auto_label_dialog)
        tools_menu.addSeparator()
        self._add_action(tools_menu, "比較文件...", self._compare_dialog)
        self._add_action(tools_menu, "最佳化 PDF...", self._optimize_dialog)
        self._add_action(tools_menu, "批次處理...", self._batch_dialog)
        tools_menu.addSeparator()
        self._add_action(tools_menu, "套用永久塗黑", self._apply_redactions)
        tools_menu.addSeparator()
        self._add_action(tools_menu, "安全性設定...", self._security_dialog)
        self._add_action(tools_menu, "數位簽章...", self._sign_dialog)
        tools_menu.addSeparator()
        self._add_action(tools_menu, "管理圖層...", self._layer_dialog)
        self._add_action(tools_menu, "管理附件...", self._attachment_dialog)
        self._add_action(tools_menu, "自訂圖章...", self._custom_stamp_dialog)
        tools_menu.addSeparator()
        self._add_action(tools_menu, "標注摘要...", self._annot_summary_dialog)
        self._add_action(tools_menu, "無障礙設定...", self._accessibility_dialog)
        tools_menu.addSeparator()
        self._add_action(tools_menu, "AI 文件摘要...", self._ai_summary_dialog)
        self._add_action(tools_menu, "AI 翻譯...", self._ai_translate_dialog)
        tools_menu.addSeparator()
        self._add_action(tools_menu, "塗黑工具...", self._redaction_dialog)
        self._add_action(tools_menu, "表單設計...", self._form_designer_dialog)
        self._add_action(tools_menu, "預檢...", self._preflight_dialog)
        self._add_action(tools_menu, "字型管理...", self._font_dialog)
        tools_menu.addSeparator()
        self._add_action(tools_menu, "MAGI 智慧助理...", self._magi_dialog)
        tools_menu.addSeparator()
        self._add_action(tools_menu, "文字重排...", self._reflow_dialog)
        self._add_action(tools_menu, "智慧歸檔...", self._filing_dialog)
        self._add_action(tools_menu, "文件範本...", self._template_dialog)

        # ── 匯出 ──────────────────────────────────
        export_menu = mb.addMenu("匯出(&X)")
        self._add_action(export_menu, "匯出為 Word (.docx)...", lambda: self._export("docx"))
        self._add_action(export_menu, "匯出為 Excel (.xlsx)...", lambda: self._export("xlsx"))
        self._add_action(export_menu, "匯出為 PowerPoint (.pptx)...", lambda: self._export("pptx"))
        self._add_action(export_menu, "匯出為圖片 (PNG)...", lambda: self._export("png"))
        self._add_action(export_menu, "匯出為純文字...", lambda: self._export("txt"))
        self._add_action(export_menu, "匯出為 HTML...", lambda: self._export("html"))
        export_menu.addSeparator()
        self._add_action(export_menu, "儲存為 PDF/A...", lambda: self._export("pdfa"))
        self._add_action(export_menu, "匯出為 PDF/X...", self._export_pdfx_dialog)

        # ── 說明 ──────────────────────────────────
        help_menu = mb.addMenu("說明(&H)")
        self._add_action(help_menu, "匯出診斷資料...", self._export_diagnostics)
        self._add_action(help_menu, "關於 AcroPDF", self._about_dialog)

    def _add_action(self, menu, text: str, slot, shortcut: str = None) -> QAction:
        act = QAction(text, self)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        act.triggered.connect(slot)
        menu.addAction(act)
        return act

    def _export_diagnostics(self):
        from core.diagnostics import default_diagnostics_path, export_diagnostics
        from main import APP_VERSION

        path, _ = QFileDialog.getSaveFileName(
            self,
            "匯出診斷資料",
            str(default_diagnostics_path()),
            "ZIP 壓縮檔 (*.zip)",
        )
        if not path:
            return
        if not path.lower().endswith(".zip"):
            path += ".zip"
        try:
            out = export_diagnostics(path, APP_VERSION)
            QMessageBox.information(self, "匯出完成", f"診斷資料已儲存至：\n{out}")
        except Exception as exc:
            QMessageBox.warning(self, "匯出失敗", f"無法匯出診斷資料：\n{exc}")

    def _about_dialog(self):
        from main import APP_NAME, APP_PUBLISHER, APP_VERSION

        QMessageBox.about(
            self,
            f"關於 {APP_NAME}",
            (
                f"<b>{APP_NAME}</b><br>"
                f"版本：{APP_VERSION}<br>"
                f"發行者：{APP_PUBLISHER}<br><br>"
                "單機版 PDF 編輯工具。"
            ),
        )

    def _setup_toolbar(self):
        tb = self.addToolBar("工具列")
        tb.setIconSize(QSize(18, 18))
        tb.setMovable(False)
        # 不設 inline stylesheet — 全部由 QSS 主題檔控制顏色

        open_act = QAction("開啟", self)
        open_act.setToolTip("開啟文件")
        open_act.triggered.connect(self.open_file_dialog)
        tb.addAction(open_act)
        save_act = QAction("儲存", self)
        save_act.setToolTip("儲存目前文件")
        save_act.triggered.connect(self.save)
        tb.addAction(save_act)
        self._save_as_action = QAction("另存新檔", self)
        self._save_as_action.setToolTip("另存新檔（Ctrl+Shift+S）")
        self._save_as_action.triggered.connect(self.save_as)
        tb.addAction(self._save_as_action)
        self._close_pdf_btn = QPushButton("關閉 PDF")
        self._close_pdf_btn.setObjectName("closePdfButton")
        self._close_pdf_btn.setToolTip("關閉目前 PDF（Ctrl+W）")
        self._close_pdf_btn.setEnabled(False)
        self._close_pdf_btn.clicked.connect(self._close_current_tab)
        tb.addWidget(self._close_pdf_btn)
        print_act = QAction("列印", self)
        print_act.setToolTip("列印目前文件")
        print_act.triggered.connect(self._print_document)
        tb.addAction(print_act)
        tb.addSeparator()

        tools_act = QAction("工具", self)
        tools_act.setToolTip("顯示 Acrobat 式工具中心")
        tools_act.triggered.connect(self._show_tools_center)
        tb.addAction(tools_act)
        props_act = QAction("屬性", self)
        props_act.setToolTip("查看文件屬性與安全狀態")
        props_act.triggered.connect(self._document_properties_dialog)
        tb.addAction(props_act)
        tb.addSeparator()

        prev_act = QAction("上一頁", self)
        prev_act.setToolTip("上一頁")
        prev_act.triggered.connect(self._prev_page)
        tb.addAction(prev_act)

        self._page_spin = QSpinBox()
        self._page_spin.setObjectName("pageSpin")
        self._page_spin.setMinimum(1)
        self._page_spin.setMaximum(1)
        self._page_spin.setFixedWidth(64)
        self._page_spin.setToolTip("跳至頁面")
        self._syncing_page_spin = False
        self._page_spin.valueChanged.connect(self._on_page_spin_changed)
        tb.addWidget(self._page_spin)

        self._page_total_label = QLabel("/ -")
        self._page_total_label.setObjectName("pageTotalLabel")
        tb.addWidget(self._page_total_label)

        next_act = QAction("下一頁", self)
        next_act.setToolTip("下一頁")
        next_act.triggered.connect(self._next_page)
        tb.addAction(next_act)
        tb.addSeparator()

        # ── 縮放（精簡下拉）──────────────────────────────────
        self._zoom_combo = QComboBox()
        self._zoom_combo.setEditable(True)
        self._zoom_combo.setFixedWidth(76)
        self._zoom_combo.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._zoom_combo.addItems([
            "50%", "75%", "100%", "125%", "150%",
            "200%", "400%", "適合頁面", "適合寬度",
        ])
        self._zoom_combo.setCurrentText("100%")
        self._zoom_combo.activated.connect(self._on_zoom_combo_activated)
        self._zoom_combo.lineEdit().returnPressed.connect(self._on_zoom_combo_return)
        tb.addWidget(self._zoom_combo)

        self.addToolBarBreak()
        mark_tb = self.addToolBar("標記工具列")
        mark_tb.setIconSize(QSize(18, 18))
        mark_tb.setMovable(False)

        def _add(label, mode, tooltip=None):
            act = QAction(label, self)
            act.setCheckable(True)
            act.setData(mode)
            if tooltip:
                act.setToolTip(tooltip)
            act.triggered.connect(lambda checked, m=mode: self._set_tool(m))
            mark_tb.addAction(act)
            self._tool_actions[mode] = act

        # ── 常用（精簡，像 macOS Preview）──────────────────────
        _add("✋", ToolMode.HAND, "拖曳")
        _add("🔍", ToolMode.ZOOM, "放大")
        mark_tb.addSeparator()

        # ── 編輯 ──────────────────────────────────────────────
        _add("📝", ToolMode.TEXT_EDIT, "編輯文字")
        _add("🖼", ToolMode.IMAGE_EDIT, "編輯圖片")
        mark_tb.addSeparator()

        # ── 標記工具（像 Preview 的 Markup Toolbar）───────────
        _add("螢光筆", ToolMode.HIGHLIGHT)
        _add("底線", ToolMode.UNDERLINE)
        _add("文字", ToolMode.TEXT_BOX, "文字框")
        _add("便利貼", ToolMode.STICKY_NOTE)
        _add("畫筆", ToolMode.FREEHAND, "手繪")
        mark_tb.addSeparator()

        # ── 圖形 ──────────────────────────────────────────────
        # 用下拉選單收納所有圖形工具
        from PyQt6.QtWidgets import QToolButton
        shapes_btn = QToolButton()
        shapes_btn.setText("圖形 ▾")
        shapes_btn.setToolTip("矩形、圓形、線條、箭頭")
        shapes_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        shapes_menu = QMenu(self)
        for label, mode in [
            ("矩形", ToolMode.SHAPE_RECT),
            ("圓形", ToolMode.SHAPE_CIRCLE),
            ("線條", ToolMode.SHAPE_LINE),
            ("箭頭", ToolMode.SHAPE_ARROW),
        ]:
            act = shapes_menu.addAction(label)
            act.triggered.connect(lambda checked, m=mode: self._set_tool(m))
        shapes_btn.setMenu(shapes_menu)
        mark_tb.addWidget(shapes_btn)

        _add("圖章", ToolMode.STAMP)
        _add("塗黑", ToolMode.REDACT, "遮蔽塗黑")
        mark_tb.addSeparator()

        # ── 更多工具（收納較少使用的工具）────────────────────
        more_btn = QToolButton()
        more_btn.setText("更多 ▾")
        more_btn.setToolTip("更多標記工具")
        more_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        more_menu = QMenu(self)
        for label, mode in [
            ("刪除線", ToolMode.STRIKEOUT),
            ("標注框", ToolMode.CALLOUT),
            ("橡皮擦", ToolMode.ERASER),
            ("裁切", ToolMode.CROP),
            ("連結", ToolMode.LINK),
            ("表單", ToolMode.FORM_FIELD),
        ]:
            act = more_menu.addAction(label)
            act.triggered.connect(lambda checked, m=mode: self._set_tool(m))
        more_menu.addSeparator()
        for label, mode in [
            ("測量距離", ToolMode.MEASURE_DIST),
            ("測量面積", ToolMode.MEASURE_AREA),
        ]:
            act = more_menu.addAction(label)
            act.triggered.connect(lambda checked, m=mode: self._set_tool(m))
        more_btn.setMenu(more_menu)
        mark_tb.addWidget(more_btn)

    def _setup_statusbar(self):
        self._status_bar = self.statusBar()
        self._page_label = QLabel("第 - 頁，共 - 頁")
        self._status_bar.addWidget(self._page_label, 1)
        self._doc_state_label = QLabel("未開啟文件")
        self._doc_state_label.setObjectName("docStateLabel")
        self._status_bar.addPermanentWidget(self._doc_state_label)

        # ── 右側縮放控制區 ─────────────────────────────
        zoom_widget = QWidget()
        zoom_layout = QHBoxLayout(zoom_widget)
        zoom_layout.setContentsMargins(0, 0, 0, 0)
        zoom_layout.setSpacing(4)

        # 縮小按鈕
        self._zoom_out_btn = QLabel("−")
        self._zoom_out_btn.setObjectName("zoomOutBtn")
        self._zoom_out_btn.setFixedSize(26, 26)
        self._zoom_out_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_out_btn.setToolTip("縮小")
        self._zoom_out_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._zoom_out_btn.mousePressEvent = lambda e: self._zoom_out()
        zoom_layout.addWidget(self._zoom_out_btn)

        # 縮放滑桿
        self._zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self._zoom_slider.setObjectName("zoomSlider")
        self._zoom_slider.setFixedWidth(120)
        self._zoom_slider.setMinimum(10)    # 10%
        self._zoom_slider.setMaximum(400)   # 400%
        self._zoom_slider.setValue(100)
        self._zoom_slider.setToolTip("拖曳調整縮放比例")
        self._zoom_slider.valueChanged.connect(self._on_zoom_slider_changed)
        zoom_layout.addWidget(self._zoom_slider)

        # 放大按鈕
        self._zoom_in_btn = QLabel("+")
        self._zoom_in_btn.setObjectName("zoomInBtn")
        self._zoom_in_btn.setFixedSize(26, 26)
        self._zoom_in_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._zoom_in_btn.setToolTip("放大")
        self._zoom_in_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._zoom_in_btn.mousePressEvent = lambda e: self._zoom_in()
        zoom_layout.addWidget(self._zoom_in_btn)

        # 百分比標籤
        self._zoom_label = QLabel("100%")
        self._zoom_label.setObjectName("zoomPctLabel")
        self._zoom_label.setFixedWidth(42)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zoom_layout.addWidget(self._zoom_label)

        self._status_bar.addPermanentWidget(zoom_widget)
        self._syncing_zoom_slider = False
        self._pending_zoom_slider_value = 100
        self._zoom_slider_timer = QTimer(self)
        self._zoom_slider_timer.setSingleShot(True)
        self._zoom_slider_timer.timeout.connect(self._apply_pending_zoom_slider)

    # ── 主題切換 ─────────────────────────────────────────────────
    def _apply_theme(self, theme: str):
        qss_path = Path(__file__).parent.parent / "resources" / "styles" / f"{theme}.qss"
        if qss_path.exists():
            with open(qss_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    def _switch_theme(self, theme: str):
        self._config.theme = theme
        self._apply_theme(theme)
        self._theme_light_act.setChecked(theme == "light")
        self._theme_dark_act.setChecked(theme == "dark")
        # 通知所有 PDFView 更新 viewport 背景色
        bg_hex = "#e8e8ed" if theme == "light" else "#3a3a3c"
        for i in range(self._doc_tabs.count()):
            w = self._doc_tabs.widget(i)
            view = getattr(w, "_view", None) or (w if isinstance(w, PDFView) else None)
            if view and hasattr(view, "set_bg_color"):
                view.set_bg_color(bg_hex)

    # ── 頁面檢視模式 ────────────────────────────────────────────
    def _set_layout_mode(self, mode: LayoutMode):
        for m, act in self._view_mode_actions.items():
            act.setChecked(m == mode)
        self._config.layout_mode = mode
        view = self._current_view()
        if view:
            view.set_layout_mode(mode)

    # ── 全螢幕簡報 ──────────────────────────────────────────────
    def _start_presentation(self):
        doc = self._current_doc()
        if not doc or not doc.fitz_doc:
            QMessageBox.information(self, "提示", "請先開啟文件")
            return
        view = self._current_view()
        start = view.current_page() if view else 0
        from ui.viewer.presentation_view import PresentationView
        self._presentation_view = PresentationView(doc.fitz_doc, start_page=start)
        self._presentation_view.show()

    # ── 分割檢視 ────────────────────────────────────────────────
    def _toggle_split_view(self):
        view = self._current_view()
        if not view:
            return
        doc = self._current_doc()
        if not doc:
            return
        if self._split_action.isChecked():
            # 建立分割檢視
            from ui.viewer.split_view import SplitViewContainer
            idx = self._doc_tabs.currentIndex()
            container = SplitViewContainer(self)
            container.load_document(doc)
            container.primary_view.page_changed.connect(self._on_page_changed)
            container.primary_view.zoom_changed.connect(self._on_zoom_changed)
            container.primary_view.page_context_requested.connect(self._show_page_context_menu)
            self._doc_tabs.blockSignals(True)
            try:
                self._doc_tabs.removeTab(idx)
                self._doc_tabs.insertTab(idx, container, doc.display_name)
                self._doc_tabs.setCurrentIndex(idx)
            finally:
                self._doc_tabs.blockSignals(False)
        else:
            # 還原為單一檢視
            idx = self._doc_tabs.currentIndex()
            new_view = PDFView(self)
            new_view.load_document(doc)
            new_view.page_changed.connect(self._on_page_changed)
            new_view.zoom_changed.connect(self._on_zoom_changed)
            new_view.page_context_requested.connect(self._show_page_context_menu)
            self._doc_tabs.blockSignals(True)
            try:
                self._doc_tabs.removeTab(idx)
                self._doc_tabs.insertTab(idx, new_view, doc.display_name)
                self._doc_tabs.setCurrentIndex(idx)
            finally:
                self._doc_tabs.blockSignals(False)

    # ── 尺規 & 格線 ─────────────────────────────────────────────
    def _toggle_rulers(self):
        visible = self._ruler_action.isChecked()
        self._config.show_rulers = visible
        self._rulers_visible = visible
        view = self._current_view()
        if view:
            view.set_rulers_visible(visible)

    def _toggle_grid(self):
        visible = self._grid_action.isChecked()
        self._config.show_grid = visible
        self._grid_visible = visible
        view = self._current_view()
        if view:
            view.set_grid_visible(visible)

    # ── 關閉視窗時檢查未儲存文件 ──────────────────────────────────
    def closeEvent(self, event):
        unsaved = [d for d in self._docs if d.is_modified]
        if unsaved:
            names = "、".join(d.display_name for d in unsaved)
            reply = QMessageBox.question(
                self, "尚未儲存",
                f"以下文件尚未儲存：\n{names}\n\n是否在關閉前全部儲存？",
                QMessageBox.StandardButton.SaveAll |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if reply == QMessageBox.StandardButton.SaveAll:
                for doc in unsaved:
                    if doc.path:
                        doc.save()
                    else:
                        from PyQt6.QtWidgets import QFileDialog
                        path, _ = QFileDialog.getSaveFileName(
                            self, f"儲存「{doc.display_name}」", "",
                            "PDF 檔案 (*.pdf)"
                        )
                        if path:
                            doc.save(path)
                        else:
                            event.ignore()
                            return
        for doc in self._docs:
            try:
                doc.close()
            except Exception:
                pass
        self._docs.clear()
        event.accept()

    # ── 拖曳開檔 ─────────────────────────────────────────────────
    def dragEnterEvent(self, event):
        _DROP_EXTS = ('.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.tif',
                      '.bmp', '.gif', '.webp', '.svg',
                      '.docx', '.doc', '.xlsx', '.xls', '.pptx')
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(_DROP_EXTS):
                    event.acceptProposedAction()
                    return

    def dropEvent(self, event):
        _EXTS = ('.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.tif',
                 '.bmp', '.gif', '.webp', '.svg',
                 '.docx', '.doc', '.xlsx', '.xls', '.pptx')
        paths = []
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p and os.path.isfile(p) and p.lower().endswith(_EXTS):
                paths.append(p)
        if not paths:
            return

        doc = self._current_doc()
        if doc and any(not p.lower().endswith('.pdf') for p in paths):
            reply = QMessageBox.question(
                self, "拖曳檔案",
                f"要將 {len(paths)} 個檔案插入到目前文件嗎？\n"
                "選「是」插入到目前文件；選「否」以新分頁開啟。",
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.No |
                QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            if reply == QMessageBox.StandardButton.Yes:
                view = self._current_view()
                insert_at = (view.current_page() + 1) if view else doc.page_count
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                try:
                    for p in paths:
                        doc.pages.insert_file(p, insert_at)
                        insert_at += 1
                except Exception as e:
                    QMessageBox.warning(self, "錯誤", f"無法插入：{e}")
                finally:
                    QApplication.restoreOverrideCursor()
                return

        for p in paths:
            try:
                self.open_file(p)
            except Exception:
                pass

    # ── 文件管理 ─────────────────────────────────────────────────
    def open_file(self, path: str):
        abs_path = os.path.abspath(path)
        for i, d in enumerate(self._docs):
            if d.path and os.path.abspath(d.path) == abs_path:
                self._doc_tabs.setCurrentIndex(i)
                return
        doc = self._open_document_with_password(path)
        if doc is None:
            return
        self._add_doc_tab(doc)
        self._config.add_recent_file(path)
        self._update_recent_menu()

    def _open_document_with_password(self, path: str) -> PDFDocument | None:
        doc = PDFDocument(self)
        if doc.open(path):
            return doc

        if self._path_needs_password(path):
            name = os.path.basename(path)
            while True:
                password, ok = QInputDialog.getText(
                    self, "需要密碼",
                    f"「{name}」已受密碼保護，請輸入密碼：",
                    QLineEdit.EchoMode.Password,
                )
                if not ok:
                    return None
                doc = PDFDocument(self)
                if doc.open(path, password):
                    return doc
                retry = QMessageBox.question(
                    self, "密碼錯誤",
                    "密碼不正確。要重新輸入嗎？",
                    QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Cancel,
                )
                if retry != QMessageBox.StandardButton.Retry:
                    return None

        QMessageBox.warning(self, "錯誤", f"無法開啟：{path}")
        return None

    @staticmethod
    def _path_needs_password(path: str) -> bool:
        try:
            doc = fitz.open(path)
            try:
                return bool(doc.needs_pass)
            finally:
                doc.close()
        except Exception:
            return False

    def open_file_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "開啟檔案", "",
            "所有支援格式 (*.pdf *.png *.jpg *.jpeg *.bmp *.tiff *.tif "
            "*.gif *.webp *.svg *.docx *.doc *.xlsx *.xls *.pptx);;"
            "PDF 檔案 (*.pdf);;"
            "圖片 (*.png *.jpg *.jpeg *.bmp *.tiff *.tif *.gif *.webp *.svg);;"
            "Word (*.docx *.doc);;Excel (*.xlsx *.xls);;PowerPoint (*.pptx);;"
            "所有檔案 (*)"
        )
        failed: list[str] = []
        for p in paths:
            try:
                self.open_file(p)
            except Exception as e:
                failed.append(f"{os.path.basename(p)}：{e}")
            QApplication.processEvents()
        if failed:
            QMessageBox.warning(self, "部分檔案無法開啟", "\n".join(failed))

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
        self._docs.append(doc)
        self._doc_tabs.blockSignals(True)
        try:
            idx = self._doc_tabs.addTab(view, name)
            self._doc_tabs.setCurrentIndex(idx)
        finally:
            self._doc_tabs.blockSignals(False)
        self._workspace_stack.setCurrentWidget(self._doc_tabs)

        self._thumbnail_panel.load_document(doc)
        self._bookmark_panel.load_document(doc)
        self._update_title()
        self._on_page_count_changed(doc, doc.page_count)
        self._refresh_workspace_state()
        QTimer.singleShot(0, view.fit_width)
        QTimer.singleShot(0, lambda: self._set_tool(ToolMode.HAND))

        doc.page_count_changed.connect(lambda count: self._on_page_count_changed(doc, count))
        doc.document_modified.connect(lambda: self._on_doc_modified(doc))

    def _close_tab(self, index: int):
        if index < 0 or index >= len(self._docs):
            return
        doc = self._docs[index]
        if doc.is_modified:
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
                if doc.path:
                    doc.save()
                else:
                    path, _ = QFileDialog.getSaveFileName(
                        self, f"儲存「{doc.display_name}」", "",
                        "PDF 檔案 (*.pdf)"
                    )
                    if path:
                        doc.save(path)
                    else:
                        return
        try:
            doc.page_count_changed.disconnect()
            doc.document_modified.disconnect()
        except (TypeError, RuntimeError):
            pass
        self._thumbnail_panel.invalidate_cache(doc)
        self._docs.pop(index)
        self._doc_tabs.blockSignals(True)
        try:
            self._doc_tabs.removeTab(index)
        finally:
            self._doc_tabs.blockSignals(False)
        doc.close()
        self._on_tab_changed(self._doc_tabs.currentIndex())
        self._refresh_workspace_state()

    def _close_current_tab(self):
        self._close_tab(self._doc_tabs.currentIndex())

    def _detach_tab(self, index: int):
        """把分頁拖離 tab bar → 在新視窗開啟該文件。"""
        if index < 0 or index >= len(self._docs):
            return
        doc = self._docs[index]

        # 先從目前視窗移除（不關閉 doc）
        try:
            doc.page_count_changed.disconnect()
            doc.document_modified.disconnect()
        except (TypeError, RuntimeError):
            pass
        self._thumbnail_panel.invalidate_cache(doc)
        self._docs.pop(index)
        self._doc_tabs.blockSignals(True)
        try:
            self._doc_tabs.removeTab(index)
        finally:
            self._doc_tabs.blockSignals(False)
        self._on_tab_changed(self._doc_tabs.currentIndex())
        self._refresh_workspace_state()

        # 建立新視窗，把 doc 加進去
        from ui.main_window import MainWindow
        new_win = MainWindow()
        new_win._add_doc_tab(doc)
        new_win.show()
        new_win.raise_()
        # 把新視窗放到滑鼠游標附近
        from PyQt6.QtGui import QCursor
        pos = QCursor.pos()
        new_win.move(pos.x() - 100, pos.y() - 40)

    def _on_tab_changed(self, index: int):
        self._search_results = []
        self._search_index = -1
        self._search_text = ""
        if self._search_bar.isVisible():
            self._search_bar.set_result_count(0, 0)
        if 0 <= index < len(self._docs):
            doc = self._docs[index]
            self._thumbnail_panel.load_document(doc)
            self._bookmark_panel.load_document(doc)
            self._update_title()
        else:
            self._thumbnail_panel.clear()
            self._thumbnail_panel._current_doc = None
            self._bookmark_panel.clear()
            self._page_label.setText("第 - 頁，共 - 頁")
            self._zoom_label.setText("-")
            self._page_total_label.setText("/ -")
            self._syncing_page_spin = True
            self._page_spin.setMaximum(1)
            self._page_spin.setValue(1)
            self._syncing_page_spin = False
            self.setWindowTitle("AcroPDF")
        self._update_document_status()
        self._refresh_workspace_state()

    def _refresh_workspace_state(self):
        if hasattr(self, "_close_pdf_btn"):
            self._close_pdf_btn.setEnabled(bool(self._docs))
        if self._docs:
            self._workspace_stack.setCurrentWidget(self._doc_tabs)
        else:
            self._welcome_panel.refresh_recent()
            self._workspace_stack.setCurrentWidget(self._welcome_panel)

    def _set_side_page(self, index: int):
        if 0 <= index < self._side_stack.count():
            self._side_stack.setCurrentIndex(index)
            if self._side_stack.currentWidget() is self._thumbnail_panel:
                self._thumbnail_panel._schedule_visible_thumbnail_render()
            button = self._nav_group.button(index)
            if button:
                button.setChecked(True)

    def _show_tools_center(self):
        self._set_side_page(1)

    def _show_thumbnails(self):
        self._set_side_page(2)

    def _current_view(self) -> PDFView | None:
        w = self._doc_tabs.currentWidget()
        if isinstance(w, PDFView):
            return w
        # 分割檢視容器
        if hasattr(w, 'primary_view'):
            return w.primary_view
        return None

    def _current_doc(self) -> PDFDocument | None:
        idx = self._doc_tabs.currentIndex()
        return self._docs[idx] if 0 <= idx < len(self._docs) else None

    def _selected_pages(self, fallback_current: bool = True) -> list[int]:
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
                if not doc.save():
                    QMessageBox.warning(self, "儲存失敗", "無法儲存檔案，請確認路徑與權限。")
                else:
                    self._update_title()
            else:
                self.save_as()

    def save_as(self):
        doc = self._current_doc()
        if not doc:
            return

        # 檔案類型篩選器（PDF 排第一＝預設）
        filters = (
            "PDF 檔案 (*.pdf);;"
            "Word 文件 (*.docx);;"
            "Excel 活頁簿 (*.xlsx);;"
            "PowerPoint 簡報 (*.pptx);;"
            "PNG 圖片 (*.png);;"
            "純文字 (*.txt);;"
            "HTML 網頁 (*.html);;"
            "PDF/A 檔案 (*.pdf)"
        )

        from ui.dialogs.export.export_dialog import default_export_path, ensure_export_suffix
        default_name = default_export_path(doc, "pdf")

        path, selected_filter = QFileDialog.getSaveFileName(
            self, "另存新檔", default_name, filters
        )
        if not path:
            return

        # 根據使用者選的篩選器判斷格式
        if selected_filter.startswith("Word"):
            path = ensure_export_suffix(path, "docx")
            self._export_save_as(doc, path, "docx")
        elif selected_filter.startswith("Excel"):
            path = ensure_export_suffix(path, "xlsx")
            self._export_save_as(doc, path, "xlsx")
        elif selected_filter.startswith("PowerPoint"):
            path = ensure_export_suffix(path, "pptx")
            self._export_save_as(doc, path, "pptx")
        elif selected_filter.startswith("PNG"):
            path = ensure_export_suffix(path, "png")
            self._export_save_as(doc, path, "png")
        elif selected_filter.startswith("純文字"):
            path = ensure_export_suffix(path, "txt")
            self._export_save_as(doc, path, "txt")
        elif selected_filter.startswith("HTML"):
            path = ensure_export_suffix(path, "html")
            self._export_save_as(doc, path, "html")
        elif selected_filter.startswith("PDF/A"):
            path = ensure_export_suffix(path, "pdfa")
            self._export_save_as(doc, path, "pdfa")
        else:
            # 預設：PDF
            path = ensure_export_suffix(path, "pdf")
            if not doc.save(path):
                QMessageBox.warning(self, "儲存失敗", "無法儲存檔案，請確認路徑與權限。")
            else:
                self._update_title()

    def _export_save_as(self, doc, path: str, fmt: str):
        """另存新檔時匯出為非 PDF 格式"""
        try:
            doc.exports.export(path, fmt)
            QMessageBox.information(self, "匯出完成", f"已儲存至：\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "匯出失敗", f"無法匯出檔案：\n{e}")

    # ── 列印 ──────────────────────────────────────────────────────
    def _print_document(self):
        from PyQt6.QtPrintSupport import QPrinter
        from PyQt6.QtGui import QPainter, QImage
        from ui.dialogs.print_dialog import PrintDialog
        import fitz

        doc = self._current_doc()
        if not doc or doc.fitz_doc is None:
            QMessageBox.warning(self, "提示", "沒有可列印的文件")
            return

        view = self._current_view()
        current_page = view.current_page() if view else 0
        dialog = PrintDialog(doc.page_count, current_page, self)
        if dialog.exec() != PrintDialog.DialogCode.Accepted:
            return
        settings = dialog.settings()

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setDocName(doc.display_name)
        printer.setCopyCount(settings.copies)
        printer.setDuplex(settings.duplex_mode)
        if settings.output_pdf_path:
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(settings.output_pdf_path)
        else:
            printer.setPrinterName(settings.printer_name)

        painter = QPainter()
        if not painter.begin(printer):
            QMessageBox.warning(self, "錯誤", "無法啟動列印")
            return

        fitz_doc = doc.fitz_doc
        dpi = printer.resolution()

        try:
            for pos, page_index in enumerate(settings.page_indices):
                QApplication.processEvents()
                if pos > 0:
                    printer.newPage()
                page = fitz_doc[page_index]
                zoom = dpi / 72.0
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = QImage(pix.samples_ptr, pix.width, pix.height,
                             pix.stride, QImage.Format.Format_RGB888).copy()
                target = printer.pageRect(QPrinter.Unit.DevicePixel)
                scaled = img.scaled(
                    int(target.width()), int(target.height()),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                x = int((target.width() - scaled.width()) / 2)
                y = int((target.height() - scaled.height()) / 2)
                painter.drawImage(x, y, scaled)
        except Exception as e:
            QMessageBox.warning(self, "列印錯誤", f"列印第 {page_index + 1} 頁時發生錯誤：{e}")
        finally:
            painter.end()
        if settings.output_pdf_path:
            QMessageBox.information(self, "列印完成", f"PDF 已輸出至：\n{settings.output_pdf_path}")

    # ── 右鍵選單 ─────────────────────────────────────────────────
    def _thumb_context_action(self, action_id: str, indices: list[int]):
        doc = self._current_doc()
        if not doc or not indices:
            return

        if action_id == "delete":
            n = len(indices)
            if QMessageBox.question(
                self, "確認刪除", f"確定要刪除第 {', '.join(str(i+1) for i in indices)} 頁（共 {n} 頁）？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) == QMessageBox.StandardButton.Yes:
                try:
                    doc.pages.delete(indices)
                except ValueError as e:
                    QMessageBox.warning(self, "無法刪除", str(e))

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
            _INS_FILTER = (
                "所有支援格式 (*.pdf *.png *.jpg *.jpeg *.bmp *.tiff *.tif "
                "*.gif *.webp *.svg *.docx *.doc *.xlsx *.xls *.pptx);;"
                "PDF 檔案 (*.pdf);;"
                "圖片 (*.png *.jpg *.jpeg *.bmp *.tiff *.tif *.gif *.webp *.svg);;"
                "Word (*.docx *.doc);;Excel (*.xlsx *.xls);;PowerPoint (*.pptx);;"
                "所有檔案 (*)"
            )
            path, _ = QFileDialog.getOpenFileName(
                self, "選擇要插入的檔案", "", _INS_FILTER
            )
            if path:
                try:
                    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                    doc.pages.insert_file(path, indices[0])
                except (RuntimeError, ValueError, Exception) as e:
                    QMessageBox.warning(self, "錯誤", f"無法插入：{e}")
                finally:
                    QApplication.restoreOverrideCursor()

        elif action_id == "replace":
            path, _ = QFileDialog.getOpenFileName(
                self, "選擇取代來源 PDF", "", "PDF 檔案 (*.pdf)"
            )
            if path:
                import fitz
                try:
                    src = fitz.open(path)
                except Exception as e:
                    QMessageBox.warning(self, "錯誤", f"無法開啟來源檔案：{e}")
                    return
                fd = doc.fitz_doc
                if fd is not None:
                    doc.begin_op("取代頁面")
                    try:
                        for i, dest_idx in enumerate(sorted(indices)):
                            if i < src.page_count and 0 <= dest_idx < fd.page_count:
                                fd[dest_idx].show_pdf_page(fd[dest_idx].rect, src, i)
                    finally:
                        doc.end_op()
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
        doc = self._current_doc()
        if not doc:
            return

        menu = QMenu(self)
        # 不設 inline stylesheet — 由 QSS 主題檔控制

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

        # ── 編輯 ──────────────────────────────────
        menu.addAction("編輯文字",
                       lambda: self._set_tool(ToolMode.TEXT_EDIT))
        menu.addAction("插入 / 編輯圖片",
                       lambda: self._set_tool(ToolMode.IMAGE_EDIT))
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
        page_submenu.addAction("從檔案插入...",
                               lambda: self._thumb_context_action("insert_from_file", [page_num + 1]))
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
            try:
                doc.pages.delete(indices)
            except ValueError as e:
                QMessageBox.warning(self, "無法刪除", str(e))

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
            doc.pages.insert_blank(view.current_page() + 1)

    def _insert_from_file(self):
        doc = self._current_doc()
        view = self._current_view()
        if not doc:
            return
        _INS_FILTER = (
            "所有支援格式 (*.pdf *.png *.jpg *.jpeg *.bmp *.tiff *.tif "
            "*.gif *.webp *.svg *.docx *.doc *.xlsx *.xls *.pptx);;"
            "PDF 檔案 (*.pdf);;"
            "圖片 (*.png *.jpg *.jpeg *.bmp *.tiff *.tif *.gif *.webp *.svg);;"
            "Word (*.docx *.doc);;Excel (*.xlsx *.xls);;PowerPoint (*.pptx);;"
            "所有檔案 (*)"
        )
        paths, _ = QFileDialog.getOpenFileNames(
            self, "選擇要插入的檔案", "", _INS_FILTER
        )
        if not paths:
            return
        insert_at = (view.current_page() + 1) if view else doc.page_count
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for p in paths:
                doc.pages.insert_file(p, insert_at)
                insert_at += 1
        except (RuntimeError, ValueError, Exception) as e:
            QMessageBox.warning(self, "錯誤", f"無法插入：{e}")
        finally:
            QApplication.restoreOverrideCursor()

    def _extract_pages(self):
        doc = self._current_doc()
        if not doc:
            return
        indices = self._selected_pages(fallback_current=False)
        from ui.dialogs.page_ops.extract_dialog import ExtractDialog
        ExtractDialog(doc, indices, self).exec()

    def _merge_pdf(self):
        _MERGE_FILTER = (
            "所有支援格式 (*.pdf *.png *.jpg *.jpeg *.bmp *.tiff *.tif "
            "*.gif *.webp *.svg *.docx *.doc *.xlsx *.xls *.pptx);;"
            "PDF 檔案 (*.pdf);;"
            "圖片 (*.png *.jpg *.jpeg *.bmp *.tiff *.tif *.gif *.webp *.svg);;"
            "Word (*.docx *.doc);;Excel (*.xlsx *.xls);;PowerPoint (*.pptx);;"
            "所有檔案 (*)"
        )
        path, _ = QFileDialog.getOpenFileName(
            self, "選擇要合併的檔案", "", _MERGE_FILTER
        )
        if path:
            doc = self._current_doc()
            if doc:
                try:
                    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                    doc.pages.insert_file(path)
                except (RuntimeError, ValueError, Exception) as e:
                    QMessageBox.warning(self, "錯誤", f"無法合併：{e}")
                finally:
                    QApplication.restoreOverrideCursor()

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
                try:
                    doc.pages.add_watermark(text)
                except Exception as e:
                    QMessageBox.warning(self, "錯誤", f"無法加浮水印：{e}")

    def _header_footer_dialog(self):
        from ui.dialogs.page_ops.header_footer_dialog import HeaderFooterDialog
        doc = self._current_doc()
        if doc:
            HeaderFooterDialog(doc, self).exec()

    def _bates_dialog(self):
        doc = self._current_doc()
        if not doc:
            return
        from ui.dialogs.bates.bates_dialog import BatesDialog
        dlg = BatesDialog(doc, self)
        if dlg.exec():
            view = self._current_view()
            if view:
                view.refresh()

    def _background_dialog(self):
        doc = self._current_doc()
        if not doc:
            return
        from ui.dialogs.background.background_dialog import BackgroundDialog
        dlg = BackgroundDialog(doc, self)
        if dlg.exec():
            view = self._current_view()
            if view:
                view.refresh()

    # ── 導覽 ─────────────────────────────────────────────────────
    def _goto_page(self, page_num: int):
        view = self._current_view()
        if view:
            view.go_to_page(page_num)

    def _prev_page(self):
        view = self._current_view()
        if view:
            view.go_to_page(view.current_page() - 1)

    def _next_page(self):
        view = self._current_view()
        doc = self._current_doc()
        if view and doc:
            view.go_to_page(min(view.current_page() + 1, doc.page_count - 1))

    def _on_page_spin_changed(self, value: int):
        if self._syncing_page_spin:
            return
        self._goto_page(value - 1)

    # ── 書籤操作 ──────────────────────────────────────────────
    def _add_bookmark(self):
        doc = self._current_doc()
        if not doc:
            return
        view = self._current_view()
        page_num = view.current_page() if view else 0
        default_title = f"第 {page_num + 1} 頁"
        title, ok = QInputDialog.getText(
            self, "新增書籤", "書籤名稱：", text=default_title
        )
        if ok and title.strip():
            doc.bookmarks.add(title.strip(), page_num)
            self._bookmark_panel.load_document(doc, force_reload=True)

    def _delete_bookmark(self, index: int):
        doc = self._current_doc()
        if not doc:
            return
        doc.bookmarks.delete(index)
        self._bookmark_panel.load_document(doc, force_reload=True)

    def _rename_bookmark(self, index: int, new_title: str):
        doc = self._current_doc()
        if not doc:
            return
        doc.bookmarks.rename(index, new_title)
        self._bookmark_panel.load_document(doc, force_reload=True)

    def _goto_page_dialog(self):
        doc = self._current_doc()
        if not doc or doc.page_count == 0:
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
        if total > 0:
            page_num = max(0, min(page_num, total - 1))
        self._page_label.setText(f"第 {page_num+1} 頁，共 {total} 頁")
        self._syncing_page_spin = True
        self._page_spin.setMaximum(max(total, 1))
        self._page_spin.setValue(page_num + 1 if total else 1)
        self._page_total_label.setText(f"/ {total}" if total else "/ -")
        self._syncing_page_spin = False
        self._thumbnail_panel._syncing_page = True
        self._thumbnail_panel.blockSignals(True)
        try:
            self._thumbnail_panel.setCurrentRow(page_num)
        finally:
            self._thumbnail_panel.blockSignals(False)
            self._thumbnail_panel._syncing_page = False

    def _on_zoom_changed(self, zoom: float):
        pct = f"{zoom*100:.0f}%"
        self._zoom_label.setText(pct)
        self._zoom_combo.blockSignals(True)
        self._zoom_combo.setCurrentText(pct)
        self._zoom_combo.blockSignals(False)
        # 同步狀態列滑桿
        self._syncing_zoom_slider = True
        self._zoom_slider.setValue(int(zoom * 100))
        self._syncing_zoom_slider = False

    def _on_zoom_slider_changed(self, value: int):
        if self._syncing_zoom_slider:
            return
        self._pending_zoom_slider_value = value
        self._zoom_label.setText(f"{value}%")
        self._zoom_slider_timer.start(90)

    def _apply_pending_zoom_slider(self):
        view = self._current_view()
        if view:
            view.set_zoom(self._pending_zoom_slider_value / 100.0)

    def _on_page_count_changed(self, doc: PDFDocument, count: int):
        if self._current_doc() is not doc:
            return
        self._thumbnail_panel.invalidate_cache(doc)
        self._thumbnail_panel.load_document(doc, force_reload=True)
        self._bookmark_panel.load_document(doc, force_reload=True)
        view = self._current_view()
        cur = view.current_page() if view else 0
        if count > 0:
            cur = min(cur, count - 1)
        self._page_label.setText(f"第 {cur+1} 頁，共 {count} 頁")
        self._syncing_page_spin = True
        self._page_spin.setMaximum(max(count, 1))
        self._page_spin.setValue(cur + 1 if count else 1)
        self._page_total_label.setText(f"/ {count}" if count else "/ -")
        self._syncing_page_spin = False

    def _update_title(self):
        doc = self._current_doc()
        if not doc:
            self.setWindowTitle("AcroPDF")
            self._update_document_status()
            return
        name = doc.display_name
        mark = " *" if doc.is_modified else ""
        self.setWindowTitle(f"{name}{mark} — AcroPDF")
        idx = self._doc_tabs.currentIndex()
        if 0 <= idx < self._doc_tabs.count():
            self._doc_tabs.setTabText(idx, f"{name}{mark}")
        self._update_document_status()

    def _update_document_status(self):
        doc = self._current_doc()
        if not doc or not doc.fitz_doc:
            self._doc_state_label.setText("未開啟文件")
            return
        bits = []
        bits.append("受保護" if doc.fitz_doc.needs_pass else "未加密")
        if doc.is_modified:
            bits.append("已修改")
        self._doc_state_label.setText(" · ".join(bits))

    def _on_doc_modified(self, doc: PDFDocument):
        if self._current_doc() is not doc:
            return
        # 只更新目前可見頁的縮圖（最常見情境：加標注、改文字）
        view = self._current_view()
        if view:
            page = view.current_page()
            self._thumbnail_panel.update_page_thumbnail(page)
        self._update_title()

        # debounce 完整縮圖重建（若頁數改變則透過 page_count_changed 處理）
        if not hasattr(self, "_thumb_refresh_timer"):
            self._thumb_refresh_timer = QTimer(self)
            self._thumb_refresh_timer.setSingleShot(True)
            self._thumb_refresh_timer.timeout.connect(self._deferred_thumb_refresh)
        self._thumb_refresh_timer.start(600)   # 600ms 後若無新事件才整份刷新

    def _deferred_thumb_refresh(self):
        doc = self._current_doc()
        if not doc:
            return
        # 僅在頁數不符時才整份重載；一般加標注不會改變頁數
        if self._thumbnail_panel.count() != doc.page_count:
            self._thumbnail_panel.load_document(doc, force_reload=True)

    def _on_zoom_combo_activated(self, index: int):
        text = self._zoom_combo.itemText(index)
        self._apply_zoom_text(text)

    def _on_zoom_combo_return(self):
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
        view.set_tool(tool)
        if mode == ToolMode.HAND:
            view.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        elif mode == ToolMode.ZOOM:
            view.viewport().setCursor(Qt.CursorShape.CrossCursor)
        elif mode == ToolMode.TEXT_EDIT:
            view.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        elif mode == ToolMode.IMAGE_EDIT:
            view.viewport().setCursor(Qt.CursorShape.CrossCursor)
        else:
            view.viewport().unsetCursor()

    # ── 最近檔案 ─────────────────────────────────────────────────
    def _update_recent_menu(self):
        self._recent_menu.clear()
        for path in self._config.recent_files:
            act = QAction(os.path.basename(path), self)
            act.setToolTip(path)
            act.triggered.connect(lambda checked, p=path: self.open_file(p))
            self._recent_menu.addAction(act)

    # ── 搜尋 ─────────────────────────────────────────────────────
    def _toggle_search(self):
        if self._search_bar.isVisible():
            self._search_bar.hide()
            self._search_bar.closed.emit()
        else:
            self._search_bar.focus_input()

    def _on_search(self, text: str):
        doc = self._current_doc()
        if not doc or not doc.fitz_doc:
            self._search_results = []
            self._search_index = -1
            self._search_bar.set_result_count(0, 0)
            return

        self._search_text = text
        self._search_results = []
        fitz_doc = doc.fitz_doc

        for page_num in range(fitz_doc.page_count):
            rects = fitz_doc[page_num].search_for(text)
            for rect in rects:
                self._search_results.append((page_num, rect))

        total = len(self._search_results)
        if total > 0:
            self._search_index = 0
            self._navigate_to_search_result()
        else:
            self._search_index = -1
            self._search_bar.set_result_count(0, 0)

    def _on_search_next(self):
        if not self._search_results:
            text = self._search_bar._input.text().strip()
            if text and text != self._search_text:
                self._on_search(text)
            return
        self._search_index = (self._search_index + 1) % len(self._search_results)
        self._navigate_to_search_result()

    def _on_search_prev(self):
        if not self._search_results:
            return
        self._search_index = (self._search_index - 1) % len(self._search_results)
        self._navigate_to_search_result()

    def _navigate_to_search_result(self):
        if not self._search_results or self._search_index < 0:
            return
        page_num, rect = self._search_results[self._search_index]
        view = self._current_view()
        if view:
            view.go_to_page(page_num)
        total = len(self._search_results)
        self._search_bar.set_result_count(self._search_index + 1, total)

    def _on_search_closed(self):
        self._search_results = []
        self._search_index = -1
        self._search_text = ""

    # ── 新功能對話框 ─────────────────────────────────────────────
    def _layer_dialog(self):
        doc = self._current_doc()
        if not doc:
            return
        from ui.dialogs.layer.layer_dialog import LayerDialog
        LayerDialog(doc, self).exec()
        view = self._current_view()
        if view:
            view.refresh()

    def _attachment_dialog(self):
        doc = self._current_doc()
        if not doc:
            return
        from ui.dialogs.attachment.attachment_dialog import AttachmentDialog
        AttachmentDialog(doc, self).exec()

    def _custom_stamp_dialog(self):
        from ui.dialogs.custom_stamp.custom_stamp_dialog import CustomStampDialog
        dlg = CustomStampDialog(self)
        if dlg.exec():
            stamp_path = dlg.get_stamp_path()
            if stamp_path:
                # 用選中的自訂圖章當圖片插入
                doc = self._current_doc()
                view = self._current_view()
                if doc and view and doc.fitz_doc:
                    page_num = view.current_page()
                    page = doc.fitz_doc[page_num]
                    # 在頁面中央插入圖章圖片
                    cx, cy = page.rect.width / 2, page.rect.height / 2
                    import fitz
                    stamp_rect = fitz.Rect(cx - 60, cy - 40, cx + 60, cy + 40)
                    doc.begin_op("自訂圖章")
                    try:
                        page.insert_image(stamp_rect, filename=stamp_path)
                    except Exception as e:
                        QMessageBox.warning(self, "錯誤", f"無法插入圖章：{e}")
                    doc.end_op()
                    doc._mark_modified()

    def _annot_summary_dialog(self):
        doc = self._current_doc()
        if not doc:
            return
        from ui.dialogs.annot_summary.annot_summary_dialog import AnnotSummaryDialog
        AnnotSummaryDialog(doc, self).exec()

    def _accessibility_dialog(self):
        doc = self._current_doc()
        if not doc:
            return
        from ui.dialogs.accessibility.accessibility_dialog import AccessibilityDialog
        AccessibilityDialog(doc, self).exec()
        view = self._current_view()
        if view:
            view.refresh()

    def _ai_summary_dialog(self):
        doc = self._current_doc()
        if not doc:
            return
        from ui.dialogs.ai.summary_dialog import SummaryDialog
        SummaryDialog(doc, self).exec()

    def _ai_translate_dialog(self):
        doc = self._current_doc()
        if not doc:
            return
        from ui.dialogs.ai.translate_dialog import TranslateDialog
        TranslateDialog(doc, self).exec()
        view = self._current_view()
        if view:
            view.refresh()

    def _export_pdfx_dialog(self):
        doc = self._current_doc()
        if not doc:
            return
        from ui.dialogs.export.pdfx_dialog import PDFXDialog
        PDFXDialog(doc, self).exec()

    # ── Phase 2/3/4 對話框 ───────────────────────────────────────
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

    def _auto_label_dialog(self):
        from ui.dialogs.auto_label.auto_label_dialog import AutoLabelDialog
        doc = self._current_doc()
        if not doc:
            return
        dlg = AutoLabelDialog(doc, self)
        if dlg.exec():
            view = self._current_view()
            if view:
                view.refresh()

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

    def _document_properties_dialog(self):
        doc = self._current_doc()
        if not doc:
            QMessageBox.information(self, "提示", "請先開啟文件")
            return
        from ui.dialogs.document_properties_dialog import DocumentPropertiesDialog
        dlg = DocumentPropertiesDialog(doc, self)
        if dlg.exec():
            self._update_title()

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

    # ── Phase 1-4 新增對話框 ─────────────────────────────────────
    def _redaction_dialog(self):
        from ui.dialogs.redaction.redaction_dialog import RedactionDialog
        doc = self._current_doc()
        if not doc:
            return
        dlg = RedactionDialog(doc, self)
        dlg.exec()
        view = self._current_view()
        if view:
            view.refresh()

    def _form_designer_dialog(self):
        from ui.dialogs.forms.form_designer_dialog import FormDesignerDialog
        doc = self._current_doc()
        if not doc:
            return
        FormDesignerDialog(doc, self).exec()
        view = self._current_view()
        if view:
            view.refresh()

    def _preflight_dialog(self):
        from ui.dialogs.preflight.preflight_dialog import PreflightDialog
        doc = self._current_doc()
        if not doc:
            return
        PreflightDialog(doc, self).exec()

    def _font_dialog(self):
        from ui.dialogs.fonts.font_dialog import FontDialog
        doc = self._current_doc()
        if not doc:
            return
        FontDialog(doc, self).exec()

    def _magi_dialog(self):
        from ui.dialogs.ai.magi_dialog import MAGIDialog
        doc = self._current_doc()
        if not doc:
            return
        MAGIDialog(doc, self).exec()

    def _reflow_dialog(self):
        from ui.dialogs.reflow.reflow_dialog import ReflowDialog
        doc = self._current_doc()
        if not doc:
            return
        ReflowDialog(doc, self).exec()

    def _filing_dialog(self):
        from ui.dialogs.filing.filing_dialog import FilingDialog
        FilingDialog(self).exec()

    def _template_dialog(self):
        from ui.dialogs.templates.template_dialog import TemplateDialog
        doc = self._current_doc()
        TemplateDialog(doc, self).exec()
