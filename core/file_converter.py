# ~/Desktop/acropdf/core/file_converter.py
"""
統一檔案轉換器：把任何支援的格式轉成 fitz.Document。
所有轉換在背景執行緒中完成，不阻塞 UI。
"""
import os
import sys
import fitz
import tempfile
import subprocess
import threading
from pathlib import Path

# ── 中文字型（reportlab 用）──────────────────────────────────────
_CJK_FONT_NAME = "ChineseFallback"
_CJK_FONT_REGISTERED = False

def _register_cjk_font():
    """註冊系統中文字型供 reportlab 使用（新細明體 → 宋體 → 蘋方）。"""
    global _CJK_FONT_REGISTERED, _CJK_FONT_NAME
    if _CJK_FONT_REGISTERED:
        return _CJK_FONT_NAME
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    # 候選字型（按優先順序）
    candidates = [
        ("/Library/Fonts/Microsoft/PMingLiU.ttf", "PMingLiU"),
        ("/Library/Fonts/PMingLiU.ttf", "PMingLiU"),
        ("/System/Library/Fonts/Supplemental/Songti.ttc", "Songti"),
        ("/System/Library/Fonts/PingFang.ttc", "PingFang"),
        ("/System/Library/Fonts/STHeiti Light.ttc", "STHeiti"),
    ]
    # Windows
    if sys.platform == "win32":
        winfonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        candidates = [
            (os.path.join(winfonts, "mingliu.ttc"), "PMingLiU"),
            (os.path.join(winfonts, "simsun.ttc"), "SimSun"),
            (os.path.join(winfonts, "msyh.ttc"), "MSYaHei"),
        ] + candidates
    for font_path, name in candidates:
        if os.path.isfile(font_path):
            try:
                pdfmetrics.registerFont(TTFont(name, font_path, subfontIndex=0))
                _CJK_FONT_NAME = name
                _CJK_FONT_REGISTERED = True
                return name
            except Exception:
                continue
    # 全部找不到 → 回退 Helvetica（中文會變方塊）
    _CJK_FONT_REGISTERED = True
    _CJK_FONT_NAME = "Helvetica"
    return "Helvetica"

# 支援的副檔名 → 類型分組
SUPPORTED_EXTS = {
    # PDF 族
    ".pdf": "pdf",
    # 圖片（fitz 原生支援）
    ".jpg": "image", ".jpeg": "image", ".png": "image",
    ".bmp": "image", ".tiff": "image", ".tif": "image",
    ".gif": "image", ".webp": "image", ".svg": "image",
    # Office（需轉換）
    ".xlsx": "excel", ".xls": "excel",
    ".docx": "word",  ".doc": "word",
    ".pptx": "pptx",
}

def get_file_type(path: str) -> str | None:
    ext = Path(path).suffix.lower()
    return SUPPORTED_EXTS.get(ext)


