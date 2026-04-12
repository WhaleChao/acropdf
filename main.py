# ~/Desktop/acropdf/main.py
import sys
import os
import json
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

APP_NAME = "AcroPDF"
APP_VERSION = "1.0.2"

# loader.py 透過此檔與子程序溝通當前開啟的 PDF
_STATE_FILE = Path(__file__).parent / ".loader_state"


def _write_state(pdf_path: str | None):
    """把當前開啟的 PDF 路徑寫給 loader，供熱重載後還原。"""
    try:
        _STATE_FILE.write_text(
            json.dumps({"current_file": pdf_path or ""})
        )
    except Exception:
        pass


def main():
    # HiDPI 設定（必須在 QApplication 之前）
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    _cleanup_temp_files()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("YourOffice")
    app.setApplicationVersion(APP_VERSION)

    # 應用程式圖示
    _set_app_icon(app)

    # 載入樣式表
    _load_stylesheet(app)

    from ui.main_window import MainWindow
    window = MainWindow()

    # ── 與 loader 溝通：追蹤當前開啟的 PDF ──────────────
    def _on_file_opened(path: str):
        _write_state(path)

    def _on_file_closed():
        _write_state(None)

    # 連接 MainWindow 的 file_opened / file_closed 信號（若有）
    # 若 MainWindow 尚未有這些信號，用 monkey-patch 方式追蹤 open_file
    _orig_open = window.open_file
    def _patched_open(path, *a, **kw):
        result = _orig_open(path, *a, **kw)
        _write_state(os.path.abspath(path))
        return result
    window.open_file = _patched_open  # type: ignore[method-assign]

    window.show()

    # 若從命令列帶入 PDF 路徑（loader 傳入的上次檔案）
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        window.open_file(sys.argv[1])

    code = app.exec()
    _write_state(None)   # 正常退出時清空狀態
    sys.exit(code)

def _is_dark_mode() -> bool:
    """偵測系統是否為深色模式（macOS / Windows 通用）。"""
    try:
        if sys.platform == "darwin":
            import subprocess
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True, text=True
            )
            return result.stdout.strip().lower() == "dark"
        elif sys.platform == "win32":
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return value == 0
    except Exception:
        pass
    return False


def _load_stylesheet(app: QApplication):
    base_dir = os.path.dirname(__file__)
    theme = "dark" if _is_dark_mode() else "light"
    qss_path = os.path.join(base_dir, "resources", "styles", f"{theme}.qss")
    # fallback to light if dark not found
    if not os.path.isfile(qss_path):
        qss_path = os.path.join(base_dir, "resources", "styles", "light.qss")
    if os.path.isfile(qss_path):
        with open(qss_path, encoding="utf-8") as f:
            app.setStyleSheet(f.read())


def _set_app_icon(app: QApplication):
    """設定應用程式圖示（Dock、工作列、視窗標題欄）。"""
    base = Path(__file__).parent / "resources" / "icons"
    # 優先使用平台原生格式
    if sys.platform == "darwin":
        icon_path = base / "acropdf.icns"
    else:
        icon_path = base / "acropdf.ico"
    # fallback 到 PNG
    if not icon_path.exists():
        icon_path = base / "acropdf_1024.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))


def _cleanup_temp_files():
    try:
        from core.temp_manager import cleanup_temp_files
        cleanup_temp_files()
    except Exception:
        pass

if __name__ == "__main__":
    main()
