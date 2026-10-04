# ~/Desktop/acropdf/core/security_manager.py
import fitz

class SecurityManager:
    def __init__(self, doc):
        self._doc = doc

    @property
    def _fitz(self) -> fitz.Document:
        return self._doc.fitz_doc

    def _safe_fitz(self) -> fitz.Document:
        doc = self._fitz
        if doc is None:
            raise RuntimeError("尚未載入文件")
        return doc

    def _private_copy(self):
        self._safe_fitz()
        copied = fitz.open("pdf", self._doc._snapshot())
        if copied.needs_pass and not copied.authenticate(self._doc._password):
            copied.close()
            raise ValueError("無法認證安全性處理快照。")
        return copied

    def encrypt(self, output_path: str,
                owner_pw: str = "", user_pw: str = "",
                owner_password: str | None = None,
                user_password: str | None = None,
                allow_print: bool = True,
                allow_copy: bool = True,
                allow_edit: bool = False,
                allow_annotate: bool = True,
                allow_print_hq: bool = False,
                allow_fill_forms: bool = True,
                allow_assemble: bool = False,
                encryption: int = fitz.PDF_ENCRYPT_AES_256,
                permissions: dict | None = None):
        """加密 PDF。支援舊式 owner_pw/user_pw 和新式 owner_password/user_password。
        permissions dict keys: print, copy, modify, annotate, fill_forms, assemble, print_hq
        """
        doc = self._safe_fitz()
        # 相容新舊參數命名
        _owner = owner_password if owner_password is not None else owner_pw
        _user = user_password if user_password is not None else user_pw
        if not _owner:
            raise ValueError("請指定擁有者密碼，以保護文件管理權限。")

        perm_flags = 0
        if permissions is not None:
            if permissions.get("print", True):
                perm_flags |= fitz.PDF_PERM_PRINT
            if permissions.get("copy", True):
                perm_flags |= fitz.PDF_PERM_COPY
            if permissions.get("modify", False):
                perm_flags |= fitz.PDF_PERM_MODIFY
            if permissions.get("annotate", True):
                perm_flags |= fitz.PDF_PERM_ANNOTATE
            # fill_forms / assemble 對應 PyMuPDF 的 PDF_PERM_FILLFORM / PDF_PERM_ASSEMBLE
            _fill = getattr(fitz, "PDF_PERM_FILLFORM", 0)
            _assem = getattr(fitz, "PDF_PERM_ASSEMBLE", 0)
            _printhq = getattr(fitz, "PDF_PERM_PRINT_HQ", 0)
            if permissions.get("fill_forms", True) and _fill:
                perm_flags |= _fill
            if permissions.get("assemble", False) and _assem:
                perm_flags |= _assem
            if permissions.get("print_hq", False) and _printhq:
                perm_flags |= _printhq
        else:
            if allow_print:      perm_flags |= fitz.PDF_PERM_PRINT
            if allow_copy:       perm_flags |= fitz.PDF_PERM_COPY
            if allow_edit:       perm_flags |= fitz.PDF_PERM_MODIFY
            if allow_annotate:   perm_flags |= fitz.PDF_PERM_ANNOTATE
            _fill = getattr(fitz, "PDF_PERM_FILLFORM", 0)
            _assem = getattr(fitz, "PDF_PERM_ASSEMBLE", 0)
            _printhq = getattr(fitz, "PDF_PERM_PRINT_HQ", 0)
            if allow_fill_forms and _fill:
                perm_flags |= _fill
            if allow_assemble and _assem:
                perm_flags |= _assem
            if allow_print_hq and _printhq:
                perm_flags |= _printhq

        from core.file_io import atomic_output
        with self._private_copy() as copied, atomic_output(output_path, source=self._doc.source_path) as temporary:
            copied.save(temporary, encryption=encryption, owner_pw=_owner, user_pw=_user,
                     permissions=perm_flags, garbage=4, deflate=True)

    def get_detailed_permissions(self) -> dict:
        """回傳詳細權限資訊，包含進階旗標"""
        if self._fitz is None:
            return {}
        p = self._fitz.permissions
        _fill = getattr(fitz, "PDF_PERM_FILLFORM", 0)
        _assem = getattr(fitz, "PDF_PERM_ASSEMBLE", 0)
        _printhq = getattr(fitz, "PDF_PERM_PRINT_HQ", 0)
        return {
            "print":      bool(p & fitz.PDF_PERM_PRINT),
            "copy":       bool(p & fitz.PDF_PERM_COPY),
            "modify":     bool(p & fitz.PDF_PERM_MODIFY),
            "annotate":   bool(p & fitz.PDF_PERM_ANNOTATE),
            "fill_forms": bool(p & _fill) if _fill else False,
            "assemble":   bool(p & _assem) if _assem else False,
            "print_hq":   bool(p & _printhq) if _printhq else False,
        }

    def remove_security(self, output_path: str):
        """需已通過驗證（doc.authenticate 成功）"""
        doc = self._safe_fitz()
        from core.file_io import atomic_output
        with self._private_copy() as copied, atomic_output(output_path, source=self._doc.source_path) as temporary:
            copied.save(temporary, encryption=fitz.PDF_ENCRYPT_NONE, garbage=4, deflate=True)

    def is_encrypted(self) -> bool:
        return self._doc.is_encrypted

    def get_permissions(self) -> dict:
        if self._fitz is None:
            return {}
        p = self._fitz.permissions
        return {
            "print":    bool(p & fitz.PDF_PERM_PRINT),
            "copy":     bool(p & fitz.PDF_PERM_COPY),
            "modify":   bool(p & fitz.PDF_PERM_MODIFY),
            "annotate": bool(p & fitz.PDF_PERM_ANNOTATE),
        }
