import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.integration_bridge import inspect_pdf, integration_status, live_validate_pdf


def test_integration_status_exposes_versioned_local_contract():
    status = integration_status("1.0.18")
    assert status["ok"] is True
    assert status["protocol_version"] == 1
    assert status["locale"] == "zh-Hant-TW"
    assert {item["id"] for item in status["capabilities"]} >= {
        "pages", "forms", "ocr", "protect", "batch", "magi"
    }


def test_pdf_inspection_returns_structure_without_document_text(sample_pdf):
    report = inspect_pdf(sample_pdf, "1.0.18")
    assert report["file_name"] == "sample.pdf"
    assert report["pages"] == 3
    assert report["characters"] > 0
    assert report["text_pages"] == 3
    assert report["scanned_pages"] == 0
    assert "text" not in report
    assert report["protocol_version"] == 1


def test_pdf_live_validation_renders_and_roundtrips(sample_pdf):
    result = live_validate_pdf(sample_pdf, "1.0.18")
    assert result["passed"] is True
    assert result["protocol_version"] == 1
    assert result["engine_version"] == "1.0.18"
    assert result["rendered_pages"] == 2
    assert result["roundtrip_pages"] == 3
    assert result["roundtrip_bytes"] > 100
    assert len(result["render_sha256"]) == 64


def test_pdf_inspection_rejects_non_pdf(tmp_path):
    path = tmp_path / "not-pdf.txt"
    path.write_text("內容", encoding="utf-8")
    with pytest.raises(ValueError, match="只接受 PDF"):
        inspect_pdf(path)


def test_main_status_cli_does_not_start_qt():
    project = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(project / "main.py"), "--integration-status"],
        cwd=project,
        capture_output=True,
        text=True,
        check=True,
    )
    value = json.loads(result.stdout)
    assert value["ok"] is True
    assert value["app_version"] == "1.1.0"
