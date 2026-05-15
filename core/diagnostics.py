from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import traceback
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APP_NAME = "AcroPDF"
APP_PUBLISHER = "WhaleChao"


def app_data_dir() -> Path:
    override = os.environ.get("ACROPDF_APP_DATA_DIR")
    if override:
        return Path(override)
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
        return base / APP_PUBLISHER / APP_NAME
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / APP_NAME


def logs_dir() -> Path:
    path = app_data_dir() / "Logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def crash_log_path() -> Path:
    return logs_dir() / "crash.log"


def runtime_log_path() -> Path:
    return logs_dir() / "runtime.log"


def install_excepthook(version: str) -> None:
    original_hook = sys.excepthook

    def _hook(exc_type, exc, tb):
        record_exception(exc_type, exc, tb, version)
        original_hook(exc_type, exc, tb)

    sys.excepthook = _hook


def record_exception(exc_type, exc, tb, version: str) -> None:
    payload = {
        "timestamp": _now(),
        "version": version,
        "exception": getattr(exc_type, "__name__", str(exc_type)),
        "message": str(exc),
        "traceback": "".join(traceback.format_exception(exc_type, exc, tb)),
        "platform": _platform_info(),
    }
    path = crash_log_path()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def write_runtime_event(event: str, **extra: Any) -> None:
    payload = {"timestamp": _now(), "event": event, **extra}
    path = runtime_log_path()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def export_diagnostics(target_zip: str | os.PathLike[str], version: str) -> Path:
    target = Path(target_zip)
    target.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "created_at": _now(),
        "app": APP_NAME,
        "publisher": APP_PUBLISHER,
        "version": version,
        "platform": _platform_info(),
        "paths": {
            "app_data_dir": str(app_data_dir()),
            "logs_dir": str(logs_dir()),
        },
    }

    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("diagnostics.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for path in logs_dir().glob("*.log"):
            zf.write(path, f"logs/{path.name}")
    return target


def default_diagnostics_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path.home() / "Desktop" / f"AcroPDF-diagnostics-{stamp}.zip"


def cleanup_old_logs(max_bytes: int = 2_000_000) -> None:
    for path in (runtime_log_path(), crash_log_path()):
        try:
            if path.exists() and path.stat().st_size > max_bytes:
                backup = path.with_suffix(path.suffix + ".1")
                shutil.move(str(path), str(backup))
        except OSError:
            pass


def _platform_info() -> dict[str, str]:
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "frozen": str(bool(getattr(sys, "frozen", False))),
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
