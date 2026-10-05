# ~/Desktop/acropdf/core/signature_manager.py
"""數位簽章（需安裝 pyhanko + pyhanko-certvalidator）"""

def _windows_validation_roots():
    """Read native roots without letting an unsupported PQC key break all verification."""
    import ssl
    from asn1crypto import x509
    roots = []
    skipped = 0
    document_purposes = {'2.5.29.37.0', '1.3.6.1.5.5.7.3.36', '1.3.6.1.4.1.311.10.3.12'}
    supported_keys = {'rsa', 'rsassa_pss', 'dsa', 'ec', 'ed25519', 'ed448'}
    for payload, encoding, trust in ssl.enum_certificates('ROOT'):
        if encoding != 'x509_asn' or not (trust is True or isinstance(trust, (set, frozenset)) and document_purposes.intersection(trust)):
            continue
        try:
            certificate = x509.Certificate.load(payload)
            if certificate.public_key['algorithm']['algorithm'].native not in supported_keys:
                skipped += 1
                continue
            # Exercise the key parser used when registering a trust anchor.
            certificate.public_key.sha256
            roots.append(certificate)
        except (ValueError, KeyError, TypeError):
            skipped += 1
    return roots, skipped


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
            import os
            from pyhanko.sign.validation import validate_pdf_signature
            from pyhanko.pdf_utils.reader import PdfFileReader
            from pyhanko_certvalidator import ValidationContext
            results = []
            context_args = {'allow_fetching': False}
            skipped_roots = 0
            if os.name == 'nt':
                roots, skipped_roots = _windows_validation_roots()
                context_args['trust_roots'] = roots
            with open(path, "rb") as f:
                reader = PdfFileReader(f)
                for sig in reader.embedded_signatures:
                    vc = validate_pdf_signature(sig, signer_validation_context=ValidationContext(**context_args))
                    result = {
                        "field": sig.field_name,
                        "valid": vc.valid,
                        "intact": vc.intact,
                        "trusted": vc.trusted,
                        "bottom_line": vc.bottom_line,
                        "signer": str(vc.signer_reported_dt),
                    }
                    if skipped_roots:
                        result['trust_warning'] = f'{skipped_roots} 份系統根憑證格式或演算法尚不受支援，未納入信任判定。'
                    results.append(result)
            return results
        except Exception as e:
            return [{"error": str(e)}]
