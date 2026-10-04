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
import hashlib
from pathlib import Path

BASE   = Path(__file__).parent.resolve()
DIST   = BASE / "dist"
BUILD  = BASE / "build"
ICON   = BASE / "resources" / "icons" / "acropdf.icns"

APP_NAME    = "AcroPDF"
BUNDLE_ID   = "com.whalechao.acropdf"
ENTRY_POINT = str(BASE / "main.py")


def run(cmd: list[str], **kw):
    print(f"\n$ {' '.join(str(c) for c in cmd)}")
    subprocess.run(cmd, check=True, **kw)


def build(onefile: bool, sign_id: str | None, skip_preflight: bool = False):
    # ── 前置檢查 ─────────────────────────────────────────
    if not skip_preflight:
        from build_preflight import run_preflight
        if not run_preflight():
            sys.exit(1)

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
        "--add-data", f"{BASE / 'docs'}:docs",
        "--add-data", f"{BASE / 'LICENSE'}:.",
        # ── PyMuPDF / PyQt6 ──────────────────────────────────
        "--hidden-import", "fitz",
        "--hidden-import", "fitz.utils",
        "--hidden-import", "PyQt6.sip",
        "--hidden-import", "PyQt6.QtPrintSupport",
        "--collect-all",  "fitz",
        "--collect-all",  "pymupdf_fonts",
        # ── PDF 安全 / 簽章 ───────────────────────────────────
        "--collect-all",  "pikepdf",
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
        # ── macOS Vision / Quartz（pyobjc，系統框架）────────────
        "--hidden-import", "Vision",
        "--hidden-import", "Quartz",
        "--hidden-import", "Foundation",
        # ── 自動標籤（stdlib，保險起見列出）─────────────────────
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

    # ── 補充 Info.plist：加入 PDF 檔案類型支援 ─────────────
    _patch_info_plist(app_path)

    print(f"\n✅  打包完成：{app_path}")

    # ── 程式碼簽署（選用）───────────────────────────────
    if sign_id:
        sign_cmd = [
            "codesign",
            "--deep", "--force", "--options", "runtime",
            "--sign", sign_id,
        ]
        entitlements = BASE / "resources" / "entitlements.plist"
        if entitlements.exists():
            sign_cmd += ["--entitlements", str(entitlements)]
        sign_cmd.append(str(app_path))
        run(sign_cmd)
        run(["codesign", "--verify", "--deep", "--strict", str(app_path)])
        print("✅  程式碼簽署完成")
    else:
        # Info.plist was changed after PyInstaller's signing step. Seal the final local bundle.
        run(["codesign", "--deep", "--force", "--sign", "-", str(app_path)])
        run(["codesign", "--verify", "--deep", "--strict", str(app_path)])
        print("✅  本機 ad-hoc 簽署完成（非 Developer ID，未 notarize）")

    # ── 建立 DMG（選用，需要 create-dmg 或 hdiutil）────────
    _make_dmg(app_path)


def _patch_info_plist(app_path: Path):
    """在 Info.plist 加入 CFBundleDocumentTypes，讓 Finder 知道可以開 PDF。"""
    import plistlib
    import re
    plist_path = app_path / "Contents" / "Info.plist"
    if not plist_path.exists():
        return
    with open(plist_path, "rb") as f:
        plist = plistlib.load(f)
    version = "1.0.0"
    try:
        main_text = (BASE / "main.py").read_text(encoding="utf-8")
        m = re.search(r'APP_VERSION\s*=\s*[\'"]([^\'"]+)[\'"]', main_text)
        if m:
            version = m.group(1)
    except OSError:
        pass
    plist["CFBundleShortVersionString"] = version
    plist["CFBundleVersion"] = version
    plist["CFBundleDevelopmentRegion"] = "zh_TW"
    plist["CFBundleLocalizations"] = ["zh_TW", "zh-Hant", "en"]
    plist["CFBundleAllowMixedLocalizations"] = True
    plist["CFBundleDocumentTypes"] = [
        {
            "CFBundleTypeName": "PDF 文件",
            "CFBundleTypeRole": "Editor",
            "LSHandlerRank": "Alternate",
            "LSItemContentTypes": ["com.adobe.pdf"],
            "CFBundleTypeExtensions": ["pdf"],
            "CFBundleTypeIconFile": "acropdf.icns",
        },
        {
            "CFBundleTypeName": "圖片",
            "CFBundleTypeRole": "Viewer",
            "LSHandlerRank": "Alternate",
            "LSItemContentTypes": [
                "public.png", "public.jpeg", "public.tiff", "com.microsoft.bmp",
            ],
            "CFBundleTypeExtensions": ["png", "jpg", "jpeg", "tiff", "tif", "bmp"],
        },
    ]
    # 重新簽名需要的欄位
    plist.setdefault("NSHighResolutionCapable", True)
    with open(plist_path, "wb") as f:
        plistlib.dump(plist, f)
    _write_info_plist_strings(app_path)
    # 重新 ad-hoc 簽名（修改 Info.plist 會使舊簽名失效）
    subprocess.run(
        ["codesign", "--deep", "--force", "--sign", "-", str(app_path)],
        capture_output=True,
    )


def _write_info_plist_strings(app_path: Path):
    """補齊繁中 Bundle 資源，讓 macOS 原生面板可採用繁體中文語系。"""
    resources = app_path / "Contents" / "Resources"
    zh_dir = resources / "zh_TW.lproj"
    zh_dir.mkdir(parents=True, exist_ok=True)
    strings = (
        'CFBundleDisplayName = "AcroPDF";\n'
        'CFBundleName = "AcroPDF";\n'
        'PDF Document = "PDF 文件";\n'
        'Image = "圖片";\n'
    )
    (zh_dir / "InfoPlist.strings").write_text(strings, encoding="utf-16")


def _make_dmg(app_path: Path):
    dmg_out = DIST / f"{APP_NAME}.dmg"
    staging = DIST / "_dmg_staging"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(exist_ok=True)
    shutil.copytree(app_path, staging / app_path.name, dirs_exist_ok=True)
    unblock_script = BASE / "scripts" / "unblock_acropdf_macos.command"
    if unblock_script.exists():
        target_script = staging / "解除 macOS 安全限制.command"
        shutil.copy2(unblock_script, target_script)
        target_script.chmod(0o755)

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
                str(staging),
            ])
            shutil.rmtree(staging)
            print(f"✅  DMG 建立完成：{dmg_out}")
            _write_checksum(dmg_out)
            return
        except subprocess.CalledProcessError:
            pass

    # fallback：用 hdiutil
    try:
        run([
            "hdiutil", "create",
            "-volname", APP_NAME,
            "-srcfolder", str(staging),
            "-ov", "-format", "UDZO",
            str(dmg_out),
        ])
        shutil.rmtree(staging)
        print(f"✅  DMG 建立完成：{dmg_out}")
        _write_checksum(dmg_out)
    except subprocess.CalledProcessError as e:
        print(f"⚠️   DMG 建立失敗（{e}），跳過")


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
    parser = argparse.ArgumentParser(description="Build AcroPDF for macOS")
    parser.add_argument("--onefile", action="store_true",
                        help="打包成單一執行檔（較慢）")
    parser.add_argument("--sign",    metavar="IDENTITY", default=None,
                        help='程式碼簽署身分，例如 "Developer ID Application: ..."')
    parser.add_argument("--skip-preflight", action="store_true",
                        help="跳過前置檢查（已確認環境正確時使用）")
    args = parser.parse_args()
    build(args.onefile, args.sign, skip_preflight=args.skip_preflight)
