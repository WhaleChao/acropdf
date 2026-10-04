"""OpenDesk TW 與 AcroPDF 的本機唯讀整合協定。

協定只輸出文件結構與健康資訊，不回傳 PDF 內文，也不開放任意命令執行。
所有會修改文件的工作仍由 AcroPDF 圖形介面明確執行。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import fitz


PROTOCOL_VERSION = 1

CAPABILITIES = [
    {"id": "view", "category": "檢視", "label": "閱讀、搜尋、縮放、分割與全螢幕"},
    {"id": "edit", "category": "編輯", "label": "文字、圖片、連結、背景、圖層與附件"},
    {"id": "pages", "category": "整理頁面", "label": "合併、分割、擷取、插入、刪除、旋轉、裁切與重排"},
    {"id": "annotate", "category": "註解", "label": "螢光筆、底線、刪除線、便利貼、圖形、圖章與手繪"},
    {"id": "forms", "category": "表單", "label": "辨識、填寫、建立、匯入匯出與扁平化"},
    {"id": "sign", "category": "簽署", "label": "簽名欄、憑證簽章與驗證"},
    {"id": "ocr", "category": "OCR", "label": "掃描頁文字化與可搜尋 PDF"},
    {"id": "convert", "category": "轉換", "label": "Word、Excel、PowerPoint、圖片、文字與 HTML；標準 PDF 轉換依引擎與驗證器能力"},
    {"id": "protect", "category": "保護", "label": "AES-256、權限、永久遮蔽、預檢與無障礙"},
    {"id": "batch", "category": "批次", "label": "浮水印、頁首頁尾、Bates 編號、分割與智慧歸檔"},
    {"id": "magi", "category": "MAGI", "label": "摘要、翻譯、分類與法律文件分析"},
]


def integration_status(app_version: str) -> dict[str, Any]:
    return {
        "ok": True,
        "engine": "AcroPDF",
        "app_version": app_version,
        "protocol_version": PROTOCOL_VERSION,
        "locale": "zh-Hant-TW",
        "privacy": "本機處理；整合報告不包含 PDF 內文",
        "capabilities": CAPABILITIES,
    }


def _safe_count(iterator) -> int:
    if iterator is None:
        return 0
    try:
        return sum(1 for _ in iterator)
    except Exception:
        return 0


def _metadata(doc: fitz.Document) -> dict[str, str]:
    raw = doc.metadata or {}
    keys = ("format", "title", "author", "subject", "keywords", "creator", "producer")
    return {key: str(raw.get(key) or "") for key in keys}


def inspect_pdf(path: str | Path, app_version: str = "unknown") -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if source.suffix.lower() != ".pdf":
        raise ValueError("整合檢查只接受 PDF 文件")
    if not source.is_file():
        raise FileNotFoundError(f"找不到 PDF：{source}")

    doc = fitz.open(source)
    try:
        metadata = _metadata(doc)
        encrypted = bool(doc.needs_pass)
        report: dict[str, Any] = {
            "protocol_version": PROTOCOL_VERSION,
            "engine_version": app_version,
            "file_name": source.name,
            "file_size": source.stat().st_size,
            "pages": doc.page_count,
            "encrypted": encrypted,
            "metadata": metadata,
            "characters": 0,
            "words": 0,
            "text_pages": 0,
            "scanned_pages": 0,
            "images": 0,
            "annotations": 0,
            "form_fields": 0,
            "signature_fields": 0,
            "links": 0,
            "bookmarks": 0,
            "attachments": 0,
            "rotated_pages": 0,
            "page_sizes": [],
            "warnings": [],
        }
        if encrypted:
            report["warnings"] = ["文件受密碼保護；輸入密碼後才能完成內容、表單與無障礙檢查。"]
            return report

        page_sizes: set[str] = set()
        for page in doc:
            text = page.get_text("text") or ""
            non_whitespace = sum(1 for char in text if not char.isspace())
            report["characters"] += non_whitespace
            report["words"] += len(text.split())
            images = len(page.get_images(full=True))
            report["images"] += images
            if non_whitespace:
                report["text_pages"] += 1
            elif images:
                report["scanned_pages"] += 1
            report["annotations"] += _safe_count(page.annots())
            widgets = list(page.widgets() or [])
            report["form_fields"] += len(widgets)
            report["signature_fields"] += sum(
                1 for widget in widgets if widget.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE
            )
            report["links"] += len(page.get_links())
            if page.rotation:
                report["rotated_pages"] += 1
            page_sizes.add(f"{round(page.rect.width)}×{round(page.rect.height)} pt")

        report["page_sizes"] = sorted(page_sizes)
        report["bookmarks"] = len(doc.get_toc() or [])
        if hasattr(doc, "embfile_count"):
            report["attachments"] = int(doc.embfile_count())

        warnings: list[str] = []
        if report["scanned_pages"]:
            warnings.append(f"有 {report['scanned_pages']} 頁只有影像，建議先執行繁體中文 OCR。")
        if doc.page_count >= 6 and not report["bookmarks"]:
            warnings.append("長文件尚無書籤，建議建立導覽結構。")
        if len(page_sizes) > 1:
            warnings.append("文件含多種頁面尺寸，列印或合併前請確認版面。")
        if not metadata["title"]:
            warnings.append("文件標題中繼資料尚未設定。")
        if report["form_fields"] and not report["signature_fields"]:
            warnings.append("文件含可填表單；送出前請確認欄位值與扁平化需求。")
        report["warnings"] = warnings
        return report
    finally:
        doc.close()


def live_validate_pdf(path: str | Path, app_version: str = "unknown") -> dict[str, Any]:
    report = inspect_pdf(path, app_version)
    if report["encrypted"]:
        return {
            "protocol_version": PROTOCOL_VERSION,
            "engine_version": app_version,
            "passed": False,
            "reason": "受密碼保護的 PDF 需要使用者輸入密碼",
            "report": report,
        }

    source = Path(path).expanduser().resolve()
    doc = fitz.open(source)
    try:
        render_pages = sorted({0, max(0, doc.page_count - 1)}) if doc.page_count else []
        render_digest = hashlib.sha256()
        rendered = 0
        for page_index in render_pages:
            pixmap = doc[page_index].get_pixmap(matrix=fitz.Matrix(0.75, 0.75), alpha=False)
            samples = pixmap.samples
            if not samples or pixmap.width < 1 or pixmap.height < 1:
                raise RuntimeError(f"第 {page_index + 1} 頁無法渲染")
            render_digest.update(samples)
            rendered += 1
        roundtrip = doc.tobytes(garbage=3, deflate=True)
    finally:
        doc.close()

    reopened = fitz.open(stream=roundtrip, filetype="pdf")
    try:
        roundtrip_pages = reopened.page_count
    finally:
        reopened.close()
    passed = roundtrip_pages == report["pages"] and rendered == len(render_pages)
    return {
        "protocol_version": PROTOCOL_VERSION,
        "engine_version": app_version,
        "passed": passed,
        "rendered_pages": rendered,
        "render_sha256": render_digest.hexdigest(),
        "roundtrip_pages": roundtrip_pages,
        "roundtrip_bytes": len(roundtrip),
        "report": report,
    }


def _emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def dispatch_integration_cli(argv: list[str], app_version: str) -> int | None:
    integration_flags = {
        "--integration-status",
        "--integration-inspect",
        "--integration-live-test",
    }
    if not integration_flags.intersection(argv):
        return None

    parser = argparse.ArgumentParser(prog="AcroPDF 本機整合協定")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--integration-status", action="store_true")
    group.add_argument("--integration-inspect", metavar="PDF")
    group.add_argument("--integration-live-test", metavar="PDF")
    try:
        args = parser.parse_args(argv)
        if args.integration_status:
            _emit(integration_status(app_version))
        elif args.integration_inspect:
            _emit(inspect_pdf(args.integration_inspect, app_version))
        else:
            _emit(live_validate_pdf(args.integration_live_test, app_version))
        return 0
    except Exception as exc:
        _emit({"ok": False, "error": str(exc), "protocol_version": PROTOCOL_VERSION})
        return 1
