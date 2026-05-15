# ~/Desktop/acropdf/main.py
import sys
import os
import json
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QLocale, QTranslator, QLibraryInfo, QEvent
from PyQt6.QtGui import QIcon, QFileOpenEvent

APP_NAME = "AcroPDF"
APP_VERSION = "1.0.10"

def _state_file_path() -> Path:
    """回傳 loader 狀態檔位置；正式 app 不可寫入已簽章的 bundle。"""
    env_path = os.environ.get("ACROPDF_STATE_FILE")
    if env_path:
        return Path(env_path)
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support" / APP_NAME
        elif sys.platform == "win32":
            base = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
        else:
            base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / APP_NAME
        return base / ".loader_state"
    return Path(__file__).parent / ".loader_state"


# loader.py 透過此檔與子程序溝通當前開啟的 PDF
_STATE_FILE = _state_file_path()


def _write_state(pdf_path: str | None):
    """把當前開啟的 PDF 路徑寫給 loader，供熱重載後還原。"""
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(
            json.dumps({"current_file": pdf_path or ""})
        )
    except Exception:
        pass


class _AcroPDFApp(QApplication):
    """自訂 QApplication：攔截 macOS Finder 傳入的檔案開啟事件。"""

    def __init__(self, argv):
        super().__init__(argv)
        self._main_window = None
        self._pending_files: list[str] = []  # 視窗尚未建立時暫存

    def set_main_window(self, w):
        self._main_window = w
        # 處理在視窗建立前就收到的開檔事件
        for path in self._pending_files:
            self._open_file_safe(path)
        self._pending_files.clear()

    def event(self, event: QEvent) -> bool:
        if isinstance(event, QFileOpenEvent):
            path = event.file()
            if path and os.path.isfile(path):
                if self._main_window:
                    self._open_file_safe(path)
                else:
                    self._pending_files.append(path)
            return True
        return super().event(event)

    def _open_file_safe(self, path: str):
        try:
            self._main_window.open_file(path)
        except Exception:
            pass


def main():
    # HiDPI 設定（必須在 QApplication 之前）
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    _cleanup_temp_files()
    app = _AcroPDFApp(sys.argv)
    QLocale.setDefault(QLocale(QLocale.Language.Chinese, QLocale.Country.Taiwan))
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("YourOffice")
    app.setApplicationVersion(APP_VERSION)

    # 載入 Qt 繁體中文翻譯（列印對話框等原生 UI 元件）
    app._translators = []  # 保留參照，避免 QTranslator 被 GC 後翻譯失效
    qt_tr_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    for prefix in ("qtbase_zh_TW", "qt_zh_TW"):
        translator = QTranslator(app)
        if translator.load(prefix, qt_tr_path):
            app.installTranslator(translator)
            app._translators.append(translator)

    # 應用程式圖示
    _set_app_icon(app)

    # 載入樣式表
    _load_stylesheet(app)

    from ui.main_window import MainWindow
    window = MainWindow()

    # ── 與 loader 溝通：追蹤當前開啟的 PDF ──────────────
    _orig_open = window.open_file
    def _patched_open(path, *a, **kw):
        result = _orig_open(path, *a, **kw)
        _write_state(os.path.abspath(path))
        return result
    window.open_file = _patched_open  # type: ignore[method-assign]

    window.show()

    # 讓 app 知道視窗已就緒，處理待開檔案
    app.set_main_window(window)

    # 若從命令列帶入 PDF 路徑（支援多檔）
    for arg in sys.argv[1:]:
        if os.path.isfile(arg):
            try:
                window.open_file(arg)
            except Exception:
                pass

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
