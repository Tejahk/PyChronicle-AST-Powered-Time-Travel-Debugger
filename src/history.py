"""Ordered history of snapshots with undo/redo and JSON persistence."""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict, List, Optional

from .snapshot import Snapshot, SnapshotError, diff_snapshots, take_snapshot


class HistoryError(Exception):
    """Raised for invalid history operations."""


class History:
    def __init__(self, max_size: Optional[int] = None) -> None:
        if max_size is not None and max_size < 1:
            raise HistoryError("max_size must be >= 1")
        self.max_size = max_size
        self._snapshots: List[Snapshot] = []
        self._index: int = -1  # points at the current snapshot

    def __len__(self) -> int:
        return len(self._snapshots)

    def __iter__(self):
        return iter(self._snapshots)

    @property
    def current(self) -> Optional[Snapshot]:
        return self._snapshots[self._index] if self._index >= 0 else None

    def record(self, data: Any, label: str = "") -> Snapshot:
        """Add a new snapshot. Discards any redo branch."""
        snap = take_snapshot(data, label)
        del self._snapshots[self._index + 1:]
        self._snapshots.append(snap)
        if self.max_size and len(self._snapshots) > self.max_size:
            del self._snapshots[: len(self._snapshots) - self.max_size]
        self._index = len(self._snapshots) - 1
        return snap

    def get(self, snapshot_id: str) -> Snapshot:
        for snap in self._snapshots:
            if snap.id == snapshot_id:
                return snap
        raise HistoryError(f"no snapshot with id {snapshot_id!r}")

    def can_undo(self) -> bool:
        return self._index > 0

    def can_redo(self) -> bool:
        return self._index < len(self._snapshots) - 1

    def undo(self) -> Snapshot:
        if not self.can_undo():
            raise HistoryError("nothing to undo")
        self._index -= 1
        return self._snapshots[self._index]

    def redo(self) -> Snapshot:
        if not self.can_redo():
            raise HistoryError("nothing to redo")
        self._index += 1
        return self._snapshots[self._index]

    def diff(self, old_id: str, new_id: str) -> Dict[str, Dict[str, Any]]:
        return diff_snapshots(self.get(old_id), self.get(new_id))

    # ---- persistence -------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_size": self.max_size,
            "index": self._index,
            "snapshots": [s.to_dict() for s in self._snapshots],
        }

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "History":
        try:
            hist = cls(max_size=raw.get("max_size"))
            hist._snapshots = [Snapshot.from_dict(s) for s in raw["snapshots"]]
            hist._index = raw["index"]
        except KeyError as exc:
            raise HistoryError(f"missing field in history: {exc}") from exc
        except SnapshotError as exc:
            raise HistoryError(str(exc)) from exc
        if not -1 <= hist._index < len(hist._snapshots):
            raise HistoryError("index out of range")
        return hist

    def save(self, path: str) -> None:
        """Atomically write history to ``path`` as JSON."""
        directory = os.path.dirname(os.path.abspath(path))
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    @classmethod
    def load(cls, path: str) -> "History":
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return cls.from_dict(json.load(fh))
        except FileNotFoundError as exc:
            raise HistoryError(f"file not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise HistoryError(f"invalid JSON in {path}: {exc}") from exc
