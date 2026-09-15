"""
example.py
==========
A quick manual test you can run in VS Code to see PyChronicle in action.

Usage:
    python example.py
"""
from src import CodeAnalyzer, parse_source

# --- 1. A little sample Python code to analyze -----------------------------
sample_code = '''
"""A tiny demo module."""
import os
from math import sqrt


def add(a, b):
    """Add two numbers."""
    return a + b


def classify(n):
    if n < 0:
        return "negative"
    elif n == 0:
        return "zero"
    else:
        for i in range(n):
            if i == 5:
                break
        return "positive"


class Shape:
    """Base shape."""

    def __init__(self, name):
        self.name = name

    def area(self):
        raise NotImplementedError


class Circle(Shape):
    def __init__(self, radius):
        super().__init__("circle")
        self.radius = radius

    def area(self):
        return 3.14159 * self.radius ** 2
'''

# --- 2. Parse it -------------------------------------------------------------
print("=" * 60)
print("PARSING")
print("=" * 60)

module = parse_source(sample_code, filename="demo.py")
print(f"Module docstring: {module.docstring}")
print(f"Functions found: {[f.name for f in module.functions]}")
print(f"Classes found:   {[c.name for c in module.classes]}")
print(f"Imports found:   {[(i.module, i.names) for i in module.imports]}")

for cls in module.classes:
    print(f"  Class '{cls.name}' (bases={cls.bases}) methods: "
          f"{[m.name for m in cls.methods]}")

# --- 3. Analyze it -------------------------------------------------------------
print()
print("=" * 60)
print("ANALYSIS")
print("=" * 60)

analyzer = CodeAnalyzer.from_source(sample_code, filename="demo.py")
print(analyzer.summary())

# --- 4. Try it on a real file on disk ----------------------------------------
print()
print("=" * 60)
print("ANALYZING A REAL FILE (src/code_analyzer.py)")
print("=" * 60)

file_analyzer = CodeAnalyzer.from_file("src/code_analyzer.py")
print(file_analyzer.summary())