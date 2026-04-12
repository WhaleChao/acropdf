"""
清理 AcroPDF 產生的暫存檔。
"""
from __future__ import annotations

import glob
import os
import shutil
import tempfile
import time


def cleanup_temp_files(max_age_hours: int = 24) -> int:
    """清理超過 max_age_hours 的 AcroPDF 暫存檔案或目錄。"""
    tmp_dir = tempfile.gettempdir()
    patterns = ["acropdf_*.pdf", "acropdf_lo_*", "acropdf_ocr_*", "acropdf_slide_*"]
    now = time.time()
    cutoff = now - (max_age_hours * 3600)
    cleaned = 0

    for pattern in patterns:
        for path in glob.glob(os.path.join(tmp_dir, pattern)):
            try:
                if os.path.getmtime(path) >= cutoff:
                    continue
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    os.unlink(path)
                cleaned += 1
            except OSError:
                continue
    return cleaned
