# ~/Desktop/acropdf/core/preflight_engine.py
from __future__ import annotations

import math
from dataclasses import dataclass, field

import fitz


@dataclass
class PreflightIssue:
    severity: str   # "error" | "warning" | "info"
    category: str   # "字型" | "圖片" | "色彩" | "透明度" | "出血"
    page: int
    message: str
    auto_fixable: bool = False


@dataclass
class PreflightReport:
    issues: list[PreflightIssue] = field(default_factory=list)
    fonts: list[dict] = field(default_factory=list)
    images: list[dict] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")


class PreflightEngine:
    PROFILES = {
        "PDF/X-1a 印刷": {
            "no_rgb": True, "no_transparency": True,
            "min_dpi": 300, "fonts_embedded": True,
        },
        "PDF/X-4 印刷": {
            "no_rgb": False, "no_transparency": False,
            "min_dpi": 300, "fonts_embedded": True,
        },
        "高品質列印": {
            "min_dpi": 200, "fonts_embedded": True,
        },
        "網頁最佳化": {
            "max_dpi": 150,
        },
    }

    def check_fonts(self, doc: fitz.Document) -> list[dict]:
        """檢查每個字型：名稱、類型、嵌入狀態、子集狀態"""
        seen: dict[tuple, dict] = {}
        for i in range(doc.page_count):
            page = doc[i]
            for f in page.get_fonts(full=True):
                # f = (xref, ext, type, basefont, name, encoding, referencer)
                xref = f[0]
                font_type = f[2]
                name = f[3] or f[4] or f"font_{xref}"
                key = (xref, name)
                if key not in seen:
                    seen[key] = {
                        "name": name,
                        "type": font_type,
                        "embedded": xref > 0 and bool(doc.extract_font(xref)[3]),
                        "subset": "+" in name,
                        "pages": [],
                        "xref": xref,
                    }
                if i not in seen[key]["pages"]:
                    seen[key]["pages"].append(i)
        return list(seen.values())

    def check_images(self, doc: fitz.Document) -> list[dict]:
        """檢查每張圖片：DPI、色彩空間、壓縮方式"""
        from core.image_inspection import inspect_images
        results = inspect_images(doc)
        for image in results:
            image['ext'] = doc.extract_image(image['xref']).get('ext', '') if image['xref'] else ''
        return results

    def check_color_spaces(self, doc: fitz.Document) -> list[str]:
        """偵測每頁使用的色彩空間（RGB/CMYK/Spot）"""
        from core.color_inspection import painted_color_spaces
        return sorted(set().union(*painted_color_spaces(doc)))

    def check_transparency(self, doc: fitz.Document) -> list[int]:
        """Report painted opacity below 1 and image soft masks, avoiding opacity=1 false positives."""
        pages_with_transparency = []
        for i in range(doc.page_count):
            page = doc[i]
            transparent = any(img[1] > 0 for img in page.get_images(full=True))
            transparent |= any(item.get('opacity', 1) < 1 for item in page.get_texttrace())
            transparent |= any(any(value is not None and value < 1
                                   for value in (item.get('fill_opacity'), item.get('stroke_opacity')))
                               for item in page.get_drawings())
            if transparent:
                pages_with_transparency.append(i)
        return pages_with_transparency

    def check_bleed(self, doc: fitz.Document) -> list[dict]:
        """比較 TrimBox vs BleedBox vs MediaBox"""
        results = []
        for i in range(doc.page_count):
            page = doc[i]
            media = page.mediabox
            trim = page.trimbox
            bleed = page.bleedbox
            results.append({
                "page": i,
                "mediabox": list(media),
                "trimbox": list(trim),
                "bleedbox": list(bleed),
                "has_bleed": bleed != media,
            })
        return results

    def full_preflight(self, doc: fitz.Document,
                       profile: str = "高品質列印") -> PreflightReport:
        """執行完整預檢，回傳結構化報告"""
        report = PreflightReport()
        cfg = self.PROFILES.get(profile, self.PROFILES["高品質列印"])

        # 字型
        fonts = self.check_fonts(doc)
        report.fonts = fonts
        for f in fonts:
            if not f["embedded"] and cfg.get("fonts_embedded"):
                report.issues.append(PreflightIssue(
                    severity="error", category="字型", page=-1,
                    message=f"字型 '{f['name']}' 未嵌入",
                    auto_fixable=False,
                ))

        # 圖片
        images = self.check_images(doc)
        report.images = images
        min_dpi = cfg.get("min_dpi", 0)
        max_dpi = cfg.get("max_dpi", 0)
        for img in images:
            dpi = img.get("dpi", 0)
            if min_dpi and dpi and dpi < min_dpi:
                report.issues.append(PreflightIssue(
                    severity="warning", category="圖片", page=img["page"],
                    message=f"圖片 DPI={dpi} 低於建議值 {min_dpi}（需更高解析度來源）",
                    auto_fixable=False,
                ))
            if max_dpi and dpi and dpi > max_dpi:
                report.issues.append(PreflightIssue(
                    severity="info", category="圖片", page=img["page"],
                    message=f"圖片 DPI={dpi} 高於 Web 建議值 {max_dpi}（可降低）",
                    auto_fixable=True,
                ))
        if cfg.get("no_rgb"):
            from core.color_inspection import painted_color_spaces
            for page_number, spaces in enumerate(painted_color_spaces(doc)):
                if 'RGB' not in spaces: continue
                report.issues.append(PreflightIssue(
                    severity="error", category="色彩", page=page_number,
                    message="RGB 色彩空間不符合 PDF/X-1a 要求",
                ))

        # 透明度
        if cfg.get("no_transparency"):
            trans = self.check_transparency(doc)
            for pg in trans:
                report.issues.append(PreflightIssue(
                    severity="error", category="透明度", page=pg,
                    message="頁面含有透明度，不符合 PDF/X-1a 要求",
                ))

        return report

    def fix_downsample_images(self, doc: fitz.Document, target_dpi: int = 150):
        """自動修正：降低圖片解析度（就地修改）"""
        if not 72 <= target_dpi <= 600:
            raise ValueError('目標 DPI 須介於 72 與 600。')
        doc.rewrite_images(dpi_threshold=int(target_dpi * 1.25), dpi_target=target_dpi,
                           lossy=True, lossless=True, bitonal=False)


def _cs_name(cs: int) -> str:
    cs_map = {1: "灰階", 2: "Lab", 3: "RGB", 4: "CMYK"}
    return cs_map.get(cs, f"未知({cs})")
