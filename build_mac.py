#!/usr/bin/env python3
"""
AcroPDF macOS 打包腳本
========================
用法：
    python3 build_mac.py [--onefile] [--sign "Developer ID Application: ..."]

產出：
    dist/AcroPDF.app       （預設：資料夾 bundle）
    dist/AcroPDF.dmg       （若系統有 create-dmg 或 hdiutil）

依賴：
    pip install pyinstaller
    （選用）brew install create-dmg

注意：
    - Tesseract OCR 需另行安裝：brew install tesseract tesseract-lang
      打包後設定 TESSDATA_PREFIX 指向 tessdata 資料夾
    - 若要 notarize，需在 Apple 開發者帳號設定 app-specific password
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
ICON   = BASE / "resources" / "icons" / "acropdf.icns"

APP_NAME    = "AcroPDF"
BUNDLE_ID   = "com.youroffice.acropdf"
ENTRY_POINT = str(BASE / "main.py")


def run(cmd: list[str], **kw):
    print(f"\n$ {' '.join(str(c) for c in cmd)}")
    subprocess.run(cmd, check=True, **kw)


def build(onefile: bool, sign_id: str | None):
    # ── 清理舊產物 ───────────────────────────────────────
    for d in (DIST / APP_NAME, DIST / f"{APP_NAME}.app",
              BUILD / APP_NAME, BUILD / "main"):
        shutil.rmtree(d, ignore_errors=True)
    for f in DIST.glob(f"{APP_NAME}*.dmg"):
        f.unlink(missing_ok=True)

    # ── PyInstaller 參數 ─────────────────────────────────
    args = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--windowed",                          # macOS .app bundle
        "--noconfirm",
        "--clean",
        "--distpath", str(DIST),
        "--workpath", str(BUILD),
        # 資源目錄整包帶入（含 app/ 常數與設定）
        "--add-data", f"{BASE / 'resources'}:resources",
        "--add-data", f"{BASE / 'ui'}:ui",
        "--add-data", f"{BASE / 'core'}:core",
        "--add-data", f"{BASE / 'app'}:app",
        "--add-data", f"{BASE / 'rendering'}:rendering",
        "--add-data", f"{BASE / 'acro_platform'}:acro_platform",
        # ── PyMuPDF / PyQt6 ──────────────────────────────────
        "--hidden-import", "fitz",
        "--hidden-import", "fitz.utils",
        "--hidden-import", "PyQt6.sip",
        "--hidden-import", "PyQt6.QtPrintSupport",
        "--collect-all",  "fitz",
        "--collect-all",  "pymupdf_fonts",
        # ── PDF 安全 / 簽章 ───────────────────────────────────
        "--collect-all",  "pikepdf",
        "--collect-all",  "pyhanko",
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
        # ── macOS Vision / Quartz（pyobjc，系統框架）────────────
        "--hidden-import", "Vision",
        "--hidden-import", "Quartz",
        "--hidden-import", "Foundation",
        # ── 自動標籤（stdlib，保險起見列出）─────────────────────
        "--hidden-import", "urllib.request",
        "--hidden-import", "xml.etree.ElementTree",
    ]

    # 圖示
    if ICON.exists():
        args += ["--icon", str(ICON)]

    # bundle identifier（macOS Info.plist）
    args += ["--osx-bundle-identifier", BUNDLE_ID]

    # 單檔模式（較慢，但只有一個執行檔）
    if onefile:
        args.append("--onefile")

    args.append(ENTRY_POINT)

    run(args)

    app_path = DIST / f"{APP_NAME}.app"
    print(f"\n✅  打包完成：{app_path}")

    # ── 程式碼簽署（選用）───────────────────────────────
    if sign_id:
        run([
            "codesign",
            "--deep", "--force", "--options", "runtime",
            "--sign", sign_id,
            "--entitlements", str(BASE / "resources" / "entitlements.plist"),
            str(app_path),
        ])
        run(["codesign", "--verify", "--deep", "--strict", str(app_path)])
        print("✅  程式碼簽署完成")

    # ── 建立 DMG（選用，需要 create-dmg 或 hdiutil）────────
    _make_dmg(app_path)


def _make_dmg(app_path: Path):
    dmg_out = DIST / f"{APP_NAME}.dmg"

    # 優先用 create-dmg（較美觀）
    if shutil.which("create-dmg"):
        try:
            run([
                "create-dmg",
                "--volname",    APP_NAME,
                "--window-size", "600", "400",
                "--icon",       f"{APP_NAME}.app", "150", "180",
                "--app-drop-link", "450", "180",
                "--background", str(BASE / "resources" / "dmg_bg.png")
                    if (BASE / "resources" / "dmg_bg.png").exists() else "",
                str(dmg_out),
                str(app_path),
            ])
            print(f"✅  DMG 建立完成：{dmg_out}")
            return
        except subprocess.CalledProcessError:
            pass

    # fallback：用 hdiutil
    try:
        staging = DIST / "_dmg_staging"
        staging.mkdir(exist_ok=True)
        shutil.copytree(app_path, staging / app_path.name, dirs_exist_ok=True)
        run([
            "hdiutil", "create",
            "-volname", APP_NAME,
            "-srcfolder", str(staging),
            "-ov", "-format", "UDZO",
            str(dmg_out),
        ])
        shutil.rmtree(staging)
        print(f"✅  DMG 建立完成：{dmg_out}")
    except subprocess.CalledProcessError as e:
        print(f"⚠️   DMG 建立失敗（{e}），跳過")


# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build AcroPDF for macOS")
    parser.add_argument("--onefile", action="store_true",
                        help="打包成單一執行檔（較慢）")
    parser.add_argument("--sign",    metavar="IDENTITY", default=None,
                        help='程式碼簽署身分，例如 "Developer ID Application: ..."')
    args = parser.parse_args()
    build(args.onefile, args.sign)
