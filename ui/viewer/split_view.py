# ~/Desktop/acropdf/ui/viewer/split_view.py
"""分割檢視容器 -- 水平並排顯示兩個 PDFView，可同步或獨立捲動。"""
from __future__ import annotations

from PyQt6.QtWidgets import QSplitter, QWidget
from PyQt6.QtCore import Qt, pyqtSignal

from core.document import PDFDocument
from ui.viewer.pdf_view import PDFView


class SplitViewContainer(QSplitter):
    """水平分割容器，內含主要與次要 PDFView。

    預設只顯示主要檢視；呼叫 :meth:`set_split_enabled(True)` 啟用分割。
    啟用同步模式時，兩邊的頁面會同步切換。

    Signals
    -------
    split_toggled(bool)
        分割模式開關狀態變更時發出。
    """

    split_toggled = pyqtSignal(bool)

    # ── 初始化 ──────────────────────────────────────────────────────

    def __init__(self, parent: QWidget | None = None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._sync = True
        self._suppress_sync = False  # 防止同步回圈

        # 主要檢視（永遠顯示）
        self._primary = PDFView(self)
        self.addWidget(self._primary)

        # 次要檢視（預設隱藏）
        self._secondary = PDFView(self)
        self.addWidget(self._secondary)
        self._secondary.setVisible(False)

        # 信號連接（頁面同步）
        self._primary.page_changed.connect(self._on_primary_page_changed)
        self._secondary.page_changed.connect(self._on_secondary_page_changed)

        # 預設平均分配
        self.setSizes([500, 500])
        self.setChildrenCollapsible(False)

    # ── 公開屬性 ────────────────────────────────────────────────────

    @property
    def primary_view(self) -> PDFView:
        """主要（左側）檢視。"""
        return self._primary

    @property
    def secondary_view(self) -> PDFView:
        """次要（右側）檢視。"""
        return self._secondary

    @property
    def sync_enabled(self) -> bool:
        """頁面同步是否啟用。"""
        return self._sync

    @sync_enabled.setter
    def sync_enabled(self, value: bool) -> None:
        self._sync = value

    @property
    def is_split(self) -> bool:
        """分割模式是否啟用。"""
        return self._secondary.isVisible()

    # ── 分割開關 ────────────────────────────────────────────────────

    def set_split_enabled(self, enabled: bool) -> None:
        """顯示或隱藏次要檢視。

        啟用時，若次要檢視尚未載入文件，會自動載入與主要檢視相同的文件。
        """
        if enabled == self._secondary.isVisible():
            return

        self._secondary.setVisible(enabled)

        if enabled:
            # 自動載入主要檢視的文件（如果次要檢視尚無文件）
            if self._primary._doc and not self._secondary._doc:
                self._secondary.load_document(self._primary._doc)
                if self._sync:
                    self._secondary.go_to_page(self._primary.current_page())
            # 平均分配寬度
            total = self.width()
            self.setSizes([total // 2, total // 2])

        self.split_toggled.emit(enabled)

    def toggle_split(self) -> None:
        """切換分割模式。"""
        self.set_split_enabled(not self._secondary.isVisible())

    # ── 文件載入 ────────────────────────────────────────────────────

    def load_document(
        self,
        doc: PDFDocument,
        secondary_doc: PDFDocument | None = None,
    ) -> None:
        """載入文件至檢視。

        Parameters
        ----------
        doc : PDFDocument
            主要檢視的文件（同時也是次要檢視的預設文件）。
        secondary_doc : PDFDocument | None
            次要檢視的文件。若為 ``None``，次要檢視使用與主要相同的文件。
        """
        self._primary.load_document(doc)
        if self._secondary.isVisible():
            self._secondary.load_document(secondary_doc or doc)

    def load_secondary_document(self, doc: PDFDocument) -> None:
        """單獨載入次要檢視的文件（不影響主要檢視）。"""
        self._secondary.load_document(doc)

    # ── 頁面同步 ────────────────────────────────────────────────────

    def _on_primary_page_changed(self, page_num: int) -> None:
        if self._sync and self._secondary.isVisible() and not self._suppress_sync:
            self._suppress_sync = True
            try:
                self._secondary.go_to_page(page_num)
            finally:
                self._suppress_sync = False

    def _on_secondary_page_changed(self, page_num: int) -> None:
        if self._sync and not self._suppress_sync:
            self._suppress_sync = True
            try:
                self._primary.go_to_page(page_num)
            finally:
                self._suppress_sync = False

    # ── 轉送常用操作 ────────────────────────────────────────────────

    def set_zoom(self, zoom: float) -> None:
        """同時設定兩個檢視的縮放比例。"""
        self._primary.set_zoom(zoom)
        if self._secondary.isVisible():
            self._secondary.set_zoom(zoom)

    def zoom_in(self) -> None:
        self._primary.zoom_in()
        if self._secondary.isVisible():
            self._secondary.zoom_in()

    def zoom_out(self) -> None:
        self._primary.zoom_out()
        if self._secondary.isVisible():
            self._secondary.zoom_out()

    def fit_page(self) -> None:
        self._primary.fit_page()
        if self._secondary.isVisible():
            self._secondary.fit_page()

    def fit_width(self) -> None:
        self._primary.fit_width()
        if self._secondary.isVisible():
            self._secondary.fit_width()

    def go_to_page(self, page_num: int) -> None:
        """導覽至指定頁面（同步模式下兩邊一起跳）。"""
        self._primary.go_to_page(page_num)
        if self._sync and self._secondary.isVisible():
            self._secondary.go_to_page(page_num)

    def current_page(self) -> int:
        """回傳主要檢視的目前頁碼。"""
        return self._primary.current_page()

    def zoom(self) -> float:
        """回傳主要檢視的目前縮放比例。"""
        return self._primary.zoom()

    def set_tool(self, tool) -> None:
        """設定兩個檢視的互動工具。"""
        self._primary.set_tool(tool)
        if self._secondary.isVisible():
            self._secondary.set_tool(tool)

    def refresh(self) -> None:
        """強制重新渲染兩個檢視。"""
        self._primary.refresh()
        if self._secondary.isVisible():
            self._secondary.refresh()
