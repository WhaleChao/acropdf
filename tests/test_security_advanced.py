import fitz
import pytest


def _blank_pdf(tmp_path, name="test.pdf"):
    path = tmp_path / name
    doc = fitz.open()
    doc.new_page()
    doc.save(str(path))
    doc.close()
    return str(path)


def test_granular_permissions(tmp_path):
    from core.document import PDFDocument
    pdf = _blank_pdf(tmp_path)
    pdoc = PDFDocument()
    pdoc.open(pdf)
    out = tmp_path / "encrypted.pdf"
    pdoc.security.encrypt(
        str(out), user_password="test", owner_password="owner",
        permissions={"print": True, "copy": False, "modify": False,
                     "annotate": False, "fill_forms": True},
    )
    check = fitz.open(str(out))
    assert check.is_encrypted
    check.close()


def test_security_manager_encrypt_decrypt(tmp_path):
    from core.document import PDFDocument
    pdf = _blank_pdf(tmp_path)
    pdoc = PDFDocument()
    pdoc.open(pdf)
    out = str(tmp_path / "enc.pdf")
    pdoc.security.encrypt(out, owner_password="owner", user_password="user",
                          allow_print=True, allow_copy=False)
    check = fitz.open(out)
    assert check.is_encrypted
    check.close()


def test_inspect_encryption(tmp_path):
    from core.security_pikepdf import PikePDFSecurity
    pdf = _blank_pdf(tmp_path)
    doc = fitz.open(pdf)
    enc_path = str(tmp_path / "enc.pdf")
    perm = fitz.PDF_PERM_PRINT | fitz.PDF_PERM_COPY
    doc.save(enc_path, encryption=fitz.PDF_ENCRYPT_AES_256,
             user_pw="u", owner_pw="o", permissions=perm)
    doc.close()

    engine = PikePDFSecurity()
    info = engine.inspect_encryption(enc_path, password="u")
    assert info["encrypted"] is True
    assert "AES" in info.get("algorithm", "")


def test_remove_security(tmp_path):
    from core.document import PDFDocument
    pdf = _blank_pdf(tmp_path)
    # 先加密
    doc_fitz = fitz.open(pdf)
    enc_path = str(tmp_path / "enc.pdf")
    doc_fitz.save(enc_path, encryption=fitz.PDF_ENCRYPT_AES_256,
                  user_pw="", owner_pw="owner")
    doc_fitz.close()

    # 開啟並移除加密
    pdoc = PDFDocument()
    pdoc.open(enc_path)
    out = str(tmp_path / "decrypted.pdf")
    pdoc.security.remove_security(out)
    check = fitz.open(out)
    assert not check.is_encrypted
    check.close()
