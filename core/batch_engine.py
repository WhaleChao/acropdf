# ~/Desktop/acropdf/core/batch_engine.py
from __future__ import annotations

import os
from datetime import date
from typing import Callable

import fitz


class BatchEngine:

    # ── 浮水印 ────────────────────────────────────────────────────
    def add_watermark(self, input_path: str, output_path: str,
                      text: str, opacity: float = 0.3,
                      position: str = "center"):
        doc = fitz.open(input_path)
        for page in doc:
            rect = page.rect
            if position == "center":
                x = rect.width / 2
                y = rect.height / 2
            elif position == "top-left":
                x, y = 50, 50
            elif position == "top-right":
                x, y = rect.width - 50, 50
            elif position == "bottom-left":
                x, y = 50, rect.height - 50
            else:  # bottom-right
                x, y = rect.width - 50, rect.height - 50

            # 使用 shape 繪製斜角浮水印（PyMuPDF insert_text 不支援非 90° 倍數旋轉）
            shape = page.new_shape()
            mat = fitz.Matrix(45)  # 45 度旋轉矩陣
            pivot = fitz.Point(x, y)
            r, g, b = 0.7, 0.7, 0.7
            shape.insert_text(
                pivot,
                text,
                fontsize=48,
                color=(r * opacity, g * opacity, b * opacity),
                morph=(pivot, mat),
            )
            shape.finish()
            shape.commit()
        doc.save(output_path, garbage=4, deflate=True)
        doc.close()

    # ── 頁首頁尾 ──────────────────────────────────────────────────
    def add_header_footer(self, input_path: str, output_path: str,
                          header: str = "", footer: str = "",
                          variables: bool = True):
        doc = fitz.open(input_path)
        total = doc.page_count
        today = date.today().strftime("%Y/%m/%d")
        for i, page in enumerate(doc):
            rect = page.rect

            def _resolve(tmpl: str) -> str:
                if not variables:
                    return tmpl
                return (tmpl
                        .replace("{page}", str(i + 1))
                        .replace("{total}", str(total))
                        .replace("{date}", today))

            if header:
                page.insert_text(
                    (rect.width / 2 - len(header) * 3, 20),
                    _resolve(header), fontsize=10, color=(0, 0, 0),
                )
            if footer:
                page.insert_text(
                    (rect.width / 2 - len(footer) * 3, rect.height - 15),
                    _resolve(footer), fontsize=10, color=(0, 0, 0),
                )
        doc.save(output_path, garbage=4, deflate=True)
        doc.close()

    # ── Bates 編號 ────────────────────────────────────────────────
    def add_bates_number(self, input_path: str, output_path: str,
                         prefix: str = "", start: int = 1,
                         digits: int = 6, position: str = "bottom-right"):
        doc = fitz.open(input_path)
        for i, page in enumerate(doc):
            rect = page.rect
            bates = f"{prefix}{str(start + i).zfill(digits)}"
            if position == "bottom-right":
                x, y = rect.width - 80, rect.height - 15
            elif position == "bottom-left":
                x, y = 15, rect.height - 15
            elif position == "top-right":
                x, y = rect.width - 80, 20
            else:  # top-left
                x, y = 15, 20
            page.insert_text((x, y), bates, fontsize=9, color=(0, 0, 0))
        doc.save(output_path, garbage=4, deflate=True)
        doc.close()

    # ── 分割 ──────────────────────────────────────────────────────
    def split_pages(self, input_path: str, output_dir: str,
                    pages_per_file: int = 1) -> list[str]:
        doc = fitz.open(input_path)
        os.makedirs(output_dir, exist_ok=True)
        stem = os.path.splitext(os.path.basename(input_path))[0]
        outputs = []
        total = doc.page_count
        idx = 0
        part = 1
        while idx < total:
            end = min(idx + pages_per_file, total)
            chunk = fitz.open()  # 新建空白文件
            chunk.insert_pdf(doc, from_page=idx, to_page=end - 1)
            out_path = os.path.join(output_dir, f"{stem}_part{part:03d}.pdf")
            chunk.save(out_path, garbage=4, deflate=True)
            chunk.close()
            outputs.append(out_path)
            idx += pages_per_file
            part += 1
        doc.close()
        return outputs

    # ── Word 匯出 ─────────────────────────────────────────────────
    def export_to_docx(self, input_path: str, output_path: str):
        try:
            from docx import Document as DocxDoc
        except ImportError:
            raise RuntimeError("請先安裝 python-docx")
        doc_fitz = fitz.open(input_path)
        docx = DocxDoc()
        for i, page in enumerate(doc_fitz):
            text = page.get_text()
            if i > 0:
                docx.add_page_break()
            docx.add_paragraph(text)
        docx.save(output_path)
        doc_fitz.close()

    # ── HTML 匯出 ─────────────────────────────────────────────────
    def export_to_html(self, input_path: str, output_path: str):
        doc = fitz.open(input_path)
        html_parts = ["<html><body>"]
        for page in doc:
            html_parts.append(f"<div class='page'>{page.get_text('html')}</div>")
        html_parts.append("</body></html>")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(html_parts))
        doc.close()

    # ── 批次入口 ──────────────────────────────────────────────────
    def batch_process(self, files: list[str], operation: str,
                      params: dict,
                      progress_callback: Callable[[int, int, str], None] | None = None
                      ) -> list[dict]:
        results = []
        total = len(files)
        for i, path in enumerate(files):
            if progress_callback:
                progress_callback(i, total, path)
            try:
                out = self._process_one(path, operation, params)
                results.append({"path": path, "output": out, "ok": True})
            except Exception as e:
                results.append({"path": path, "error": str(e), "ok": False})
        if progress_callback:
            progress_callback(total, total, "完成")
        return results

    def _process_one(self, path: str, operation: str, params: dict) -> str:
        stem = os.path.splitext(path)[0]
        if operation == "watermark":
            out = stem + "_watermarked.pdf"
            self.add_watermark(path, out,
                               params.get("text", "浮水印"),
                               params.get("opacity", 0.3),
                               params.get("position", "center"))
            return out
        elif operation == "header_footer":
            out = stem + "_hf.pdf"
            self.add_header_footer(path, out,
                                   params.get("header", ""),
                                   params.get("footer", ""))
            return out
        elif operation == "bates":
            out = stem + "_bates.pdf"
            self.add_bates_number(path, out,
                                  params.get("prefix", ""),
                                  params.get("start", 1),
                                  params.get("digits", 6),
                                  params.get("position", "bottom-right"))
            return out
        elif operation == "split":
            out_dir = stem + "_split"
            parts = self.split_pages(path, out_dir,
                                     params.get("pages_per_file", 1))
            return out_dir
        elif operation == "docx":
            out = stem + ".docx"
            self.export_to_docx(path, out)
            return out
        elif operation == "html":
            out = stem + ".html"
            self.export_to_html(path, out)
            return out
        else:
            raise ValueError(f"未知操作：{operation}")
