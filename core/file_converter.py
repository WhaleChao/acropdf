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
        doc = fitz.open()               # 空 PDF
        try:
            img_doc = fitz.open(path)    # fitz 自動辨識圖片格式
        except Exception:
            return doc  # 損壞或不支援的圖片，回傳空文件
        if img_doc.page_count == 0:
            img_doc.close()
            return doc
        rect = img_doc[0].rect
        w = max(rect.width, 1)
        h = max(rect.height, 1)
        page = doc.new_page(width=w, height=h)
        # 如果 fitz 能直接當 PDF 使用就用 show_pdf_page，否則用 insert_image
        if img_doc.is_pdf:
            page.show_pdf_page(page.rect, img_doc, 0)
            img_doc.close()
        else:
            img_doc.close()
            page.insert_image(page.rect, filename=path)
        return doc

    # ── Excel（openpyxl → 逐格渲染）──────────────────────────────
    @staticmethod
    def excel_to_fitz(path: str) -> fitz.Document:
        """XLSX → fitz.Document（每個工作表一頁）"""
        # 優先嘗試 LibreOffice 高品質轉換
        lo_result = FileConverter._libreoffice_to_pdf(path)
        if lo_result:
            return fitz.open(lo_result)

        # Fallback：openpyxl 純文字渲染
        import openpyxl
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as rl_canvas
        import io

        cjk = _register_cjk_font()
        wb = openpyxl.load_workbook(path, data_only=True)
        doc = fitz.open()

        for sheet in wb.worksheets:
            buf = io.BytesIO()
            c = rl_canvas.Canvas(buf, pagesize=A4)
            W, H = A4
            c.setFont(cjk, 8)

            # 頁面標題
            c.setFont(cjk, 10)
            c.drawString(30, H - 30, f"工作表：{sheet.title}")
            c.setFont(cjk, 8)

            y = H - 50
            col_width = min(80, (W - 60) / max(sheet.max_column or 1, 1))

            # 欄位標題
            for col_idx, col in enumerate(sheet.iter_cols(
                    max_row=1, values_only=True), start=0):
                pass  # 跳過，直接渲染資料

            for row in sheet.iter_rows(values_only=True):
                if y < 40:
                    c.showPage()
                    c.setFont(cjk, 8)
                    y = H - 30
                x = 30
                for cell in row:
                    text = str(cell) if cell is not None else ""
                    text = text[:15]  # 截斷過長
                    c.drawString(x, y, text)
                    x += col_width
                y -= 14

            c.save()
            buf.seek(0)
            sheet_doc = fitz.open("pdf", buf.getvalue())
            doc.insert_pdf(sheet_doc)
            sheet_doc.close()

        return doc

    # ── Word DOCX ────────────────────────────────────────────────
    @staticmethod
    def docx_to_fitz(path: str) -> fitz.Document:
        """DOCX/DOC → fitz.Document"""
        lo_result = FileConverter._libreoffice_to_pdf(path)
        if lo_result:
            return fitz.open(lo_result)

        # Fallback：python-docx 純文字渲染
        from docx import Document as DocxDoc
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
        import io

        cjk = _register_cjk_font()
        word = DocxDoc(path)
        buf = io.BytesIO()
        pdf_doc = SimpleDocTemplate(buf, pagesize=A4,
                                    rightMargin=40, leftMargin=40,
                                    topMargin=40, bottomMargin=40)
        base_styles = getSampleStyleSheet()
        # 替換預設字型為中文字型
        styles = {
            "Normal": ParagraphStyle("Normal_CJK", parent=base_styles["Normal"],
                                     fontName=cjk, fontSize=10, leading=14),
            "Heading1": ParagraphStyle("H1_CJK", parent=base_styles["Heading1"],
                                       fontName=cjk, fontSize=16, leading=20),
            "Heading2": ParagraphStyle("H2_CJK", parent=base_styles["Heading2"],
                                       fontName=cjk, fontSize=13, leading=17),
        }
        story = []

        for para in word.paragraphs:
            text = para.text.strip()
            if not text:
                story.append(Spacer(1, 8))
                continue
            style_name = "Heading1" if para.style.name.startswith("Heading 1") else \
                         "Heading2" if para.style.name.startswith("Heading 2") else "Normal"
            try:
                story.append(Paragraph(text, styles[style_name]))
            except Exception:
                story.append(Paragraph(text, styles["Normal"]))
            story.append(Spacer(1, 4))

        # 表格
        tbl_style = ParagraphStyle("Tbl_CJK", fontName=cjk, fontSize=8, leading=10)
        for table in word.tables:
            data = []
            for row in table.rows:
                data.append([Paragraph(cell.text or "", tbl_style) for cell in row.cells])
            if data:
                tbl = Table(data, repeatRows=1)
                story.append(tbl)
                story.append(Spacer(1, 8))

        pdf_doc.build(story)
        buf.seek(0)
        return fitz.open("pdf", buf.getvalue())

    # ── PPTX ────────────────────────────────────────────────────
    @staticmethod
    def pptx_to_fitz(path: str) -> fitz.Document:
        """PPTX → fitz.Document（每張投影片一頁）"""
        lo_result = FileConverter._libreoffice_to_pdf(path)
        if lo_result:
            return fitz.open(lo_result)

        # Fallback：python-pptx → 投影片截圖
        from pptx import Presentation
        from pptx.util import Inches
        import io

        prs = Presentation(path)
        doc = fitz.open()

        slide_w = prs.slide_width.pt
        slide_h = prs.slide_height.pt

        for slide_num, slide in enumerate(prs.slides):
            page = doc.new_page(width=slide_w, height=slide_h)
            # 渲染文字內容（使用 PyMuPDF 內建繁中字型）
            y = 40
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    page.insert_text(
                        fitz.Point(20, y),
                        shape.text[:200],
                        fontname="china-t",
                        fontsize=10,
                        color=(0, 0, 0),
                    )
                    y += 18
                    if y > slide_h - 20:
                        break

        return doc

    # ── LibreOffice headless（最高品質）─────────────────────────
    @staticmethod
    def _libreoffice_to_pdf(path: str) -> str | None:
        """
        嘗試用 LibreOffice headless 轉 PDF。
        回傳暫存 PDF 路徑，失敗回傳 None。
        LibreOffice 搜尋路徑：
          macOS: /Applications/LibreOffice.app/Contents/MacOS/soffice
          Windows: C:\\Program Files\\LibreOffice\\program\\soffice.exe
        """
        soffice = FileConverter._find_soffice()
        if not soffice:
            return None
        try:
            tmp_dir = tempfile.mkdtemp(prefix="acropdf_lo_")
            run_kwargs = {"capture_output": True, "timeout": 60}
            # CREATE_NO_WINDOW 只在 Windows 上有效，其他平台不傳
            if sys.platform == "win32":
                run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            result = subprocess.run(
                [soffice, "--headless", "--convert-to", "pdf",
                 "--outdir", tmp_dir, path],
                **run_kwargs,
            )
            if result.returncode != 0:
                import shutil
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return None
            # 找轉出的 PDF
            base = os.path.splitext(os.path.basename(path))[0]
            pdf_path = os.path.join(tmp_dir, base + ".pdf")
            if not os.path.isfile(pdf_path):
                import shutil
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return None
            return pdf_path
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            try:
                import shutil
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
            return None

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
