#!/usr/bin/env python3
"""
build_preflight.py — AcroPDF 打包前置檢查與自動修復
=====================================================
功能：
  1. Python 版本檢查（需 3.10+；3.13+ 警告 PyInstaller 相容性）
  2. 必要套件偵測 → 缺少自動 pip install
  3. 選用套件偵測 → 缺少只警告，不中斷
  4. 平台套件過濾（macOS 不裝 winrt；Windows 不裝 pyobjc）
  5. Windows 版本檢查（WinRT OCR 需要 Win10 1809+）
  6. PyInstaller 版本檢查（需 ≥ 6.0；建議 6.x）
  7. UPX 工具偵測（Windows 選用壓縮）

用法（由 build_mac.py / build_win.py 自動呼叫）：
    from build_preflight import run_preflight
    run_preflight()          # 失敗直接 sys.exit(1)
"""

from __future__ import annotations

import importlib
import importlib.metadata
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional

# ── ANSI 顏色 ─────────────────────────────────────────────────────────
_NO_COLOR = not sys.stdout.isatty() or platform.system() == "Windows"

def _c(code: str, text: str) -> str:
    if _NO_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"

OK   = lambda s: _c("32", f"✅  {s}")
WARN = lambda s: _c("33", f"⚠️   {s}")
ERR  = lambda s: _c("31", f"❌  {s}")
INFO = lambda s: _c("36", f"ℹ️   {s}")
HEAD = lambda s: _c("1;37", s)


# ── 套件規格 ──────────────────────────────────────────────────────────

@dataclass
class Pkg:
    import_name: str                  # import 時用的名稱
    pip_name: str   = ""              # pip install 時用的名稱（空 = 同 import_name）
    min_ver: str    = ""              # 最低版本（空 = 不檢查）
    optional: bool  = False           # True = 缺少只警告
    mac_only: bool  = False           # 僅 macOS
    win_only: bool  = False           # 僅 Windows
    extra: str      = ""              # 說明文字

    def __post_init__(self):
        if not self.pip_name:
            self.pip_name = self.import_name


# 套件清單
PACKAGES: list[Pkg] = [
    # ── 核心 ─────────────────────────────────────────────────────────
    Pkg("fitz",          "PyMuPDF",         min_ver="1.24"),
    Pkg("PyQt6",         "PyQt6",           min_ver="6.6"),
    Pkg("PyQt6.sip",     "PyQt6-sip",       optional=True),
    Pkg("pymupdf_fonts", "pymupdf-fonts"),

    # ── PDF 操作 ──────────────────────────────────────────────────────
    Pkg("pikepdf",       "pikepdf"),
    Pkg("pypdf",         "pypdf"),

    # ── 數位簽章 ──────────────────────────────────────────────────────
    Pkg("pyhanko",       "pyhanko",         optional=True,
        extra="數位簽章功能需要"),
    Pkg("pyhanko_certvalidator", "pyhanko-certvalidator", optional=True),
    Pkg("cryptography",  "cryptography"),

    # ── 匯出格式 ──────────────────────────────────────────────────────
    Pkg("openpyxl",      "openpyxl"),
    Pkg("pptx",          "python-pptx"),
    Pkg("docx",          "python-docx"),
    Pkg("reportlab",     "reportlab"),

    # ── 圖像 / OCR ────────────────────────────────────────────────────
    Pkg("PIL",           "Pillow"),
    Pkg("pytesseract",   "pytesseract",     optional=True,
        extra="Tesseract OCR fallback 需要"),

    # ── 打包工具 ──────────────────────────────────────────────────────
    Pkg("PyInstaller",   "pyinstaller",     min_ver="6.0"),

    # ── 選用強化 ──────────────────────────────────────────────────────
    Pkg("markitdown",    "markitdown",      optional=True,
        extra="自動標籤 MarkItDown 策略需要"),

    # ── macOS 專用（pyobjc 為系統框架，optional；runtime 時由 macOS 提供）──
    Pkg("Vision",        "pyobjc-framework-Vision",    mac_only=True, optional=True,
        extra="Apple Vision OCR 需要（缺少將 fallback 至 Tesseract）"),
    Pkg("Quartz",        "pyobjc-framework-Quartz",    mac_only=True, optional=True),
    Pkg("Foundation",    "pyobjc-framework-Foundation",mac_only=True, optional=True),
]


# ── 版本工具 ──────────────────────────────────────────────────────────

