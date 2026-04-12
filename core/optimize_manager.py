# ~/Desktop/acropdf/core/optimize_manager.py
import fitz

class OptimizeManager:
    def __init__(self, doc):
        self._doc = doc

    @property
    def _fitz(self) -> fitz.Document:
        return self._doc.fitz_doc

    def optimize(self, output_path: str, compress_images: bool = True,
                 subset_fonts: bool = True, remove_metadata: bool = False,
                 linearize: bool = False, preset: int = 1):
        garbage_level = 2 if preset == 0 else 3 if preset == 1 else 4
        doc = fitz.open("pdf", self._fitz.tobytes(garbage=garbage_level, deflate=compress_images))
        try:
            if remove_metadata:
                doc.scrub()
            save_kwargs = {
                "garbage": garbage_level,
                "deflate": compress_images,
                "clean": True,
            }
            if linearize:
                save_kwargs["linear"] = True
            try:
                doc.save(output_path, **save_kwargs)
            except Exception as exc:
                if linearize and "Linearisation is no longer supported" in str(exc):
                    save_kwargs.pop("linear", None)
                    doc.save(output_path, **save_kwargs)
                else:
                    raise
        finally:
            doc.close()

    def compress(self, output_path: str, image_quality: int = 75):
        """壓縮圖片並儲存"""
        for i in range(self._fitz.page_count):
            page = self._fitz[i]
            for img in page.get_images():
                xref = img[0]
                try:
                    self._fitz.update_stream(
                        xref,
                        self._fitz.extract_image(xref)["image"],
                        compress=True
                    )
                except Exception:
                    pass
        self._fitz.save(
            output_path, garbage=4, deflate=True,
            clean=True, linear=False
        )

    def linearize(self, output_path: str):
        """線性化（適合 Web 快速瀏覽）"""
        self._fitz.save(output_path, linear=True, garbage=4, deflate=True)

    def scrub_metadata(self, output_path: str):
        """清除隱藏內容、中繼資料"""
        self._fitz.scrub()
        self._fitz.save(output_path, garbage=4, deflate=True, clean=True)

    def full_optimize(self, output_path: str):
        """一鍵全套最佳化"""
        self._fitz.scrub()
        self._fitz.save(
            output_path,
            garbage=4, deflate=True, clean=True,
            linear=True
        )
