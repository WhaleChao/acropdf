# ~/Desktop/acropdf/platform/__init__.py
"""
跨平台抽象層入口。
根據 sys.platform 自動選擇正確的實作，其他模組只需：
    from acro_platform import get_ocr_backend
不需知道底層是 Vision / WinRT / Tesseract。
"""
import sys

def get_ocr_backend():
    """回傳當前平台最佳的 OCR backend 實例"""
    if sys.platform == "darwin":
        try:
            from acro_platform.mac import MacVisionOCR
            return MacVisionOCR()
        except ImportError:
            pass
    elif sys.platform == "win32":
        try:
            from acro_platform.windows import WinRTOCR
            return WinRTOCR()
        except ImportError:
            pass
    # 所有平台的最終 fallback
    from acro_platform.common import TesseractOCR
    return TesseractOCR()

def get_native_printer():
    """回傳平台原生列印介面"""
    # PyQt6 的 QPrintDialog 已跨平台，不需額外抽象
    return None

def get_temp_dir() -> str:
    """回傳暫存目錄（跨平台安全路徑）"""
    import tempfile
    return tempfile.gettempdir()

def find_executable(name: str) -> str | None:
    """跨平台尋找可執行檔（替代 Unix which）"""
    import shutil
    return shutil.which(name)
