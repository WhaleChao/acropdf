"""AcroPDF 無視窗操作模式（--headless-op）。

供 MAGI 以子程序呼叫 AcroPDF 獨有的能力：PDF/A 轉換與檢查、Apple Vision OCR。
本模組不得 import PyQt6（也不得經由任何依賴間接載入 Qt）；
程序只讀 --input、只寫 --output（先寫暫存檔再原子更名），不連網。

stdout 僅輸出一行 JSON；診斷訊息一律走 stderr。
結束碼：成功 0、參數錯誤 64、處理失敗 2。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = 2
EXIT_OK, EXIT_USAGE, EXIT_FAIL = 0, 64, 2
OPS = ("pdfa_convert", "pdfa_validate", "vision_ocr", "capabilities")


class OpError(Exception):
    """帶錯誤代碼與白話繁中訊息的操作錯誤。"""

    def __init__(self, code: str, message: str, exit_code: int = EXIT_FAIL, details: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.exit_code, self.details = code, message, exit_code, details or {}


# ── 參數解析（不使用 argparse，避免它自行寫 stderr / 結束）──────────────
def parse_args(argv: list[str]) -> dict[str, Any]:
    known = {"--headless-op": "op", "--input": "input", "--output": "output", "--params-json": "params"}
    values: dict[str, str] = {}
    i = 0
    while i < len(argv):
        token = argv[i]
        key, eq, inline = token.partition("=")
        if key not in known:
            raise OpError("bad_args", f"不認得的參數：{token}", EXIT_USAGE)
        if eq:
            value = inline
        else:
            if i + 1 >= len(argv):
                raise OpError("bad_args", f"參數 {key} 缺少值。", EXIT_USAGE)
            i += 1
            value = argv[i]
        if known[key] in values:
            raise OpError("bad_args", f"參數 {key} 重複出現。", EXIT_USAGE)
        values[known[key]] = value
        i += 1
    op = values.get("op")
    if not op:
        raise OpError("bad_args", "缺少 --headless-op。", EXIT_USAGE)
    if op not in OPS:
        raise OpError("bad_args", f"不支援的操作：{op}。可用：{', '.join(OPS)}。", EXIT_USAGE)
    params: dict[str, Any] = {}
    if "params" in values:
        try:
            params = json.loads(values["params"])
        except ValueError:
            raise OpError("bad_args", "--params-json 不是有效的 JSON。", EXIT_USAGE)
        if not isinstance(params, dict):
            raise OpError("bad_args", "--params-json 必須是 JSON 物件。", EXIT_USAGE)
    for name in ("input", "output"):
        path = values.get(name)
        if path is not None and not os.path.isabs(path):
            raise OpError("bad_args", f"--{name} 必須是絕對路徑。", EXIT_USAGE)
    if op in ("pdfa_convert", "pdfa_validate", "vision_ocr") and not values.get("input"):
        raise OpError("bad_args", f"{op} 需要 --input。", EXIT_USAGE)
    if op in ("pdfa_convert", "vision_ocr") and not values.get("output"):
        raise OpError("bad_args", f"{op} 需要 --output。", EXIT_USAGE)
    return {"op": op, "input": values.get("input"), "output": values.get("output"), "params": params}


# ── 共用工具 ────────────────────────────────────────────────────────────
def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_input(path: str) -> None:
    if not os.path.isfile(path):
        raise OpError("input_not_found", f"找不到輸入檔：{path}", EXIT_USAGE)
    with open(path, "rb") as handle:
        head = handle.read(1024)
    if b"%PDF-" not in head:
        raise OpError("input_not_pdf", "輸入檔不是 PDF 文件。", EXIT_FAIL)


def _check_output(inp: str, out: str) -> None:
    if os.path.realpath(inp) == os.path.realpath(out):
        raise OpError("output_is_input", "輸出不能覆寫輸入檔。", EXIT_USAGE)
    if not os.path.isdir(os.path.dirname(out)):
        raise OpError("output_dir_missing", f"輸出資料夾不存在：{os.path.dirname(out)}", EXIT_USAGE)


def _open_plain(path: str):
    """開啟輸入 PDF；加密或損毀時丟出 OpError。"""
    import fitz
    try:
        doc = fitz.open(path)
    except Exception as exc:
        raise OpError("pdf_unreadable", f"PDF 無法開啟或已損毀：{exc}")
    if doc.needs_pass:
        doc.close()
        raise OpError("encrypted", "PDF 受密碼保護，無視窗模式不處理加密文件。")
    return doc


def _publish(temporary: Path, output: str) -> None:
    """暫存檔 fsync 後原子更名到 --output（同資料夾，確保 os.replace 原子）。"""
    if not temporary.stat().st_size:
        raise OpError("empty_output", "輸出為空，未發佈檔案。")
    with temporary.open("r+b") as stream:
        os.fsync(stream.fileno())
    os.replace(temporary, output)


class _Staged:
    """在 --output 同資料夾建立隱藏暫存檔；離開時一定清除。"""

    def __init__(self, output: str):
        self.output = output

    def __enter__(self) -> Path:
        handle, name = tempfile.mkstemp(prefix=".acropdf_headless_", suffix=".pdf", dir=os.path.dirname(self.output))
        os.close(handle)
        self.path = Path(name)
        return self.path

    def __exit__(self, *exc):
        self.path.unlink(missing_ok=True)
        return False


# ── 外部工具探測 ─────────────────────────────────────────────────────────
def find_gs(params: dict) -> str | None:
    explicit = params.get("gs_path")
    if explicit:
        if not os.path.isabs(str(explicit)) or not os.path.isfile(str(explicit)):
            raise OpError("gs_missing", "params 指定的 Ghostscript 路徑不存在。", EXIT_USAGE)
        return str(explicit)
    for candidate in (os.environ.get("ACROPDF_GHOSTSCRIPT"), "/opt/homebrew/bin/gs", "/usr/local/bin/gs", shutil.which("gs")):
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def _java_ok(java: str) -> bool:
    try:
        return subprocess.run([java, "-version"], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def find_verapdf(params: dict) -> tuple[list[str] | None, str]:
    """回傳 (指令前綴, 來源)。找不到回 (None, '')。"""
    explicit = params.get("verapdf_path")
    if explicit:
        if not os.path.isabs(str(explicit)) or not os.path.isfile(str(explicit)):
            raise OpError("verapdf_missing", "params 指定的 veraPDF 路徑不存在。", EXIT_USAGE)
        return [str(explicit)], "params"
    env = os.environ.get("ACROPDF_VERAPDF")
    if env and os.path.isfile(env):
        return [env], "env"
    for name in ("verapdf",):
        located = shutil.which(name)
        if located:
            return [located], "path"
    # 隨 App 附帶的 veraPDF CLI jar（需系統有可用的 Java）
    root = Path(__file__).resolve().parents[1]
    jar = root / "resources/validators/verapdf-cli-1.30.2.jar"
    if jar.is_file():
        java = None
        for candidate in (os.environ.get("ACROPDF_JAVA"), shutil.which("java"), "/usr/bin/java"):
            if candidate and os.path.isfile(candidate) and _java_ok(candidate):
                java = candidate
                break
        if java:
            return [java, "-jar", str(jar)], "bundled_jar"
    return None, ""


def vision_available() -> tuple[bool, str]:
    if sys.platform != "darwin":
        return False, "僅 macOS 提供 Apple Vision。"
    try:
        import Vision  # noqa: F401
        import Quartz  # noqa: F401
        import Foundation  # noqa: F401
    except ImportError as exc:
        return False, f"缺少 pyobjc Vision/Quartz：{exc}"
    return True, ""


# ── PDF/A 基本檢查與 veraPDF ─────────────────────────────────────────────
def basic_pdfa_checks(path: str) -> dict[str, Any]:
    """XMP pdfaid、字型內嵌、OutputIntent。不等同於正式 PDF/A 驗證。"""
    import fitz
    import pikepdf

    result: dict[str, Any] = {}
    claimed = None
    with pikepdf.open(path) as pdf:
        meta = pdf.Root.get("/Metadata")
        xmp = bytes(meta.read_bytes()).decode("utf-8", "replace") if meta is not None else ""
        part = re.search(r"pdfaid:part(?:>|=[\"'])\s*([0-9]+)", xmp)
        conf = re.search(r"pdfaid:conformance(?:>|=[\"'])\s*([A-Za-z])", xmp)
        if part:
            claimed = f"{part.group(1)}{(conf.group(1) if conf else '').lower()}"
        result["xmp_pdfaid"] = {"pass": bool(part and conf), "claimed_level": claimed}
        intents = pdf.Root.get("/OutputIntents")
        has_intent = bool(intents) and any(i.get("/DestOutputProfile") is not None for i in intents)
        result["output_intent"] = {"pass": has_intent}
        result["encrypted"] = {"pass": not pdf.is_encrypted}
    unembedded: list[str] = []
    with fitz.open(path) as doc:
        seen: set[int] = set()
        for page in doc:
            for font in page.get_fonts(full=True):
                xref = font[0]
                if xref in seen:
                    continue
                seen.add(xref)
                try:
                    embedded = xref > 0 and bool(doc.extract_font(xref)[3])
                except Exception:
                    embedded = False
                if not embedded:
                    unembedded.append(str(font[3]))
        result["fonts_embedded"] = {"pass": not unembedded, "font_count": len(seen), "unembedded": unembedded[:10]}
        result["page_count"] = doc.page_count
    result["all_pass"] = all(v.get("pass") for k, v in result.items() if isinstance(v, dict))
    result["claimed_level"] = claimed
    return result


_RULE_HINTS = (
    ("font", "embed", "字型未完整內嵌；PDF/A 要求所有字型都內嵌在檔案中。"),
    ("outputintent", "", "缺少或錯誤的輸出意圖（OutputIntent／ICC 色彩描述檔）。"),
    ("output intent", "", "缺少或錯誤的輸出意圖（OutputIntent／ICC 色彩描述檔）。"),
    ("xmp", "", "XMP 中繼資料缺少、不完整，或與文件資訊字典不一致。"),
    ("metadata", "", "中繼資料缺少、不完整，或與文件資訊字典不一致。"),
    ("transparen", "", "含透明度；此 PDF/A 等級不允許（PDF/A-1 禁止透明）。"),
    ("encrypt", "", "文件加密；PDF/A 不允許加密。"),
    ("javascript", "", "含 JavaScript；PDF/A 不允許。"),
    ("device", "", "使用與色彩設定不符的裝置相關色彩空間（如 DeviceRGB／DeviceCMYK）。"),
    ("colour", "", "色彩空間設定不符合 PDF/A。"),
    ("color", "", "色彩空間設定不符合 PDF/A。"),
    ("lzw", "", "使用 LZW 壓縮；PDF/A 不允許。"),
    ("embedded file", "", "含內嵌附件；此 PDF/A 等級限制附件。"),
    ("annotation", "", "註解設定不符合 PDF/A（例如缺少外觀串流或旗標）。"),
    ("action", "", "含不被允許的動作（如啟動外部程式、跳轉網址）。"),
    ("glyph", "", "字型缺少部分字形或字寬資訊不一致。"),
    ("trailer", "", "檔案結構（trailer／ID）不符合 PDF/A。"),
    ("header", "", "檔案標頭不符合 PDF/A。"),
)


def explain_rule(rule: dict) -> dict[str, Any]:
    """把 veraPDF 的失敗規則整理成白話繁中。原文保留於 original。"""
    text = str(rule.get("description", ""))
    low = text.lower()
    hint = next((zh for a, b, zh in _RULE_HINTS if a in low and b in low), "")
    clause = f"{rule.get('specification', '')} 第 {rule.get('clause', '?')} 條 測試 {rule.get('testNumber', '?')}".strip()
    message = f"{clause}：{hint or '不符合 PDF/A 規範，詳見原文。'}（失敗 {rule.get('failedChecks', '?')} 處）"
    return {"clause": str(rule.get("clause", "")), "test": rule.get("testNumber"),
            "failed_checks": rule.get("failedChecks"), "message": message, "original": text}


def verapdf_validate(command: list[str], path: str, flavour: str) -> dict[str, Any]:
    proc = subprocess.run(command + ["--format", "json", "--flavour", flavour, path],
                          capture_output=True, text=True, timeout=300)
    if proc.returncode not in (0, 1):
        raise OpError("verapdf_failed", "veraPDF 執行失敗，無法完成正式驗證。", EXIT_FAIL,
                      {"stderr_tail": (proc.stderr or proc.stdout)[-500:]})
    try:
        job = json.loads(proc.stdout)["report"]["jobs"][0]
        res = job["validationResult"][0]
        compliant = res.get("compliant") is True
        details = res["details"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise OpError("verapdf_failed", "veraPDF 未回傳可判定的合規結果。", EXIT_FAIL)
    failed = [r for r in details.get("ruleSummaries", []) if r.get("ruleStatus") == "FAILED"]
    failed_rules = [r.get("description", "") for r in failed]
    issues = [explain_rule(r) for r in failed]
    return {"compliant": compliant and details.get("failedChecks", 1) == 0,
            "profile": res.get("profileName", ""), "failed_checks": details.get("failedChecks"),
            "passed_checks": details.get("passedChecks"), "failed_rules": failed_rules[:20], "issues": issues[:30]}


def _validate_file(path: str, level: str, params: dict) -> dict[str, Any]:
    flavour = level
    checks = basic_pdfa_checks(path)
    command, source = find_verapdf(params)
    info: dict[str, Any] = {"level": level, "basic_checks": checks}
    if command:
        vera = verapdf_validate(command, path, flavour)
        info.update({"validation": "verapdf", "verapdf_source": source, "compliant": vera["compliant"], "verapdf": vera})
    else:
        info.update({"validation": "basic_only", "compliant": bool(checks["all_pass"]),
                     "note": "僅做基本檢查（XMP pdfaid、字型內嵌、OutputIntent）；正式驗證需 veraPDF。"})
    return info


def _level(params: dict) -> str:
    level = str(params.get("level", "2b")).lower()
    if level not in ("1b", "2b", "3b"):
        raise OpError("bad_args", "level 只支援 1b、2b、3b。", EXIT_USAGE)
    return level


def _ps_string(text: Any) -> str:
    return "(" + str(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


# ── 各 op ───────────────────────────────────────────────────────────────
def op_capabilities(app_version: str, params: dict | None = None) -> dict[str, Any]:
    params = params or {}
    gs = find_gs(params)
    vera, source = find_verapdf(params)
    ok, reason = vision_available()
    return {"app_version": app_version, "protocol_version": PROTOCOL_VERSION, "ops": list(OPS),
            "ghostscript": {"available": bool(gs), "path": gs or ""},
            "verapdf": {"available": bool(vera), "source": source},
            "vision": {"available": ok, "reason": reason},
            "pdfa_levels": ["1b", "2b", "3b"]}


def op_pdfa_validate(inp: str, params: dict) -> dict[str, Any]:
    _check_input(inp)
    doc = _open_plain(inp)
    doc.close()
    level = _level(params)
    return _validate_file(inp, level, params)


def op_pdfa_convert(inp: str, out: str, params: dict) -> dict[str, Any]:
    import fitz
    _check_input(inp)
    _check_output(inp, out)
    level = _level(params)
    gs = find_gs(params)
    if not gs:
        raise OpError("gs_missing", "找不到 Ghostscript，無法轉換 PDF/A。", EXIT_FAIL)
    icc_src = Path(__file__).resolve().parents[1] / "resources/color/sRGB2014.icc"
    if not icc_src.is_file():
        raise OpError("icc_missing", "找不到內建 sRGB 色彩描述檔。", EXIT_FAIL)
    doc = _open_plain(inp)
    try:
        pages = doc.page_count
        if any(w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE and w.is_signed for p in doc for w in p.widgets() or ()):
            raise OpError("signed_document", "標準轉換會改寫已簽署內容，請使用未簽署的來源副本。")
        with tempfile.TemporaryDirectory(prefix="acropdf_headless_") as stage_dir, _Staged(out) as temporary:
            stage = Path(stage_dir)
            source, icc, definition = stage / "source.pdf", stage / "sRGB.icc", stage / "definition.ps"
            shutil.copyfile(icc_src, icc)
            doc.save(source, garbage=4, deflate=True)
            definition.write_text(f"""%!
