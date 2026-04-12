# ~/Desktop/acropdf/core/security_manager.py
import fitz

class SecurityManager:
    def __init__(self, doc):
        self._doc = doc

    @property
    def _fitz(self) -> fitz.Document:
        return self._doc.fitz_doc

    def encrypt(self, output_path: str,
                owner_pw: str, user_pw: str,
                allow_print: bool = True,
                allow_copy: bool = True,
                allow_edit: bool = False,
                allow_annotate: bool = True,
                encryption: int = fitz.PDF_ENCRYPT_AES_256):
        permissions = 0
        if allow_print:    permissions |= fitz.PDF_PERM_PRINT
        if allow_copy:     permissions |= fitz.PDF_PERM_COPY
        if allow_edit:     permissions |= fitz.PDF_PERM_MODIFY
        if allow_annotate: permissions |= fitz.PDF_PERM_ANNOTATE
        self._fitz.save(
            output_path,
            encryption=encryption,
            owner_pw=owner_pw,
            user_pw=user_pw,
            permissions=permissions,
            garbage=4, deflate=True,
        )

    def remove_security(self, output_path: str):
        """需已通過驗證（doc.authenticate 成功）"""
        self._fitz.save(
            output_path,
            encryption=fitz.PDF_ENCRYPT_NONE,
            garbage=4, deflate=True,
        )

    def is_encrypted(self) -> bool:
        return self._fitz.needs_pass if self._fitz else False

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
