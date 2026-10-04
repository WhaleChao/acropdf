# ~/Desktop/acropdf/core/dependency_manager.py
"""
外部依賴管理器。
掃描 Tesseract、LibreOffice 等外部程式，
缺失時提供自動安裝（Homebrew/winget）或一鍵下載引導。
"""
import os
import sys
import shutil
import subprocess
import platform as _platform
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

class DepStatus(Enum):
    INSTALLED = "已安裝"
    MISSING = "未安裝"
    OPTIONAL_MISSING = "未安裝（選用）"

@dataclass
class Dependency:
    name: str                     # 顯示名稱
    purpose: str                  # 功能說明
    required: bool                # True = 必須, False = 選用（有 fallback）
    status: DepStatus = DepStatus.MISSING
    version: str = ""
    path: str = ""
    install_cmd_mac: str = ""     # Homebrew 自動安裝指令
    install_cmd_win: str = ""     # winget / choco 自動安裝指令
    download_url: str = ""        # 手動下載 URL
    install_note: str = ""        # 安裝後備註


class DependencyManager:
    """掃描並管理所有外部依賴"""

    def __init__(self):
        self.deps: list[Dependency] = []
        self._define_deps()

    def _define_deps(self):
        self.deps = [
            Dependency(
                name="Tesseract OCR",
                purpose="文字辨識（OCR）— 將掃描 PDF 轉為可搜尋文字",
                required=False,  # Mac 有 Vision、Win 有 WinRT 作為替代
                install_cmd_mac="brew install tesseract tesseract-lang",
                install_cmd_win='winget install --id UB-Mannheim.TesseractOCR --accept-source-agreements --accept-package-agreements',
                download_url="https://github.com/UB-Mannheim/tesseract/wiki",
                install_note="安裝時請勾選「繁體中文 (chi_tra)」語言包",
            ),
            Dependency(
                name="LibreOffice",
                purpose="開啟 Word/Excel/PowerPoint 檔案（高品質轉換）",
                required=False,  # Office 匯入需要；PDF 操作不需要
                install_cmd_mac="brew install --cask libreoffice",
                install_cmd_win='winget install --id TheDocumentFoundation.LibreOffice --accept-source-agreements --accept-package-agreements',
                download_url="https://www.libreoffice.org/download/download/",
                install_note="安裝後 AcroPDF 會自動偵測，無需額外設定",
            ),
            Dependency(
                name="Ghostscript",
                purpose="PDF/A 與 PDF/X 的 ICC／字型轉換",
                required=False,
                install_cmd_mac="brew install ghostscript",
                install_cmd_win='winget install --id ArtifexSoftware.GhostScript --accept-source-agreements --accept-package-agreements',
                download_url="https://ghostscript.com/releases/gsdnld.html",
                install_note="",
            ),
            Dependency(name="Java (veraPDF)",purpose="離線 PDF/A 與 PDF/UA 獨立驗證",required=False,
                       install_cmd_mac="brew install --cask temurin",
                       install_cmd_win="winget install --id EclipseAdoptium.Temurin.21.JRE --accept-source-agreements --accept-package-agreements",
                       download_url="https://adoptium.net/temurin/releases/",install_note="veraPDF 驗證器已附於 AcroPDF，Java 需另行安裝。"),
        ]

    # ── 掃描 ─────────────────────────────────────────────────────
    def scan_all(self) -> list[Dependency]:
        """掃描所有外部依賴的安裝狀態"""
        for dep in self.deps:
            if dep.name == "Tesseract OCR":
                self._check_tesseract(dep)
            elif dep.name == "LibreOffice":
                self._check_libreoffice(dep)
            elif dep.name == "Ghostscript":
                self._check_ghostscript(dep)
            elif dep.name == "Java (veraPDF)":
                from core.pdf_standards import find_java
                path = find_java()
                dep.status = DepStatus.INSTALLED if path else DepStatus.OPTIONAL_MISSING
                dep.path = path or ""
                dep.version = self._get_version([path,"-version"]) if path else ""
        return self.deps

    def get_missing(self, required_only: bool = False) -> list[Dependency]:
        """取得缺失的依賴清單"""
        self.scan_all()
        return [d for d in self.deps
                if d.status != DepStatus.INSTALLED
                and (not required_only or d.required)]

    # ── Tesseract ────────────────────────────────────────────────
    def _check_tesseract(self, dep: Dependency):
        path = self._find_executable("tesseract", [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            "/opt/homebrew/bin/tesseract",
            "/usr/local/bin/tesseract",
        ])
        if path:
            dep.status = DepStatus.INSTALLED
            dep.path = path
            dep.version = self._get_version([path, "--version"])
        else:
            dep.status = DepStatus.OPTIONAL_MISSING if not dep.required else DepStatus.MISSING

    # ── LibreOffice ──────────────────────────────────────────────
    def _check_libreoffice(self, dep: Dependency):
        path = self._find_executable("soffice", [
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
            "/Applications/LibreOffice.app/Contents/MacOS/soffice",
            "/usr/local/bin/soffice",
        ])
        if path:
            dep.status = DepStatus.INSTALLED
            dep.path = path
            dep.version = self._get_version([path, "--version"])
        else:
            dep.status = DepStatus.OPTIONAL_MISSING

    # ── Ghostscript ──────────────────────────────────────────────
    def _check_ghostscript(self, dep: Dependency):
        from core.pdf_standards import find_executable
        try: path = find_executable('gs')
        except (RuntimeError, FileNotFoundError): path = None
        if path:
            dep.status = DepStatus.INSTALLED
            dep.path = path
            dep.version = self._get_version([path, "--version"])
        else:
            dep.status = DepStatus.OPTIONAL_MISSING

    # ── 工具方法 ─────────────────────────────────────────────────
    @staticmethod
    def _find_executable(name: str, extra_paths: list[str]) -> str | None:
        """跨平台搜尋執行檔"""
        # 1. shutil.which（搜尋 PATH）
        found = shutil.which(name)
        if found:
            return found
        # 2. 常見安裝路徑
        for p in extra_paths:
            if os.path.isfile(p):
                return p
        return None

    @staticmethod
    def _get_version(cmd: list[str]) -> str:
        """安全取得版本號"""
        try:
            kwargs = {"capture_output": True, "text": True, "timeout": 5}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            r = subprocess.run(cmd, **kwargs)
            output = r.stdout.strip() or r.stderr.strip()
            # 取第一行
            return output.splitlines()[0] if output else ""
        except Exception:
            return ""

    # ── 自動安裝 ─────────────────────────────────────────────────
    @staticmethod
    def auto_install(dep: Dependency) -> tuple[bool, str]:
        """
        嘗試自動安裝。回傳 (成功, 訊息)。
        macOS: 用 Homebrew
        Windows: 用 winget（Win10 內建）
        """
        if sys.platform == "darwin":
            cmd = dep.install_cmd_mac
            # 先確認 Homebrew 已安裝
            if not shutil.which("brew"):
                return False, "需要先安裝 Homebrew：https://brew.sh"
        elif sys.platform == "win32":
            cmd = dep.install_cmd_win
            # 先確認 winget 可用
            if not shutil.which("winget"):
                return False, "Windows 版本過舊或 winget 不可用，請手動下載安裝"
        else:
            return False, "不支援自動安裝，請手動安裝"

        if not cmd:
            return False, "此程式不支援自動安裝，請手動下載"

        try:
            kwargs = {"capture_output": True, "text": True, "timeout": 300}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            r = subprocess.run(cmd.split(), **kwargs)
            if r.returncode == 0:
                return True, f"{dep.name} 安裝成功！"
            else:
                error = r.stderr.strip()[:200] if r.stderr else "未知錯誤"
                return False, f"自動安裝失敗：{error}"
        except subprocess.TimeoutExpired:
            return False, "安裝逾時（超過 5 分鐘），請手動安裝"
        except Exception as e:
            return False, f"安裝失敗：{e}"
