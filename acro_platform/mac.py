# ~/Desktop/acropdf/platform/mac.py
"""
macOS Vision Framework OCR。
僅在 macOS 上使用，其他平台不會 import 此檔案。
"""
import fitz

class MacVisionOCR:
    name = "Apple Vision"

    def __init__(self):
        # 這些 import 只在 macOS 上成功，其他平台會 ImportError
        import Vision  # noqa: F401 — pyobjc-framework-Vision
        import Quartz  # noqa: F401 — pyobjc-framework-Quartz
        self._Vision = Vision
        self._Quartz = Quartz

    def is_available(self) -> bool:
        return True  # 既然 __init__ 成功就可用

    def ocr_page(self, page: fitz.Page, lang: str, dpi: int) -> None:
        """用 macOS Vision 辨識頁面文字，寫入 page 的 text layer"""
        import io
        from PIL import Image
        from Foundation import NSData

        # 1. 渲染頁面為圖片
        mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        png_bytes = pix.tobytes("png")

        # 2. 建立 Vision request
        ns_data = NSData.dataWithBytes_length_(png_bytes, len(png_bytes))
        ci_image = self._Quartz.CIImage.imageWithData_(ns_data)
        handler = self._Vision.VNImageRequestHandler.alloc().initWithCIImage_options_(
            ci_image, None
        )
        request = self._Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(self._Vision.VNRequestTextRecognitionLevelAccurate)

        # 設定語言（Vision 用 ISO 639-1 codes）
        lang_map = {
            "chi_tra": "zh-Hant", "chi_sim": "zh-Hans",
            "eng": "en", "jpn": "ja",
        }
        vision_langs = []
        for l in lang.split("+"):
            vision_langs.append(lang_map.get(l.strip(), l.strip()))
        request.setRecognitionLanguages_(vision_langs)
        request.setUsesLanguageCorrection_(True)

        # 3. 執行辨識
        success = handler.performRequests_error_([request], None)
        if not success[0]:
            return

        # 4. 提取結果並寫入 page 的透明文字層
        results = request.results()
        if not results:
            return

        page_rect = page.rect
        for observation in results:
            text = observation.topCandidates_(1)[0].string()
            bbox = observation.boundingBox()
            # Vision bbox: 原點左下角，正規化座標 [0,1]
            x0 = bbox.origin.x * page_rect.width
            y0 = (1.0 - bbox.origin.y - bbox.size.height) * page_rect.height
            x1 = (bbox.origin.x + bbox.size.width) * page_rect.width
            y1 = (1.0 - bbox.origin.y) * page_rect.height
            # 插入透明文字
            fontsize = max(6, min((y1 - y0) * 0.8, 14))
            try:
                page.insert_text(
                    fitz.Point(x0, y1 - 2),
                    text, fontsize=fontsize,
                    color=(0, 0, 0), render_mode=3,  # 3 = invisible
                )
            except Exception:
                pass

    def ocr_image_path(self, image_path: str, lang: str = "chi_tra+eng") -> str:
        """
        OCR 指定 PNG/JPG 路徑，回傳辨識文字字串（供 auto_label_engine 使用）。
        不寫入 PDF，純回傳文字。
        """
        try:
            from Foundation import NSData
            with open(image_path, "rb") as f:
                png_bytes = f.read()

            ns_data = NSData.dataWithBytes_length_(png_bytes, len(png_bytes))
            ci_image = self._Quartz.CIImage.imageWithData_(ns_data)
            handler = self._Vision.VNImageRequestHandler.alloc().initWithCIImage_options_(
                ci_image, None
            )
            request = self._Vision.VNRecognizeTextRequest.alloc().init()
            request.setRecognitionLevel_(self._Vision.VNRequestTextRecognitionLevelAccurate)

            lang_map = {
                "chi_tra": "zh-Hant", "chi_sim": "zh-Hans",
                "eng": "en", "jpn": "ja",
            }
            vision_langs = [lang_map.get(l.strip(), l.strip()) for l in lang.split("+")]
            request.setRecognitionLanguages_(vision_langs)
            request.setUsesLanguageCorrection_(True)

            success = handler.performRequests_error_([request], None)
            if not success[0]:
                return ""

            results = request.results()
            if not results:
                return ""

            lines = []
            for obs in results:
                cands = obs.topCandidates_(1)
                if cands:
                    lines.append(cands[0].string())
            return "\n".join(lines)
        except Exception:
            return ""

    def supported_languages(self) -> list[str]:
        try:
            request = self._Vision.VNRecognizeTextRequest.alloc().init()
            langs = request.supportedRecognitionLanguagesAndReturnError_(None)
            return list(langs[0]) if langs and langs[0] else ["en"]
        except Exception:
            return ["en", "zh-Hant", "zh-Hans", "ja"]
