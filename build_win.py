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
from pathlib import Path

BASE   = Path(__file__).parent.resolve()
DIST   = BASE / "dist"
BUILD  = BASE / "build"
ICON   = BASE / "resources" / "icons" / "acropdf.ico"

APP_NAME    = "AcroPDF"
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
        # ── PyMuPDF / PyQt6 ──────────────────────────────────
        "--hidden-import", "fitz",
        "--hidden-import", "fitz.utils",
        "--hidden-import", "PyQt6.sip",
        "--hidden-import", "PyQt6.QtPrintSupport",
        "--collect-all", "fitz",
        "--collect-all", "pymupdf_fonts",
        # ── PDF 安全 / 簽章 ───────────────────────────────────
        "--collect-all", "pikepdf",
        "--collect-all", "pyhanko",
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


def _write_version_file() -> str:
    """產生 PyInstaller 版本資訊檔（Windows VERSIONINFO resource）。"""
    content = """
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(1, 0, 2, 0),
    prodvers=(1, 0, 2, 0),
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
        StringStruct(u'CompanyName',      u'YourOffice'),
        StringStruct(u'FileDescription',  u'AcroPDF - PDF Editor'),
        StringStruct(u'FileVersion',      u'1.0.2.0'),
        StringStruct(u'InternalName',     u'AcroPDF'),
        StringStruct(u'LegalCopyright',   u'\\xa9 2026 YourOffice'),
        StringStruct(u'OriginalFilename', u'AcroPDF.exe'),
        StringStruct(u'ProductName',      u'AcroPDF'),
        StringStruct(u'ProductVersion',   u'1.0.2.0'),
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
    except Exception as e:
        print(f"⚠️   ZIP 建立失敗：{e}")


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