def _parse_ver(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.split(".")[:3])
    except ValueError:
        return (0,)


def _installed_ver(pip_name: str) -> Optional[str]:
    try:
        return importlib.metadata.version(pip_name)
    except importlib.metadata.PackageNotFoundError:
        return None


# ── pip 安裝 ──────────────────────────────────────────────────────────

def _in_venv() -> bool:
    """是否在 virtualenv / conda / venv 環境中。"""
    return (
        sys.prefix != sys.base_prefix
        or "VIRTUAL_ENV" in __import__("os").environ
        or "CONDA_DEFAULT_ENV" in __import__("os").environ
    )


def _pip_install(pip_name: str, min_ver: str = "") -> bool:
    """
    嘗試安裝套件，自動處理：
      - 一般環境：直接 pip install
      - Homebrew / externally-managed Python（PEP 668）：
        先試 --user，失敗再加 --break-system-packages
      - venv：不需要特殊旗標
    """
    spec = f"{pip_name}>={min_ver}" if min_ver else pip_name
    base_cmd = [sys.executable, "-m", "pip", "install", "--quiet", "--upgrade", spec]

    def _try(extra_flags: list[str]) -> bool:
        cmd = base_cmd[:-1] + extra_flags + [spec]
        flag_str = " ".join(extra_flags) if extra_flags else ""
        print(f"     → pip install {flag_str} {spec}".strip())
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            if r.returncode == 0:
                return True
            # PEP 668：externally-managed-environment
            if "externally-managed-environment" in r.stderr:
                return None   # 需要升級旗標
            print(ERR(f"pip install 失敗：{r.stderr[-300:].strip()}"))
            return False
        except subprocess.TimeoutExpired:
            print(ERR("pip install 逾時"))
            return False

    if _in_venv():
        result = _try([])
        return result is True

    # 非 venv：先試無旗標
    result = _try([])
    if result is True:
        return True
    if result is None:
        # PEP 668：改試 --user
        result = _try(["--user"])
        if result is True:
            return True
        if result is None:
            # 仍受管制：加 --break-system-packages
            result = _try(["--user", "--break-system-packages"])
            return result is True
    return False


# ── Python 版本檢查 ────────────────────────────────────────────────────

def _check_python() -> bool:
    major, minor = sys.version_info[:2]
    ver_str = f"Python {major}.{minor}.{sys.version_info.micro}"

    if (major, minor) < (3, 10):
        print(ERR(f"{ver_str} 不支援（需要 3.10+）"))
        print(INFO("請升級 Python：https://www.python.org/downloads/"))
        return False

    if (major, minor) >= (3, 13):
        print(WARN(
            f"{ver_str} — PyInstaller 對 3.13+ 的支援仍在 beta，"
            "若遇到打包錯誤可改用 3.11/3.12"
        ))
    else:
        print(OK(f"{ver_str}"))
    return True


# ── Windows 版本檢查 ───────────────────────────────────────────────────

def _check_windows_version():
    if platform.system() != "Windows":
        return
    try:
        ver = sys.getwindowsversion()
        build = ver.build
        # Win10 1809 = build 17763
        if ver.major < 10 or (ver.major == 10 and build < 17763):
            print(WARN(
                f"Windows build {build} — WinRT OCR 需要 Win10 1809+（build 17763+）。"
                "自動標籤 AI 策略將 fallback 至 Tesseract。"
            ))
        else:
            print(OK(f"Windows build {build}（WinRT OCR 可用）"))
    except Exception:
        pass


# ── PyInstaller 版本檢查 ───────────────────────────────────────────────

def _check_pyinstaller() -> bool:
    ver_str = _installed_ver("pyinstaller")
    if not ver_str:
        print(INFO("PyInstaller 未安裝，嘗試安裝…"))
        if not _pip_install("pyinstaller", "6.0"):
            return False
        ver_str = _installed_ver("pyinstaller") or "?"

    parsed = _parse_ver(ver_str)
    if parsed < (6, 0):
        print(WARN(f"PyInstaller {ver_str} 過舊（建議 ≥6.0），嘗試升級…"))
        _pip_install("pyinstaller", "6.0")
        ver_str = _installed_ver("pyinstaller") or ver_str

    print(OK(f"PyInstaller {ver_str}"))
    return True


# ── 套件主檢查迴圈 ────────────────────────────────────────────────────

