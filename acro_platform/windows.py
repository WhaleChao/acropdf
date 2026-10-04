"""WinRT OCR with fixed PowerShell code, safe parameters and persistent text layers."""
import os
import sys
import fitz

_SCRIPT = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder,Windows.Foundation,ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap,Windows.Foundation,ContentType=WindowsRuntime]
$null = [Windows.Storage.StorageFile,Windows.Foundation,ContentType=WindowsRuntime]
$null = [Windows.Storage.Streams.IRandomAccessStream,Windows.Foundation,ContentType=WindowsRuntime]
$null = [Windows.Globalization.Language,Windows.Foundation,ContentType=WindowsRuntime]
function Await($Operation, [Type]$ResultType) {
    $method = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and
        $_.GetGenericArguments().Count -eq 1 -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    } | Select-Object -First 1
    if (-not $method) { throw 'WinRT async bridge unavailable' }
    $task = $method.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.Wait()
    return $task.Result
}
$lang = [Windows.Globalization.Language]::new($env:ACROPDF_OCR_LOCALE)
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
if (-not $engine) { throw ('OCR language pack not installed: ' + $env:ACROPDF_OCR_LOCALE) }
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($env:ACROPDF_OCR_IMAGE)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
try {
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    try {
        if ($bitmap.PixelWidth -gt [Windows.Media.Ocr.OcrEngine]::MaxImageDimension -or $bitmap.PixelHeight -gt [Windows.Media.Ocr.OcrEngine]::MaxImageDimension) { throw 'Image exceeds WinRT OCR maximum size' }
        $result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
        $output = @()
        foreach ($line in $result.Lines) {
            $words = @()
            foreach ($word in $line.Words) {
                $r = $word.BoundingRect
                $words += @{ text=$word.Text; x=$r.X; y=$r.Y; w=$r.Width; h=$r.Height }
            }
            $output += @{ text=$line.Text; words=$words }
        }
        ConvertTo-Json -InputObject @($output) -Depth 5 -Compress
    } finally { $bitmap.Dispose() }
} finally { $stream.Dispose() }
'''


class WinRTOCR:
    name = 'Windows OCR'
    def __init__(self):
        if sys.platform != 'win32' or sys.getwindowsversion().major < 10:
            raise ImportError('WinRT OCR 需要 Windows 10 以上。')

    def is_available(self):
        import subprocess
        try:
            result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',
                '[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime] | Out-Null; Write-Output OK'],capture_output=True,text=True,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
            return result.returncode==0 and 'OK' in result.stdout
        except Exception: return False

    @staticmethod
    def _recognize(path,lang):
        import json
        import subprocess
        locales={'chi_tra':'zh-Hant-TW','chi_sim':'zh-Hans-CN','eng':'en-US','jpn':'ja-JP','kor':'ko-KR'}
        first=lang.split('+')[0].strip()
        if first not in locales: raise ValueError('Windows OCR 尚無此語言映射，請選擇已安裝的語言。')
        environment=os.environ.copy();environment['ACROPDF_OCR_IMAGE']=os.path.abspath(path);environment['ACROPDF_OCR_LOCALE']=locales[first]
        result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',_SCRIPT],env=environment,
            capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120,creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode: raise RuntimeError('Windows OCR 失敗：'+result.stderr[-1500:])
        data=json.loads(result.stdout)
        if not isinstance(data,list): raise RuntimeError('Windows OCR 回傳格式無效。')
        return data

    def ocr_page(self,page,lang,dpi):
        import tempfile
        from pathlib import Path
        from acro_platform.common import insert_ocr_line
        zoom=min(dpi/72,2000/max(page.rect.width,page.rect.height))
        pix=page.get_pixmap(matrix=fitz.Matrix(zoom,zoom),alpha=False)
        with tempfile.TemporaryDirectory(prefix='acropdf_winocr_') as directory:
            image=Path(directory)/'page.png';pix.save(image)
            data=self._recognize(str(image),lang)
        sx=page.rect.width/pix.width;sy=page.rect.height/pix.height
        for line in data:
            words=line.get('words',[])
            if not words: continue
            rect=fitz.Rect(min(w['x'] for w in words)*sx,min(w['y'] for w in words)*sy,
                           max(w['x']+w['w'] for w in words)*sx,max(w['y']+w['h'] for w in words)*sy)
            insert_ocr_line(page,line.get('text',''),rect)

    def ocr_image_path(self,image_path,lang='chi_tra+eng'):
        return '\n'.join(line.get('text','') for line in self._recognize(image_path,lang))
