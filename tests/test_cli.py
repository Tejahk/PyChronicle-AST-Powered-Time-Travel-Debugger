"""Tests for src.cli."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.cli import main  # noqa: E402

SAMPLE = '''def greet(name):
    if name:
        return "hi " + name
    return "hi"
'''

SAMPLE_V2 = '''def greet(name):
    if name:
        return "hi " + name
    return "hi"


def farewell(name):
    return "bye " + name
'''

BROKEN = "def broken(:\n    pass\n"


@pytest.fixture()
def sample_file(tmp_path):
    path = tmp_path / "sample.py"
    path.write_text(SAMPLE, encoding="utf-8")
    return path


@pytest.fixture()
def two_version_history(sample_file, tmp_path):
    history_path = tmp_path / "history.json"
    main(["record", str(sample_file), "--history", str(history_path), "--label", "v1"])
    sample_file.write_text(SAMPLE_V2, encoding="utf-8")
    main(["record", str(sample_file), "--history", str(history_path), "--label", "v2"])
    return history_path


# --------------------------------------------------------------------------- #
# analyze
# --------------------------------------------------------------------------- #
def test_analyze_prints_summary(sample_file, capsys):
    code = main(["analyze", str(sample_file)])
    out = capsys.readouterr().out
    assert code == 0
    assert "Functions: 1" in out
    assert "greet: 2" in out


def test_analyze_missing_file(tmp_path, capsys):
    code = main(["analyze", str(tmp_path / "nope.py")])
    captured = capsys.readouterr()
    assert code == 1
    assert "not found" in captured.err.lower()


def test_analyze_syntax_error(tmp_path, capsys):
    path = tmp_path / "broken.py"
    path.write_text(BROKEN, encoding="utf-8")
    code = main(["analyze", str(path)])
    captured = capsys.readouterr()
    assert code == 1
    assert "Error:" in captured.err


# --------------------------------------------------------------------------- #
# record / timeline
# --------------------------------------------------------------------------- #
def test_record_creates_new_history(sample_file, tmp_path, capsys):
    history_path = tmp_path / "history.json"
    code = main(["record", str(sample_file), "--history", str(history_path), "--label", "v1"])
    out = capsys.readouterr().out
    assert code == 0
    assert history_path.exists()
    assert "Recorded 'v1'" in out

    data = json.loads(history_path.read_text(encoding="utf-8"))
    assert data["snapshots"][0]["label"] == "v1"


def test_record_appends_to_existing_history(sample_file, tmp_path):
    history_path = tmp_path / "history.json"
    main(["record", str(sample_file), "--history", str(history_path), "--label", "v1"])

    sample_file.write_text(SAMPLE_V2, encoding="utf-8")
    main(["record", str(sample_file), "--history", str(history_path), "--label", "v2"])

    data = json.loads(history_path.read_text(encoding="utf-8"))
    assert [s["label"] for s in data["snapshots"]] == ["v1", "v2"]


def test_record_duplicate_label_errors(sample_file, tmp_path, capsys):
    history_path = tmp_path / "history.json"
    main(["record", str(sample_file), "--history", str(history_path), "--label", "v1"])
    code = main(["record", str(sample_file), "--history", str(history_path), "--label", "v1"])
    captured = capsys.readouterr()
    assert code == 1
    assert "already exists" in captured.err


def test_record_missing_file(tmp_path, capsys):
    history_path = tmp_path / "history.json"
    code = main(["record", str(tmp_path / "nope.py"), "--history", str(history_path)])
    captured = capsys.readouterr()
    assert code == 1
    assert "not found" in captured.err.lower()


def test_record_syntax_error_file(tmp_path, capsys):
    bad = tmp_path / "broken.py"
    bad.write_text(BROKEN, encoding="utf-8")
    history_path = tmp_path / "history.json"
    code = main(["record", str(bad), "--history", str(history_path)])
    captured = capsys.readouterr()
    assert code == 1
    assert "Error:" in captured.err
    assert not history_path.exists()


def test_timeline_lists_snapshots(sample_file, tmp_path, capsys):
    history_path = tmp_path / "history.json"
    main(["record", str(sample_file), "--history", str(history_path), "--label", "v1"])
    code = main(["timeline", "--history", str(history_path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "v1" in out


def test_timeline_missing_history_file(tmp_path, capsys):
    code = main(["timeline", "--history", str(tmp_path / "nope.json")])
    captured = capsys.readouterr()
    assert code == 1
    assert "not found" in captured.err.lower()


# --------------------------------------------------------------------------- #
# diff
# --------------------------------------------------------------------------- #
def test_diff_summary(two_version_history, capsys):
    code = main(["diff", "--history", str(two_version_history), "--from", "v1", "--to", "v2"])
    out = capsys.readouterr().out
    assert code == 0
    assert "Added functions: farewell" in out


def test_diff_full_includes_line_diff(two_version_history, capsys):
    code = main(
        ["diff", "--history", str(two_version_history), "--from", "v1", "--to", "v2", "--full"]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "+def farewell(name):" in out


def test_diff_default_refs(two_version_history, capsys):
    code = main(["diff", "--history", str(two_version_history)])
    out = capsys.readouterr().out
    assert code == 0
    assert "v1 -> v2" in out


def test_diff_unknown_ref_errors(two_version_history, capsys):
    code = main(["diff", "--history", str(two_version_history), "--from", "nope"])
    captured = capsys.readouterr()
    assert code == 1
    assert "Error:" in captured.err


# --------------------------------------------------------------------------- #
# checkout
# --------------------------------------------------------------------------- #
def test_checkout_prints_source(two_version_history, capsys):
    code = main(["checkout", "--history", str(two_version_history), "--ref", "v1"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.strip() == SAMPLE.strip()


def test_checkout_writes_file(two_version_history, tmp_path, capsys):
    out_path = tmp_path / "restored.py"
    code = main(
        ["checkout", "--history", str(two_version_history), "--ref", "v1", "--out", str(out_path)]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert out_path.read_text(encoding="utf-8") == SAMPLE
    assert "Wrote snapshot" in captured.out


def test_checkout_by_index(two_version_history, capsys):
    code = main(["checkout", "--history", str(two_version_history), "--ref", "0"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.strip() == SAMPLE.strip()


def test_checkout_unknown_ref(two_version_history, capsys):
    code = main(["checkout", "--history", str(two_version_history), "--ref", "nope"])
    captured = capsys.readouterr()
    assert code == 1
    assert "Error:" in captured.err


# --------------------------------------------------------------------------- #
# trend
# --------------------------------------------------------------------------- #
def test_trend_shows_each_snapshot(two_version_history, capsys):
    code = main(["trend", "--history", str(two_version_history), "--function", "greet"])
    out = capsys.readouterr().out
    assert code == 0
    assert "v1" in out and "v2" in out


def test_trend_missing_function_shows_dash(two_version_history, capsys):
    code = main(["trend", "--history", str(two_version_history), "--function", "does_not_exist"])
    out = capsys.readouterr().out
    assert code == 0
    assert "-" in out


# --------------------------------------------------------------------------- #
# argparse-level behaviour
# --------------------------------------------------------------------------- #
def test_no_command_exits_nonzero():
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code != 0


def test_unknown_command_exits_nonzero():
    with pytest.raises(SystemExit):
        main(["bogus-command"])