def _check_packages(is_mac: bool, is_win: bool) -> bool:
    all_ok = True

    for pkg in PACKAGES:
        # 平台過濾
        if pkg.mac_only and not is_mac:
            continue
        if pkg.win_only and not is_win:
            continue

        # 嘗試 import
        try:
            importlib.import_module(pkg.import_name)
            imported = True
        except ImportError:
            imported = False

        # 版本檢查
        if imported and pkg.min_ver:
            installed = _installed_ver(pkg.pip_name)
            if installed and _parse_ver(installed) < _parse_ver(pkg.min_ver):
                print(WARN(
                    f"{pkg.pip_name} {installed} 過舊（需要 ≥{pkg.min_ver}），升級中…"
                ))
                if _pip_install(pkg.pip_name, pkg.min_ver):
                    print(OK(f"{pkg.pip_name} 已升級"))
                else:
                    print(ERR(f"{pkg.pip_name} 升級失敗"))
                    if not pkg.optional:
                        all_ok = False
                continue

        if imported:
            ver = _installed_ver(pkg.pip_name)
            label = f"{pkg.pip_name}" + (f" {ver}" if ver else "")
            print(OK(label))
            continue

        # 未安裝 → 嘗試自動安裝（optional 的也試裝，但失敗只警告）
        hint = f"（{pkg.extra}）" if pkg.extra else ""
        print(INFO(f"{pkg.pip_name} 未安裝{hint}，嘗試安裝…"))
        installed_ok = _pip_install(pkg.pip_name, pkg.min_ver)

        if installed_ok:
            # 驗證 import 可用
            try:
                importlib.import_module(pkg.import_name)
                ver = _installed_ver(pkg.pip_name)
                print(OK(f"{pkg.pip_name} {ver or ''} 安裝成功"))
            except ImportError:
                if pkg.optional:
                    print(WARN(f"{pkg.pip_name} 安裝後仍無法 import，跳過"))
                else:
                    print(ERR(f"{pkg.pip_name} 安裝後仍無法 import"))
                    all_ok = False
        else:
            if pkg.optional:
                print(WARN(f"{pkg.pip_name} 安裝失敗，相關功能將被跳過"))
            else:
                print(ERR(f"{pkg.pip_name} 安裝失敗，打包可能不完整"))
                all_ok = False

    return all_ok


# ── UPX 偵測（Windows）────────────────────────────────────────────────

def _check_upx():
    if platform.system() != "Windows":
        return
    import shutil
    if shutil.which("upx"):
        print(OK("UPX 壓縮工具已安裝"))
    else:
        print(INFO(
            "UPX 未安裝（選用，可縮減 EXE 體積）。"
            "下載：https://upx.github.io/"
        ))


# ── 磁碟空間快速估計 ──────────────────────────────────────────────────

def _check_disk():
    import shutil as _shutil
    from pathlib import Path
    try:
        free_gb = _shutil.disk_usage(Path.home()).free / 1e9
        if free_gb < 2.0:
            print(WARN(f"可用磁碟空間 {free_gb:.1f} GB，建議至少 2 GB（打包產物約 400MB）"))
        else:
            print(OK(f"可用磁碟空間 {free_gb:.1f} GB"))
    except Exception:
        pass


# ── 主入口 ────────────────────────────────────────────────────────────

def run_preflight(auto_fix: bool = True) -> bool:
    """
    執行所有前置檢查。
    auto_fix=True：缺少必要套件時自動 pip install。
    回傳 True 代表可繼續打包；False 代表有無法修復的問題。
    """
    is_mac = platform.system() == "Darwin"
    is_win = platform.system() == "Windows"

    print(Head := HEAD("\n╔══ AcroPDF 打包前置檢查 ══╗"))
    print(f"  平台：{platform.system()} {platform.machine()}")

    passed = True
    print(HEAD("\n── Python ──"))
    if not _check_python():
        return False

    if is_win:
        print(HEAD("\n── Windows ──"))
        _check_windows_version()

    print(HEAD("\n── 套件 ──"))
    if not _check_packages(is_mac, is_win):
        passed = False

    print(HEAD("\n── 打包工具 ──"))
    if not _check_pyinstaller():
        passed = False

    _check_upx()
    _check_disk()

    if passed:
        print(HEAD("\n✅  前置檢查通過，開始打包…\n"))
    else:
        print(HEAD("\n❌  部分必要套件無法安裝，請手動排除後重試。\n"))

    return passed


if __name__ == "__main__":
    ok = run_preflight()
    sys.exit(0 if ok else 1)
