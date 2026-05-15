# ~/Desktop/acropdf/core/template_engine.py
from __future__ import annotations

import json
import os
from pathlib import Path

import fitz


class TemplateEngine:
    _TEMPLATE_DIR = Path(__file__).parent.parent / "resources" / "templates"

    def __init__(self):
        self._TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

    def list_templates(self) -> list[dict]:
        """列出可用範本"""
        templates = []
        for p in self._TEMPLATE_DIR.rglob("*.json"):
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
            for page in doc:
                for key, value in data.items():
                    rects = page.search_for(f"{{{key}}}")
                    for rect in rects:
                        page.add_redact_annot(rect)
                    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
                    for rect in rects:
                        page.insert_text(rect.tl, str(value), fontsize=11)
            return doc

        # 生成空白範本（fallback）
        doc = fitz.open()
        page = doc.new_page()
        y = 72
        page.insert_text((72, 50), template_name, fontsize=16)
        for key, value in data.items():
            page.insert_text((72, y), f"{key}：{value}", fontsize=11)
            y += 20
        return doc

    def save_as_template(self, doc: fitz.Document, name: str,
                         category: str = "其他",
                         variables: list[str] | None = None):
        """將目前文件存為範本"""
        safe_name = name.replace(" ", "_").replace("/", "_")
        pdf_path = self._TEMPLATE_DIR / f"{safe_name}.pdf"
        meta_path = self._TEMPLATE_DIR / f"{safe_name}.json"

        doc.save(str(pdf_path), garbage=4, deflate=True)
        meta = {
            "name": name,
            "category": category,
            "variables": variables or [],
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
