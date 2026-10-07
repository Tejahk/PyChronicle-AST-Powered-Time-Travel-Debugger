import json

import pytest

from src.snapshot import Snapshot, SnapshotError, diff_snapshots, take_snapshot


def test_snapshot_deep_copies_data():
    data = {"a": [1, 2]}
    snap = take_snapshot(data, "first")
    data["a"].append(3)
    assert snap.data == {"a": [1, 2]}


def test_checksum_is_deterministic_and_verifies():
    s1 = take_snapshot({"b": 1, "a": 2})
    s2 = take_snapshot({"a": 2, "b": 1})
    assert s1.checksum == s2.checksum
    assert s1.verify()


def test_non_serializable_raises():
    with pytest.raises(SnapshotError):
        take_snapshot({"x": object()})


def test_json_round_trip():
    snap = take_snapshot({"k": "v"}, "label")
    restored = Snapshot.from_json(snap.to_json())
    assert restored == snap


def test_tampered_snapshot_detected():
    raw = take_snapshot({"k": 1}).to_dict()
    raw["data"]["k"] = 2
    with pytest.raises(SnapshotError):
        Snapshot.from_dict(raw)


def test_invalid_json_and_missing_field():
    with pytest.raises(SnapshotError):
        Snapshot.from_json("{not json")
    with pytest.raises(SnapshotError):
        Snapshot.from_dict({"data": 1})


def test_diff():
    old = take_snapshot({"a": 1, "b": 2, "c": 3})
    new = take_snapshot({"a": 1, "b": 20, "d": 4})
    d = diff_snapshots(old, new)
    assert d["added"] == {"d": 4}
    assert d["removed"] == {"c": 3}
    assert d["changed"] == {"b": (2, 20)}


def test_diff_requires_dicts():
    with pytest.raises(SnapshotError):
        diff_snapshots(take_snapshot([1]), take_snapshot({"a": 1}))
