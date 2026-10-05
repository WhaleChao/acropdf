"""Atomic file publication shared by conversion and batch workflows."""
from contextlib import contextmanager
import os
import sys
from pathlib import Path
import tempfile


def publish_exclusive(temporary, target):
    """Publish atomically without replacing a file created by another process."""
    if sys.platform == 'darwin':
        # Hard-link publication can block in macOS protected/file-provider folders.
        # RENAME_EXCL preserves the no-overwrite guarantee without a hard link.
        import ctypes
        rename = ctypes.CDLL(None, use_errno=True).renamex_np
        rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(os.fsencode(temporary), os.fsencode(target), 0x00000004):
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), str(target))
    elif os.name == 'nt':
        # Windows rename refuses an existing destination.
        os.rename(temporary, target)
    else:
        os.link(temporary, target)


@contextmanager
def atomic_output(destination, *, source=None, overwrite=False):
    target = Path(destination).expanduser().absolute()
    if source:
        aliases = os.path.realpath(source) == os.path.realpath(target)
        if not aliases and os.path.exists(source) and target.exists():
            aliases = os.path.samefile(source, target)
        if aliases:
            raise ValueError("輸出不能覆寫目前的來源檔案。")
    if not target.parent.is_dir():
        raise FileNotFoundError(f"輸出資料夾不存在：{target.parent}")
    if target.exists() and not overwrite:
        raise FileExistsError(f"輸出檔案已存在：{target}")
    handle, name = tempfile.mkstemp(prefix='.acropdf_', suffix=target.suffix, dir=target.parent)
    os.close(handle)
    temporary = Path(name)
    try:
        yield temporary
        if not temporary.stat().st_size:
            raise ValueError("輸出為空，未發佈檔案。")
        with temporary.open('rb') as stream:
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, target)
        else:
            publish_exclusive(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
