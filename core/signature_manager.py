# ~/Desktop/acropdf/core/signature_manager.py
"""數位簽章（需安裝 pyhanko + pyhanko-certvalidator）"""

class SignatureManager:
    def __init__(self, doc):
        self._doc = doc
        self.last_error = ""

    def sign_pdf(self, input_path: str, output_path: str,
                 cert_path: str, cert_password: bytes,
                 field_name: str = "Signature1",
                 reason: str = "", location: str = "") -> bool:
        try:
            import os
            import tempfile
            self.last_error = ""
            if os.path.realpath(input_path) == os.path.realpath(output_path):
                raise ValueError("請將簽章存為新檔，保留未簽署的來源。")
            from pyhanko.sign import signers, fields as sig_fields
            from pyhanko.sign.fields import SigFieldSpec
            import pyhanko.pdf_utils.incremental_writer as iw

            signer = signers.SimpleSigner.load_pkcs12(
                pfx_file=cert_path,
                passphrase=cert_password,
            )
            if signer is None:
                raise ValueError("無法載入簽章憑證。")
            with open(input_path, "rb") as f:
                writer = iw.IncrementalPdfFileWriter(f)
                sig_fields.append_signature_field(
                    writer,
                    sig_field_spec=SigFieldSpec(sig_field_name=field_name),
                )
                fd, temporary = tempfile.mkstemp(prefix="acropdf_sign_", suffix=".pdf",
                                                  dir=os.path.dirname(os.path.abspath(output_path)))
                os.close(fd)
                try:
                    with open(temporary, "wb") as out:
                        signers.sign_pdf(
                        writer,
                        signature_meta=signers.PdfSignatureMetadata(
                            field_name=field_name,
                            reason=reason,
                            location=location,
                        ),
                        signer=signer,
                        output=out,
                        )
                        out.flush()
                        os.fsync(out.fileno())
                    os.replace(temporary, output_path)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
            return True
        except ImportError:
            self.last_error = "請安裝 pyhanko 與憑證驗證相依套件。"
            print("[SignatureManager] 請安裝 pyhanko：pip install pyhanko")
            return False
        except Exception as e:
            self.last_error = str(e)
            print(f"[SignatureManager] 簽章失敗：{e}")
            return False

    def verify(self, path: str) -> list[dict]:
        try:
            from pyhanko.sign.validation import validate_pdf_signature
            from pyhanko.pdf_utils.reader import PdfFileReader
            from pyhanko_certvalidator import ValidationContext
            results = []
            with open(path, "rb") as f:
                reader = PdfFileReader(f)
                for sig in reader.embedded_signatures:
                    vc = validate_pdf_signature(sig, signer_validation_context=ValidationContext(allow_fetching=False))
                    results.append({
                        "field": sig.field_name,
                        "valid": vc.valid,
                        "intact": vc.intact,
                        "trusted": vc.trusted,
                        "bottom_line": vc.bottom_line,
                        "signer": str(vc.signer_reported_dt),
                    })
            return results
        except Exception as e:
            return [{"error": str(e)}]
