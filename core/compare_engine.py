# ~/Desktop/acropdf/core/compare_engine.py
import fitz
import difflib
from dataclasses import dataclass, field

@dataclass
class PageDiff:
    page_num: int
    visual_rects: list[fitz.Rect] = field(default_factory=list)
    text_added: list[str] = field(default_factory=list)
    text_removed: list[str] = field(default_factory=list)
    diff_ratio: float = 0.0

class CompareEngine:
    def compare(self, doc_a, doc_b, zoom: float = 1.0,
                text: bool = True, visual: bool = True) -> dict:
        left, close_left = self._open_if_needed(doc_a)
        right, close_right = self._open_if_needed(doc_b)
        try:
            results = []
            count = min(left.page_count, right.page_count)
            for i in range(count):
                diff = self._compare_page(left[i], right[i], zoom, text=text, visual=visual)
                diff.page_num = i
                results.append(diff)

            for i in range(count,max(left.page_count,right.page_count)):
                page=left[i] if i<len(left) else right[i]
                diff=PageDiff(i)
                if text:
                    if i<len(left): diff.text_removed=page.get_text().splitlines()
                    else: diff.text_added=page.get_text().splitlines()
                if visual: diff.visual_rects=[page.rect];diff.diff_ratio=1.0
                results.append(diff)
            extra_a = max(left.page_count - right.page_count, 0)
            extra_b = max(right.page_count - left.page_count, 0)
            pages_with_diff = sum(
                1 for diff in results
                if diff.visual_rects or diff.text_added or diff.text_removed
            )
            return {
                "page_diffs": results,
                "pages_compared": count,
                "pages_with_diff": pages_with_diff,
                "extra_pages_in_a": extra_a,
                "extra_pages_in_b": extra_b,
            }
        finally:
            if close_left:
                left.close()
            if close_right:
                right.close()

    def _compare_page(self, page_a: fitz.Page, page_b: fitz.Page,
                      zoom: float, text: bool = True, visual: bool = True) -> PageDiff:
        diff = PageDiff(page_num=0)

        if visual:
            mask, scale = self._difference_mask(page_a, page_b, zoom)
            box = mask.getbbox()
            if box: diff.visual_rects.append(fitz.Rect(*(n/scale for n in box)))
            histogram=mask.histogram(); diff.diff_ratio=(sum(histogram[1:])/max(1,mask.width*mask.height))
            if page_a.rect != page_b.rect and not box:
                diff.visual_rects.append(page_a.rect | page_b.rect);diff.diff_ratio=1.0

        # 文字差異
        if text:
            text_a = page_a.get_text().splitlines()
            text_b = page_b.get_text().splitlines()
            for line in difflib.unified_diff(text_a, text_b, lineterm=""):
                if line.startswith("+") and not line.startswith("+++"):
                    diff.text_added.append(line[1:])
                elif line.startswith("-") and not line.startswith("---"):
                    diff.text_removed.append(line[1:])

        return diff

    @staticmethod
    def _difference_mask(page_a,page_b,zoom):
        import math
        from PIL import Image, ImageChops
        if not math.isfinite(zoom) or zoom<=0: raise ValueError("比對縮放倍率必須有效且大於零。")
        area=max(page_a.rect.width*page_a.rect.height,page_b.rect.width*page_b.rect.height,1)
        scale=min(zoom,math.sqrt(24_000_000/area),16384/max(page_a.rect.width,page_a.rect.height,page_b.rect.width,page_b.rect.height))
        images=[]
        for page in (page_a,page_b):
            pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),colorspace=fitz.csRGB,alpha=False)
            images.append(Image.frombytes('RGB',(pix.width,pix.height),pix.samples))
        width=max(i.width for i in images);height=max(i.height for i in images)
        padded=[]
        for image in images:
            canvas=Image.new('RGB',(width,height),'white');canvas.paste(image,(0,0));padded.append(canvas)
        channels=ImageChops.difference(*padded).split()
        maximum=ImageChops.lighter(ImageChops.lighter(channels[0],channels[1]),channels[2])
        return maximum.point(lambda p:255 if p>10 else 0),scale

    # ── 公開輔助方法（供 compare_result_dialog 使用）──────────────

    def compare_text(self, path_a: str, path_b: str) -> list[dict]:
        """只比較文字，回傳有差異的頁面清單"""
        result = self.compare(path_a, path_b, text=True, visual=False)
        diffs = []
        for d in result["page_diffs"]:
            if d.text_added or d.text_removed:
                diffs.append({
                    "page": d.page_num,
                    "added": d.text_added,
                    "removed": d.text_removed,
                })
        return diffs

    def compare_visual(self, path_a: str, path_b: str) -> list[dict]:
        """只做視覺比對，回傳每頁差異比例"""
        result = self.compare(path_a, path_b, text=False, visual=True)
        out = []
        for d in result["page_diffs"]:
            out.append({
                "page": d.page_num,
                "diff_ratio": d.diff_ratio,
                "rects": d.visual_rects,
            })
        return out

    def cluster_diff_regions(self, path_a: str, path_b: str,
                             page_num: int = 0) -> list[fitz.Rect]:
        """將像素差異聚類為多個小矩形"""
        doc_a = fitz.open(path_a)
        doc_b = fitz.open(path_b)
        try:
            if page_num >= doc_a.page_count or page_num >= doc_b.page_count:
                return []
            page_a = doc_a[page_num]
            page_b = doc_b[page_num]
            mask, scale = self._difference_mask(page_a,page_b,1)
            clusters = []
            for y in range(0,mask.height,20):
                for x in range(0,mask.width,20):
                    crop=mask.crop((x,y,min(x+20,mask.width),min(y+20,mask.height)))
                    box=crop.getbbox()
                    if box: clusters.append(fitz.Rect((box[0]+x)/scale,(box[1]+y)/scale,(box[2]+x)/scale,(box[3]+y)/scale))
            return clusters
        finally:
            doc_a.close()
            doc_b.close()

    def generate_diff_report(self, path_a: str, path_b: str,
                             output_path: str, results: dict):
        """產生並排對照 PDF 報告"""
        from core.file_io import atomic_output
        import os
        if os.path.realpath(output_path) in (os.path.realpath(path_a),os.path.realpath(path_b)):
            raise ValueError("比對報告不能覆寫任何來源。")
        with fitz.open(path_a) as doc_a, fitz.open(path_b) as doc_b, fitz.open() as report:
            for i in range(max(len(doc_a),len(doc_b))):
                images=[]
                for source in (doc_a,doc_b):
                    images.append(source[i].get_pixmap(matrix=fitz.Matrix(.7,.7),alpha=False) if i<len(source) else None)
                width=max(pix.width for pix in images if pix is not None);height=max(pix.height for pix in images if pix is not None)
                page=report.new_page(width=width*2+30,height=height+50)
                for column,pix in enumerate(images):
                    x=column*(width+30)
                    if pix is None: page.insert_text((x+10,80),"此版本沒有此頁",fontname="china-t",fontsize=12)
                    else: page.insert_image(fitz.Rect(x,40,x+pix.width,40+pix.height),pixmap=pix)
                diff=next((d for d in results.get('page_diffs',[]) if d.page_num==i),None)
                if diff:
                    for rect in diff.visual_rects:
                        page.draw_rect(fitz.Rect(rect.x0*.7,rect.y0*.7+40,rect.x1*.7,rect.y1*.7+40),color=(1,0,0))
                page.insert_text((10,20),f"第 {i+1} 頁比較",fontname="china-t",fontsize=10)
            with atomic_output(output_path) as stage: report.save(stage,garbage=4,deflate=True)

    @staticmethod
    def _open_if_needed(doc_or_path):
        if isinstance(doc_or_path, fitz.Document):
            return doc_or_path, False
        return fitz.open(doc_or_path), True
