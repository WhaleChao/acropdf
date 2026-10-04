"""Atomic file publication shared by conversion and batch workflows."""
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile


@contextmanager
def atomic_output(destination, *, source=None, overwrite=False):
    target = Path(destination).expanduser().absolute()
    if source and os.path.realpath(source) == os.path.realpath(target):
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
            os.link(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
