"""Print copies with private documents and bounded rendering."""
import math

import fitz

from core.file_io import atomic_output


def validate_print_pages(doc, page_indices, copies=1, password=None):
    if not page_indices or any(not isinstance(i, int) or not 0 <= i < len(doc) for i in page_indices):
        raise ValueError('請選擇有效的列印頁面。')
    if not isinstance(copies, int) or not 1 <= copies <= 99:
        raise ValueError('列印份數必須介於 1 與 99。')
    if not doc.permissions & fitz.PDF_PERM_PRINT and not (password is not None and doc.authenticate(password) & 4):
        raise ValueError('此文件沒有列印權限。')


def prepare_print_appearances(doc):
    """Respect PDF annotation printing flags on a private print document."""
    invisible = fitz.PDF_ANNOT_IS_HIDDEN | fitz.PDF_ANNOT_IS_INVISIBLE
    for page in doc:
        for annotation in list(page.annots() or ()):
            if not annotation.flags & fitz.PDF_ANNOT_IS_PRINT or annotation.flags & invisible:
                page.delete_annot(annotation)
        for widget in list(page.widgets() or ()):
            raw = doc.xref_get_key(widget.xref, 'F')[1]
            flags = int(raw) if raw != 'null' else 0
            if not flags & fitz.PDF_ANNOT_IS_PRINT or flags & invisible:
                page.delete_widget(widget)


class PrintEngine:
    def __init__(self, document):
        self.document = document

    def export_pdf(self, output_path, page_indices, copies=1,
                   paper_size=(595.276, 841.89), margin=18,
                   landscape=False, overwrite=False, interrupted=None, progress=None):
        """Create a vector print copy, including visible annotation/form appearances."""
        original = self.document.fitz_doc
        validate_print_pages(original, page_indices, copies, self.document._password)
        width, height = paper_size
        if not all(math.isfinite(n) and n > 0 for n in (width, height)):
            raise ValueError('紙張尺寸必須有效。')
        if landscape:
            width, height = height, width
        if not math.isfinite(margin) or margin < 0 or margin * 2 >= min(width, height):
            raise ValueError('紙張邊界必須小於紙張尺寸。')
        target = fitz.Rect(margin, margin, width - margin, height - margin)
        with atomic_output(output_path, source=self.document.source_path, overwrite=overwrite) as temporary:
            with fitz.open() as selected, fitz.open() as output:
                for number in page_indices:
                    if interrupted and interrupted():
                        raise InterruptedError('列印已取消，沒有輸出檔案。')
                    selected.insert_pdf(original, from_page=number, to_page=number)
                prepare_print_appearances(selected)
                selected.bake(annots=True, widgets=True)
                total = len(selected) * copies
                for copy in range(copies):
                    for number in range(len(selected)):
                        if interrupted and interrupted():
                            raise InterruptedError('列印已取消，沒有輸出檔案。')
                        page = output.new_page(width=width, height=height)
                        source_page = selected[number]
                        # Empty pages have no content stream to import.
                        if source_page.get_contents():
                            page.show_pdf_page(target, selected, number, keep_proportion=True)
                        if progress:
                            progress(round(100 * (copy * len(selected) + number + 1) / total))
                output.set_metadata({'title': self.document.display_name + ' — 列印副本', 'creator': 'AcroPDF'})
                output.save(temporary, garbage=4, deflate=True)
            with fitz.open(temporary) as check:
                if len(check) != total:
                    raise ValueError('列印副本頁數不符，沒有輸出檔案。')
            if interrupted and interrupted():
                raise InterruptedError('列印已取消，沒有輸出檔案。')
        return {'path': str(output_path), 'pages': total, 'vector_content': True}


def render_scale(page_rect, printer_dpi, max_pixels=24_000_000, max_edge=16384):
    width, height = page_rect.width, page_rect.height
    if width <= 0 or height <= 0:
        raise ValueError('頁面尺寸必須有效。')
    # Reserve two pixels on each edge for renderer rounding.
    area = width * height
    pixel_scale = (math.sqrt((width+height)**2 + area*(max_pixels-4)) - (width+height)) / area
    return min(max(1, min(printer_dpi, 300)) / 72,
               pixel_scale, (max_edge-2) / max(width, height))


def print_to_device(doc, printer, page_indices, interrupted=None, progress=None, password=None):
    """Submit physical pages without allocating printer-resolution page images."""
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QPainter, QImage
    from PyQt6.QtPrintSupport import QPrinter
    validate_print_pages(doc, page_indices, password=password)
    painter = QPainter()
    if not painter.begin(printer):
        raise RuntimeError('無法啟動列印。')
    try:
        for position, number in enumerate(page_indices):
            if interrupted and interrupted():
                printer.abort()
                raise InterruptedError('列印已取消，部分頁面可能已送至印表機。')
            if position and not printer.newPage():
                raise RuntimeError('印表機無法開始下一頁。')
            page = doc[number]
            zoom = render_scale(page.rect, printer.resolution())
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), colorspace=fitz.csRGB, alpha=False)
            image = QImage(pix.samples_ptr, pix.width, pix.height, pix.stride,
                           QImage.Format.Format_RGB888).copy()
            bounds = printer.pageRect(QPrinter.Unit.DevicePixel)
            scale = min(bounds.width() / image.width(), bounds.height() / image.height())
            width, height = image.width() * scale, image.height() * scale
            target = QRectF((bounds.width()-width)/2, (bounds.height()-height)/2, width, height)
            painter.drawImage(target, image)
            if printer.printerState() == QPrinter.PrinterState.Error:
                raise RuntimeError(f'印表機在第 {number+1} 頁回報錯誤。')
            if progress:
                progress(position + 1)
        if interrupted and interrupted():
            printer.abort()
            raise InterruptedError('列印已取消，部分頁面可能已送至印表機。')
    except Exception:
        printer.abort()
        raise
    finally:
        ended = painter.end()
    if not ended or printer.printerState() == QPrinter.PrinterState.Error:
        raise RuntimeError('印表機未能完成列印。')
