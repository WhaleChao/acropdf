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

            extra_a = max(left.page_count - right.page_count, 0)
            extra_b = max(right.page_count - left.page_count, 0)
            pages_with_diff = sum(
                1 for diff in results
                if diff.visual_rects or diff.text_added or diff.text_removed
            ) + extra_a + extra_b
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

        # 視覺差異（像素 XOR）
        if visual:
            mat = fitz.Matrix(zoom, zoom)
            pix_a = page_a.get_pixmap(matrix=mat, alpha=False)
            pix_b = page_b.get_pixmap(matrix=mat, alpha=False)
            if pix_a.size == pix_b.size:
                data_a = pix_a.samples
                data_b = pix_b.samples
                threshold = 10
                stride = pix_a.stride
                w, h = pix_a.width, pix_a.height
                diff_pixels = []
                for y in range(h):
                    for x in range(w):
                        off = y * stride + x * 3
                        if (abs(data_a[off] - data_b[off]) > threshold or
                            abs(data_a[off+1] - data_b[off+1]) > threshold or
                            abs(data_a[off+2] - data_b[off+2]) > threshold):
                            diff_pixels.append((x / zoom, y / zoom))
                if diff_pixels:
                    xs = [p[0] for p in diff_pixels]
                    ys = [p[1] for p in diff_pixels]
                    diff.visual_rects.append(fitz.Rect(
                        min(xs) - 2, min(ys) - 2,
                        max(xs) + 2, max(ys) + 2
                    ))

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
                "diff_ratio": len(d.visual_rects),
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
            zoom = 1.0
            mat = fitz.Matrix(zoom, zoom)
            pix_a = page_a.get_pixmap(matrix=mat, alpha=False)
            pix_b = page_b.get_pixmap(matrix=mat, alpha=False)
            clusters: list[fitz.Rect] = []
            if pix_a.size != pix_b.size:
                return clusters
            data_a = pix_a.samples
            data_b = pix_b.samples
            threshold = 10
            stride = pix_a.stride
            w, h = pix_a.width, pix_a.height
            CLUSTER_SIZE = 20  # 每 20px 一格
            buckets: dict[tuple, list[tuple]] = {}
            for y in range(h):
                for x in range(w):
                    off = y * stride + x * 3
                    if (abs(data_a[off] - data_b[off]) > threshold or
                            abs(data_a[off + 1] - data_b[off + 1]) > threshold or
                            abs(data_a[off + 2] - data_b[off + 2]) > threshold):
                        key = (x // CLUSTER_SIZE, y // CLUSTER_SIZE)
                        buckets.setdefault(key, []).append((x / zoom, y / zoom))
            for pts in buckets.values():
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                clusters.append(fitz.Rect(
                    min(xs) - 1, min(ys) - 1,
                    max(xs) + 1, max(ys) + 1
                ))
            return clusters
        finally:
            doc_a.close()
            doc_b.close()

    def generate_diff_report(self, path_a: str, path_b: str,
                             output_path: str, results: dict):
        """產生並排對照 PDF 報告"""
        doc_a = fitz.open(path_a)
        doc_b = fitz.open(path_b)
        report = fitz.open()
        page_diffs = results.get("page_diffs", [])
        count = min(doc_a.page_count, doc_b.page_count)
        for i in range(count):
            pix_a = doc_a[i].get_pixmap(matrix=fitz.Matrix(0.7, 0.7), alpha=False)
            pix_b = doc_b[i].get_pixmap(matrix=fitz.Matrix(0.7, 0.7), alpha=False)
            # 建立 A4 橫式頁面
            page_w = pix_a.width + pix_b.width + 30
            page_h = max(pix_a.height, pix_b.height) + 50
            page = report.new_page(width=page_w, height=page_h)
            page.insert_image(fitz.Rect(0, 40, pix_a.width, 40 + pix_a.height),
                              pixmap=pix_a)
            page.insert_image(fitz.Rect(pix_a.width + 30, 40,
                                        pix_a.width + 30 + pix_b.width,
                                        40 + pix_b.height),
                              pixmap=pix_b)
            # 標記差異
            diff = next((d for d in page_diffs if d.page_num == i), None)
            if diff and diff.visual_rects:
                for rect in diff.visual_rects:
                    r = fitz.Rect(rect.x0 * 0.7, rect.y0 * 0.7 + 40,
                                  rect.x1 * 0.7, rect.y1 * 0.7 + 40)
                    page.draw_rect(r, color=(1, 0, 0), width=1)
            # 頁碼
            page.insert_text((10, 20), f"第 {i + 1} 頁比較", fontsize=10)
        report.save(output_path, garbage=4, deflate=True)
        doc_a.close()
        doc_b.close()
        report.close()

    @staticmethod
    def _open_if_needed(doc_or_path):
        if isinstance(doc_or_path, fitz.Document):
            return doc_or_path, False
        return fitz.open(doc_or_path), True
