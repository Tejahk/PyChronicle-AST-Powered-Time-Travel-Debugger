import json

import pytest

from src.history import History, HistoryError


def make_history():
    h = History()
    h.record({"v": 1}, "one")
    h.record({"v": 2}, "two")
    h.record({"v": 3}, "three")
    return h


def test_record_and_current():
    h = make_history()
    assert len(h) == 3
    assert h.current.data == {"v": 3}


def test_undo_redo():
    h = make_history()
    assert h.undo().data == {"v": 2}
    assert h.undo().data == {"v": 1}
    assert not h.can_undo()
    with pytest.raises(HistoryError):
        h.undo()
    assert h.redo().data == {"v": 2}
    assert h.can_redo()


def test_record_after_undo_discards_redo_branch():
    h = make_history()
    h.undo()
    h.record({"v": 99})
    assert not h.can_redo()
    assert [s.data["v"] for s in h] == [1, 2, 99]


def test_max_size_trims_oldest():
    h = History(max_size=2)
    for i in range(5):
        h.record({"i": i})
    assert [s.data["i"] for s in h] == [3, 4]
    assert h.current.data == {"i": 4}


def test_invalid_max_size():
    with pytest.raises(HistoryError):
        History(max_size=0)


def test_get_and_diff():
    h = make_history()
    first, last = list(h)[0], list(h)[-1]
    assert h.get(first.id) is first
    assert h.diff(first.id, last.id)["changed"] == {"v": (1, 3)}
    with pytest.raises(HistoryError):
        h.get("nope")


def test_empty_history():
    h = History()
    assert h.current is None
    assert not h.can_undo() and not h.can_redo()


def test_save_and_load_round_trip(tmp_path):
    h = make_history()
    h.undo()
    path = tmp_path / "history.json"
    h.save(str(path))
    loaded = History.load(str(path))
    assert [s.id for s in loaded] == [s.id for s in h]
    assert loaded.current.data == {"v": 2}
    assert loaded.can_redo()


def test_load_errors(tmp_path):
    with pytest.raises(HistoryError):
        History.load(str(tmp_path / "missing.json"))
    bad = tmp_path / "bad.json"
    bad.write_text("{oops")
    with pytest.raises(HistoryError):
        History.load(str(bad))


def test_load_detects_tampering(tmp_path):
    h = make_history()
    path = tmp_path / "h.json"
    h.save(str(path))
    raw = json.loads(path.read_text())
    raw["snapshots"][0]["data"]["v"] = 1000
    path.write_text(json.dumps(raw))
    with pytest.raises(HistoryError):
        History.load(str(path))
