# ~/Desktop/acropdf/core/export_manager.py
import fitz
import os
import tempfile

class ExportManager:
    def __init__(self, doc):
        self._doc = doc

    @property
    def _fitz(self) -> fitz.Document:
        return self._doc.fitz_doc

    def export(self, output_path: str, fmt: str, dpi: int = 150):
        normalized = fmt.lower().replace("/a", "a")
        if normalized == "docx":
            return self.export_docx(output_path)
        if normalized == "xlsx":
            return self.export_xlsx(output_path)
        if normalized == "pptx":
            return self.export_pptx(output_path)
        if normalized in {"png", "jpg", "jpeg", "tiff"}:
            output_dir = output_path
            if os.path.splitext(output_path)[1]:
                output_dir = os.path.dirname(output_path) or "."
            return self.export_images(output_dir, fmt=normalized.replace("jpeg", "jpg"), dpi=dpi)
        if normalized == "txt":
            return self.export_txt(output_path)
        if normalized == "html":
            return self.export_html(output_path)
        if normalized in {"pdfa", "pdf"}:
            return self.export_pdfa(output_path)
        raise ValueError(f"不支援的匯出格式：{fmt}")

    # ── Word ─────────────────────────────────────────────────────
    def export_docx(self, output_path: str):
        from docx import Document
        from docx.shared import Pt, RGBColor
        word_doc = Document()
        for i in range(self._fitz.page_count):
            page = self._fitz[i]
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if block["type"] == 0:  # 文字 block
                    for line in block["lines"]:
                        text = " ".join(span["text"] for span in line["spans"])
                        if text.strip():
                            p = word_doc.add_paragraph(text)
                            # 嘗試保留字型大小
                            if line["spans"]:
                                fs = line["spans"][0].get("size", 11)
                                for run in p.runs:
                                    run.font.size = Pt(fs)
            if i < self._fitz.page_count - 1:
                word_doc.add_page_break()
        word_doc.save(output_path)

    # ── Excel（表格偵測）─────────────────────────────────────────
    def export_xlsx(self, output_path: str):
        import openpyxl
        wb = openpyxl.Workbook()
        for i in range(self._fitz.page_count):
            page = self._fitz[i]
            ws = wb.create_sheet(f"頁面{i+1}")
            # PyMuPDF 1.23+ 自動偵測表格
            if hasattr(page, "find_tables"):
                tabs = page.find_tables()
                row_offset = 1
                for tab in tabs:
                    for r, row in enumerate(tab.extract()):
                        for c, cell in enumerate(row):
                            ws.cell(row=row_offset + r, column=c + 1, value=cell or "")
                    row_offset += len(tab.extract()) + 2
            else:
                text = page.get_text()
                for r, line in enumerate(text.splitlines()):
                    ws.cell(row=r + 1, column=1, value=line)
        if "Sheet" in wb.sheetnames:
            del wb["Sheet"]
        wb.save(output_path)

    # ── PowerPoint ───────────────────────────────────────────────
    def export_pptx(self, output_path: str):
        from pptx import Presentation
        prs = Presentation()
        for i in range(self._fitz.page_count):
            page = self._fitz[i]
            slide_layout = prs.slide_layouts[6]  # Blank
            slide = prs.slides.add_slide(slide_layout)
            # 渲染頁面為圖片當背景
            mat = fitz.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            with tempfile.NamedTemporaryFile(prefix="acropdf_slide_", suffix=".png", delete=False) as tmp:
                img_path = tmp.name
            try:
                pix.save(img_path)
                slide.shapes.add_picture(
                    img_path,
                    left=0,
                    top=0,
                    width=prs.slide_width,
                    height=prs.slide_height,
                )
            finally:
                if os.path.exists(img_path):
                    os.remove(img_path)
        prs.save(output_path)

    # ── 圖片（每頁）─────────────────────────────────────────────
    def export_images(self, output_dir: str, fmt: str = "png", dpi: int = 150):
        base = os.path.splitext(os.path.basename(self._doc.path or "page"))[0]
        paths = []
        for i in range(self._fitz.page_count):
            page = self._fitz[i]
            zoom = dpi / 72.0
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            out = os.path.join(output_dir, f"{base}_p{i+1:03d}.{fmt}")
            pix.save(out)
            paths.append(out)
        return paths

    # ── 純文字 ───────────────────────────────────────────────────
    def export_txt(self, output_path: str):
        text = ""
        for i in range(self._fitz.page_count):
            text += self._fitz[i].get_text() + "\n\f\n"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)

    # ── HTML ─────────────────────────────────────────────────────
    def export_html(self, output_path: str):
        html_parts = ['<!DOCTYPE html><html><body>']
        for i in range(self._fitz.page_count):
            html_parts.append(self._fitz[i].get_text("html"))
            html_parts.append('<hr/>')
        html_parts.append('</body></html>')
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(html_parts))

    # ── PDF/A ────────────────────────────────────────────────────
    def export_pdfa(self, output_path: str):
        try:
            self._fitz.save(
                output_path,
                pdfa=True,
                garbage=4,
                deflate=True,
                clean=True,
            )
        except TypeError:
            self._fitz.save(output_path, garbage=4, deflate=True, clean=True)
