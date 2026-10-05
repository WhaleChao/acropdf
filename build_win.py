#!/usr/bin/env python3
"""
AcroPDF Windows 打包腳本
==========================
用法（在 Windows 上執行）：
    python build_win.py [--onefile] [--upx] [--sign cert.pfx --sign-pass PASSWORD]

產出：
    dist\\AcroPDF\\AcroPDF.exe   （資料夾模式，較快啟動）
    dist\\AcroPDF.exe            （若 --onefile）

依賴（Windows 環境）：
    pip install pyinstaller
    （選用）下載 UPX：https://upx.github.io/  → 放到 PATH

注意：
    - Tesseract OCR 需另行安裝（https://github.com/UB-Mannheim/tesseract/wiki）
      打包後設 TESSDATA_PREFIX 環境變數指向 tessdata 資料夾
    - 若需要程式碼簽署，需要 signtool.exe（隨 Windows SDK 安裝）
"""

import os
import sys
import shutil
import subprocess
import argparse
import re
import hashlib
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE   = Path(__file__).parent.resolve()
DIST   = BASE / "dist"
BUILD  = BASE / "build"
ICON   = BASE / "resources" / "icons" / "acropdf.ico"

APP_NAME    = "AcroPDF"
APP_PUBLISHER = "WhaleChao"
ENTRY_POINT = str(BASE / "main.py")


def run(cmd: list[str], **kw):
    print(f"\n$ {' '.join(str(c) for c in cmd)}")
    subprocess.run(cmd, check=True, **kw)


