# ~/Desktop/acropdf/core/auto_label_engine.py
"""
自動標籤引擎 — 三段策略，記憶體友好設計。

策略優先序（auto 模式自動選擇）：
  1. toc         — 直接讀 PDF 目錄（最快，0 AI，0 OCR）
  2. text        — fitz 文字層 + 正規表示式（快，適用有文字層的 PDF）
  3. markitdown  — MarkItDown 轉 Markdown → heading 偵測（需安裝 markitdown）
  4. ai          — Apple Vision OCR 上半頁 + Gemma 4 推斷標題（最準，適用掃描檔）

記憶體設計：
  - 逐頁處理，絕不同時載入全部頁面的 pixmap
  - AI 策略只 OCR 上半頁（clip=top 35%），立即釋放 pixmap
  - Gemma 呼叫使用 streaming=False + timeout=15s，避免 OOM
"""
from __future__ import annotations

import re
import json
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Optional

import fitz


# ────────────────────────────── 資料結構 ──────────────────────────────

@dataclass
class DocBoundary:
    page_num: int           # 0-based 頁碼
    title: str              # 偵測到的文件名稱
    strategy: str           # 'toc' | 'text' | 'markitdown' | 'ai'
    confidence: float       # 0.0 ~ 1.0


# ────────────────────────────── 主引擎 ────────────────────────────────

