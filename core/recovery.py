"""Private, atomic recovery snapshots. Originals are never autosaved over."""
import hashlib
import json
import os
import tempfile
import time
import math
import uuid
from pathlib import Path

from PyQt6.QtCore import QStandardPaths


def _secure_windows_directory(path):
    """Protect the recovery DACL on Python versions where mkdir mode is ignored."""
    import ctypes
    from ctypes import wintypes
    import re
    import subprocess
    identity = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'],
                              capture_output=True, check=True, timeout=10,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    match = re.search(rb'"(S-\d+(?:-\d+)+)"', identity.stdout)
    if not match:
        raise OSError('無法取得恢復資料夾的使用者身分。')
    sid = match[1].decode('ascii')
    descriptor_text = f'D:P(A;OICI;FA;;;{sid})(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)'
    api = ctypes.WinDLL('advapi32', use_last_error=True)
    convert = api.ConvertStringSecurityDescriptorToSecurityDescriptorW
    convert.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.DWORD)]
    convert.restype = wintypes.BOOL
    set_security = api.SetFileSecurityW
    set_security.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
    set_security.restype = wintypes.BOOL
    descriptor = ctypes.c_void_p()
    if not convert(descriptor_text, 1, ctypes.byref(descriptor), None):
        raise ctypes.WinError(ctypes.get_last_error())
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    try:
        if not set_security(str(path.resolve()), 0x80000004, descriptor):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.LocalFree(descriptor)


class RecoveryStore:
    def __init__(self, directory=None):
        default = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)) / "recovery"
        self.directory = Path(directory or os.environ.get("ACROPDF_RECOVERY_DIR") or default)
        self._directory_secured = False

    def _write(self, path, data):
        existed = self.directory.is_dir()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not self._directory_secured or not existed:
            if os.name == 'nt':
                _secure_windows_directory(self.directory)
            else:
                self.directory.chmod(0o700)
            self._directory_secured = True
        fd, temporary = tempfile.mkstemp(prefix=".writing_", dir=self.directory)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data); handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)

    def capture(self, doc):
        if not doc.is_modified or doc.fitz_doc is None:
            return
        if not hasattr(doc, "_recovery_id"):
            doc._recovery_id = uuid.uuid4().hex
        identity = doc._recovery_id
        data = doc._snapshot()  # encrypted PDFs remain encrypted
        filename = identity + "_" + uuid.uuid4().hex + ".pdf"
        metadata = {"id": identity, "file": filename, "source": doc.source_path,
                    "name": doc.display_name, "timestamp": time.time(),
                    "sha256": hashlib.sha256(data).hexdigest()}
        self._write(self.directory / filename, data)
        self._write(self.directory / (identity + ".json"), json.dumps(metadata, ensure_ascii=False).encode("utf-8"))
        for old in self.directory.glob(identity + "_*.pdf"):
            if old.name != filename: old.unlink(missing_ok=True)

    def entries(self):
        if not self.directory.exists(): return []
        results = []
        for path in self.directory.glob("*.json"):
            try:
                metadata = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(metadata.get("timestamp"), (int, float)) or not math.isfinite(metadata["timestamp"]): continue
                if metadata.get("source") is not None and not isinstance(metadata["source"], str): continue
                if not isinstance(metadata.get("name"), str) or not isinstance(metadata.get("sha256"), str): continue
                if metadata["id"] != path.stem or len(path.stem) != 32 or any(c not in "0123456789abcdef" for c in path.stem): continue
                filename = metadata["file"]
                if Path(filename).name != filename or not filename.startswith(path.stem + "_"): continue
                if not (self.directory / filename).is_file(): continue
                results.append(metadata)
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return sorted(results, key=lambda entry: entry["timestamp"], reverse=True)

    def restore(self, entry, parent=None, password=""):
        from core.document import PDFDocument
        if entry not in self.entries():
            raise ValueError("恢復紀錄無效。")
        path = self.directory / entry["file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError("恢復檔案校驗失敗，請保留原檔並檢查磁碟。")
        doc = PDFDocument(parent)
        if not doc.open(str(path), password):
            return None
        doc._path = None  # restoration always asks for a Save As destination
        doc._source_path = entry.get("source")
        doc._modified = True
        doc._recovery_id = entry["id"]
        return doc

    def remove(self, doc_or_entry):
        identity = doc_or_entry.get("id") if isinstance(doc_or_entry, dict) else getattr(doc_or_entry, "_recovery_id", None)
        if not identity or len(identity) != 32 or any(c not in "0123456789abcdef" for c in identity): return
        for path in self.directory.glob(identity + "_*.pdf"):
            try: path.unlink(missing_ok=True)
            except OSError: pass
        try: (self.directory / (identity + ".json")).unlink(missing_ok=True)
        except OSError: pass
