# ~/Desktop/acropdf/core/security_pikepdf.py
from __future__ import annotations


class PikePDFSecurity:

    def set_permissions_advanced(self, input_path: str, output_path: str,
                                 permissions: dict, owner_pw: str = "", user_pw: str = "", input_password: str = ""):
        """精細權限控制
        permissions keys: print, print_hq, modify, copy, annotate,
                          fill_forms, assemble, extract
        """
        import pikepdf
        if not owner_pw:
            raise ValueError("請指定擁有者密碼。")
        pdf = pikepdf.open(input_path, password=input_password)
        allow = pikepdf.Permissions(
            print_lowres=permissions.get("print", True),
            print_highres=permissions.get("print_hq", False),
            modify_other=permissions.get("modify", False),
            extract=permissions.get("copy", False),
            modify_annotation=permissions.get("annotate", True),
            modify_form=permissions.get("fill_forms", True),
            modify_assembly=permissions.get("assemble", False),
            accessibility=permissions.get("extract", True),
        )
        enc = pikepdf.Encryption(
            owner=owner_pw,
            user=user_pw,
            allow=allow,
        )
        from core.file_io import atomic_output
        try:
            with atomic_output(output_path, source=input_path) as temporary:
                pdf.save(temporary, encryption=enc)
        finally:
            pdf.close()

    def inspect_encryption(self, path: str, password: str = "") -> dict:
        """檢查加密狀態：演算法、金鑰長度、權限明細"""
        import pikepdf
        try:
            pdf = pikepdf.open(path, password=password)
            enc_info = pdf.encryption if pdf.is_encrypted else None
            result = {
                "encrypted": enc_info is not None,
                "algorithm": "",
                "key_length": 0,
                "permissions": {},
            }
            if enc_info is not None:
                bits = getattr(enc_info, "bits", 0)
                R = getattr(enc_info, "R", 0)
                result["key_length"] = bits
                if bits == 256:
                    result["algorithm"] = "AES-256"
                elif bits == 128:
                    result["algorithm"] = "AES-128"
                else:
                    result["algorithm"] = f"RC4 (R={R})"
                try:
                    perms = pdf.allow
                    result["permissions"] = {
                        "print": perms.print_lowres,
                        "print_hq": perms.print_highres,
                        "modify": perms.modify_other,
                        "copy": perms.extract,
                        "annotate": perms.modify_annotation,
                        "fill_forms": perms.fill_forms,
                        "assemble": perms.assemble,
                    }
                except Exception:
                    pass
            pdf.close()
            return result
        except pikepdf.PasswordError:
            # 需要密碼代表有加密
            return {"encrypted": True, "algorithm": "未知（需要密碼）", "key_length": 0}
        except Exception as e:
            return {"encrypted": False, "error": str(e)}

    def encrypt_with_aes256(self, input_path: str, output_path: str,
                            user_pw: str = "", owner_pw: str = "",
                            permissions: dict | None = None):
        """AES-256 加密快捷方法"""
        self.set_permissions_advanced(input_path, output_path,
                                      permissions or {"print": True, "copy": True},
                                      owner_pw=owner_pw, user_pw=user_pw)
