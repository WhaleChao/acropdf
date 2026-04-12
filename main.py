# ~/Desktop/acropdf/main.py
import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

APP_NAME = "AcroPDF"
APP_VERSION = "1.0.1-hotfix1"

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

    # 載入樣式表
    _load_stylesheet(app)

    from ui.main_window import MainWindow
    window = MainWindow()
    window.show()

    # 若從命令列帶入 PDF 路徑
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        window.open_file(sys.argv[1])

    sys.exit(app.exec())

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


def _cleanup_temp_files():
    try:
        from core.temp_manager import cleanup_temp_files
        cleanup_temp_files()
    except Exception:
        pass

if __name__ == "__main__":
    main()