def build(onefile: bool, use_upx: bool, sign_cert: str | None, sign_pass: str | None,
          skip_preflight: bool = False):
    # ── 前置檢查 ─────────────────────────────────────────
    if not skip_preflight:
        from build_preflight import run_preflight
        if not run_preflight():
            sys.exit(1)

    # ── 清理舊產物 ───────────────────────────────────────
    for d in (DIST / APP_NAME, BUILD / APP_NAME, BUILD / "main"):
        shutil.rmtree(d, ignore_errors=True)
    for f in DIST.glob(f"{APP_NAME}*.exe"):
        f.unlink(missing_ok=True)

    # ── PyInstaller 參數 ─────────────────────────────────
    sep = ";" if sys.platform == "win32" else ":"   # PyInstaller 路徑分隔符

    args = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--windowed",                         # 不顯示 console 視窗
        "--noconfirm",
        "--clean",
        "--distpath", str(DIST),
        "--workpath", str(BUILD),
        # 資源目錄（含 app/ 常數與設定）
        f"--add-data={BASE / 'resources'}{sep}resources",
        f"--add-data={BASE / 'ui'}{sep}ui",
        f"--add-data={BASE / 'core'}{sep}core",
        f"--add-data={BASE / 'app'}{sep}app",
        f"--add-data={BASE / 'rendering'}{sep}rendering",
        f"--add-data={BASE / 'acro_platform'}{sep}acro_platform",
        f"--add-data={BASE / 'docs'}{sep}docs",
        f"--add-data={BASE / 'LICENSE'}{sep}.",
        f"--add-data={BASE / 'THIRD_PARTY_NOTICES.md'}{sep}.",
        # ── PyMuPDF / PyQt6 ──────────────────────────────────
        "--hidden-import", "fitz",
        "--hidden-import", "fitz.utils",
        "--hidden-import", "PyQt6.sip",
        "--hidden-import", "PyQt6.QtPrintSupport",
        "--collect-all", "fitz",
        "--collect-all", "pymupdf_fonts",
        # ── PDF 安全 / 簽章 ───────────────────────────────────
        "--collect-all", "pikepdf",
        # pyhanko: 只匯入實際用到的模組，避免 collect-all 拉進
        # torch/transformers/scipy 等巨型無關套件
        "--hidden-import", "pyhanko",
        "--hidden-import", "pyhanko.sign",
        "--hidden-import", "pyhanko.sign.signers",
        "--hidden-import", "pyhanko.sign.fields",
        "--hidden-import", "pyhanko.sign.validation",
        "--hidden-import", "pyhanko.pdf_utils",
        "--hidden-import", "pyhanko.pdf_utils.reader",
        "--hidden-import", "pyhanko.pdf_utils.incremental_writer",
        "--hidden-import", "pyhanko_certvalidator",
        "--hidden-import", "cryptography",
        # ── 匯出 / 轉換 ───────────────────────────────────────
        "--hidden-import", "openpyxl",
        "--hidden-import", "pptx",
        "--hidden-import", "docx",
        "--hidden-import", "reportlab",
        "--hidden-import", "reportlab.graphics",
        # ── OCR / 圖像 ────────────────────────────────────────
        "--hidden-import", "pytesseract",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL.Image",
        # ── 自動標籤（stdlib）────────────────────────────────
        "--hidden-import", "urllib.request",
        "--hidden-import", "xml.etree.ElementTree",
        # ── 排除不需要的巨型套件（防止被間接拉入）──────────────
        "--exclude-module", "torch",
        "--exclude-module", "transformers",
        "--exclude-module", "scipy",
        "--exclude-module", "tensorflow",
        "--exclude-module", "tensorboard",
        "--exclude-module", "onnxruntime",
        "--exclude-module", "pytest",
        "--exclude-module", "sympy",
        "--exclude-module", "IPython",
        "--exclude-module", "notebook",
        "--exclude-module", "matplotlib",
        # ── Windows 版本資訊 ──────────────────────────────────
        "--version-file", _write_version_file(),
    ]

    # 圖示（.ico 格式）
    if ICON.exists():
        args += ["--icon", str(ICON)]

    # UPX 壓縮（縮減體積，但反病毒軟體可能誤報）
    if use_upx and shutil.which("upx"):
        args += ["--upx-dir", shutil.which("upx")]
    elif use_upx:
        print("⚠️   找不到 upx，略過壓縮")

    # 單檔模式
    if onefile:
        args.append("--onefile")

    args.append(ENTRY_POINT)

    run(args)

    # 找到產出的 exe
    if onefile:
        exe_path = DIST / f"{APP_NAME}.exe"
    else:
        exe_path = DIST / APP_NAME / f"{APP_NAME}.exe"

    print(f"\n✅  打包完成：{exe_path}")

    # ── Authenticode 簽署（選用）────────────────────────
    if sign_cert and exe_path.exists():
        _sign(exe_path, sign_cert, sign_pass)

    # ── 建立 ZIP 壓縮包（資料夾模式）───────────────────
    if not onefile and (DIST / APP_NAME).is_dir():
        _make_zip()
        _make_installer()


def _write_version_file() -> str:
    """產生 PyInstaller 版本資訊檔（Windows VERSIONINFO resource）。"""
    version = _app_version()
    file_version = _version_tuple(version)
    content = f"""
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={file_version},
    prodvers={file_version},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(u'040404b0', [
        StringStruct(u'CompanyName',      u'{APP_PUBLISHER}'),
        StringStruct(u'FileDescription',  u'AcroPDF - PDF Editor'),
        StringStruct(u'FileVersion',      u'{version}'),
        StringStruct(u'InternalName',     u'AcroPDF'),
        StringStruct(u'LegalCopyright',   u'\\xa9 2026 {APP_PUBLISHER}'),
        StringStruct(u'OriginalFilename', u'AcroPDF.exe'),
        StringStruct(u'ProductName',      u'AcroPDF'),
        StringStruct(u'ProductVersion',   u'{version}'),
      ])
    ]),
    VarFileInfo([VarStruct(u'Translation', [0x0404, 0x04b0])])
  ]
)
""".strip()
    ver_file = BASE / "build" / "version_info.txt"
    ver_file.parent.mkdir(exist_ok=True)
    ver_file.write_text(content, encoding="utf-8")
    return str(ver_file)


