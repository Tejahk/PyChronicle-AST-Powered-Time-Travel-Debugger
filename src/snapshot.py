"""Immutable snapshots of JSON-serializable data."""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class SnapshotError(Exception):
    """Raised when a snapshot cannot be created, loaded or verified."""


def _canonical(data: Any) -> str:
    """Deterministic JSON string (sorted keys) used for hashing."""
    try:
        return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise SnapshotError(f"data is not JSON-serializable: {exc}") from exc


def compute_checksum(data: Any) -> str:
    return hashlib.sha256(_canonical(data).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Snapshot:
    data: Any
    label: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    checksum: str = ""

    def __post_init__(self) -> None:
        # Deep-copy so later mutation of the original object can't change history.
        object.__setattr__(self, "data", copy.deepcopy(self.data))
        if not self.checksum:
            object.__setattr__(self, "checksum", compute_checksum(self.data))

    def verify(self) -> bool:
        return self.checksum == compute_checksum(self.data)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "timestamp": self.timestamp,
            "checksum": self.checksum,
            "data": copy.deepcopy(self.data),
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Snapshot":
        try:
            snap = cls(
                data=raw["data"],
                label=raw.get("label", ""),
                id=raw["id"],
                timestamp=raw["timestamp"],
                checksum=raw.get("checksum", ""),
            )
        except KeyError as exc:
            raise SnapshotError(f"missing field in snapshot: {exc}") from exc
        if not snap.verify():
            raise SnapshotError(f"checksum mismatch for snapshot {snap.id}")
        return snap

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> "Snapshot":
        try:
            return cls.from_dict(json.loads(text))
        except json.JSONDecodeError as exc:
            raise SnapshotError(f"invalid JSON: {exc}") from exc


def take_snapshot(data: Any, label: str = "") -> Snapshot:
    """Create a snapshot of ``data`` (deep-copied)."""
    return Snapshot(data=data, label=label)


def diff_snapshots(old: Snapshot, new: Snapshot) -> Dict[str, Dict[str, Any]]:
    """Top-level key diff between two dict snapshots.

    Returns {"added": {...}, "removed": {...}, "changed": {key: (old, new)}}.
    """
    if not isinstance(old.data, dict) or not isinstance(new.data, dict):
        raise SnapshotError("diff requires both snapshots to contain dicts")
    a, b = old.data, new.data
    return {
        "added": {k: b[k] for k in b.keys() - a.keys()},
        "removed": {k: a[k] for k in a.keys() - b.keys()},
        "changed": {k: (a[k], b[k]) for k in a.keys() & b.keys() if a[k] != b[k]},
    }
