"""Tests for src.ast_parser and src.code_analyzer."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.ast_parser import (  # noqa: E402
    ASTParseError,
    parse_file,
    parse_source,
)
from src.code_analyzer import CodeAnalyzer  # noqa: E402


SAMPLE_SOURCE = '''
"""Sample module docstring."""
import os
from collections import OrderedDict as OD

CONST = 1


def greet(name, greeting="Hello"):
    """Greet someone."""
    if name:
        return f"{greeting}, {name}!"
    return greeting


async def fetch_data(url):
    for i in range(3):
        if i == 2:
            break
    return url


class Animal:
    """Base animal class."""

    def __init__(self, name):
        self.name = name

    def speak(self):
        raise NotImplementedError


class Dog(Animal):
    def speak(self):
        return "Woof"
'''

EMPTY_SOURCE = "x = 1\ny = 2\n"

BROKEN_SOURCE = "def broken(:\n    pass\n"


# --------------------------------------------------------------------------- #
# parse_source
# --------------------------------------------------------------------------- #
def test_parse_source_module_docstring_and_line_count():
    module = parse_source(SAMPLE_SOURCE, filename="sample.py")
    assert module.docstring == "Sample module docstring."
    assert module.filename == "sample.py"
    assert module.source_lines == len(SAMPLE_SOURCE.splitlines())


def test_parse_functions():
    module = parse_source(SAMPLE_SOURCE)
    names = {f.name for f in module.functions}
    assert names == {"greet", "fetch_data"}

    greet = next(f for f in module.functions if f.name == "greet")
    assert greet.args == ["name", "greeting"]
    assert greet.docstring == "Greet someone."
    assert greet.is_async is False

    fetch = next(f for f in module.functions if f.name == "fetch_data")
    assert fetch.is_async is True
    assert fetch.args == ["url"]


def test_parse_classes_and_methods():
    module = parse_source(SAMPLE_SOURCE)
    names = {c.name for c in module.classes}
    assert names == {"Animal", "Dog"}

    animal = next(c for c in module.classes if c.name == "Animal")
    assert animal.docstring == "Base animal class."
    assert {m.name for m in animal.methods} == {"__init__", "speak"}

    dog = next(c for c in module.classes if c.name == "Dog")
    assert dog.bases == ["Animal"]
    assert [m.name for m in dog.methods] == ["speak"]


def test_parse_imports():
    module = parse_source(SAMPLE_SOURCE)
    assert len(module.imports) == 2

    plain = next(i for i in module.imports if not i.is_from)
    assert plain.names == ["os"]
    assert plain.module is None

    from_import = next(i for i in module.imports if i.is_from)
    assert from_import.module == "collections"
    assert from_import.names == ["OrderedDict"]


def test_parse_source_with_no_functions_or_classes():
    module = parse_source(EMPTY_SOURCE)
    assert module.functions == []
    assert module.classes == []
    assert module.imports == []
    assert module.docstring is None


def test_parse_source_syntax_error_raises():
    with pytest.raises(ASTParseError):
        parse_source(BROKEN_SOURCE)


# --------------------------------------------------------------------------- #
# parse_file
# --------------------------------------------------------------------------- #
def test_parse_file_reads_from_disk(tmp_path):
    file_path = tmp_path / "mod.py"
    file_path.write_text(SAMPLE_SOURCE, encoding="utf-8")

    module = parse_file(str(file_path))
    assert module.filename == str(file_path)
    assert len(module.functions) == 2
    assert len(module.classes) == 2


def test_parse_file_missing_raises_file_not_found(tmp_path):
    missing = tmp_path / "does_not_exist.py"
    with pytest.raises(FileNotFoundError):
        parse_file(str(missing))


# --------------------------------------------------------------------------- #
# CodeAnalyzer
# --------------------------------------------------------------------------- #
def test_code_analyzer_counts():
    analyzer = CodeAnalyzer.from_source(SAMPLE_SOURCE, filename="sample.py")
    report = analyzer.analyze()

    assert report.filename == "sample.py"
    assert report.num_classes == 2
    assert report.num_imports == 2
    # 2 module-level functions + 2 methods on Animal + 1 method on Dog
    assert report.num_functions == 5


def test_code_analyzer_complexity_and_most_complex():
    analyzer = CodeAnalyzer.from_source(SAMPLE_SOURCE)
    report = analyzer.analyze()

    scores = {fc.name: fc.complexity for fc in report.function_complexity}
    assert scores["greet"] == 2         # base + if
    assert scores["fetch_data"] == 3    # base + for + if
    assert scores["__init__"] == 1
    assert scores["speak"] == 1         # appears twice (Animal & Dog), both 1

    assert report.most_complex == "fetch_data"


def test_code_analyzer_summary_text_contains_key_facts():
    analyzer = CodeAnalyzer.from_source(SAMPLE_SOURCE, filename="sample.py")
    text = analyzer.summary()

    assert "File: sample.py" in text
    assert "Functions: 5" in text
    assert "Classes: 2" in text
    assert "Imports: 2" in text
    assert "Most complex: fetch_data" in text


def test_code_analyzer_from_file(tmp_path):
    file_path = tmp_path / "mod.py"
    file_path.write_text(SAMPLE_SOURCE, encoding="utf-8")

    analyzer = CodeAnalyzer.from_file(str(file_path))
    report = analyzer.analyze()
    assert report.num_classes == 2


def test_code_analyzer_handles_no_functions():
    analyzer = CodeAnalyzer.from_source(EMPTY_SOURCE)
    report = analyzer.analyze()

    assert report.num_functions == 0
    assert report.most_complex == ""
    assert report.function_complexity == []