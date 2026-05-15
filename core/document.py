# ~/Desktop/acropdf/core/document.py
from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

import fitz
from PyQt6.QtCore import QObject, pyqtSignal

class PDFDocument(QObject):
    page_count_changed = pyqtSignal(int)
    document_modified = pyqtSignal()
    document_saved = pyqtSignal()
    password_required = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fitz_doc: fitz.Document | None = None
        self._path: str | None = None
        self._source_path: str | None = None
        self._modified = False
        self._page_manager = None
        self._bookmark_manager = None
        self._annotation_manager = None
        self._form_manager = None
        self._security_manager = None
        self._signature_manager = None
        self._export_manager = None
        self._optimize_manager = None
        self._redaction_manager = None
        self._preflight_manager = None
        self._font_manager = None
        self._magi_manager = None
        self._undo_stack: list[bytes] = []
        self._redo_stack: list[bytes] = []

    # ── 開啟 / 關閉 ──────────────────────────────────────────────
    def open(self, path: str, password: str = "") -> bool:
        normalized = os.path.abspath(path)
        try:
            doc = fitz.open(normalized)
        except Exception:
            try:
                from core.file_converter import FileConverter
                doc = FileConverter.convert(normalized)
            except Exception:
                return False
        if doc is None:
            return False
        if doc.needs_pass:
            if not doc.authenticate(password):
                doc.close()
                self.password_required.emit()
                return False
        if self._fitz_doc:
            self._fitz_doc.close()
        self._fitz_doc = doc
        self._path = normalized if doc.is_pdf else None
        self._source_path = normalized
        self._modified = False
        self._journal_enable()
        self.page_count_changed.emit(doc.page_count)
        return True

    def new(self):
        if self._fitz_doc:
            self._fitz_doc.close()
        self._fitz_doc = fitz.open()
        self._path = None
        self._source_path = None
        self._modified = False
        self._journal_enable()
        self.page_count_changed.emit(0)

    def close(self):
        if self._fitz_doc:
            self._fitz_doc.close()
            self._fitz_doc = None
        self._path = None
        self._source_path = None
        self._modified = False
        self._undo_stack.clear()
        self._redo_stack.clear()

    # ── 存檔 ─────────────────────────────────────────────────────
    def save(self, path: str | None = None, incremental: bool = False) -> bool:
        if self._fitz_doc is None:
            return False
        out = os.path.abspath(path or self._path or "")
        if not out:
            return False
        try:
            same_target = bool(self._path) and os.path.abspath(self._path) == out
            if incremental and same_target:
                self._fitz_doc.save(out, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
            else:
                self._atomic_save(out)
            self._path = out
            self._source_path = out
            self._modified = False
            self.document_saved.emit()
            return True
        except Exception as e:
            print(f"[PDFDocument] save error: {e}")
            return False

    # ── 屬性 ─────────────────────────────────────────────────────
    @property
    def fitz_doc(self) -> fitz.Document | None:
        return self._fitz_doc

    @property
    def path(self) -> str | None:
        return self._path

    @property
    def source_path(self) -> str | None:
        return self._source_path or self._path

    @property
    def display_name(self) -> str:
        path = self.source_path
        return Path(path).name if path else "新文件"

    @property
    def page_count(self) -> int:
        return self._fitz_doc.page_count if self._fitz_doc else 0

    @property
    def is_modified(self) -> bool:
        return self._modified

    def _mark_modified(self):
        self._modified = True
        self.document_modified.emit()

    # ── Sub-managers（延遲初始化）────────────────────────────────
    @property
    def pages(self):
        if not self._page_manager:
            from core.page_manager import PageManager
            self._page_manager = PageManager(self)
        return self._page_manager

    @property
    def bookmarks(self):
        if not self._bookmark_manager:
            from core.bookmark_manager import BookmarkManager
            self._bookmark_manager = BookmarkManager(self)
        return self._bookmark_manager

    @property
    def annotations(self):
        if not self._annotation_manager:
            from core.annotation_manager import AnnotationManager
            self._annotation_manager = AnnotationManager(self)
        return self._annotation_manager

    @property
    def forms(self):
        if not self._form_manager:
            from core.form_manager import FormManager
            self._form_manager = FormManager(self)
        return self._form_manager

    @property
    def security(self):
        if not self._security_manager:
            from core.security_manager import SecurityManager
            self._security_manager = SecurityManager(self)
        return self._security_manager

    @property
    def signatures(self):
        if not self._signature_manager:
            from core.signature_manager import SignatureManager
            self._signature_manager = SignatureManager(self)
        return self._signature_manager

    @property
    def exports(self):
        if not self._export_manager:
            from core.export_manager import ExportManager
            self._export_manager = ExportManager(self)
        return self._export_manager

    @property
    def optimize(self):
        if not self._optimize_manager:
            from core.optimize_manager import OptimizeManager
            self._optimize_manager = OptimizeManager(self)
        return self._optimize_manager

    @property
    def redaction(self):
        if not self._redaction_manager:
            from core.redaction_engine import RedactionEngine
            self._redaction_manager = RedactionEngine(self)
        return self._redaction_manager

    @property
    def preflight(self):
        if not self._preflight_manager:
            from core.preflight_engine import PreflightEngine
            self._preflight_manager = PreflightEngine()
        return self._preflight_manager

    @property
    def fonts(self):
        if not self._font_manager:
            from core.font_manager import FontManager
            self._font_manager = FontManager(self)
        return self._font_manager

    @property
    def magi(self):
        if not self._magi_manager:
            from core.magi_engine import MAGIEngine
            self._magi_manager = MAGIEngine()
        return self._magi_manager

    # ── Undo / Redo（snapshot-based，相容 PyMuPDF 1.24+）───────────
    # fitz journal 不支援結構操作（insert_page/delete_page/move_page），
    # 改用序列化快照方式實作 undo/redo。
    _MAX_UNDO = 20
    _MAX_UNDO_BYTES = 300_000_000  # 300 MB 上限，避免大檔案吃爆記憶體

    def _journal_enable(self):
        """不再使用 fitz journal；初始化快照堆疊。"""
        self._undo_stack: list[bytes] = []
        self._redo_stack: list[bytes] = []

    def _snapshot(self) -> bytes:
        """序列化目前文件為 bytes。"""
        if self._fitz_doc is None:
            return b""
        buf = io.BytesIO()
        self._fitz_doc.save(buf, garbage=0, deflate=False)
        return buf.getvalue()

    def begin_op(self, name: str):
        """在操作前呼叫，儲存快照供 undo 使用。"""
        if self._fitz_doc:
            snap = self._snapshot()
            self._undo_stack.append(snap)
            # 同時限制筆數與總容量
            while len(self._undo_stack) > self._MAX_UNDO:
                self._undo_stack.pop(0)
            while (sum(len(s) for s in self._undo_stack) > self._MAX_UNDO_BYTES
                   and len(self._undo_stack) > 1):
                self._undo_stack.pop(0)
            self._redo_stack.clear()

    def end_op(self):
        """操作後呼叫（快照模式下為空操作，保留 API 相容性）。"""
        pass

    def undo(self) -> bool:
        if self._fitz_doc is None or not self._undo_stack:
            return False
        try:
            # 儲存目前狀態到 redo
            self._redo_stack.append(self._snapshot())
            snap = self._undo_stack.pop()
            new_doc = fitz.open("pdf", snap)
            self._fitz_doc.close()
            self._fitz_doc = new_doc
            self._mark_modified()
            self.page_count_changed.emit(self._fitz_doc.page_count)
            return True
        except Exception:
            return False

    def redo(self) -> bool:
        if self._fitz_doc is None or not self._redo_stack:
            return False
        try:
            self._undo_stack.append(self._snapshot())
            snap = self._redo_stack.pop()
            new_doc = fitz.open("pdf", snap)
            self._fitz_doc.close()
            self._fitz_doc = new_doc
            self._mark_modified()
            self.page_count_changed.emit(self._fitz_doc.page_count)
            return True
        except Exception:
            return False

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def _atomic_save(self, output_path: str):
        target_dir = os.path.dirname(output_path) or "."
        fd, tmp_path = tempfile.mkstemp(prefix="acropdf_save_", suffix=".pdf", dir=target_dir)
        os.close(fd)
        try:
            self._fitz_doc.save(tmp_path, garbage=4, deflate=True)
            os.replace(tmp_path, output_path)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
