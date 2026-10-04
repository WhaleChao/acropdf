"""Batch processing never overwrites inputs or existing generated outputs."""
from __future__ import annotations
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Callable
import fitz
from core.file_io import atomic_output


class BatchEngine:
    @staticmethod
    def _open(path):
        doc = fitz.open(path)
        if doc.needs_pass:
            doc.close()
            raise ValueError('批次來源需要密碼，請先另存授權副本。')
        return doc

    @staticmethod
    def _save(doc, source, target):
        with atomic_output(target, source=source) as temporary:
            doc.save(temporary, garbage=4, deflate=True, encryption=fitz.PDF_ENCRYPT_KEEP)

    def add_watermark(self, input_path, output_path, text, opacity=.3, position='center'):
        if not 0 <= opacity <= 1:
            raise ValueError('透明度須介於 0 與 1。')
        with self._open(input_path) as doc:
            for page in doc:
                bounds = page.rect * page.derotation_matrix
                x = 50 if position.endswith('left') else bounds.width - 50
                y = 60 if position.startswith('top') else bounds.height - 60
                if position == 'center': x, y = bounds.width / 2, bounds.height / 2
                font = 'china-t' if any(ord(c) > 255 for c in text) else 'helv'
                width = fitz.Font(fontname=font).text_length(text, fontsize=40)
                x = max(20, min(x - width / 2, bounds.width - width - 20))
                shape = page.new_shape()
                shape.insert_text((x, y), text, fontsize=40, fontname=font,
                                  color=(.7, .7, .7), fill_opacity=opacity,
                                  morph=(fitz.Point(x, y), fitz.Matrix(45)))
                shape.commit()
            self._save(doc, input_path, output_path)

    def add_header_footer(self, input_path, output_path, header='', footer='', variables=True):
        with self._open(input_path) as doc:
            for i, page in enumerate(doc):
                bounds = page.rect * page.derotation_matrix
                for template, y in ((header, 25), (footer, bounds.height - 20)):
                    text = template
                    if variables:
                        text = text.replace('{page}', str(i + 1)).replace('{total}', str(len(doc))).replace('{date}', date.today().strftime('%Y/%m/%d'))
                    if not text: continue
                    font = 'china-t' if any(ord(c) > 255 for c in text) else 'helv'
                    width = fitz.Font(fontname=font).text_length(text, fontsize=10)
                    if width > bounds.width - 40: raise ValueError('頁首頁尾文字超出頁面。')
                    page.insert_text(((bounds.width - width) / 2, y), text, fontsize=10, fontname=font)
            self._save(doc, input_path, output_path)

    def add_bates_number(self, input_path, output_path, prefix='', start=1, digits=6, position='bottom-right'):
        if start < 0 or not 1 <= digits <= 20: raise ValueError('Bates 編號設定無效。')
        with self._open(input_path) as doc:
            for i, page in enumerate(doc):
                bounds = page.rect * page.derotation_matrix
                text = f'{prefix}{start + i:0{digits}d}'
                font = 'china-t' if any(ord(c) > 255 for c in text) else 'helv'
                width = fitz.Font(fontname=font).text_length(text, fontsize=9)
                if width > bounds.width - 40: raise ValueError('Bates 編號超出頁面。')
                x = 20 if position.endswith('left') else bounds.width - width - 20
                y = 25 if position.startswith('top') else bounds.height - 20
                page.insert_text((x, y), text, fontsize=9, fontname=font)
            self._save(doc, input_path, output_path)

    def split_pages(self, input_path, output_dir, pages_per_file=1):
        if not isinstance(pages_per_file, int) or pages_per_file < 1:
            raise ValueError('每個分割檔至少須有一頁。')
        destination = Path(output_dir); destination.mkdir(parents=True, exist_ok=True)
        published = []
        with self._open(input_path) as doc, tempfile.TemporaryDirectory(dir=destination, prefix='.split_') as stage:
            pairs = []
            for part, start in enumerate(range(0, len(doc), pages_per_file), 1):
                target = destination / f'{Path(input_path).stem}_part{part:03d}.pdf'
                if target.exists(): raise FileExistsError(f'分割檔已存在：{target}')
                temporary = Path(stage) / target.name
                with fitz.open() as chunk:
                    chunk.insert_pdf(doc, from_page=start, to_page=min(start + pages_per_file, len(doc)) - 1)
                    chunk.save(temporary, garbage=4, deflate=True)
                pairs.append((temporary, target))
            try:
                for temporary, target in pairs:
                    os.link(temporary, target); published.append(str(target))
            except Exception:
                for path in published: Path(path).unlink(missing_ok=True)
                raise
        return published

    def _export(self, source, target, fmt):
        from core.document import PDFDocument
        doc = PDFDocument()
        try:
            if not doc.open(source): raise ValueError(doc.last_error or '無法開啟批次来源')
            with atomic_output(target, source=source) as temporary:
                getattr(doc.exports, f'export_{fmt}')(str(temporary))
        finally: doc.close()

    def export_to_docx(self, input_path, output_path): self._export(input_path, output_path, 'docx')
    def export_to_html(self, input_path, output_path): self._export(input_path, output_path, 'html')

    def batch_process(self, files, operation, params, progress_callback=None, is_cancelled=None):
        if operation == 'merge':
            target = str(Path(params['output_dir']) / 'merged.pdf')
            try:
                with fitz.open() as merged:
                    for source in files:
                        if is_cancelled and is_cancelled(): raise RuntimeError('批次處理已取消。')
                        with self._open(source) as doc: merged.insert_pdf(doc)
                    if any(os.path.realpath(source) == os.path.realpath(target) for source in files):
                        raise ValueError('合併輸出不能覆寫來源。')
                    self._save(merged, None, target)
                return [{'path': str(source), 'output': target, 'ok': True} for source in files]
            except Exception as exc:
                return [{'path': str(source), 'error': str(exc), 'ok': False} for source in files]
        results = []; names = {}; bates_start = params.get("start", 1)
        for i, path in enumerate(files):
            if is_cancelled and is_cancelled():
                results.extend({'path': str(p), 'error': '已取消，未處理。', 'ok': False} for p in files[i:]); break
            if progress_callback: progress_callback(i, len(files), path)
            try:
                options = dict(params)
                stem = Path(path).stem; names[stem] = names.get(stem,0)+1
                options['output_stem'] = stem if names[stem]==1 else f"{stem}_{names[stem]}"
                if operation == 'bates': options['start'] = bates_start
                output = self._process_one(path, operation, options)
                if operation == 'bates':
                    with self._open(path) as counted: bates_start += len(counted)
                results.append({'path': path, 'output': output, 'ok': True})
            except Exception as exc:
                results.append({'path': path, 'error': str(exc), 'ok': False})
        if progress_callback: progress_callback(len(results), len(files), '完成')
        return results

    def _process_one(self, path, operation, params):
        folder = Path(params.get('output_dir') or Path(path).parent)
        folder.mkdir(parents=True, exist_ok=True)
        stem = folder / params.get("output_stem", Path(path).stem)
        if operation == 'watermark':
            target = str(stem) + '_watermarked.pdf'; self.add_watermark(path, target, params.get('text', '浮水印'), params.get('opacity', .3), params.get('position', 'center'))
        elif operation == 'header_footer':
            target = str(stem) + '_hf.pdf'; self.add_header_footer(path, target, params.get('header', ''), params.get('footer', ''))
        elif operation == 'bates':
            target = str(stem) + '_bates.pdf'; self.add_bates_number(path, target, params.get('prefix', ''), params.get('start', 1), params.get('digits', 6), params.get('position', 'bottom-right'))
        elif operation == 'split':
            target = str(stem) + '_split'; self.split_pages(path, target, params.get('pages_per_file', 1))
        elif operation in ('docx', 'html', 'txt'):
            target = str(stem) + '.' + operation; self._export(path, target, operation)
        elif operation == 'ocr':
            from core.ocr_engine import OCREngine
            target = str(stem) + '_ocr.pdf'
            OCREngine.run_sync(path, target, lang=params.get('lang', 'chi_tra+eng'), dpi=params.get('dpi', 300))
        elif operation in ('optimize', 'encrypt', 'png', 'redact'):
            from core.document import PDFDocument
            doc = PDFDocument()
            try:
                if not doc.open(path): raise ValueError(doc.last_error or '批次來源需要密碼或無法開啟。')
                if operation == 'png':
                    target = str(stem) + '_images'; Path(target).mkdir(exist_ok=True)
                    doc.exports.export_images(target, base=Path(path).stem)
                else:
                    target = str(stem) + {'optimize':'_opt', 'encrypt':'_enc', 'redact':'_redacted'}[operation] + '.pdf'
                    if operation == 'encrypt':
                        owner, user = params.get('owner_password', ''), params.get('user_password', '')
                        if not owner: raise ValueError('批次加密必須指定擁有者密碼，不能使用內建固定密碼。')
                        doc.security.encrypt(target, owner_pw=owner, user_pw=user)
                    elif operation == 'optimize': doc.optimize.optimize(target)
                    else:
                        doc.redaction.apply_all()
                        self._save(doc.fitz_doc, path, target)
            finally: doc.close()
        else: raise ValueError(f'未知操作：{operation}')
        return target
