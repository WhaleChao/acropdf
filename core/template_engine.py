# ~/Desktop/acropdf/core/template_engine.py
from __future__ import annotations

import json
import os
from pathlib import Path

import fitz


class TemplateEngine:
    _BUNDLED_DIR = Path(__file__).parent.parent / "resources" / "templates"
    _TEMPLATE_DIR = None

    def __init__(self):
        if self._TEMPLATE_DIR is None:
            from PyQt6.QtCore import QStandardPaths
            self._TEMPLATE_DIR = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)) / "templates"
        self._TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

    def list_templates(self) -> list[dict]:
        """列出可用範本"""
        templates = []
        paths = list(self._BUNDLED_DIR.glob("*.json")) + list(self._TEMPLATE_DIR.glob("*.json"))
        for p in paths:
            try:
                with open(p, encoding="utf-8") as f:
                    meta = json.load(f)
                templates.append({
                    "name": meta.get("name", p.stem),
                    "category": meta.get("category", "其他"),
                    "variables": meta.get("variables", []),
                    "meta_path": str(p),
                    "pdf_path": str(p.with_suffix(".pdf")) if p.with_suffix(".pdf").exists() else "",
                })
            except Exception:
                pass
        return templates

    def create_from_template(self, template_name: str, data: dict) -> fitz.Document:
        """從範本產生 PDF（變數替換）"""
        templates = self.list_templates()
        tmpl = next((t for t in templates if t["name"] == template_name), None)

        if tmpl and tmpl.get("pdf_path") and os.path.exists(tmpl["pdf_path"]):
            doc = fitz.open(tmpl["pdf_path"])
            try:
                for page in doc:
                    replacements = []
                    for key, value in data.items():
                        text = str(value);font = "china-t" if any(ord(c)>255 for c in text) else "helv"
                        for rect in page.search_for(f"{{{key}}}"):
                            # Fit and place inside the original placeholder; never erase surrounding graphics.
                            size = min(11, rect.width/max(1, fitz.Font(fontname=font).text_length(text,fontsize=1)))
                            if size < 6: raise ValueError(f"變數 {key} 超出範本欄位，請縮短文字。")
                            replacements.append((rect,text,font,size))
                    for rect,_,_,_ in replacements: page.add_redact_annot(rect,fill=False)
                    if replacements:
                        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE,graphics=fitz.PDF_REDACT_LINE_ART_NONE)
                    for rect,text,font,size in replacements:
                        page.insert_text((rect.x0,rect.y1-size*.2),text,fontsize=size,fontname=font)
                return doc
            except Exception:
                doc.close();raise

        # 生成空白範本（fallback）
        doc = fitz.open()
        page = doc.new_page()
        y = 72
        page.insert_text((72, 50), template_name, fontsize=16, fontname="china-t")
        for key, value in data.items():
            if y > page.rect.height-50: page=doc.new_page();y=72
            page.insert_text((72, y), f"{key}：{value}", fontsize=11, fontname="china-t")
            y += 20
        return doc

    def save_as_template(self, doc: fitz.Document, name: str,
                         category: str = "其他",
                         variables: list[str] | None = None):
        """將目前文件存為範本"""
        import re
        import uuid
        from core.file_io import atomic_output
        safe_name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', name).strip().strip('.')
        if not safe_name or len(safe_name)>120: raise ValueError("範本名稱無效。")
        # Unique names keep both files together and preserve existing templates.
        stem = safe_name.replace(" ", "_") + "_" + uuid.uuid4().hex[:8]
        pdf_path = self._TEMPLATE_DIR / f"{stem}.pdf"
        meta_path = self._TEMPLATE_DIR / f"{stem}.json"
        with atomic_output(pdf_path) as stage: doc.save(stage,garbage=4,deflate=True,encryption=fitz.PDF_ENCRYPT_KEEP)
        meta = {"name":name,"category":category,"variables":variables or []}
        try:
            with atomic_output(meta_path) as stage: stage.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
        except Exception:
            pdf_path.unlink();raise
