import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from main import _AcroPDFApp


def test_command_line_open_failure_is_recorded(tmp_path, monkeypatch):
    monkeypatch.setenv("ACROPDF_APP_DATA_DIR", str(tmp_path))

    class FailedWindow:
        def open_file(self, path):
            raise RuntimeError("packaged dependency unavailable")

    # Exercise the callback without constructing a second QApplication.
    _AcroPDFApp._open_file_safe(SimpleNamespace(_main_window=FailedWindow()), "sample.pdf")
    record = json.loads((tmp_path / "Logs" / "crash.log").read_text())
    assert record["exception"] == "RuntimeError"
    assert record["message"] == "packaged dependency unavailable"
    assert "FailedWindow" not in record["message"]


@pytest.mark.skipif(sys.platform != "darwin", reason="native Cocoa image conversion")
def test_native_macos_app_icon():
    # Offscreen Qt skips the Cocoa conversion that triggered the startup SIGTRAP.
    result = subprocess.run(
        [sys.executable, "-c", """
from PyQt6.QtCore import qVersion
from PyQt6.QtWidgets import QApplication
from main import _set_app_icon
assert tuple(map(int, qVersion().split('.'))) >= (6, 11, 2), qVersion()
app = QApplication([])
_set_app_icon(app)
app.processEvents()
assert not app.windowIcon().isNull()
"""],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "QT_QPA_PLATFORM": "cocoa"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"exit={result.returncode}\n{result.stdout}\n{result.stderr}"
