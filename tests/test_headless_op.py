"""--headless-op 無視窗模式：以真正的子程序呼叫 main.py 驗證協定、錯誤碼與不載入 Qt。"""
import json
import subprocess
import sys
from pathlib import Path

import fitz
import pytest

ROOT = Path(__file__).resolve().parents[1]


def run(*args, timeout=300):
    proc = subprocess.run(["nice", "-n", "15", sys.executable, str(ROOT / "main.py"), *args],
                          capture_output=True, text=True, timeout=timeout, cwd=ROOT)
    lines = proc.stdout.strip().splitlines()
    assert len(lines) == 1, f"stdout 必須只有一行 JSON：{proc.stdout!r} / {proc.stderr[-500:]}"
    return proc.returncode, json.loads(lines[0])


@pytest.fixture
def text_pdf(tmp_path):
    path = tmp_path / "text.pdf"
    doc = fitz.open()
    for n in range(2):
        page = doc.new_page()
        page.insert_text((72, 100), f"Hello headless page {n + 1}", fontsize=14)
    doc.save(path)
    return path


@pytest.fixture
def scan_pdf(tmp_path):
    src = fitz.open()
    page = src.new_page()
    page.insert_text((72, 120), "HEADLESS OCR TEST 12345", fontsize=36)
    pix = page.get_pixmap(dpi=200)
    doc = fitz.open()
    p = doc.new_page(width=page.rect.width, height=page.rect.height)
    p.insert_image(p.rect, stream=pix.tobytes("png"))
    path = tmp_path / "scan.pdf"
    doc.save(path)
    return path


def test_capabilities_no_qt():
    code = subprocess.run(["nice", "-n", "15", sys.executable, "-c",
        "import sys,runpy;sys.argv=['main.py','--headless-op','capabilities'];"
        "\ntry:\n runpy.run_path('main.py',run_name='__main__')\nexcept SystemExit as e:\n"
        " leaked=[m for m in sys.modules if m.startswith('PyQt6')];"
        " sys.stderr.write('QT:'+','.join(leaked)); sys.exit(e.code)"],
        capture_output=True, text=True, cwd=ROOT)
    assert code.returncode == 0
    assert "QT:" in code.stderr and code.stderr.split("QT:")[1].strip() == ""
    data = json.loads(code.stdout.strip().splitlines()[-1])
    assert data["ok"] and data["protocol_version"] == 2
    assert set(data["details"]["ops"]) == {"pdfa_convert", "pdfa_validate", "vision_ocr", "capabilities"}


def test_usage_errors(tmp_path, text_pdf):
    for argv in (["--headless-op", "nope"], ["--headless-op", "pdfa_convert", "--input", str(text_pdf)],
                 ["--headless-op", "pdfa_validate", "--input", "relative.pdf"],
                 ["--headless-op", "pdfa_validate", "--input", str(text_pdf), "--params-json", "{bad"],
                 ["--headless-op", "pdfa_validate", "--input", str(tmp_path / "missing.pdf")],
                 ["--headless-op", "pdfa_convert", "--input", str(text_pdf), "--output", str(text_pdf)],
                 ["--headless-op", "pdfa_validate", "--input", str(text_pdf), "--params-json", '{"level":"9z"}']):
        code, data = run(*argv)
        assert code == 64 and data["ok"] is False and data["error"]["code"]


def test_not_pdf_and_corrupt(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"hello")
    code, data = run("--headless-op", "pdfa_validate", "--input", str(bad))
    assert code == 2 and data["error"]["code"] == "input_not_pdf"


def test_encrypted_rejected(tmp_path, text_pdf):
    enc = tmp_path / "enc.pdf"
    fitz.open(text_pdf).save(enc, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="a", owner_pw="b")
    code, data = run("--headless-op", "pdfa_validate", "--input", str(enc))
    assert code == 2 and data["error"]["code"] == "encrypted"


