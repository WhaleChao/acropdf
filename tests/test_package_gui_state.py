import json
import os

import pytest

from scripts.verify_windows_package import gui_loaded_sample


def test_gui_state_accepts_alias_to_the_same_file(tmp_path):
    sample = tmp_path / "sample.pdf"
    sample.write_bytes(b"sample")
    alias = tmp_path / "alias.pdf"
    os.link(sample, alias)
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"current_file": str(alias)}))
    assert gui_loaded_sample(state, sample)


def test_gui_state_rejects_a_different_file(tmp_path):
    sample = tmp_path / "sample.pdf"
    other = tmp_path / "other.pdf"
    sample.write_bytes(b"same bytes")
    other.write_bytes(sample.read_bytes())
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"current_file": str(other)}))
    assert not gui_loaded_sample(state, sample)


@pytest.mark.parametrize("contents", [None, "{", '{"current_file":""}', '{}'])
def test_gui_state_retries_missing_or_incomplete_state(tmp_path, contents):
    state = tmp_path / "state.json"
    if contents is not None:
        state.write_text(contents)
    assert not gui_loaded_sample(state, tmp_path / "sample.pdf")