class FileConverter:
    """
    轉換各種格式為 fitz.Document。
    呼叫 convert() 是同步的；AsyncConverter 做非同步包裝。
    """

    # ── 圖片（fitz 直接開啟）──────────────────────────────────────
    @staticmethod
    def image_to_fitz(path: str) -> fitz.Document:
        """JPEG/PNG/BMP 等 → fitz.Document（單頁）"""
        if Path(path).suffix.lower() in (".tif", ".tiff"):
            import io
            from PIL import Image, ImageSequence, ImageOps
            doc = fitz.open()
            try:
                with Image.open(path) as image:
                    for frame in ImageSequence.Iterator(image):
                        oriented=ImageOps.exif_transpose(frame).convert("RGB")
                        dpi=frame.info.get("dpi",(96,96))
                        xdpi=max(1,float(dpi[0]));ydpi=max(1,float(dpi[1]))
                        page=doc.new_page(width=oriented.width*72/xdpi,height=oriented.height*72/ydpi)
                        buffer=io.BytesIO();oriented.save(buffer,format="PNG")
                        page.insert_image(page.rect,stream=buffer.getvalue())
                return doc
            except Exception:
                doc.close();raise
        with fitz.open(path) as original:
            if len(original)==0: raise ValueError("圖片沒有可轉換的頁面。")
            return fitz.open('pdf',original.convert_to_pdf())

    # ── Excel（openpyxl → 逐格渲染）──────────────────────────────
    @staticmethod
    def excel_to_fitz(path: str) -> fitz.Document:
        """XLSX → fitz.Document（每個工作表一頁）"""
        # 優先嘗試 LibreOffice 高品質轉換
        lo_result = FileConverter._libreoffice_to_pdf(path)
        if lo_result is not None:
            return lo_result

        raise RuntimeError("Office 版面轉換需要 LibreOffice。請在依賴管理器安裝，避免截斷儲存格內容。")

    # ── Word DOCX ────────────────────────────────────────────────
    @staticmethod
    def docx_to_fitz(path: str) -> fitz.Document:
        """DOCX/DOC → fitz.Document"""
        lo_result = FileConverter._libreoffice_to_pdf(path)
        if lo_result is not None:
            return lo_result

        raise RuntimeError("Office 版面轉換需要 LibreOffice。請在依賴管理器安裝，避免遺失圖片、表格與版面。")

    # ── PPTX ────────────────────────────────────────────────────
    @staticmethod
    def pptx_to_fitz(path: str) -> fitz.Document:
        """PPTX → fitz.Document（每張投影片一頁）"""
        lo_result = FileConverter._libreoffice_to_pdf(path)
        if lo_result is not None:
            return lo_result

        raise RuntimeError("投影片版面轉換需要 LibreOffice。請在依賴管理器安裝，避免遺失圖表和文字。")

    # ── LibreOffice headless（最高品質）─────────────────────────
    @staticmethod
    def _libreoffice_to_pdf(path: str) -> fitz.Document | None:
        """Isolated profile and temporary output, preserving actual Office layout."""
        soffice = FileConverter._find_soffice()
        if not soffice: return None
        source = Path(path).resolve()
        if not source.is_file(): raise FileNotFoundError(source)
        with tempfile.TemporaryDirectory(prefix="acropdf_office_") as stage:
            stage=Path(stage);profile=stage/"profile";profile.mkdir();output=stage/"output";output.mkdir()
            (profile/"user").mkdir()
            (profile/"user/registrymodifications.xcu").write_text('<oor:items xmlns:oor="http://openoffice.org/2001/registry"><item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item></oor:items>')
            kwargs={"capture_output":True,"text":True,"timeout":120}
            if sys.platform == "win32": kwargs['creationflags']=subprocess.CREATE_NO_WINDOW
            result=subprocess.run([soffice,"-env:UserInstallation="+profile.as_uri(),"--headless","--norestore","--nodefault","--convert-to","pdf","--outdir",str(output),str(source)],**kwargs)
            target=output/(source.stem+".pdf")
            if result.returncode or not target.is_file():
                raise RuntimeError("LibreOffice 無法轉換此檔案："+(result.stderr or result.stdout)[-1000:])
            raw=target.read_bytes()
            converted=fitz.open('pdf',raw)
            if not len(converted): converted.close();raise ValueError("Office 轉換沒有產生任何頁面。")
            return converted

    @staticmethod
    def _find_soffice() -> str | None:
        candidates = []
        if sys.platform == "darwin":
            candidates = [
                "/Applications/LibreOffice.app/Contents/MacOS/soffice",
                "/usr/local/bin/soffice",
            ]
        elif sys.platform == "win32":
            candidates = [
                r"C:\Program Files\LibreOffice\program\soffice.exe",
                r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
            ]
        else:
            candidates = ["/usr/bin/soffice", "/usr/local/bin/soffice"]
        for c in candidates:
            if os.path.isfile(c):
                return c
        # 嘗試系統 PATH（shutil.which 跨平台，取代 Unix 的 which 指令）
        import shutil
        found = shutil.which("soffice")
        if found:
            return found
        return None

    # ── 統一入口 ────────────────────────────────────────────────
    @classmethod
    def convert(cls, path: str) -> fitz.Document:
        """根據副檔名自動選擇轉換策略，回傳 fitz.Document。"""
        file_type = get_file_type(path)
        if file_type is None:
            raise ValueError(f"不支援的格式：{path}")
        if file_type == "pdf":
            return fitz.open(path)
        if file_type == "image":
            return cls.image_to_fitz(path)
        if file_type == "excel":
            return cls.excel_to_fitz(path)
        if file_type == "word":
            return cls.docx_to_fitz(path)
        if file_type == "pptx":
            return cls.pptx_to_fitz(path)
        raise ValueError(f"未知類型：{file_type}")