def test_pdfa_validate_plain_pdf_not_compliant(text_pdf):
    before = text_pdf.read_bytes()
    code, data = run("--headless-op", "pdfa_validate", "--input", str(text_pdf))
    assert code == 0 and data["ok"] and data["details"]["compliant"] is False
    assert data["details"]["validation"] in ("basic_only", "verapdf")
    assert text_pdf.read_bytes() == before


@pytest.mark.skipif(not Path("/opt/homebrew/bin/gs").exists(), reason="需要 Ghostscript")
@pytest.mark.parametrize("level", ["1b", "2b", "3b"])
def test_pdfa_convert_roundtrip(tmp_path, text_pdf, level):
    out = tmp_path / f"out-{level}.pdf"
    code, data = run("--headless-op", "pdfa_convert", "--input", str(text_pdf), "--output", str(out),
                     "--params-json", json.dumps({"level": level}))
    assert code == 0, data
    assert data["output"] == str(out) and len(data["output_sha256"]) == 64
    assert data["details"]["compliant"] is True and data["details"]["pages"] == 2
    checks = data["details"]["basic_checks"]
    assert checks["all_pass"] and checks["claimed_level"] == level
    code, again = run("--headless-op", "pdfa_validate", "--input", str(out), "--params-json", json.dumps({"level": level}))
    assert code == 0 and again["details"]["compliant"] is True
    assert not list(tmp_path.glob(".acropdf_*"))


def test_pdfa_convert_missing_gs(tmp_path, text_pdf):
    out = tmp_path / "o.pdf"
    code, data = run("--headless-op", "pdfa_convert", "--input", str(text_pdf), "--output", str(out),
                     "--params-json", '{"gs_path":"/nonexistent/gs"}')
    assert code == 64 and data["error"]["code"] == "gs_missing" and not out.exists()


@pytest.mark.skipif(sys.platform != "darwin", reason="Apple Vision 僅 macOS")
def test_vision_ocr_and_skip(tmp_path, scan_pdf, text_pdf):
    out = tmp_path / "ocr.pdf"
    code, data = run("--headless-op", "vision_ocr", "--input", str(scan_pdf), "--output", str(out))
    assert code == 0, data
    page0 = data["details"]["per_page"][0]
    assert page0["status"] == "ocr" and page0["chars"] > 5 and 0 < page0["confidence"] <= 1
    with fitz.open(out) as doc:
        assert "12345" in doc[0].get_text().replace(" ", "")
    out2 = tmp_path / "skip.pdf"
    code, data = run("--headless-op", "vision_ocr", "--input", str(text_pdf), "--output", str(out2))
    assert code == 0 and data["details"]["pages_skipped"] == 2 and data["details"]["pages_ocr"] == 0


VERA = "/Users/ai/Documents/MAGI/tools/verapdf/1.30.2/verapdf"


@pytest.mark.skipif(not Path(VERA).exists() or not Path("/opt/homebrew/bin/gs").exists(), reason="需要 veraPDF 與 Ghostscript")
def test_verapdf_path_formal_validation(tmp_path, text_pdf):
    params = json.dumps({"verapdf_path": VERA})
    code, data = run("--headless-op", "pdfa_validate", "--input", str(text_pdf), "--params-json", params)
    assert code == 0 and data["details"]["validation"] == "verapdf" and data["details"]["verapdf_source"] == "params"
    assert data["details"]["compliant"] is False and data["details"]["verapdf"]["issues"]
    assert all("message" in i and "original" in i for i in data["details"]["verapdf"]["issues"])
    out = tmp_path / "a.pdf"
    code, data = run("--headless-op", "pdfa_convert", "--input", str(text_pdf), "--output", str(out), "--params-json", params)
    assert code == 0 and data["details"]["validation"] == "verapdf" and data["details"]["verapdf"]["issues"] == []
    code, data = run("--headless-op", "capabilities", "--params-json", params)
    assert data["details"]["verapdf"] == {"available": True, "source": "params"}
