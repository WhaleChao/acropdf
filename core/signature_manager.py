# ~/Desktop/acropdf/core/signature_manager.py
"""數位簽章（需安裝 pyhanko + pyhanko-certvalidator）"""

class SignatureManager:
    def __init__(self, doc):
        self._doc = doc

    def sign_pdf(self, input_path: str, output_path: str,
                 cert_path: str, cert_password: bytes,
                 field_name: str = "Signature1",
                 reason: str = "", location: str = "") -> bool:
        try:
            from pyhanko.sign import signers, fields as sig_fields
            from pyhanko.sign.fields import SigFieldSpec
            import pyhanko.pdf_utils.incremental_writer as iw

            signer = signers.SimpleSigner.load_pkcs12(
                pfx_file=cert_path,
                passphrase=cert_password,
            )
            with open(input_path, "rb") as f:
                writer = iw.IncrementalPdfFileWriter(f)
                sig_fields.append_signature_field(
                    writer,
                    sig_field_spec=SigFieldSpec(sig_field_name=field_name),
                )
                with open(output_path, "wb") as out:
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
            return True
        except ImportError:
            print("[SignatureManager] 請安裝 pyhanko：pip install pyhanko")
            return False
        except Exception as e:
            print(f"[SignatureManager] 簽章失敗：{e}")
            return False

    def verify(self, path: str) -> list[dict]:
        try:
            from pyhanko.sign.validation import validate_pdf_signature
            from pyhanko.pdf_utils.reader import PdfFileReader
            results = []
            with open(path, "rb") as f:
                reader = PdfFileReader(f)
                for sig in reader.embedded_signatures:
                    vc = validate_pdf_signature(sig)
                    results.append({
                        "field": sig.field_name,
                        "valid": vc.valid,
                        "intact": vc.intact,
                        "signer": str(vc.signer_reported_dt),
                    })
            return results
        except Exception as e:
            return [{"error": str(e)}]
