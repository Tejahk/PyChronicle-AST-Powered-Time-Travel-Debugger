"""
ast_parser.py
=============
Low-level parsing utilities for PyChronicle.

Turns raw Python source code into structured, easy-to-consume data
(functions, classes, methods, imports, docstrings) using the standard
library ``ast`` module.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import List, Optional


class ASTParseError(Exception):
    """Raised when source code cannot be parsed into a valid AST."""


@dataclass
class FunctionInfo:
    name: str
    lineno: int
    end_lineno: Optional[int]
    args: List[str]
    docstring: Optional[str]
    decorators: List[str]
    is_async: bool = False


@dataclass
class ClassInfo:
    name: str
    lineno: int
    end_lineno: Optional[int]
    bases: List[str]
    docstring: Optional[str]
    methods: List[FunctionInfo] = field(default_factory=list)


@dataclass
class ImportInfo:
    module: Optional[str]   # None for plain `import x`
    names: List[str]
    lineno: int
    is_from: bool = False


@dataclass
class ParsedModule:
    filename: str
    docstring: Optional[str]
    functions: List[FunctionInfo] = field(default_factory=list)
    classes: List[ClassInfo] = field(default_factory=list)
    imports: List[ImportInfo] = field(default_factory=list)
    source_lines: int = 0
    tree: Optional[ast.Module] = None


def parse_source(source: str, filename: str = "<string>") -> ParsedModule:
    """Parse a string of Python source code into a :class:`ParsedModule`.

    Raises:
        ASTParseError: if the source contains a syntax error.
    """
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        raise ASTParseError(f"Syntax error in {filename}: {exc}") from exc

    module = ParsedModule(
        filename=filename,
        docstring=ast.get_docstring(tree),
        source_lines=len(source.splitlines()),
        tree=tree,
    )

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            module.functions.append(_extract_function(node))
        elif isinstance(node, ast.ClassDef):
            module.classes.append(_extract_class(node))
        elif isinstance(node, ast.Import):
            module.imports.append(
                ImportInfo(
                    module=None,
                    names=[alias.name for alias in node.names],
                    lineno=node.lineno,
                    is_from=False,
                )
            )
        elif isinstance(node, ast.ImportFrom):
            module.imports.append(
                ImportInfo(
                    module=node.module,
                    names=[alias.name for alias in node.names],
                    lineno=node.lineno,
                    is_from=True,
                )
            )

    return module


def parse_file(filepath: str) -> ParsedModule:
    """Read a ``.py`` file from disk and parse it into a :class:`ParsedModule`."""
    with open(filepath, "r", encoding="utf-8") as handle:
        source = handle.read()
    return parse_source(source, filename=filepath)


# --------------------------------------------------------------------------- #
# internal helpers
# --------------------------------------------------------------------------- #
def _extract_function(node) -> FunctionInfo:
    args = [a.arg for a in node.args.args]
    decorators = [_expr_name(d) for d in node.decorator_list]
    return FunctionInfo(
        name=node.name,
        lineno=node.lineno,
        end_lineno=getattr(node, "end_lineno", None),
        args=args,
        docstring=ast.get_docstring(node),
        decorators=decorators,
        is_async=isinstance(node, ast.AsyncFunctionDef),
    )


def _extract_class(node: ast.ClassDef) -> ClassInfo:
    bases = [_expr_name(b) for b in node.bases]
    methods = [
        _extract_function(child)
        for child in node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    return ClassInfo(
        name=node.name,
        lineno=node.lineno,
        end_lineno=getattr(node, "end_lineno", None),
        bases=bases,
        docstring=ast.get_docstring(node),
        methods=methods,
    )


def _expr_name(node) -> str:
    """Best-effort stringification of a decorator/base-class expression."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_expr_name(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return _expr_name(node.func)
    return ast.dump(node)