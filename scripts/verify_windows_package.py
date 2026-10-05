"""Verify the Windows EXE, silent installation, PDF engine and GUI startup.

Run on a disposable Windows build runner. Uses only generated test documents.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import time

import fitz

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def assert_pe(path):
    with path.open("rb") as stream:
        assert stream.read(2) == b"MZ", path
        stream.seek(0x3C)
        offset = struct.unpack("<I", stream.read(4))[0]
        stream.seek(offset)
        assert stream.read(4) == b"PE\0\0", path


def gui_loaded_sample(state, sample):
    """Compare filesystem identity: Windows may report an 8.3 path alias."""
    try:
        recorded = json.loads(state.read_text(encoding="utf-8"))["current_file"]
        return bool(recorded) and os.path.samefile(recorded, sample)
    except (OSError, ValueError, KeyError, TypeError):
        # Poll again when the state file is missing or being written.
        return False


def contract(exe, sample, scratch, version):
    results = {}
    for flag, key in (("--integration-status", "status"), ("--integration-live-test", "live")):
        output = scratch / f"{key}.json"
        output.unlink(missing_ok=True)
        args = [str(exe), flag]
        if key == "live":
            args.append(str(sample))
        subprocess.run([*args, "--integration-output", str(output)], check=True, timeout=90)
        result = json.loads(output.read_text(encoding="utf-8"))
        if key == "status":
            assert result["ok"] and result["app_version"] == version
        else:
            assert result["passed"] and result["engine_version"] == version
            assert result["roundtrip_pages"] == 3 and result["rendered_pages"] == 2
        results[key] = result
    # A real invalid-PDF invocation must fail, including in a windowed EXE.
    error = scratch / "error.json"
    result = subprocess.run([str(exe), "--integration-inspect", str(scratch / "missing.pdf"),
                             "--integration-output", str(error)], timeout=90)
    assert result.returncode == 1 and not json.loads(error.read_text(encoding="utf-8"))["ok"]
    return results


def main():
    assert os.name == "nt", "Run on Windows"
    version = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', (ROOT / "main.py").read_text(encoding="utf-8"))[1]
    exe = DIST / "AcroPDF" / "AcroPDF.exe"
    installer = DIST / "AcroPDF_Setup.exe"
    assert (DIST / "AcroPDF" / "_internal" / "THIRD_PARTY_NOTICES.md").is_file()
    assert (DIST / "AcroPDF" / "_internal" / "resources" / "third-party" / "manifest.json").is_file()
    report = {"version": version, "source_commit": os.environ.get("GITHUB_SHA"), "checksums": {}}
    for path in (exe, installer):
        assert_pe(path)
    for name in ("AcroPDF_win.zip", "AcroPDF_Setup.exe"):
        path = DIST / name
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert (DIST / f"{name}.sha256").read_text(encoding="utf-8").split()[0] == digest
        report["checksums"][name] = digest
    with tempfile.TemporaryDirectory(prefix="acropdf_package_") as folder:
        scratch = Path(folder)
        sample = scratch / "sample.pdf"
        with fitz.open() as doc:
            for index in range(3):
                doc.new_page().insert_text((72, 72), f"Package validation page {index + 1}")
            doc.save(sample)
        original = hashlib.sha256(sample.read_bytes()).hexdigest()
        report["portable"] = contract(exe, sample, scratch, version)
        installed = scratch / "installed"
        subprocess.run([str(installer), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
                        "/TASKS=", f"/DIR={installed}", f"/LOG={scratch / 'install.log'}"],
                       check=True, timeout=180)
        installed_exe = installed / "AcroPDF.exe"
        assert installed_exe.read_bytes() == exe.read_bytes()
        report["installed"] = contract(installed_exe, sample, scratch, version)
        env = os.environ.copy()
        env.pop("QT_QPA_PLATFORM", None)
        env["ACROPDF_RECOVERY_DIR"] = str(scratch / "recovery")
        env["ACROPDF_STATE_FILE"] = str(scratch / "state.json")
        env["ACROPDF_APP_DATA_DIR"] = str(scratch / "diagnostics")
        process = subprocess.Popen([str(installed_exe), str(sample)], env=env)
        try:
            deadline = time.monotonic() + 30
            state = scratch / "state.json"
            while time.monotonic() < deadline:
                assert process.poll() is None, "Installed GUI exited unexpectedly"
                if gui_loaded_sample(state, sample):
                    break
                time.sleep(0.5)
            else:
                raise AssertionError("Installed GUI did not open the sample PDF")
            time.sleep(3)
            assert process.poll() is None, "Installed GUI crashed after loading PDF"
            report["installed_gui_opened_pdf"] = True
            report["gui_document_identity"] = {
                "requested": str(sample),
                "reported": json.loads(state.read_text(encoding="utf-8"))["current_file"],
                "samefile": True,
            }
        except Exception:
            # Preserve startup evidence before the disposable directory is removed.
            for log in (scratch / "diagnostics" / "Logs").glob("*.log"):
                print(f"GUI diagnostic {log.name}: {log.read_text(encoding='utf-8')}")
            print(f"GUI state: {state.read_text(encoding='utf-8') if state.exists() else 'missing'}; exit code: {process.poll()}")
            raise
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=30)
        assert hashlib.sha256(sample.read_bytes()).hexdigest() == original
        report["source_pdf_unchanged"] = True
        uninstall = installed / "unins000.exe"
        subprocess.run([str(uninstall), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], check=True, timeout=90)
        assert not installed_exe.exists()
        report["silent_install_uninstall_passed"] = True
    report["passed"] = True
    report["limitations"] = ["No Authenticode certificate", "GUI startup smoke test only; physical printer and assistive technology require device testing"]
    (DIST / "windows-package-validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"version": version, "passed": True, "checksums": report["checksums"]}))


if __name__ == "__main__":
    main()
