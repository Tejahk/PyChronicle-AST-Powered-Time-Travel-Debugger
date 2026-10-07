"""
cli.py
======
Command-line interface for PyChronicle.

Recommended: run as a module from the project root so package-relative
imports resolve correctly:

    python -m src.cli analyze path/to/file.py
    python -m src.cli record path/to/file.py --history history.json --label v1
    python -m src.cli timeline --history history.json
    python -m src.cli diff --history history.json --from v1 --to v2 --full
    python -m src.cli checkout --history history.json --ref v1 --out restored.py
    python -m src.cli trend --history history.json --function my_function

Every command prints a plain-text result and exits 0 on success. Any
problem (missing file, syntax error, bad snapshot reference, corrupt
history file, ...) is reported as ``Error: ...`` on stderr and the process
exits 1 -- nothing ever raises a raw traceback at the user.
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

# Support both `python -m src.cli ...` (recommended, relative imports work)
# and running this file directly as a script from inside the src/ folder.
try:
    from .ast_parser import ASTParseError
    from .code_analyzer import CodeAnalyzer
    from .time_travel import SnapshotNotFoundError, TimeTravel, TimeTravelError
except ImportError:  # pragma: no cover - fallback for direct script execution
    from ast_parser import ASTParseError
    from code_analyzer import CodeAnalyzer
    from time_travel import SnapshotNotFoundError, TimeTravel, TimeTravelError


class CLIError(Exception):
    """Any user-facing failure; caught in main() and printed as 'Error: ...'."""


def _parse_ref(value: Optional[str]):
    """A ref that looks like an integer is treated as an index; otherwise a label."""
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def _load_history(path: str) -> TimeTravel:
    try:
        return TimeTravel.load(path)
    except FileNotFoundError:
        raise CLIError(f"History file not found: {path}")
    except ValueError as exc:
        raise CLIError(f"Could not read history file '{path}': {exc}")


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def cmd_analyze(args: argparse.Namespace) -> int:
    try:
        analyzer = CodeAnalyzer.from_file(args.file)
    except FileNotFoundError:
        raise CLIError(f"File not found: {args.file}")
    except ASTParseError as exc:
        raise CLIError(str(exc))
    print(analyzer.summary())
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    import os

    if os.path.exists(args.history):
        history = _load_history(args.history)
    else:
        history = TimeTravel(args.name or os.path.splitext(os.path.basename(args.history))[0])

    try:
        snapshot = history.record_file(args.file, label=args.label)
    except FileNotFoundError:
        raise CLIError(f"File not found: {args.file}")
    except (ASTParseError, ValueError) as exc:
        raise CLIError(str(exc))

    history.save(args.history)
    print(f"Recorded '{snapshot.label}' (#{snapshot.short_hash}) -> {args.history}")
    return 0


def cmd_timeline(args: argparse.Namespace) -> int:
    history = _load_history(args.history)
    print(history.timeline())
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    history = _load_history(args.history)
    try:
        report = history.diff(_parse_ref(args.from_ref), _parse_ref(args.to_ref))
    except SnapshotNotFoundError as exc:
        raise CLIError(str(exc))

    print(report.summary())
    if args.full and report.diff_text:
        print()
        print(report.diff_text, end="")
    return 0


def cmd_checkout(args: argparse.Namespace) -> int:
    history = _load_history(args.history)
    try:
        source = history.checkout(_parse_ref(args.ref), path=args.out)
    except SnapshotNotFoundError as exc:
        raise CLIError(str(exc))

    if args.out:
        print(f"Wrote snapshot '{args.ref}' to {args.out}")
    else:
        print(source, end="" if source.endswith("\n") else "\n")
    return 0


def cmd_trend(args: argparse.Namespace) -> int:
    history = _load_history(args.history)
    trend = history.complexity_trend(args.function)
    if not trend:
        raise CLIError("History has no snapshots.")
    for label, complexity in trend:
        print(f"{label:<20} {complexity if complexity is not None else '-'}")
    return 0


# --------------------------------------------------------------------------- #
# argument parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pychronicle",
        description="PyChronicle -- parse, analyze, and time-travel through Python source code.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_analyze = sub.add_parser(
        "analyze", help="Parse a file and print a structural/complexity summary."
    )
    p_analyze.add_argument("file", help="Path to a .py file")
    p_analyze.set_defaults(func=cmd_analyze)

    p_record = sub.add_parser(
        "record", help="Record a snapshot of a file into a history file (created if missing)."
    )
    p_record.add_argument("file", help="Path to a .py file to snapshot")
    p_record.add_argument("--history", required=True, help="Path to the history JSON file")
    p_record.add_argument("--label", help="Label for this snapshot (auto-generated if omitted)")
    p_record.add_argument(
        "--name", help="Name for a brand-new history (ignored if the history file already exists)"
    )
    p_record.set_defaults(func=cmd_record)

    p_timeline = sub.add_parser("timeline", help="List every snapshot in a history file.")
    p_timeline.add_argument("--history", required=True)
    p_timeline.set_defaults(func=cmd_timeline)

    p_diff = sub.add_parser(
        "diff", help="Show structural + line differences between two snapshots."
    )
    p_diff.add_argument("--history", required=True)
    p_diff.add_argument(
        "--from", dest="from_ref", help="Snapshot label or index (default: second-to-last)"
    )
    p_diff.add_argument("--to", dest="to_ref", help="Snapshot label or index (default: latest)")
    p_diff.add_argument("--full", action="store_true", help="Also print the full unified line diff")
    p_diff.set_defaults(func=cmd_diff)

    p_checkout = sub.add_parser("checkout", help="Print or restore the source of one snapshot.")
    p_checkout.add_argument("--history", required=True)
    p_checkout.add_argument("--ref", required=True, help="Snapshot label or index")
    p_checkout.add_argument("--out", help="Write the source to this file instead of stdout")
    p_checkout.set_defaults(func=cmd_checkout)

    p_trend = sub.add_parser("trend", help="Show one function's complexity across every snapshot.")
    p_trend.add_argument("--history", required=True)
    p_trend.add_argument(
        "--function", required=True, help="Qualified function name, e.g. 'greet' or 'Class.method'"
    )
    p_trend.set_defaults(func=cmd_trend)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (CLIError, TimeTravelError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())