"""Tesseract OCR with a persistent, searchable Unicode text layer."""
import os
import shutil
import sys
import fitz


def insert_ocr_line(page, text, visual_rect):
    if not text.strip(): return
    rect = fitz.Rect(visual_rect)
    existing = page.get_text('words')
    unrotated = rect * page.derotation_matrix
    if any((fitz.Rect(word[:4]) & unrotated).get_area() > fitz.Rect(word[:4]).get_area() * .7 for word in existing):
        return
    fontname = 'china-t' if any(ord(c) > 255 for c in text) else 'helv'
    fontsize = max(1, rect.height * .75)
    width = fitz.Font(fontname=fontname).text_length(text, fontsize=fontsize)
    if width > rect.width and width > 0: fontsize *= rect.width / width
    origin = fitz.Point(rect.x0, rect.y1 - rect.height * .1) * page.derotation_matrix
    page.insert_text(origin, text, fontsize=fontsize, fontname=fontname,
                     rotate=page.rotation, render_mode=3, color=(0, 0, 0))


class TesseractOCR:
    name = 'Tesseract'

    def __init__(self):
        self._tess_cmd = shutil.which('tesseract')
        if not self._tess_cmd:
            paths = ['/opt/homebrew/bin/tesseract', '/usr/local/bin/tesseract'] if sys.platform == 'darwin' else [os.path.join(os.environ.get('ProgramFiles', 'C:/Program Files'), 'Tesseract-OCR/tesseract.exe')]
            self._tess_cmd = next((path for path in paths if os.path.isfile(path)), None)

    def is_available(self): return self._tess_cmd is not None

    def _configure(self):
        if not self._tess_cmd: raise RuntimeError('找不到 Tesseract OCR 執行檔。')
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = self._tess_cmd
        return pytesseract

    def ocr_page(self, page, lang, dpi):
        import math
        from PIL import Image
        pytesseract = self._configure()
        scale = min(dpi / 72, math.sqrt(24_000_000 / page.rect.get_area()))
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), colorspace=fitz.csRGB, alpha=False)
        image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
        data = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT, timeout=120)
        groups = {}
        for index, word in enumerate(data['text']):
            if not word.strip() or float(data['conf'][index]) < 0: continue
            key = (data['block_num'][index], data['par_num'][index], data['line_num'][index])
            rect = fitz.Rect(data['left'][index], data['top'][index],
                             data['left'][index] + data['width'][index],
                             data['top'][index] + data['height'][index])
            groups.setdefault(key, []).append((word, rect))
        for group in groups.values():
            rect = fitz.Rect(group[0][1])
            for _, bounds in group[1:]: rect |= bounds
            text = ' '.join(word for word, _ in group)
            insert_ocr_line(page, text, rect * fitz.Matrix(1 / scale, 1 / scale))

    def ocr_image_path(self, image_path, lang='chi_tra+eng'):
        from PIL import Image
        with Image.open(image_path) as image:
            return self._configure().image_to_string(image, lang=lang, timeout=120)

    def supported_languages(self):
        if not self._tess_cmd: return []
        return self._configure().get_languages(config='')
