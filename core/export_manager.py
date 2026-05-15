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

    def _safe_fitz(self) -> fitz.Document:
        doc = self._fitz
        if doc is None:
            raise RuntimeError("尚未載入文件")
        return doc

    def export(self, output_path: str, fmt: str, dpi: int = 150):
        self._safe_fitz()  # 提早檢查
        normalized = fmt.lower().replace("/a", "a")
        if normalized == "docx":
            output_path = self._validated_output_path(output_path)
            return self.export_docx(output_path)
        if normalized == "xlsx":
            output_path = self._validated_output_path(output_path)
            return self.export_xlsx(output_path)
        if normalized == "pptx":
            output_path = self._validated_output_path(output_path)
            return self.export_pptx(output_path)
        if normalized in {"png", "jpg", "jpeg", "tiff"}:
            output_dir = output_path
            if os.path.splitext(output_path)[1]:
                output_dir = os.path.dirname(output_path) or "."
            output_dir = self._validated_output_dir(output_dir)
            return self.export_images(output_dir, fmt=normalized.replace("jpeg", "jpg"), dpi=dpi)
        if normalized == "txt":
            output_path = self._validated_output_path(output_path)
            return self.export_txt(output_path)
        if normalized == "html":
            output_path = self._validated_output_path(output_path)
            return self.export_html(output_path)
        if normalized in {"pdfa", "pdf"}:
            output_path = self._validated_output_path(output_path)
            return self.export_pdfa(output_path)
        raise ValueError(f"不支援的匯出格式：{fmt}")

    def _validated_output_path(self, output_path: str) -> str:
        output_path = os.path.expanduser(output_path or "")
        if not output_path:
            raise ValueError("請先選擇匯出檔案位置。")
        parent = os.path.dirname(output_path) or "."
        self._ensure_writable_dir(parent)
        return output_path

    def _validated_output_dir(self, output_dir: str) -> str:
        output_dir = os.path.expanduser(output_dir or "")
        if not output_dir:
            raise ValueError("請先選擇匯出資料夾。")
        self._ensure_writable_dir(output_dir)
        return output_dir

    @staticmethod
    def _ensure_writable_dir(path: str):
        if not os.path.isdir(path):
            raise FileNotFoundError(f"匯出資料夾不存在：{path}")
        if not os.access(path, os.W_OK):
            raise PermissionError(f"儲存位置不可寫入：{path}\n請改存到「文件」或「桌面」。")

    # ── Word ─────────────────────────────────────────────────────
    def export_docx(self, output_path: str):
        self._safe_fitz()  # raises RuntimeError if None
        from docx import Document
        from docx.shared import Pt, RGBColor
        word_doc = Document()
        page_count = self._fitz.page_count
        for i in range(page_count):
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
            if i < page_count - 1:
                word_doc.add_page_break()
        word_doc.save(output_path)

    # ── Excel（表格偵測）─────────────────────────────────────────
    def export_xlsx(self, output_path: str):
        self._safe_fitz()
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
        doc = self._safe_fitz()
        prs = Presentation()
        for i in range(doc.page_count):
            page = doc[i]
            slide_layout = prs.slide_layouts[6]  # Blank
            slide = prs.slides.add_slide(slide_layout)
            mat = fitz.Matrix(2, 2)
            try:
                pix = page.get_pixmap(matrix=mat, alpha=False)
            except Exception:
                continue  # 跳過無法渲染的頁面
            with tempfile.NamedTemporaryFile(prefix="acropdf_slide_", suffix=".png", delete=False) as tmp:
                img_path = tmp.name
            try:
                pix.save(img_path)
                slide.shapes.add_picture(
                    img_path, left=0, top=0,
                    width=prs.slide_width, height=prs.slide_height,
                )
            finally:
                if os.path.exists(img_path):
                    os.remove(img_path)
        prs.save(output_path)

    # ── 圖片（每頁）─────────────────────────────────────────────
    def export_images(self, output_dir: str, fmt: str = "png", dpi: int = 150):
        doc = self._safe_fitz()
        base = os.path.splitext(os.path.basename(self._doc.path or "page"))[0]
        paths = []
        zoom = max(dpi, 1) / 72.0
        for i in range(doc.page_count):
            try:
                page = doc[i]
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                out = os.path.join(output_dir, f"{base}_p{i+1:03d}.{fmt}")
                pix.save(out)
                paths.append(out)
            except Exception:
                continue
        return paths

    # ── 純文字 ───────────────────────────────────────────────────
    def export_txt(self, output_path: str):
        self._safe_fitz()
        text = ""
        for i in range(self._fitz.page_count):
            text += self._fitz[i].get_text() + "\n\f\n"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)

    # ── HTML ─────────────────────────────────────────────────────
    def export_html(self, output_path: str):
        self._safe_fitz()
        html_parts = ['<!DOCTYPE html><html><body>']
        for i in range(self._fitz.page_count):
            html_parts.append(self._fitz[i].get_text("html"))
            html_parts.append('<hr/>')
        html_parts.append('</body></html>')
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(html_parts))

    # ── PDF/A ────────────────────────────────────────────────────
    def export_pdfa(self, output_path: str):
        doc = self._safe_fitz()
        try:
            doc.save(
                output_path,
                pdfa=True,
                garbage=4,
                deflate=True,
                clean=True,
            )
        except TypeError:
            doc.save(output_path, garbage=4, deflate=True, clean=True)
