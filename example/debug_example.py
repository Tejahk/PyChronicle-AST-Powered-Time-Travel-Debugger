"""
example/debug_example.py
=========================
A small, deliberately-buggy function used to walk through a realistic
PyChronicle debugging session, end to end, using the real CLI
(`python -m src.cli ...`) rather than calling the library directly.

Workflow demonstrated:
    1. analyze  the buggy version (see its inflated complexity)
    2. record   it into a history file, labelled "buggy"
    3. fix the bug
    4. analyze  the fixed version
    5. record   it, labelled "fixed"
    6. diff     "buggy" -> "fixed" to see exactly what changed
    7. timeline to see the whole history

Run from the PyChronicle project root:

    python example/debug_example.py
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A classic copy-paste bug: the zero-check loop is dead code, and the
# division by `divisor` still runs unconditionally afterwards, so
# divide_all([1, 2], 0) crashes with ZeroDivisionError instead of being
# handled -- while also being needlessly complex.
BUGGY_VERSION = '''def divide_all(numbers, divisor):
    """Divide every number in the list by divisor."""
    results = []
    for n in numbers:
        if divisor == 0:
            for x in numbers:
                results.append(x)
        results.append(n / divisor)
    return results
'''

FIXED_VERSION = '''def divide_all(numbers, divisor):
    """Divide every number in the list by divisor."""
    if divisor == 0:
        raise ValueError("divisor must not be zero")
    return [n / divisor for n in numbers]
'''


def run_cli(*args):
    """Run `python -m src.cli <args>` from the project root; return combined output."""
    result = subprocess.run(
        [sys.executable, "-m", "src.cli", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode, (result.stdout + result.stderr)


def section(title):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def main():
    workdir = tempfile.mkdtemp(prefix="pychronicle_debug_")
    target = os.path.join(workdir, "buggy.py")
    history = os.path.join(workdir, "history.json")

    try:
        with open(target, "w", encoding="utf-8") as f:
            f.write(BUGGY_VERSION)

        section("STEP 1: analyze the buggy version")
        code, out = run_cli("analyze", target)
        print(out.strip())
        assert code == 0

        section("STEP 2: record it")
        code, out = run_cli("record", target, "--history", history, "--label", "buggy")
        print(out.strip())
        assert code == 0

        with open(target, "w", encoding="utf-8") as f:
            f.write(FIXED_VERSION)

        section("STEP 3: analyze the fixed version")
        code, out = run_cli("analyze", target)
        print(out.strip())
        assert code == 0

        section("STEP 4: record the fix")
        code, out = run_cli("record", target, "--history", history, "--label", "fixed")
        print(out.strip())
        assert code == 0

        section("STEP 5: diff 'buggy' -> 'fixed'")
        code, out = run_cli(
            "diff", "--history", history, "--from", "buggy", "--to", "fixed", "--full"
        )
        print(out.strip())
        assert code == 0

        section("STEP 6: full timeline")
        code, out = run_cli("timeline", "--history", history)
        print(out.strip())
        assert code == 0

        section("Done")
        print("Temporary files cleaned up.")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()