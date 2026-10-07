"""
time_travel.py
==============
Version-history tracking for Python source code, built on PyChronicle's
parser and analyzer.

Record snapshots of a piece of source code over time, then:

* diff any two snapshots *structurally* (added/removed functions, classes and
  imports, plus cyclomatic-complexity changes) alongside a normal line diff,
* "travel" back by checking out the exact source of any earlier snapshot,
* follow how one function's complexity evolved (``complexity_trend``),
* save the whole history to JSON and load it again later.

Example::

    tt = TimeTravel("my_module")
    tt.record(open("mod.py").read(), label="before-refactor")
    ...  # edit the file
    tt.record(open("mod.py").read(), label="after-refactor")
    print(tt.diff("before-refactor", "after-refactor").summary())
"""
from __future__ import annotations

import ast
import difflib
import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Union

from .ast_parser import parse_source
from .code_analyzer import CodeAnalyzer

# A snapshot can be referenced by position (0, -1, ...) or by its label.
Ref = Union[int, str]

_FORMAT_VERSION = 1


class TimeTravelError(Exception):
    """Base class for time-travel specific errors."""


class SnapshotNotFoundError(TimeTravelError, LookupError):
    """Raised when a snapshot index or label does not exist."""


# --------------------------------------------------------------------------- #
# data classes
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Snapshot:
    """An immutable record of the source (and its analysis) at one point in time."""

    index: int
    label: str
    timestamp: str
    source: str
    source_hash: str
    total_lines: int
    functions: Dict[str, int]  # qualified name -> cyclomatic complexity
    classes: List[str]
    imports: List[str]

    @property
    def short_hash(self) -> str:
        return self.source_hash[:8]


@dataclass
class ChangeReport:
    """Structural + textual differences between two snapshots."""

    from_label: str
    to_label: str
    added_functions: List[str] = field(default_factory=list)
    removed_functions: List[str] = field(default_factory=list)
    complexity_changes: Dict[str, Tuple[int, int]] = field(default_factory=dict)
    added_classes: List[str] = field(default_factory=list)
    removed_classes: List[str] = field(default_factory=list)
    added_imports: List[str] = field(default_factory=list)
    removed_imports: List[str] = field(default_factory=list)
    lines_delta: int = 0
    diff_text: str = ""

    @property
    def has_structural_changes(self) -> bool:
        """True if functions, classes, imports or complexity differ."""
        return bool(
            self.added_functions
            or self.removed_functions
            or self.complexity_changes
            or self.added_classes
            or self.removed_classes
            or self.added_imports
            or self.removed_imports
        )

    @property
    def has_changes(self) -> bool:
        """True if the source text differs at all (even whitespace/comments)."""
        return bool(self.diff_text)

    def summary(self) -> str:
        lines = [f"Changes: {self.from_label} -> {self.to_label}"]
        if not self.has_changes:
            lines.append("  No changes.")
            return "\n".join(lines)

        lines.append(f"  Lines: {self.lines_delta:+d}")
        for title, items in (
            ("Added functions", self.added_functions),
            ("Removed functions", self.removed_functions),
            ("Added classes", self.added_classes),
            ("Removed classes", self.removed_classes),
            ("Added imports", self.added_imports),
            ("Removed imports", self.removed_imports),
        ):
            if items:
                lines.append(f"  {title}: {', '.join(items)}")
        if self.complexity_changes:
            lines.append("  Complexity changes:")
            for name, (old, new) in self.complexity_changes.items():
                lines.append(f"    {name}: {old} -> {new} ({new - old:+d})")
        if not self.has_structural_changes:
            lines.append("  (text changed, structure unchanged)")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# analysis helpers