[/_objdef {{icc}} /type /stream /OBJ pdfmark
[{{icc}} << /N 3 >> /PUT pdfmark
[{{icc}} {_ps_string(icc)} (r) file /PUT pdfmark
[/_objdef {{intent}} /type /dict /OBJ pdfmark
[{{intent}} << /Type /OutputIntent /S /GTS_PDFA1 /DestOutputProfile {{icc}} /OutputConditionIdentifier (sRGB) >> /PUT pdfmark
[{{Catalog}} << /OutputIntents [{{intent}}] >> /PUT pdfmark
""")
            cmd = [gs, "-dSAFER", "-dBATCH", "-dNOPAUSE", "-dQUIET", f"-dPDFA={level[0]}",
                   "-dPDFACompatibilityPolicy=2", "-sDEVICE=pdfwrite", "-sColorConversionStrategy=RGB",
                   "-sBlendConversionStrategy=Managed", "-dEmbedAllFonts=true",
                   f"--permit-file-read={icc}", f"-sOutputICCProfile={icc}",
                   f"-sOutputFile={temporary}", str(definition), str(source)]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=int(params.get("timeout_sec", 300)))
            except subprocess.TimeoutExpired:
                raise OpError("gs_timeout", "Ghostscript 轉換逾時。")
            if proc.returncode != 0:
                raise OpError("conversion_failed", "Ghostscript 轉換失敗。", EXIT_FAIL,
                              {"stderr_tail": (proc.stderr or proc.stdout)[-500:]})
            with fitz.open(temporary) as converted:
                if converted.page_count != pages:
                    raise OpError("page_count_mismatch", "轉換後頁數不符，未發佈輸出。")
            info = _validate_file(str(temporary), level, params)
            if not info["compliant"]:
                raise OpError("validation_failed", "轉換後的檔案未通過 PDF/A 驗證，未發佈輸出。", EXIT_FAIL, info)
            _publish(temporary, out)
    finally:
        doc.close()
    info["pages"] = pages
    info["engine"] = "ghostscript"
    return info


def op_vision_ocr(inp: str, out: str, params: dict) -> dict[str, Any]:
    import fitz
    from acro_platform.common import insert_ocr_line
    _check_input(inp)
    _check_output(inp, out)
    ok, reason = vision_available()
    if not ok:
        raise OpError("vision_unavailable", f"Apple Vision 無法使用：{reason}", EXIT_FAIL)
    from acro_platform.mac import MacVisionOCR
    backend = MacVisionOCR()
    dpi = int(params.get("dpi", 300))
    if not 72 <= dpi <= 600:
        raise OpError("bad_args", "dpi 須介於 72 與 600。", EXIT_USAGE)
    langs = params.get("languages", ["zh-Hant", "en"])
    if not isinstance(langs, list) or not langs or not all(isinstance(x, str) for x in langs):
        raise OpError("bad_args", "languages 必須是非空字串陣列。", EXIT_USAGE)
    skip_text = bool(params.get("skip_text_pages", True))
    doc = _open_plain(inp)
    per_page: list[dict[str, Any]] = []
    try:
        with _Staged(out) as temporary:
            for index in range(doc.page_count):
                page = doc[index]
                if skip_text and page.get_text().strip():
                    per_page.append({"page": index + 1, "status": "skipped_has_text", "chars": 0, "confidence": None})
                    continue
                lines = backend.recognize_page(page, langs, dpi)
                chars, confs = 0, []
                for text, conf, rect in lines:
                    insert_ocr_line(page, text, rect)
                    chars += len(text.replace("\n", ""))
                    confs.append(conf)
                per_page.append({"page": index + 1, "status": "ocr", "chars": chars,
                                 "confidence": round(sum(confs) / len(confs), 4) if confs else None})
            doc.save(temporary, garbage=4, deflate=True)
            _publish(temporary, out)
    finally:
        doc.close()
    scored = [p["confidence"] for p in per_page if p["confidence"] is not None]
    return {"engine": "apple_vision", "languages": langs, "dpi": dpi, "pages": len(per_page),
            "pages_ocr": sum(p["status"] == "ocr" for p in per_page),
            "pages_skipped": sum(p["status"] != "ocr" for p in per_page),
            "total_chars": sum(p["chars"] for p in per_page),
            "mean_confidence": round(sum(scored) / len(scored), 4) if scored else None,
            "per_page": per_page}


# ── 入口 ────────────────────────────────────────────────────────────────
def _run(argv: list[str], app_version: str) -> tuple[dict[str, Any], int]:
    op = ""
    try:
        args = parse_args(argv)
        op = args["op"]
        inp, out, params = args["input"], args["output"], args["params"]
        if op == "capabilities":
            details = op_capabilities(app_version, params)
        elif op == "pdfa_validate":
            details = op_pdfa_validate(inp, params)
        elif op == "pdfa_convert":
            details = op_pdfa_convert(inp, out, params)
        else:
            details = op_vision_ocr(inp, out, params)
        if inp and os.path.isfile(inp):
            details["input_sha256"] = sha256_file(inp)
        written = out if (out and op in ("pdfa_convert", "vision_ocr")) else ""
        return ({"protocol_version": PROTOCOL_VERSION, "ok": True, "op": op, "output": written,
                 "output_sha256": sha256_file(written) if written else "", "details": details,
                 "error": None}, EXIT_OK)
    except OpError as err:
        return ({"protocol_version": PROTOCOL_VERSION, "ok": False, "op": op, "output": "", "output_sha256": "",
                 "details": err.details, "error": {"code": err.code, "message": err.message}}, err.exit_code)
    except Exception as exc:  # 不可讓例外洩漏成非 JSON 輸出
        print(f"[headless-op] 未預期錯誤：{type(exc).__name__}: {exc}", file=sys.stderr)
        return ({"protocol_version": PROTOCOL_VERSION, "ok": False, "op": op, "output": "", "output_sha256": "",
                 "details": {}, "error": {"code": "internal_error", "message": f"處理時發生未預期的錯誤：{exc}"}}, EXIT_FAIL)


def run_headless(argv: list[str], app_version: str) -> int:
    """執行並以單行 JSON 寫到真正的 stdout；其他任何寫入 fd 1 的內容改導向 stderr。"""
    real_out = os.dup(1)
    try:
        os.dup2(2, 1)
    except OSError:
        pass
    try:
        payload, code = _run(argv, app_version)
    finally:
        try:
            os.dup2(real_out, 1)
        except OSError:
            pass
    line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    os.write(real_out, line.encode("utf-8"))
    os.close(real_out)
    return code


def dispatch_headless(argv: list[str], app_version: str) -> int | None:
    """argv 不含 --headless-op 時回傳 None（交給其他入口）。"""
    if not any(a == "--headless-op" or a.startswith("--headless-op=") for a in argv):
        return None
    return run_headless(argv, app_version)
