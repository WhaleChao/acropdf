# ~/Desktop/acropdf/platform/windows.py
"""
Windows WinRT OCR（Win10 1809+ 內建，不需安裝任何東西）。
僅在 Windows 上使用，其他平台不會 import 此檔案。
"""
import sys
import fitz

class WinRTOCR:
    name = "Windows OCR"

    def __init__(self):
        if sys.platform != "win32":
            raise ImportError("WinRT OCR 只能在 Windows 上使用")
        # 驗證 WinRT 可用（Win10 1809+）
        try:
            import ctypes
            ver = sys.getwindowsversion()
            if ver.major < 10:
                raise ImportError("需要 Windows 10 以上")
        except Exception:
            raise ImportError("無法取得 Windows 版本")

    def is_available(self) -> bool:
        try:
            import subprocess
            # 用 PowerShell 檢測 WinRT OCR 是否可用
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]"
                 " | Out-Null; Write-Host 'OK'"],
                capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return "OK" in r.stdout
        except Exception:
            return False

    def ocr_page(self, page: fitz.Page, lang: str, dpi: int) -> None:
        """
        用 Windows WinRT OCR 辨識頁面。
        透過 PowerShell 調用 WinRT API（避免直接依賴 winrt-runtime pip 套件）。
        """
        import subprocess
        import json
        import tempfile
        import os

        # 1. 渲染頁面為 PNG
        mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        tmp_png = tempfile.NamedTemporaryFile(suffix=".png", delete=False, prefix="acropdf_ocr_")
        pix.save(tmp_png.name)
        tmp_png.close()

        # 2. 語言映射
        lang_map = {
            "chi_tra": "zh-Hant-TW", "chi_sim": "zh-Hans-CN",
            "eng": "en-US", "jpn": "ja-JP",
        }
        first_lang = lang.split("+")[0].strip()
        win_lang = lang_map.get(first_lang, "en-US")

        # 3. PowerShell 腳本執行 WinRT OCR
        ps_script = f'''
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap,Windows.Foundation,ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.RandomAccessStream,Windows.Foundation,ContentType=WindowsRuntime]

function Await($WinRtTask, $ResultType) {{
    $asTask = $WinRtTask.GetType().GetMethod('AsTask', [type[]])
    if ($asTask) {{ $task = $asTask.Invoke($null, @($WinRtTask)) }}
    else {{ $task = [System.WindowsRuntimeSystemExtensions]::AsTask($WinRtTask) }}
    $task.Wait()
    return $task.Result
}}

$lang = [Windows.Globalization.Language]::new("{win_lang}")
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
if (-not $engine) {{ $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }}

$stream = [Windows.Storage.Streams.RandomAccessStream,Windows.Foundation,ContentType=WindowsRuntime]
$file = [System.IO.File]::OpenRead("{tmp_png.name.replace(chr(92), '/')}")
$memStream = [Windows.Storage.Streams.InMemoryRandomAccessStream]::new()
[System.IO.WindowsRuntimeStreamExtensions]::CopyToAsync($file, $memStream).Wait()
$file.Close()
$memStream.Seek(0)

$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($memStream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])

$output = @()
foreach ($line in $result.Lines) {{
    $words = @()
    foreach ($word in $line.Words) {{
        $rect = $word.BoundingRect
        $words += @{{
            text = $word.Text
            x = $rect.X; y = $rect.Y
            w = $rect.Width; h = $rect.Height
        }}
    }}
    $output += @{{ text = $line.Text; words = $words }}
}}
$output | ConvertTo-Json -Depth 5
$memStream.Dispose()
$bitmap.Dispose()
'''
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True, text=True, timeout=60,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if r.returncode == 0 and r.stdout.strip():
                lines = json.loads(r.stdout)
                if isinstance(lines, dict):
                    lines = [lines]  # 單行時 PowerShell JSON 不包在陣列
                page_rect = page.rect
                scale = 72.0 / dpi  # DPI → PDF 座標
                for line in lines:
                    text = line.get("text", "")
                    words = line.get("words", [])
                    if words:
                        y_pos = words[0].get("y", 0) * scale + words[0].get("h", 12) * scale
                        x_pos = words[0].get("x", 0) * scale
                        fontsize = max(6, min(words[0].get("h", 12) * scale * 0.8, 14))
                    else:
                        continue
                    try:
                        page.insert_text(
                            fitz.Point(x_pos, y_pos),
                            text, fontsize=fontsize,
                            color=(0, 0, 0), render_mode=3,
                        )
                    except Exception:
                        pass
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            print(f"[WinRTOCR] 辨識失敗：{e}")
        finally:
            os.unlink(tmp_png.name)

    def ocr_image_path(self, image_path: str, lang: str = "chi_tra+eng") -> str:
        """
        OCR 指定 PNG/JPG，回傳文字字串（供 auto_label_engine 使用）。
        重用 ocr_page 的 PowerShell 邏輯，但不需要 fitz.Page，直接回傳文字。
        """
        import subprocess, json, os

        lang_map = {
            "chi_tra": "zh-Hant-TW", "chi_sim": "zh-Hans-CN",
            "eng": "en-US", "jpn": "ja-JP",
        }
        first_lang = lang.split("+")[0].strip()
        win_lang = lang_map.get(first_lang, "en-US")
        img_path_fwd = image_path.replace("\\", "/")

        ps_script = f'''
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap,Windows.Foundation,ContentType=WindowsRuntime]

function Await($WinRtTask) {{
    $asTask = [System.WindowsRuntimeSystemExtensions]::AsTask($WinRtTask)
    $asTask.Wait()
    return $asTask.Result
}}

$lang = [Windows.Globalization.Language]::new("{win_lang}")
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
if (-not $engine) {{ $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }}

$file = [System.IO.File]::OpenRead("{img_path_fwd}")
$memStream = [Windows.Storage.Streams.InMemoryRandomAccessStream]::new()
[System.IO.WindowsRuntimeStreamExtensions]::CopyToAsync($file, $memStream).Wait()
$file.Close(); $memStream.Seek(0)

$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($memStream))
$bitmap  = Await ($decoder.GetSoftwareBitmapAsync())
$result  = Await ($engine.RecognizeAsync($bitmap))

$result.Lines | ForEach-Object {{ $_.Text }}
$memStream.Dispose(); $bitmap.Dispose()
'''
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                capture_output=True, text=True, timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            return r.stdout.strip() if r.returncode == 0 else ""
        except Exception:
            return ""

    def supported_languages(self) -> list[str]:
        try:
            import subprocess
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]"
                 " | Out-Null;"
                 "[Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages"
                 " | ForEach-Object { $_.LanguageTag }"],
                capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            langs = [l.strip() for l in r.stdout.splitlines() if l.strip()]
            return langs if langs else ["en-US"]
        except Exception:
            return ["en-US"]