# --------------------------------------------------------------------------- #
def _collect_definitions(tree: ast.AST) -> Tuple[Dict[str, int], List[str]]:
    """Return ({qualified function name: complexity}, [qualified class names]).

    Methods are qualified with their class (``Class.method``) and nested
    functions with ``outer.<locals>.inner`` so that identically-named methods
    in different classes never collide.
    """
    functions: Dict[str, int] = {}
    classes: List[str] = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualname = prefix + child.name
                functions[qualname] = CodeAnalyzer._cyclomatic_complexity(child)
                visit(child, qualname + ".<locals>.")
            elif isinstance(child, ast.ClassDef):
                qualname = prefix + child.name
                classes.append(qualname)
                visit(child, qualname + ".")
            else:
                # Definitions can hide inside if/try/with blocks.
                visit(child, prefix)

    visit(tree, "")
    return functions, classes


def _import_names(parsed) -> List[str]:
    names: List[str] = []
    for info in parsed.imports:
        for name in info.names:
            if info.is_from:
                names.append(f"{info.module}.{name}" if info.module else f".{name}")
            else:
                names.append(name)
    return sorted(set(names))


def _build_snapshot(index: int, label: str, timestamp: str, source: str) -> Snapshot:
    parsed = parse_source(source, filename=label)  # raises ASTParseError on bad syntax
    functions, classes = _collect_definitions(parsed.tree)
    return Snapshot(
        index=index,
        label=label,
        timestamp=timestamp,
        source=source,
        source_hash=hashlib.sha256(source.encode("utf-8")).hexdigest(),
        total_lines=parsed.source_lines,
        functions=functions,
        classes=sorted(classes),
        imports=_import_names(parsed),
    )


