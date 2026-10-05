# ~/Desktop/acropdf/ui/viewer/pdf_view.py
import fitz
from PyQt6.QtWidgets import (QScrollArea, QWidget, QVBoxLayout,
                              QHBoxLayout, QGridLayout, QSizePolicy, QFrame)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPoint, QRect, QThreadPool
from PyQt6.QtGui import QWheelEvent, QPalette, QColor, QImage, QPixmap

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
        self._row_containers: list[QWidget] = []   # 雙頁模式的行容器
        self._cache = PixmapCache()
        self._active_tool = None
        self._pending_signals: list = []  # 防止 RenderSignals 被 GC
        self._rendering_keys: set[tuple[int, float, int]] = set()
        self._render_gen = 0              # 渲染世代：丟棄過時結果
        QThreadPool.globalInstance().setMaxThreadCount(3)

        # 尺規 & 格線
        self._rulers_visible = False
        self._grid_visible = False
        self._h_ruler = None
        self._v_ruler = None
        self._grid_overlay = None

        self.setWidgetResizable(False)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        # 明確設定 viewport 背景色，防止繼承到系統暗色背景顯示黑影
        from ui.theme import COLORS, theme_manager
        _bg = QColor(COLORS[theme_manager().resolved]["canvas"])
        vp = self.viewport()
        vp.setObjectName("pdfViewport")
        vp.setAutoFillBackground(True)
        _pal = vp.palette()
        _pal.setColor(QPalette.ColorRole.Window, _bg)
        vp.setPalette(_pal)

        self._container = QWidget()
        self._container.setObjectName("pdfCanvas")
        self._container.setAutoFillBackground(True)
        _pal2 = self._container.palette()
        _pal2.setColor(QPalette.ColorRole.Window, _bg)
        self._container.setPalette(_pal2)
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._container_layout.setSpacing(8)
        self._container_layout.setContentsMargins(16, 16, 16, 16)
        self.setWidget(self._container)

        # 捲動監控（更新目前頁碼 + 尺規偏移）
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.horizontalScrollBar().valueChanged.connect(self._on_h_scroll)

    def load_document(self, doc: PDFDocument):
        # 斷開舊文件信號，避免連線累積
        if self._doc is not None:
            try:
                self._doc.document_modified.disconnect(self._on_document_modified)
            except (TypeError, RuntimeError):
                pass
            try:
                self._doc.document_saved.disconnect(self._on_document_saved)
            except (TypeError, RuntimeError):
                pass
        self._doc = doc
        self._cache.invalidate()
        self._rebuild_pages()
        self.document_loaded.emit()
        doc.document_modified.connect(self._on_document_modified)
        doc.document_saved.connect(self._on_document_saved)

    def _rebuild_pages(self):
        self._rebuilding_pages = True
        # 遞增世代，使進行中的背景渲染結果自動失效
        self._render_gen += 1
        self._rendering_keys.clear()

        # Remove layout items immediately. Deferred widgets must not affect new geometry.
        while self._container_layout.count():
            item = self._container_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self._page_widgets.clear()
        self._row_containers.clear()

        if not self._doc or not self._doc.fitz_doc:
            self._rebuilding_pages = False
            return

        # 夾住 _current_page，防止刪頁後越界
        max_page = max(0, self._doc.page_count - 1)
        if self._current_page > max_page:
            self._current_page = max_page

        if self._layout_mode == LayoutMode.CONTINUOUS:
            self._build_continuous()
        elif self._layout_mode == LayoutMode.SINGLE:
            self._build_single()
        elif self._layout_mode == LayoutMode.DOUBLE:
            self._build_double()

        # New child widgets otherwise wait until the next event loop to become
        # visible. Their layout positions must exist before restoring the page.
        for row in self._row_containers:
            row.show()
        for page in self._page_widgets:
            page.show()
        self._container_layout.activate()
        self._container.adjustSize()
        self._rebuilding_pages = False

        # 非同步渲染可見頁面
        QTimer.singleShot(0, self._render_visible_pages)

    def _build_continuous(self):
        """連續捲動模式：所有頁面垂直排列。"""
        for i in range(self._doc.page_count):
            pw = self._make_page_widget(i)
            self._container_layout.addWidget(pw)

    def _build_single(self):
        """單頁模式：只顯示目前頁面。"""
        if self._doc.page_count == 0:
            return
        page_num = min(self._current_page, self._doc.page_count - 1)
        pw = self._make_page_widget(page_num)
        self._container_layout.addWidget(pw)

    def _build_double(self):
        """雙頁模式：兩頁並排，第 0 頁單獨在右側（模擬書本翻頁）。"""
        pc = self._doc.page_count
        if pc == 0:
            return

        i = 0
        while i < pc:
            if i == 0:
                # 第一頁（封面）單獨置右
                row = QWidget(self._container)
                row_layout = QHBoxLayout(row)
                row_layout.setSpacing(12)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                pw = self._make_page_widget(0)
                row_layout.addWidget(pw)
                self._container_layout.addWidget(row)
                self._row_containers.append(row)
                i = 1
            else:
                row = QWidget(self._container)
                row_layout = QHBoxLayout(row)
                row_layout.setSpacing(12)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
                # 左頁
                pw_left = self._make_page_widget(i)
                row_layout.addWidget(pw_left)
                # 右頁（若存在）
                if i + 1 < pc:
                    pw_right = self._make_page_widget(i + 1)
                    row_layout.addWidget(pw_right)
                self._container_layout.addWidget(row)
                self._row_containers.append(row)
                i += 2

    def _make_page_widget(self, page_num: int) -> PageWidget:
        """建立單一頁面 widget 並設定尺寸。"""
        pw = PageWidget(page_num, self._container)
        if self._active_tool:
            pw.set_tool(self._active_tool)
        pw.context_requested.connect(self.page_context_requested)
        pw.render_retry.connect(self._render_visible_pages)
        page = self._doc.fitz_doc[page_num]
        pw.setFixedSize(
            int(page.rect.width * self._zoom),
            int(page.rect.height * self._zoom),
        )
        self._page_widgets.append(pw)
        return pw

    def _render_visible_pages(self):
        if not self._doc or not self._doc.fitz_doc:
            return
        gen = self._render_gen
        fitz_doc = self._doc.fitz_doc
        pc = fitz_doc.page_count
        for pw in self._page_widgets:
            i = pw.page_num
            if i >= pc:
                continue
            # 檢查是否在可見區域附近（±3頁）
            if abs(i - self._current_page) <= 3:
                cached = self._cache.get(i, self._zoom, 0)
                if cached:
                    pw.set_pixmap(cached, self._zoom)
                elif self._doc.path and not self._doc.is_modified and not self._doc.is_encrypted:
                    key = (i, round(self._zoom, 3), gen)
                    if key in self._rendering_keys:
                        continue
                    self._rendering_keys.add(key)
                    # 有檔案路徑且未修改：非同步渲染（背景執行緒）
                    sig = PageRenderer.make_signals()
                    sig.done.connect(
                        lambda pn, z, pm, g=gen: self._on_render_done(pn, z, pm, g)
                    )
                    sig.done.connect(lambda _pn, _z, _pm, s=sig, k=key: self._release_render_signal(s, k))
                    sig.error.connect(lambda _pn, _msg, s=sig, k=key: self._release_render_signal(s, k))
                    sig.error.connect(lambda pn, msg, g=gen: self._on_render_error(pn, msg, g))
                    self._pending_signals.append(sig)
                    PageRenderer.start_worker(self._doc.path, i, self._zoom, sig)
                else:
                    # 無檔案路徑或有未儲存修改：同步渲染
                    try:
                        pm = PageRenderer.render_page_sync(fitz_doc[i], self._zoom)
                        self._on_render_done(i, self._zoom, pm, gen)
                    except Exception as exc:
                        self._on_render_error(i, str(exc), gen)
            elif abs(i - self._current_page) > 5:
                pw.clear_pixmap()

    def _on_render_error(self, page_num, message, gen):
        if gen != self._render_gen:
            return
        for widget in self._page_widgets:
            if widget.page_num == page_num:
                widget.set_render_error(message)
                break

    def _on_render_done(self, page_num: int, zoom: float, pm, gen: int = -1):
        self._rendering_keys.discard((page_num, round(zoom, 3), gen))
        if gen >= 0 and gen != self._render_gen:
            return   # 過時的渲染結果，丟棄
        if self._doc is None:
            return
        if isinstance(pm, QImage):
            pm = QPixmap.fromImage(pm)
        self._cache.put(page_num, zoom, 0, pm)
        if abs(zoom - self._zoom) < 0.001:
            for pw in self._page_widgets:
                if pw.page_num == page_num:
                    pw.set_pixmap(pm, zoom)
                    break
            self._container.adjustSize()

    def _release_render_signal(self, signal, key: tuple[int, float, int]):
        self._rendering_keys.discard(key)
        try:
            self._pending_signals.remove(signal)
        except ValueError:
            pass

    def _on_scroll(self, value: int):
        if getattr(self, '_rebuilding_pages', False):
            return
        if self._layout_mode == LayoutMode.SINGLE:
            # 單頁模式不需要根據捲動更新頁碼
            self._render_visible_pages()
            self._sync_rulers()
            return

        # 找出目前在視埠中央（或最近）的頁面
        viewport_center = value + self.viewport().height() // 2
        best = self._current_page
        best_dist = float('inf')
        pages = self._page_widgets
        if self._layout_mode == LayoutMode.DOUBLE:
            # Both pages share a row. Preserve the selected side while that row
            # remains centered, rather than always selecting its left page.
            pages = sorted(pages, key=lambda page: page.page_num != self._current_page)
        for pw in pages:
            i = pw.page_num
            pw_top = pw.mapTo(self._container, pw.rect().topLeft()).y()
            pw_bot = pw_top + pw.height()
            if pw_top <= viewport_center <= pw_bot:
                best = i
                break
            mid = (pw_top + pw_bot) // 2
            dist = abs(mid - viewport_center)
            if dist < best_dist:
                best_dist = dist
                best = i
        if best != self._current_page:
            self._current_page = best
            self.page_changed.emit(best)
        self._render_visible_pages()
        self._sync_rulers()

    def _on_h_scroll(self, _value: int):
        self._sync_rulers()

    def _sync_rulers(self):
        """更新尺規偏移量。"""
        if self._h_ruler and self._h_ruler.isVisible():
            self._h_ruler.set_scroll_offset(self.horizontalScrollBar().value())
            self._h_ruler.set_zoom(self._zoom)
        if self._v_ruler and self._v_ruler.isVisible():
            self._v_ruler.set_scroll_offset(self.verticalScrollBar().value())
            self._v_ruler.set_zoom(self._zoom)

    def _on_document_modified(self):
        if not self._doc or self._doc.fitz_doc is None:
            return
        saved_page = self._current_page
        # Rotation, crop, reorder and edits can affect any page, even with an unchanged count.
        self._cache.invalidate()
        self._rebuild_pages()
        self._restore_scroll(min(saved_page, max(self._doc.page_count - 1, 0)))

    def _on_document_saved(self):
        self.refresh()

    def unload_document(self):
        self._render_gen += 1
        if self._doc is not None:
            for signal, slot in ((self._doc.document_modified, self._on_document_modified),
                                 (self._doc.document_saved, self._on_document_saved)):
                try:
                    signal.disconnect(slot)
                except (TypeError, RuntimeError):
                    pass
        self._doc = None
        self._active_tool = None
        self._rendering_keys.clear()
        self._cache.invalidate()

    def _restore_scroll(self, page_num: int):
        """恢復捲動到指定頁面。"""
        for pw in self._page_widgets:
            if pw.page_num == page_num:
                self.verticalScrollBar().setValue(
                    pw.mapTo(self._container, pw.rect().topLeft()).y()
                )
                return

    def refresh(self):
        """強制重新渲染所有可見頁面（供外部呼叫）。"""
        saved_page = self._current_page
        self._rendering_keys.clear()
        self._cache.invalidate()
        self._rebuild_pages()
        self._restore_scroll(saved_page)

    def set_bg_color(self, hex_color: str):
        """主題切換時更新 viewport 與容器背景色。"""
        bg = QColor(hex_color)
        for widget in (self.viewport(), self._container):
            # A local background survives Qt's palette reset when a view is reparented into a tab.
            widget.setStyleSheet(f"background-color: {hex_color};")
            widget.ensurePolished()
            widget.setAutoFillBackground(True)
            pal = widget.palette()
            pal.setColor(QPalette.ColorRole.Window, bg)
            widget.setPalette(pal)

    # ── 公開控制 ─────────────────────────────────────────────────
    def set_zoom(self, zoom: float):
        import math
        if not math.isfinite(zoom):
            return
        saved_page = self._current_page
        self._zoom = max(0.1, min(zoom, 8.0))
        self._cache.invalidate()
        self._rebuild_pages()
        self._restore_scroll(saved_page)
        self.zoom_changed.emit(self._zoom)
        self._sync_rulers()

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
        if self._current_page >= self._doc.page_count:
            return
        page = self._doc.fitz_doc[self._current_page]
        pw, ph = page.rect.width, page.rect.height
        if pw <= 0 or ph <= 0:
            return
        vw = max(self.viewport().width() - 32, 1)
        vh = max(self.viewport().height() - 32, 1)
        self.set_zoom(min(vw / pw, vh / ph))

    def fit_width(self):
        if not self._doc or not self._doc.fitz_doc:
            return
        if self._current_page >= self._doc.page_count:
            return
        page = self._doc.fitz_doc[self._current_page]
        pw = page.rect.width
        if pw <= 0:
            return
        vw = max(self.viewport().width() - 32, 1)
        # 雙頁模式需要兩倍寬度
        if self._layout_mode == LayoutMode.DOUBLE:
            self.set_zoom(vw / (pw * 2 + 12))
        else:
            self.set_zoom(vw / pw)

    def go_to_page(self, page_num: int):
        if not self._doc or not self._doc.fitz_doc:
            return
        page_num = max(0, min(page_num, self._doc.page_count - 1))

        if self._layout_mode == LayoutMode.SINGLE:
            # 單頁模式：重建只顯示該頁
            self._current_page = page_num
            self._cache.invalidate()
            self._rebuild_pages()
            self.page_changed.emit(page_num)
            return

        # 連續/雙頁模式：捲動到目標頁面
        self._current_page = page_num
        for pw in self._page_widgets:
            if pw.page_num == page_num:
                self.verticalScrollBar().setValue(
                    pw.mapTo(self._container, pw.rect().topLeft()).y()
                )
                break
        self.page_changed.emit(page_num)
        self._render_visible_pages()

    def set_tool(self, tool):
        self._active_tool = tool
        for pw in self._page_widgets:
            pw.set_tool(tool)

    def current_page(self) -> int:
        return self._current_page

    def zoom(self) -> float:
        return self._zoom

    def set_layout_mode(self, mode):
        """切換頁面檢視模式（連續 / 單頁 / 雙頁）。"""
        if self._layout_mode == mode:
            return
        saved_page = self._current_page
        self._layout_mode = mode
        self._cache.invalidate()
        self._rebuild_pages()
        self._restore_scroll(saved_page)

    # ── 尺規 & 格線 ──────────────────────────────────────────────
    def set_rulers_visible(self, visible: bool):
        """顯示 / 隱藏尺規。"""
        self._rulers_visible = visible
        if visible:
            self._ensure_rulers()
            self._h_ruler.show()
            self._v_ruler.show()
            self._sync_rulers()
        else:
            if self._h_ruler:
                self._h_ruler.hide()
            if self._v_ruler:
                self._v_ruler.hide()

    def set_grid_visible(self, visible: bool):
        """顯示 / 隱藏格線覆蓋層。"""
        self._grid_visible = visible
        if visible:
            self._ensure_grid()
            self._grid_overlay.show()
            self._update_grid_geometry()
        else:
            if self._grid_overlay:
                self._grid_overlay.hide()

    def _ensure_rulers(self):
        """延遲建立尺規元件（只在首次需要時建立）。"""
        if self._h_ruler is None:
            from ui.widgets.ruler_widget import HorizontalRuler, VerticalRuler
            self._h_ruler = HorizontalRuler(self)
            self._v_ruler = VerticalRuler(self)
            # 放在 viewport 上方/左側
            self._h_ruler.raise_()
            self._v_ruler.raise_()

    def _ensure_grid(self):
        """延遲建立格線覆蓋層。"""
        if self._grid_overlay is None:
            from ui.widgets.ruler_widget import GridOverlay
            self._grid_overlay = GridOverlay(self.viewport())
            self._grid_overlay.raise_()

    def _update_grid_geometry(self):
        """更新格線覆蓋層的幾何資訊。"""
        if not self._grid_overlay or not self._grid_overlay.isVisible():
            return
        self._grid_overlay.setGeometry(self.viewport().rect())
        self._grid_overlay.set_zoom(self._zoom)
        # 找出目前頁面的螢幕矩形
        for pw in self._page_widgets:
            if pw.page_num == self._current_page:
                pos = pw.mapTo(self.viewport(), pw.rect().topLeft())
                self._grid_overlay.set_page_rect(
                    QRect(pos.x(), pos.y(), pw.width(), pw.height())
                )
                break

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 重新定位尺規
        if self._h_ruler and self._h_ruler.isVisible():
            ruler_h = self._h_ruler.height()
            self._h_ruler.setGeometry(20, 0, self.width() - 20, ruler_h)
        if self._v_ruler and self._v_ruler.isVisible():
            ruler_w = self._v_ruler.width()
            h_offset = self._h_ruler.height() if (self._h_ruler and self._h_ruler.isVisible()) else 0
            self._v_ruler.setGeometry(0, h_offset, ruler_w, self.height() - h_offset)
        if self._grid_overlay and self._grid_overlay.isVisible():
            self._update_grid_geometry()

    # ── 單頁模式導覽 ─────────────────────────────────────────────
    def _navigate_single(self, delta: int):
        """單頁模式：翻到前一頁或下一頁。"""
        if self._layout_mode != LayoutMode.SINGLE:
            return
        if not self._doc:
            return
        new_page = self._current_page + delta
        if 0 <= new_page < self._doc.page_count:
            self.go_to_page(new_page)

    def keyPressEvent(self, event):
        if self._layout_mode == LayoutMode.SINGLE:
            if event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_PageDown, Qt.Key.Key_Space):
                self._navigate_single(1)
                event.accept()
                return
            elif event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_PageUp):
                self._navigate_single(-1)
                event.accept()
                return
            elif event.key() == Qt.Key.Key_Home:
                self.go_to_page(0)
                event.accept()
                return
            elif event.key() == Qt.Key.Key_End:
                self.go_to_page(self._doc.page_count - 1 if self._doc else 0)
                event.accept()
                return
        super().keyPressEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in()
            elif delta < 0:
                self.zoom_out()
            event.accept()
        elif self._layout_mode == LayoutMode.SINGLE:
            # 單頁模式：滾輪翻頁
            delta = event.angleDelta().y()
            if delta < -30:
                self._navigate_single(1)
            elif delta > 30:
                self._navigate_single(-1)
            event.accept()
        else:
            super().wheelEvent(event)