def _app_version() -> str:
    """從 main.py 讀取單一版本來源，避免 Windows metadata 落後。"""
    try:
        main_text = (BASE / "main.py").read_text(encoding="utf-8")
        m = re.search(r'APP_VERSION\s*=\s*[\'"]([^\'"]+)[\'"]', main_text)
        if m:
            return m.group(1)
    except OSError:
        pass
    return "1.0.0"


def _version_tuple(version: str) -> tuple[int, int, int, int]:
    parts: list[int] = []
    for part in version.split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return tuple((parts + [0, 0, 0, 0])[:4])


def _sign(exe_path: Path, cert: str, password: str | None):
    """用 signtool.exe 簽署 EXE（需要 Windows SDK）。"""
    signtool = shutil.which("signtool")
    if not signtool:
        # 常見路徑
        candidates = [
            r"C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe",
            r"C:\Program Files\Windows Kits\10\bin\x64\signtool.exe",
        ]
        for c in candidates:
            if os.path.isfile(c):
                signtool = c
                break
    if not signtool:
        print("⚠️   找不到 signtool.exe，跳過簽署")
        return

    cmd = [
        signtool, "sign",
        "/fd", "SHA256",
        "/t", "http://timestamp.digicert.com",
        "/f", cert,
    ]
    if password:
        cmd += ["/p", password]
    cmd.append(str(exe_path))
    run(cmd)
    print(f"✅  Authenticode 簽署完成：{exe_path.name}")


def _make_zip():
    """把 dist/AcroPDF 資料夾壓縮為 dist/AcroPDF.zip。"""
    src = DIST / APP_NAME
    out = DIST / f"{APP_NAME}_win"
    try:
        shutil.make_archive(str(out), "zip", str(DIST), APP_NAME)
        print(f"✅  ZIP 建立完成：{out}.zip")
        _write_checksum(Path(f"{out}.zip"))
    except Exception as e:
        print(f"⚠️   ZIP 建立失敗：{e}")


def _make_installer():
    """若有 Inno Setup，建立 Windows 安裝程式。"""
    iscc = shutil.which("ISCC.exe") or shutil.which("ISCC")
    if not iscc:
        candidates = [
            r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
            r"C:\Program Files\Inno Setup 6\ISCC.exe",
        ]
        for candidate in candidates:
            if os.path.isfile(candidate):
                iscc = candidate
                break
    if not iscc:
        print("ℹ️  找不到 Inno Setup，略過 Windows 安裝程式")
        return

    iss = BASE / "installer" / "AcroPDF.iss"
    if not iss.exists():
        print("⚠️   找不到 Inno Setup 腳本，略過 Windows 安裝程式")
        return

    version = _app_version()
    run([iscc, f"/DMyAppVersion={version}", str(iss)])
    installer = DIST / "AcroPDF_Setup.exe"
    if installer.exists():
        print(f"✅  Windows 安裝程式建立完成：{installer}")
        _write_checksum(installer)


def _write_checksum(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    out = path.with_suffix(path.suffix + ".sha256")
    out.write_text(f"{digest.hexdigest()}  {path.name}\n", encoding="utf-8")
    print(f"✅  SHA256 建立完成：{out}")


# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build AcroPDF for Windows")
    parser.add_argument("--onefile",       action="store_true",
                        help="打包成單一 EXE（較慢啟動）")
    parser.add_argument("--upx",           action="store_true",
                        help="使用 UPX 壓縮（縮減體積）")
    parser.add_argument("--sign",          metavar="CERT.PFX", default=None,
                        help="Authenticode 憑證檔案路徑（.pfx）")
    parser.add_argument("--sign-pass",     metavar="PASSWORD",  default=None,
                        help="憑證密碼")
    parser.add_argument("--skip-preflight", action="store_true",
                        help="跳過前置檢查（已確認環境正確時使用）")
    args = parser.parse_args()
    build(args.onefile, args.upx, args.sign, args.sign_pass,
          skip_preflight=args.skip_preflight)