def _lines_for_diff(source: str) -> List[str]:
    lines = source.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    return lines


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# TimeTravel
# --------------------------------------------------------------------------- #
class TimeTravel:
    """An ordered history of snapshots for one piece of Python source."""

    def __init__(self, name: str = "untitled"):
        self.name = name
        self._snapshots: List[Snapshot] = []

    # ---- basic container behaviour ------------------------------------ #
    def __len__(self) -> int:
        return len(self._snapshots)

    @property
    def snapshots(self) -> Tuple[Snapshot, ...]:
        return tuple(self._snapshots)

    def labels(self) -> List[str]:
        return [s.label for s in self._snapshots]

    # ---- recording ------------------------------------------------------ #
    def record(
        self,
        source: str,
        label: Optional[str] = None,
        timestamp: Optional[str] = None,
        allow_duplicate: bool = False,
    ) -> Snapshot:
        """Record ``source`` as the newest snapshot and return it.

        * ``label`` must be unique; if omitted, ``v1``, ``v2``... is used.
        * If ``source`` is identical to the latest snapshot it is *not*
          recorded again (the existing latest snapshot is returned) unless
          ``allow_duplicate=True``.
        * Source with a syntax error raises ``ASTParseError`` and leaves the
          history untouched.
        """
        if not isinstance(source, str):
            raise TypeError("source must be a string")
        if label is not None:
            if not isinstance(label, str) or not label.strip():
                raise ValueError("label must be a non-empty string")
            if label in self.labels():
                raise ValueError(f"Label '{label}' already exists")
        else:
            label = self._next_label()

        snapshot = _build_snapshot(
            index=len(self._snapshots),
            label=label,
            timestamp=timestamp or _now(),
            source=source,
        )

        if (
            not allow_duplicate
            and self._snapshots
            and self._snapshots[-1].source_hash == snapshot.source_hash
        ):
            return self._snapshots[-1]

        self._snapshots.append(snapshot)
        return snapshot

    def record_file(self, filepath: str, label: Optional[str] = None, **kwargs) -> Snapshot:
        """Read a file from disk and record its contents."""
        with open(filepath, "r", encoding="utf-8") as handle:
            source = handle.read()
        return self.record(source, label=label, **kwargs)

    def _next_label(self) -> str:
        n = len(self._snapshots) + 1
        existing = set(self.labels())
        while f"v{n}" in existing:
            n += 1
        return f"v{n}"

    # ---- retrieval / travelling ------------------------------------------ #
    def get(self, ref: Ref) -> Snapshot:
        """Fetch a snapshot by index (negative allowed) or by label."""
        if isinstance(ref, bool):
            raise TypeError("ref must be an int index or a str label")
        if isinstance(ref, int):
            try:
                return self._snapshots[ref]
            except IndexError:
                raise SnapshotNotFoundError(
                    f"No snapshot at index {ref} (history has {len(self)} snapshots)"
                ) from None
        if isinstance(ref, str):
            for snap in self._snapshots:
                if snap.label == ref:
                    return snap
            raise SnapshotNotFoundError(f"No snapshot labelled '{ref}'")
        raise TypeError("ref must be an int index or a str label")

    def checkout(self, ref: Ref, path: Optional[str] = None) -> str:
        """Travel back: return the exact source of a snapshot.

        If ``path`` is given, the source is also written to that file.
        """
        source = self.get(ref).source
        if path is not None:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(source)
        return source

    # ---- comparing --------------------------------------------------------- #
    def diff(self, from_ref: Optional[Ref] = None, to_ref: Optional[Ref] = None) -> ChangeReport:
        """Compare two snapshots. Defaults to the previous vs. latest snapshot."""
        a = self.get(-2 if from_ref is None else from_ref)
        b = self.get(-1 if to_ref is None else to_ref)

        funcs_a, funcs_b = set(a.functions), set(b.functions)
        common = sorted(funcs_a & funcs_b)

        return ChangeReport(
            from_label=a.label,
            to_label=b.label,
            added_functions=sorted(funcs_b - funcs_a),
            removed_functions=sorted(funcs_a - funcs_b),
            complexity_changes={
                name: (a.functions[name], b.functions[name])
                for name in common
                if a.functions[name] != b.functions[name]
            },
            added_classes=sorted(set(b.classes) - set(a.classes)),
            removed_classes=sorted(set(a.classes) - set(b.classes)),
            added_imports=sorted(set(b.imports) - set(a.imports)),
            removed_imports=sorted(set(a.imports) - set(b.imports)),
            lines_delta=b.total_lines - a.total_lines,
            diff_text="".join(
                difflib.unified_diff(
                    _lines_for_diff(a.source),
                    _lines_for_diff(b.source),
                    fromfile=a.label,
                    tofile=b.label,
                )
            ),
        )

    def complexity_trend(self, function_name: str) -> List[Tuple[str, Optional[int]]]:
        """Complexity of one function at every snapshot (None where it doesn't exist)."""
        return [(s.label, s.functions.get(function_name)) for s in self._snapshots]

    def timeline(self) -> str:
        """A human-readable overview of the whole history."""
        lines = [f"Timeline for '{self.name}' ({len(self)} snapshot(s))"]
        for s in self._snapshots:
            lines.append(
                f"  [{s.index}] {s.label:<16} {s.timestamp}  "
                f"{s.total_lines:>4} lines  {len(s.functions):>3} functions  #{s.short_hash}"
            )
        return "\n".join(lines)

    # ---- persistence -------------------------------------------------------- #
    def save(self, path: str) -> None:
        """Write the whole history to a JSON file."""
        payload = {
            "format": _FORMAT_VERSION,
            "name": self.name,
            "snapshots": [
                {"label": s.label, "timestamp": s.timestamp, "source": s.source}
                for s in self._snapshots
            ],
        }
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    @classmethod
    def load(cls, path: str) -> "TimeTravel":
        """Load a history saved with :meth:`save`; every snapshot is re-analyzed."""
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)  # JSONDecodeError is a ValueError

        if not isinstance(data, dict) or not isinstance(data.get("snapshots"), list):
            raise ValueError("Not a valid PyChronicle time-travel file")

        tt = cls(str(data.get("name", "untitled")))
        for entry in data["snapshots"]:
            if not (
                isinstance(entry, dict)
                and isinstance(entry.get("label"), str)
                and isinstance(entry.get("timestamp"), str)
                and isinstance(entry.get("source"), str)
            ):
                raise ValueError("Malformed snapshot entry in time-travel file")
            tt.record(
                entry["source"],
                label=entry["label"],
                timestamp=entry["timestamp"],
                allow_duplicate=True,
            )
        return tt