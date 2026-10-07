"""Tests for src.time_travel."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.ast_parser import ASTParseError  # noqa: E402
from src.time_travel import (  # noqa: E402
    ChangeReport,
    SnapshotNotFoundError,
    TimeTravel,
)

V1 = '''import os


def greet(name):
    return "hi " + name


class Greeter:
    def hello(self):
        return "hello"
'''

V2 = '''import os
import sys
from collections import OrderedDict


def greet(name):
    if name:
        return "hi " + name
    return "hi"


def farewell(name):
    return "bye " + name


class Greeter:
    def hello(self):
        if True:
            return "hello"
        return "x"

    def wave(self):
        return "wave"
'''

V3 = '''import os


def greet(name):
    return "hi " + name


class Dog:
    def hello(self):
        return "woof"
'''


@pytest.fixture()
def tt():
    history = TimeTravel("demo")
    history.record(V1, label="v1", timestamp="2026-01-01T00:00:00+00:00")
    history.record(V2, label="v2", timestamp="2026-01-02T00:00:00+00:00")
    history.record(V3, label="v3", timestamp="2026-01-03T00:00:00+00:00")
    return history


# --------------------------------------------------------------------------- #
# recording
# --------------------------------------------------------------------------- #
def test_record_analyzes_source():
    history = TimeTravel()
    snap = history.record(V1)
    assert snap.label == "v1"
    assert snap.index == 0
    assert snap.total_lines == len(V1.splitlines())
    assert snap.functions == {"greet": 1, "Greeter.hello": 1}
    assert snap.classes == ["Greeter"]
    assert snap.imports == ["os"]
    assert len(snap.source_hash) == 64


def test_auto_labels_increment():
    history = TimeTravel()
    history.record(V1)
    history.record(V2)
    assert history.labels() == ["v1", "v2"]


def test_auto_label_skips_existing_custom_label():
    history = TimeTravel()
    history.record(V1, label="v2")
    snap = history.record(V2)
    assert snap.label == "v3"


def test_identical_consecutive_source_is_not_recorded_twice():
    history = TimeTravel()
    first = history.record(V1)
    again = history.record(V1, label="ignored")
    assert len(history) == 1
    assert again is first


def test_allow_duplicate_records_again():
    history = TimeTravel()
    history.record(V1)
    history.record(V1, allow_duplicate=True)
    assert len(history) == 2


def test_duplicate_label_rejected():
    history = TimeTravel()
    history.record(V1, label="a")
    with pytest.raises(ValueError):
        history.record(V2, label="a")


def test_empty_label_rejected():
    with pytest.raises(ValueError):
        TimeTravel().record(V1, label="   ")


def test_non_string_source_rejected():
    with pytest.raises(TypeError):
        TimeTravel().record(123)


def test_syntax_error_does_not_pollute_history():
    history = TimeTravel()
    history.record(V1)
    with pytest.raises(ASTParseError):
        history.record("def broken(:\n    pass\n")
    assert len(history) == 1


def test_record_file(tmp_path):
    path = tmp_path / "mod.py"
    path.write_text(V1, encoding="utf-8")
    history = TimeTravel()
    snap = history.record_file(str(path), label="from-disk")
    assert snap.label == "from-disk"
    assert "greet" in snap.functions


# --------------------------------------------------------------------------- #
# retrieval / checkout
# --------------------------------------------------------------------------- #
def test_get_by_index_negative_and_label(tt):
    assert tt.get(0).label == "v1"
    assert tt.get(-1).label == "v3"
    assert tt.get("v2").label == "v2"


def test_get_missing_raises(tt):
    with pytest.raises(SnapshotNotFoundError):
        tt.get(10)
    with pytest.raises(SnapshotNotFoundError):
        tt.get("nope")


def test_get_bad_type_raises(tt):
    with pytest.raises(TypeError):
        tt.get(1.5)
    with pytest.raises(TypeError):
        tt.get(True)


def test_get_on_empty_history_raises():
    with pytest.raises(SnapshotNotFoundError):
        TimeTravel().get(-1)


def test_checkout_returns_exact_source(tt):
    assert tt.checkout("v1") == V1
    assert tt.checkout(1) == V2


def test_checkout_writes_file(tt, tmp_path):
    target = tmp_path / "restored.py"
    tt.checkout("v1", path=str(target))
    assert target.read_text(encoding="utf-8") == V1


# --------------------------------------------------------------------------- #
# diff
# --------------------------------------------------------------------------- #
def test_diff_v1_to_v2(tt):
    report = tt.diff("v1", "v2")
    assert isinstance(report, ChangeReport)
    assert report.added_functions == ["Greeter.wave", "farewell"]
    assert report.removed_functions == []
    assert report.complexity_changes == {"Greeter.hello": (1, 2), "greet": (1, 2)}
    assert report.added_imports == ["collections.OrderedDict", "sys"]
    assert report.removed_imports == []
    assert report.added_classes == []
    assert report.lines_delta == len(V2.splitlines()) - len(V1.splitlines())
    assert report.has_changes and report.has_structural_changes
    assert "+def farewell(name):" in report.diff_text


def test_diff_v2_to_v3_removals_and_class_swap(tt):
    report = tt.diff("v2", "v3")
    assert "farewell" in report.removed_functions
    assert "Greeter.hello" in report.removed_functions
    assert "Dog.hello" in report.added_functions
    assert report.added_classes == ["Dog"]
    assert report.removed_classes == ["Greeter"]
    assert report.removed_imports == ["collections.OrderedDict", "sys"]


def test_diff_defaults_to_previous_vs_latest(tt):
    report = tt.diff()
    assert (report.from_label, report.to_label) == ("v2", "v3")


def test_diff_with_only_from_ref_compares_to_latest(tt):
    report = tt.diff("v1")
    assert (report.from_label, report.to_label) == ("v1", "v3")


def test_diff_needs_two_snapshots():
    history = TimeTravel()
    history.record(V1)
    with pytest.raises(SnapshotNotFoundError):
        history.diff()


def test_diff_identical_reports_no_changes():
    history = TimeTravel()
    history.record(V1, label="a")
    history.record(V1, label="b", allow_duplicate=True)
    report = history.diff("a", "b")
    assert not report.has_changes
    assert not report.has_structural_changes
    assert "No changes." in report.summary()


def test_diff_comment_only_change_is_text_not_structural():
    history = TimeTravel()
    history.record(V1, label="a")
    history.record(V1 + "# just a comment\n", label="b")
    report = history.diff("a", "b")
    assert report.has_changes
    assert not report.has_structural_changes
    assert "structure unchanged" in report.summary()


def test_diff_handles_source_without_trailing_newline():
    history = TimeTravel()
    history.record("x = 1", label="a")
    history.record("x = 1\ny = 2", label="b")
    report = history.diff("a", "b")
    assert "+y = 2\n" in report.diff_text


def test_summary_text_mentions_key_facts(tt):
    text = tt.diff("v1", "v2").summary()
    assert "Changes: v1 -> v2" in text
    assert "Added functions: Greeter.wave, farewell" in text
    assert "greet: 1 -> 2 (+1)" in text
    assert "Added imports: collections.OrderedDict, sys" in text


# --------------------------------------------------------------------------- #
# trend / timeline / nested definitions
# --------------------------------------------------------------------------- #
def test_complexity_trend(tt):
    assert tt.complexity_trend("greet") == [("v1", 1), ("v2", 2), ("v3", 1)]
    assert tt.complexity_trend("farewell") == [("v1", None), ("v2", 1), ("v3", None)]


def test_timeline_lists_every_snapshot(tt):
    text = tt.timeline()
    assert "Timeline for 'demo' (3 snapshot(s))" in text
    for label in ("v1", "v2", "v3"):
        assert label in text


def test_nested_and_conditional_definitions_are_qualified():
    source = (
        "def outer():\n"
        "    def inner():\n"
        "        return 1\n"
        "    return inner\n"
        "\n"
        "try:\n"
        "    import json\n"
        "except ImportError:\n"
        "    json = None\n"
        "\n"
        "if True:\n"
        "    def conditional():\n"
        "        pass\n"
    )
    snap = TimeTravel().record(source)
    assert "outer" in snap.functions
    assert "outer.<locals>.inner" in snap.functions
    assert "conditional" in snap.functions


def test_async_function_and_relative_import():
    source = "from . import sibling\n\nasync def fetch():\n    return 1\n"
    snap = TimeTravel().record(source)
    assert "fetch" in snap.functions
    assert snap.imports == [".sibling"]


# --------------------------------------------------------------------------- #
# persistence
# --------------------------------------------------------------------------- #
def test_save_and_load_roundtrip(tt, tmp_path):
    path = tmp_path / "sub" / "history.json"
    tt.save(str(path))

    loaded = TimeTravel.load(str(path))
    assert loaded.name == "demo"
    assert loaded.labels() == ["v1", "v2", "v3"]
    assert loaded.checkout("v2") == V2
    assert loaded.get("v1").timestamp == "2026-01-01T00:00:00+00:00"
    assert loaded.get("v2").functions == tt.get("v2").functions
    assert loaded.diff("v1", "v2").added_functions == ["Greeter.wave", "farewell"]


def test_load_rejects_invalid_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        TimeTravel.load(str(path))


def test_load_rejects_wrong_structure(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"hello": "world"}), encoding="utf-8")
    with pytest.raises(ValueError):
        TimeTravel.load(str(path))


def test_load_rejects_malformed_snapshot_entry(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"snapshots": [{"label": "a"}]}), encoding="utf-8")
    with pytest.raises(ValueError):
        TimeTravel.load(str(path))


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        TimeTravel.load(str(tmp_path / "missing.json"))