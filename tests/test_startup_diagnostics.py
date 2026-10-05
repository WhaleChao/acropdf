import json
from types import SimpleNamespace

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
