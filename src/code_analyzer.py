"""
code_analyzer.py
=================
Higher-level analysis built on top of :mod:`ast_parser`.

Provides summary statistics (function/class/import counts) and a simple
cyclomatic-complexity score for every function and method in a module.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import List

from .ast_parser import ParsedModule, parse_file, parse_source


@dataclass
class ComplexityReport:
    name: str
    complexity: int


@dataclass
class AnalysisReport:
    filename: str
    total_lines: int
    num_functions: int
    num_classes: int
    num_imports: int
    function_complexity: List[ComplexityReport] = field(default_factory=list)
    most_complex: str = ""


class CodeAnalyzer:
    """Runs analysis passes over an already-parsed module."""

    # Node types that each add one branch to cyclomatic complexity.
    _DECISION_NODES = (
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.Try,
        ast.ExceptHandler,
        ast.With,
        ast.AsyncWith,
        ast.BoolOp,
        ast.IfExp,
    )

    def __init__(self, parsed_module: ParsedModule):
        self.module = parsed_module

    @classmethod
    def from_file(cls, filepath: str) -> "CodeAnalyzer":
        return cls(parse_file(filepath))

    @classmethod
    def from_source(cls, source: str, filename: str = "<string>") -> "CodeAnalyzer":
        return cls(parse_source(source, filename))

    def analyze(self) -> AnalysisReport:
        complexities = [
            ComplexityReport(name=node.name, complexity=self._cyclomatic_complexity(node))
            for node in self._iter_function_nodes()
        ]

        most_complex = ""
        if complexities:
            most_complex = max(complexities, key=lambda c: c.complexity).name

        return AnalysisReport(
            filename=self.module.filename,
            total_lines=self.module.source_lines,
            num_functions=len(complexities),
            num_classes=len(self.module.classes),
            num_imports=len(self.module.imports),
            function_complexity=complexities,
            most_complex=most_complex,
        )

    def summary(self) -> str:
        """A short, human-readable text report."""
        report = self.analyze()
        lines = [
            f"File: {report.filename}",
            f"Total lines: {report.total_lines}",
            f"Functions: {report.num_functions}",
            f"Classes: {report.num_classes}",
            f"Imports: {report.num_imports}",
        ]
        if report.function_complexity:
            lines.append("Function complexity:")
            for fc in sorted(report.function_complexity, key=lambda c: -c.complexity):
                lines.append(f"  {fc.name}: {fc.complexity}")
            lines.append(f"Most complex: {report.most_complex}")
        return "\n".join(lines)

    # ----------------------------------------------------------------- #
    # internals
    # ----------------------------------------------------------------- #
    def _iter_function_nodes(self):
        if self.module.tree is None:
            return
        for node in ast.walk(self.module.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield node

    @classmethod
    def _cyclomatic_complexity(cls, func_node) -> int:
        complexity = 1  # base path
        for node in ast.walk(func_node):
            if isinstance(node, cls._DECISION_NODES):
                complexity += 1
            elif isinstance(node, ast.comprehension):
                complexity += len(node.ifs) + 1
        return complexity