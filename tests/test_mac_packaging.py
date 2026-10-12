import sys
from pathlib import Path

import pytest

import build_mac


@pytest.mark.skipif(sys.platform == "win32", reason="macOS framework symlink staging")
def test_dmg_staging_preserves_signed_framework_links(tmp_path, monkeypatch):
    app = tmp_path / "AcroPDF.app"
    framework = app / "Contents/Frameworks/Python.framework"
    version = framework / "Versions/3.14"
    version.mkdir(parents=True)
    (version / "Python").write_bytes(b"framework binary")
    (framework / "Versions/Current").symlink_to("3.14", target_is_directory=True)
    (framework / "Python").symlink_to("Versions/Current/Python")
    dist = tmp_path / "dist"
    dist.mkdir()
    monkeypatch.setattr(build_mac, "BASE", tmp_path)
    monkeypatch.setattr(build_mac, "DIST", dist)
    monkeypatch.setattr(build_mac.shutil, "which", lambda name: None)
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command[0])
        staged = dist / "_dmg_staging/AcroPDF.app/Contents/Frameworks/Python.framework"
        assert (staged / "Versions/Current").is_symlink()
        assert (staged / "Python").is_symlink()
        assert (staged / "Python").read_bytes() == b"framework binary"
        if command[0] == "hdiutil":
            Path(command[-1]).write_bytes(b"verified image fixture")

    monkeypatch.setattr(build_mac, "run", fake_run)
    build_mac._make_dmg(app)
    assert commands == ["codesign", "hdiutil"]
    assert (dist / "AcroPDF.dmg.sha256").is_file()