class AutoLabelEngine:
    # 橫幅外觀設定（可被 dialog 覆蓋）
    LABEL_HEIGHT  = 26        # pt（PDF 座標）
    LABEL_COLOR   = (0.12, 0.31, 0.55)   # 深藍背景
    TEXT_COLOR    = (1.0,  1.0,  1.0)    # 白字
    FONT_SIZE     = 10
    FONT_NAME     = "helv"

    # Gemma 4 API（oMLX localhost）
    GEMMA_API     = "http://localhost:8080/v1/chat/completions"
    GEMMA_MODEL   = "gemma-4-26b-a4b-it-4bit"
    GEMMA_TIMEOUT = 20        # 秒

    # ── 偵測入口 ──────────────────────────────────────────────────────
    @staticmethod
    def detect(
        doc: fitz.Document,
        strategy: str = "auto",
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> list[DocBoundary]:
        """
        偵測文件邊界，回傳 DocBoundary 列表。
        strategy: 'auto' | 'toc' | 'text' | 'markitdown' | 'ai'
        """
        if strategy == "auto":
            strategy = AutoLabelEngine._pick_strategy(doc)

        if strategy == "toc":
            return AutoLabelEngine._from_toc(doc)
        elif strategy == "text":
            return AutoLabelEngine._from_text(doc, on_progress)
        elif strategy == "markitdown":
            return AutoLabelEngine._from_markitdown(doc, on_progress)
        else:  # ai
            return AutoLabelEngine._from_ai(doc, on_progress)

    @staticmethod
    def _pick_strategy(doc: fitz.Document) -> str:
        """依 PDF 特性自動選擇最佳策略。"""
        if doc.get_toc():
            return "toc"
        # 取前 5 頁採樣，判斷是否有文字層
        sample_chars = sum(
            len(doc[i].get_text())
            for i in range(min(5, doc.page_count))
        )
        return "text" if sample_chars > 80 else "ai"

    # ── 策略 1：TOC ────────────────────────────────────────────────
    @staticmethod
    def _from_toc(doc: fitz.Document) -> list[DocBoundary]:
        toc = doc.get_toc()
        result = []
        for level, title, page in toc:
            pg = page - 1  # TOC 是 1-based
            if 0 <= pg < doc.page_count and title.strip():
                result.append(DocBoundary(
                    page_num=pg, title=title.strip(),
                    strategy="toc", confidence=1.0,
                ))
        return result

    # ── 策略 2：Text pattern ───────────────────────────────────────
    @staticmethod
    def _from_text(
        doc: fitz.Document,
        on_progress: Optional[Callable] = None,
    ) -> list[DocBoundary]:
        boundaries = []
        total = doc.page_count
        prev_empty = True

        for i in range(total):
            if on_progress:
                on_progress(i + 1, total)
            page = doc[i]
            text = page.get_text().strip()
            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

            if not lines:
                prev_empty = True
                continue

            title = _extract_title_heuristic(lines)
            if title and (prev_empty or i == 0):
                boundaries.append(DocBoundary(
                    page_num=i, title=title,
                    strategy="text", confidence=0.7,
                ))
            prev_empty = False

        return boundaries

    # ── 策略 3：MarkItDown ─────────────────────────────────────────
    @staticmethod
    def _from_markitdown(
        doc: fitz.Document,
        on_progress: Optional[Callable] = None,
    ) -> list[DocBoundary]:
        """
        需要 pip install markitdown
        適用有文字層的 PDF；掃描檔效果有限。
        """
        try:
            from markitdown import MarkItDown
        except ImportError:
            # fallback to text strategy
            return AutoLabelEngine._from_text(doc, on_progress)

        boundaries = []
        total = doc.page_count
        md_converter = MarkItDown()

        for i in range(total):
            if on_progress:
                on_progress(i + 1, total)
            page = doc[i]
            text = page.get_text()
            if not text.strip():
                continue
            # MarkItDown 接受 file-like 或 str；傳 text 作為 txt
            try:
                result = md_converter.convert_stream(
                    __import__("io").StringIO(text),
                    file_extension=".txt",
                )
                md_text = result.text_content if hasattr(result, "text_content") else str(result)
                title = _extract_title_from_markdown(md_text)
                if title:
                    boundaries.append(DocBoundary(
                        page_num=i, title=title,
                        strategy="markitdown", confidence=0.75,
                    ))
            except Exception:
                pass

        return boundaries

    # ── 策略 4：AI（OCR + Gemma 4）────────────────────────────────
    @staticmethod
    def _from_ai(
        doc: fitz.Document,
        on_progress: Optional[Callable] = None,
    ) -> list[DocBoundary]:
        """
        逐頁：僅 OCR 頁面上半 35% → Gemma 4 判斷是否為新文件首頁並提取標題。
        記憶體：每頁 pixmap 用完立即釋放。
        """
        try:
            from acro_platform import get_ocr_backend
            backend = get_ocr_backend()
        except Exception:
            backend = None

        boundaries = []
        total = doc.page_count
        prev_title: Optional[str] = None

        for i in range(total):
            if on_progress:
                on_progress(i + 1, total)

            page = doc[i]
            rect = page.rect

            # ── 1. 只裁頂部 35%，省記憶體 ──────────────────────
            clip = fitz.Rect(
                rect.x0, rect.y0,
                rect.x1, rect.y0 + rect.height * 0.35,
            )
            pix = page.get_pixmap(clip=clip, dpi=150)

            # ── 2. OCR ──────────────────────────────────────────
            ocr_text = ""
            if backend:
                ocr_text = _ocr_pixmap_to_text(backend, pix)
            pix = None   # ★ 立即釋放 pixmap

            if not ocr_text.strip():
                continue

            # ── 3. Gemma 4 推斷標題 ─────────────────────────────
            title = _gemma_extract_title(ocr_text, prev_title)
            if title:
                boundaries.append(DocBoundary(
                    page_num=i, title=title,
                    strategy="ai", confidence=0.8,
                ))
                prev_title = title

        return boundaries

    # ── 套用標籤到 PDF ─────────────────────────────────────────────
    @staticmethod
    def apply_labels(
        doc: fitz.Document,
        boundaries: list[DocBoundary],
        style: str = "banner",
        label_height: float = None,
        bg_color: tuple = None,
        text_color: tuple = None,
        font_size: int = None,
    ):
        """
        將 DocBoundary 寫入 PDF 為 FreeText annotation 橫幅。
        style: 'banner'（頁頂橫幅）| 'corner'（右上角小標）
        """
        h   = label_height or AutoLabelEngine.LABEL_HEIGHT
        bgc = bg_color   or AutoLabelEngine.LABEL_COLOR
        txc = text_color or AutoLabelEngine.TEXT_COLOR
        fs  = font_size  or AutoLabelEngine.FONT_SIZE

        for b in boundaries:
            if not (0 <= b.page_num < doc.page_count):
                continue
            page = doc[b.page_num]
            r = page.rect

            if style == "corner":
                # 右上角，寬 200pt，高 h
                rect = fitz.Rect(r.x1 - 205, r.y0 + 4, r.x1 - 5, r.y0 + h + 4)
            else:
                # 整頁頂部橫幅
                rect = fitz.Rect(r.x0, r.y0, r.x1, r.y0 + h)

            annot = page.add_freetext_annot(
                rect,
                b.title,
                fontsize=fs,
                fontname=AutoLabelEngine.FONT_NAME,
                text_color=txc,
                fill_color=bgc,
                border_color=bgc,
            )
            annot.set_opacity(0.88)
            annot.update()


# ────────────────────── 內部輔助函式 ──────────────────────────────────

# 常見公文標題正規表示式
_DATE_RE    = re.compile(r"\d{2,3}[./年]\d{1,2}[./月]?\d{0,2}")
_TITLE_STOP = re.compile(r"(第\d+頁|共\d+頁|附件|附表|備註|說明：)")


def _extract_title_heuristic(lines: list[str]) -> str:
    """
    從頁面前幾行試圖找出文件標題。
    策略：最長且符合格式的前三行。
    """
    candidates = []
    for ln in lines[:6]:
        if len(ln) < 3 or _TITLE_STOP.search(ln):
            continue
        if _DATE_RE.search(ln) and len(ln) < 50:
            candidates.append(ln)
        elif re.search(r"(筆錄|書|票|表|狀|函|令|報告|裁定|判決)", ln):
            candidates.append(ln)

    if candidates:
        return candidates[0][:60]
    # fallback：第一行夠短就用
    if lines and len(lines[0]) <= 40:
        return lines[0]
    return ""


def _extract_title_from_markdown(md: str) -> str:
    """從 MarkItDown 輸出的 Markdown 提取第一個標題。"""
    for line in md.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return re.sub(r"^#+\s*", "", line)[:60]
    return ""


def _ocr_pixmap_to_text(backend, pix: fitz.Pixmap) -> str:
    """
    把 fitz.Pixmap 轉成暫存 PNG → 交給 acro_platform OCR backend。
    用完立即刪除暫存檔。
    """
    import tempfile, os
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp_path = f.name
        pix.save(tmp_path)

        # acro_platform backend 以 fitz.Page 為介面；此處用 Vision directly
        # 嘗試 Apple Vision 直接讀圖
        if hasattr(backend, "ocr_image_path"):
            return backend.ocr_image_path(tmp_path)

        # fallback：用 pytesseract（若有安裝）
        try:
            import pytesseract
            from PIL import Image
            return pytesseract.image_to_string(Image.open(tmp_path), lang="chi_tra+eng")
        except ImportError:
            pass

        return ""
    except Exception:
        return ""
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def _gemma_extract_title(ocr_text: str, prev_title: Optional[str] = None) -> str:
    """
    呼叫 Gemma 4（oMLX port 8080）判斷 OCR 文字是否為新文件首頁，
    並提取簡短文件名稱（≤ 30 字）。
    記憶體友好：只傳前 400 字，streaming=False，timeout=20s。
    """
    snippet = ocr_text.strip()[:400]
    context = f"\n（上一份文件：{prev_title}）" if prev_title else ""
    prompt = (
        f"以下是一份台灣法院偵查卷證文件首頁上半部的 OCR 文字{context}。\n"
        f"請判斷這是否是一份新文件的第一頁。\n"
        f"若是，請只回覆文件名稱（不超過 30 字，格式如：YYMMDD_姓名_文件類型）；\n"
        f"若不是（例如是內文續頁），只回覆「續頁」。\n\n"
        f"OCR 文字：\n{snippet}"
    )

    payload = json.dumps({
        "model": AutoLabelEngine.GEMMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 60,
        "temperature": 0.1,
        "stream": False,
    }).encode()

    try:
        req = urllib.request.Request(
            AutoLabelEngine.GEMMA_API,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=AutoLabelEngine.GEMMA_TIMEOUT) as resp:
            data = json.loads(resp.read())
        reply = data["choices"][0]["message"]["content"].strip()
        if "續頁" in reply or len(reply) < 2:
            return ""
        # 清理 Gemma 可能加的前綴
        reply = re.sub(r"^(文件名稱[：:]\s*|名稱[：:]\s*)", "", reply).strip()
        return reply[:60]
    except Exception:
        return ""
