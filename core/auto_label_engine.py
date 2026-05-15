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

    # ── 策略 4：AI（專精 OCR 引擎 + 啟發式 + 可選 Gemma 文字清理）─────
    @staticmethod
    def _from_ai(
        doc: fitz.Document,
        on_progress: Optional[Callable] = None,
    ) -> list[DocBoundary]:
        """
        影像辨識策略（適用掃描 PDF）。

        架構：
          ① macOS → Apple Vision Framework（OS 原生，專精 OCR，零額外記憶體）
             Windows → WinRT OCR（Win10 內建，同理）
             fallback → Tesseract
          ② OCR 文字 → 啟發式正規表示式提取標題（大多數情況就夠）
          ③ 啟發式失敗 → 送 Gemma 4 文字模型做語意判斷
             ★ Gemma 4 在此只做「文字理解」，不做影像處理
             ★ 影像辨識完全交給 ① 的專用 OCR 引擎
             ★ Gemma 4 已常駐記憶體（port 8080），不另外載入模型

        記憶體設計：
          - 每頁只裁頂部 30%，dpi=120（夠 OCR 辨識，避免大圖）
          - pixmap 用後立即設 None 釋放
          - Gemma 呼叫：max_tokens=40，純文字，不送圖片
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

            # ── ① 只裁頂部 30%，dpi=120，省記憶體 ───────────────
            clip = fitz.Rect(
                rect.x0, rect.y0,
                rect.x1, rect.y0 + rect.height * 0.30,
            )
            pix = page.get_pixmap(clip=clip, dpi=120)

            # ── ② 專用 OCR 引擎辨識影像 ─────────────────────────
            ocr_text = ""
            if backend:
                ocr_text = _ocr_pixmap_to_text(backend, pix)
            pix = None   # ★ 立即釋放

            if not ocr_text.strip():
                continue

            lines = [ln.strip() for ln in ocr_text.split("\n") if ln.strip()]

            # ── ③-a 啟發式：大多數有規律文件直接命中 ───────────
            title = _extract_title_heuristic(lines)
            confidence = 0.8

            # ── ③-b 啟發式失敗 → Gemma 4 文字語意判斷 ──────────
            if not title:
                title = _gemma_clarify_title(ocr_text[:300], prev_title)
                confidence = 0.7 if title else 0.0

            if title:
                boundaries.append(DocBoundary(
                    page_num=i, title=title,
                    strategy="ai", confidence=confidence,
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

# ── OCR 數字間距修正：「1 1 4」→「114」、「3 0 5 8」→「3058」────────
# 匹配「單一數字 + 空格」連續出現 2+ 次，後接一個數字（漢字前後也適用）
_SPACED_DIGITS = re.compile(r"(\d)((?:\s\d){2,})")

def _fix_spaced_digits(text: str) -> str:
    """修正 OCR 掃描時數字被空格拆開的問題，例如 '1 1 4' → '114'。"""
    return _SPACED_DIGITS.sub(lambda m: m.group(0).replace(" ", ""), text)


# ── 臺灣司法文件常見 OCR 清洗規則 ────────────────────────────────────
# 司法院線上閱卷系統 (OLA) 每頁都會印使用者姓名 + 系統浮水印，需過濾
_OLA_WATERMARK = re.compile(
    r"(司法院線上閱卷系統|作業平台|\d{3}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})"
)
# 數字/符號雜訊行（OCR 對印章/表格邊框誤讀）
_NOISE_LINE    = re.compile(r"^[\d\s\-_/\\|.,:;。、　]+$")
# 常見「不是標題」的行
_TITLE_STOP    = re.compile(
    r"(第\d+頁|共\d+頁|附件|附表|備註|說明：|文書種類|起訖頁數|本卷宗連底)"
)
# 公文日期（民國格式）
_DATE_RE       = re.compile(r"\d{2,3}[./年]\d{1,2}[./月]?\d{0,2}")
# 公文類型關鍵字
_DOC_TYPE_RE   = re.compile(
    r"(筆錄|判決|裁定|起訴書|不起訴|聲請書|搜索票|拘票|押票"
    r"|扣押|調查報告|鑑定書|相驗|解剖|診斷書|證明書|委任狀"
    r"|函|令|通知書|傳票|聲押書|警詢|偵訊|訊問|陳述書|告訴狀)"
)


def _clean_ocr_lines(lines: list[str]) -> list[str]:
    """
    去除 OLA 浮水印、雜訊行，回傳有意義的文字行。

    OLA 浮水印模式：
      - 使用者姓名（2~5字）連續出現 ≥3 行 → 全部視為浮水印
      - 同一短詞在單行內重複 ≥3 次
      - 司法院線上閱卷系統 + 時間戳記
    """
    # 先找出連續重複短行（使用者姓名浮水印）
    watermark_lines: set[int] = set()
    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        if 2 <= len(ln) <= 8:
            # 計算連續相同行數
            j = i + 1
            while j < len(lines) and lines[j].strip() == ln:
                j += 1
            if j - i >= 2:   # 相同行出現 ≥2 次視為浮水印
                watermark_lines.update(range(i, j))
        i += 1

    cleaned = []
    for idx, ln in enumerate(lines):
        ln = ln.strip()
        if not ln or len(ln) < 2:
            continue
        if idx in watermark_lines:
            continue
        if _OLA_WATERMARK.search(ln):
            continue
        if _NOISE_LINE.match(ln):
            continue
        if _TITLE_STOP.search(ln):
            continue
        # 單行內同一短詞重複 ≥3 次
        if re.search(r"(.{2,6})\1{2,}", ln):
            continue
        # 修正 OCR 數字間距（「1 1 4」→「114」）
        cleaned.append(_fix_spaced_digits(ln))
    return cleaned


def _extract_title_heuristic(lines: list[str]) -> str:
    """
    從頁面行列中提取文件標題。
    先清洗 OLA 浮水印，再按優先序抓標題：
      1. 含文件類型關鍵字的行（最高信心）
      2. 含民國年月日的短行
      3. 第一個長度 ≤ 40 字的非雜訊行（fallback）
    """
    clean = _clean_ocr_lines(lines)
    if not clean:
        return ""

    # 優先：文件類型關鍵字
    for ln in clean[:10]:
        if _DOC_TYPE_RE.search(ln) and len(ln) <= 60:
            return ln[:60]

    # 次選：含日期的短行
    for ln in clean[:8]:
        if _DATE_RE.search(ln) and 4 < len(ln) <= 50:
            return ln[:50]

    # fallback：第一個乾淨行（夠短）
    if clean and len(clean[0]) <= 40:
        return clean[0]
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


def _gemma_clarify_title(ocr_text: str, prev_title: Optional[str] = None) -> str:
    """
    Gemma 4 純文字語意兜底：僅在啟發式無法從 OCR 文字辨識標題時呼叫。

    ★ 角色分工：
      - 影像辨識（OCR）由 Apple Vision / WinRT / Tesseract 負責（專精 OCR 引擎）
      - Gemma 4 只做「文字理解與標題清理」，不接觸圖片
      - Gemma 4 已在 port 8080 常駐，此呼叫不載入任何新模型

    記憶體設計：
      - 只傳前 300 字（夠判斷，不浪費 token）
      - max_tokens=40（只需短回覆）
      - timeout=15s（避免 UI 卡住）
      - 優先取 content，其次取 reasoning_content（Gemma 4 思考模式）
    """
    snippet = ocr_text.strip()[:300]
    context = f"（上一份：{prev_title}）" if prev_title else ""
    prompt = (
        f"以下是臺灣司法文件的 OCR 文字片段{context}。"
        f"若這是新文件首頁，只回答文件名稱（≤20字）；若是續頁，回答「續頁」。\n"
        f"文字：{snippet}"
    )

    payload = json.dumps({
        "model": AutoLabelEngine.GEMMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 40,
        "temperature": 0.05,
        "stream": False,
    }).encode()

    try:
        req = urllib.request.Request(
            AutoLabelEngine.GEMMA_API,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        msg = data["choices"][0]["message"]
        # Gemma 4 思考模式：content 可能為 None，從 reasoning_content 取最後結論
        reply = (msg.get("content") or "").strip()
        if not reply:
            rc = (msg.get("reasoning_content") or "")
            # reasoning 末尾通常是結論，取最後一個非空行
            lines = [l.strip() for l in rc.splitlines() if l.strip()]
            reply = lines[-1] if lines else ""
        if not reply or "續頁" in reply or len(reply) < 2:
            return ""
        reply = re.sub(r"^(文件名稱[：:]\s*|名稱[：:]\s*|答[：:]\s*)", "", reply).strip()
        return reply[:60]
    except Exception:
        return ""
