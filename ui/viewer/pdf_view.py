# ~/Desktop/acropdf/ui/viewer/pdf_view.py
import fitz
from PyQt6.QtWidgets import (QScrollArea, QWidget, QVBoxLayout,
                              QHBoxLayout, QSizePolicy, QFrame)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPoint
from PyQt6.QtGui import QWheelEvent

from app.constants import LayoutMode, DEFAULT_ZOOM, ZOOM_LEVELS
from core.document import PDFDocument
from rendering.renderer import PageRenderer
from rendering.cache import PixmapCache
from ui.viewer.page_widget import PageWidget

class PDFView(QScrollArea):
    page_changed = pyqtSignal(int)
    zoom_changed = pyqtSignal(float)
    document_loaded = pyqtSignal()
    page_context_requested = pyqtSignal(int, QPoint)   # page_num, global_pos

    def __init__(self, parent=None):
        super().__init__(parent)
        self._doc: PDFDocument | None = None
        self._zoom = DEFAULT_ZOOM
        self._layout_mode = LayoutMode.CONTINUOUS
        self._current_page = 0
        self._page_widgets: list[PageWidget] = []
        self._cache = PixmapCache()
        self._active_tool = None
        self._pending_signals: list = []  # 防止 RenderSignals 被 GC

        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._container_layout.setSpacing(8)
        self._container_layout.setContentsMargins(16, 16, 16, 16)
        self.setWidget(self._container)

        # 捲動監控（更新目前頁碼）
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def load_document(self, doc: PDFDocument):
        self._doc = doc
        self._cache.invalidate()
        self._rebuild_pages()
        self.document_loaded.emit()
        doc.document_modified.connect(self._on_document_modified)
        doc.document_saved.connect(self._on_document_saved)

    def _rebuild_pages(self):
        # 清除舊 widgets
        for w in self._page_widgets:
            w.deleteLater()
        self._page_widgets.clear()

        if not self._doc or not self._doc.fitz_doc:
            return

        for i in range(self._doc.page_count):
            pw = PageWidget(i, self._container)
            if self._active_tool:
                pw.set_tool(self._active_tool)
            pw.context_requested.connect(self.page_context_requested)
            # 用 fitz 頁面尺寸設定初始佔位大小，讓 layout 知道高度
            page = self._doc.fitz_doc[i]
            pw.setFixedSize(
                int(page.rect.width * self._zoom),
                int(page.rect.height * self._zoom),
            )
            self._container_layout.addWidget(pw)
            self._page_widgets.append(pw)

        # 強制容器更新大小
        self._container.adjustSize()

        # 非同步渲染可見頁面
        QTimer.singleShot(0, self._render_visible_pages)

    def _render_visible_pages(self):
        if not self._doc or not self._doc.fitz_doc:
            return
        for i, pw in enumerate(self._page_widgets):
            # 檢查是否在可見區域附近（±3頁）
            if abs(i - self._current_page) <= 3:
                cached = self._cache.get(i, self._zoom, 0)
                if cached:
                    pw.set_pixmap(cached, self._zoom)
                elif self._doc.path and not self._doc.is_modified:
                    # 有檔案路徑且未修改：非同步渲染（背景執行緒）
                    sig = PageRenderer.make_signals()
                    sig.done.connect(self._on_render_done)
                    self._pending_signals.append(sig)
                    PageRenderer.start_worker(self._doc.path, i, self._zoom, sig)
                else:
                    # 無檔案路徑或有未儲存修改：同步渲染（使用記憶體中的 fitz doc）
                    pm = PageRenderer.render_page_sync(self._doc.fitz_doc[i], self._zoom)
                    self._on_render_done(i, self._zoom, pm)

    def _on_render_done(self, page_num: int, zoom: float, pm):
        self._cache.put(page_num, zoom, 0, pm)
        if page_num < len(self._page_widgets) and abs(zoom - self._zoom) < 0.001:
            self._page_widgets[page_num].set_pixmap(pm, zoom)
            self._container.adjustSize()

    def _on_scroll(self, value: int):
        # 找出目前在視埠中央的頁面
        viewport_center = value + self.viewport().height() // 2
        for i, pw in enumerate(self._page_widgets):
            pw_top = pw.mapTo(self._container, pw.rect().topLeft()).y()
            pw_bot = pw_top + pw.height()
            if pw_top <= viewport_center <= pw_bot:
                if i != self._current_page:
                    self._current_page = i
                    self.page_changed.emit(i)
                break
        self._render_visible_pages()

    def _on_document_modified(self):
        self._pending_signals.clear()
        self._cache.invalidate()
        self._rebuild_pages()

    def _on_document_saved(self):
        # 儲存後從磁碟重新渲染（顯示含標注的版本）
        self._pending_signals.clear()
        self._cache.invalidate()
        self._rebuild_pages()

    def refresh(self):
        """強制重新渲染所有可見頁面（供外部呼叫）。"""
        self._pending_signals.clear()
        self._cache.invalidate()
        self._rebuild_pages()

    # ── 公開控制 ─────────────────────────────────────────────────
    def set_zoom(self, zoom: float):
        self._zoom = max(0.1, min(zoom, 8.0))
        self._cache.invalidate()
        self._rebuild_pages()
        self.zoom_changed.emit(self._zoom)

    def zoom_in(self):
        for z in ZOOM_LEVELS:
            if z > self._zoom + 0.001:
                self.set_zoom(z)
                return
        self.set_zoom(8.0)

    def zoom_out(self):
        for z in reversed(ZOOM_LEVELS):
            if z < self._zoom - 0.001:
                self.set_zoom(z)
                return
        self.set_zoom(0.1)

    def fit_page(self):
        if not self._doc or not self._doc.fitz_doc:
            return
        page = self._doc.fitz_doc[self._current_page]
        vw = self.viewport().width() - 32
        vh = self.viewport().height() - 32
        zoom_w = vw / page.rect.width
        zoom_h = vh / page.rect.height
        self.set_zoom(min(zoom_w, zoom_h))

    def fit_width(self):
        if not self._doc or not self._doc.fitz_doc:
            return
        page = self._doc.fitz_doc[self._current_page]
        vw = self.viewport().width() - 32
        self.set_zoom(vw / page.rect.width)

    def go_to_page(self, page_num: int):
        if 0 <= page_num < len(self._page_widgets):
            pw = self._page_widgets[page_num]
            self.verticalScrollBar().setValue(
                pw.mapTo(self._container, pw.rect().topLeft()).y()
            )
            self._current_page = page_num
            self.page_changed.emit(page_num)

    def set_tool(self, tool):
        self._active_tool = tool
        for pw in self._page_widgets:
            pw.set_tool(tool)

    def current_page(self) -> int:
        return self._current_page

    def zoom(self) -> float:
        return self._zoom

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in()
            elif delta < 0:
                self.zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)
