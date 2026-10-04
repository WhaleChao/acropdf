import os
import sys
from pathlib import Path

import fitz
import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSettings
from app.config import Config

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Tests must never overwrite the user's theme, folders or recent files."""
    config = object.__new__(Config)
    config._settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    monkeypatch.setattr(Config, "_instance", config)
    monkeypatch.setenv("ACROPDF_RECOVERY_DIR", str(tmp_path / "recovery"))


@pytest.fixture()
def sample_pdf(tmp_path):
    path = tmp_path / "sample.pdf"
    doc = fitz.open()
    for i in range(3):
        page = doc.new_page()
        page.insert_text((72, 72), f"Sample page {i + 1}")
    doc.save(path)
    doc.close()
    return path
