"""Optimize a private copy; preserve content, encryption and the original document."""
import tempfile
from pathlib import Path
import fitz
from core.file_io import atomic_output


class OptimizeManager:
    def __init__(self, doc): self._doc = doc

    @property
    def _fitz(self): return self._doc.fitz_doc

    def _clone(self):
        if self._fitz is None: raise RuntimeError('尚未載入文件')
        doc = fitz.open('pdf', self._doc._snapshot())
        if doc.needs_pass and not doc.authenticate(self._doc._password):
            doc.close(); raise ValueError('無法認證最佳化快照。')
        if any(w.field_type == fitz.PDF_WIDGET_TYPE_SIGNATURE and w.is_signed for p in doc for w in p.widgets() or ()):
            doc.close(); raise ValueError('最佳化會改寫已簽署文件，請先取得未簽署副本。')
        return doc

    @staticmethod
    def _remove_metadata(doc):
        doc.set_metadata({}); doc.del_xml_metadata()
        for page in doc: doc.xref_set_key(page.xref, 'Thumb', 'null')

    def _save(self, doc, output_path, linearize=False):
        with atomic_output(output_path, source=self._doc.source_path) as temporary:
            if linearize:
                import pikepdf
                with tempfile.TemporaryDirectory(dir=temporary.parent) as stage:
                    intermediary = Path(stage) / 'optimized.pdf'
                    doc.save(intermediary, garbage=4, deflate=True, encryption=fitz.PDF_ENCRYPT_KEEP)
                    with pikepdf.open(intermediary, password=self._doc._password) as pdf:
                        pdf.save(temporary, linearize=True, encryption=True if pdf.is_encrypted else None)
            else:
                doc.save(temporary, garbage=4, deflate=True, encryption=fitz.PDF_ENCRYPT_KEEP)

    def optimize(self, output_path, compress_images=True, subset_fonts=True,
                 remove_metadata=False, linearize=False, preset=1):
        if preset not in (0, 1, 2): raise ValueError('壓縮等級無效。')
        with self._clone() as doc:
            if compress_images:
                target, quality = ((300, 95), (200, 85), (150, 70))[preset]
                doc.rewrite_images(dpi_threshold=int(target * 1.25), dpi_target=target, quality=quality)
            if subset_fonts: doc.subset_fonts()
            if remove_metadata: self._remove_metadata(doc)
            self._save(doc, output_path, linearize)
        return output_path

    def compress(self, output_path, image_quality=75):
        if not 1 <= image_quality <= 100: raise ValueError('圖片品質須介於 1 與 100。')
        with self._clone() as doc:
            doc.rewrite_images(quality=image_quality)
            self._save(doc, output_path)
        return output_path

    def linearize(self, output_path):
        with self._clone() as doc: self._save(doc, output_path, True)
        return output_path

    def scrub_metadata(self, output_path):
        with self._clone() as doc:
            self._remove_metadata(doc); self._save(doc, output_path)
        return output_path

    def full_optimize(self, output_path):
        return self.optimize(output_path, remove_metadata=True, linearize=True)
