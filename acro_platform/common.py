# ~/Desktop/acropdf/platform/common.py
"""
Tesseract OCR — 跨平台 fallback。
macOS 和 Windows 都能用，只需安裝 Tesseract 並確保在 PATH 或設定路徑。
"""
import os
import sys
import shutil
import fitz

class TesseractOCR:
    """Tesseract OCR backend（Mac + Windows 通用）"""
    name = "Tesseract"

    def __init__(self):
        self._tess_cmd = self._find_tesseract()

    def is_available(self) -> bool:
        return self._tess_cmd is not None

    def _find_tesseract(self) -> str | None:
        """跨平台搜尋 Tesseract 執行檔"""
        # 1. 環境變數
        env_path = os.environ.get("TESSERACT_CMD")
        if env_path and os.path.isfile(env_path):
            return env_path

        # 2. shutil.which（跨平台，取代 Unix 的 which 指令）
        found = shutil.which("tesseract")
        if found:
            return found

        # 3. 平台常見安裝路徑
        if sys.platform == "win32":
            candidates = [
                r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe"),
            ]
        elif sys.platform == "darwin":
            candidates = [
                "/opt/homebrew/bin/tesseract",
                "/usr/local/bin/tesseract",
            ]
        else:
            candidates = ["/usr/bin/tesseract"]

        for c in candidates:
            if os.path.isfile(c):
                return c
        return None

    def ocr_page(self, page: fitz.Page, lang: str, dpi: int) -> None:
        """用 PyMuPDF 內建 Tesseract 整合做 OCR"""
        if self._tess_cmd:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = self._tess_cmd
        page.get_textpage_ocr(language=lang, dpi=dpi, full=True)

    def ocr_image_path(self, image_path: str, lang: str = "chi_tra+eng") -> str:
        """OCR 指定圖片，回傳文字字串（供 auto_label_engine 使用）。"""
        try:
            import pytesseract
            from PIL import Image
            if self._tess_cmd:
                pytesseract.pytesseract.tesseract_cmd = self._tess_cmd
            return pytesseract.image_to_string(Image.open(image_path), lang=lang)
        except Exception:
            return ""

    def supported_languages(self) -> list[str]:
        if not self._tess_cmd:
            return ["eng"]
        try:
            import subprocess
            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            r = subprocess.run(
                [self._tess_cmd, "--list-langs"],
                capture_output=True, text=True, timeout=10, **kwargs
            )
            langs = [l.strip() for l in r.stdout.splitlines() if l.strip() and not l.startswith("List")]
            return langs if langs else ["eng"]
        except Exception:
            return ["eng"]
