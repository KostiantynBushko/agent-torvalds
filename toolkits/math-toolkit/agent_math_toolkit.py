"""
Math Toolkit - the LlamaIndex agent adapter.

This module is the **agent-facing half** of the math toolkit.  It turns the
pure-mathematics operations of :mod:`operations` into LlamaIndex
``FunctionTool`` objects, so the agent can call them.

It is the **only** module of the toolkit that knows about LlamaIndex.  The
library half (``operations.py``) stays free of it, so the mathematics
remains usable - and testable - as a plain Python library.

Importing this adapter
----------------------

The toolkit lives in a hyphenated directory (``toolkits/math-toolkit/``),
which is not a valid Python identifier, so it is reached through the alias
that ``toolkits/__init__.py`` registers::

    from toolkits.math_toolkit.agent_math_toolkit import get_all_tools

The adapter pulls the core package in with a **relative** import
(``from . import ...``), so the adapter and the library share one set of
module objects - there is never a second copy of ``operations.py`` in
memory.

Category: Mathematics
Retriever Keywords: calculation, math, arithmetic, trigonometry, logarithm, statistics
"""

from __future__ import annotations

import logging

from llama_index.core.tools import FunctionTool

# The core package is imported with a *relative* import.  That is the only
# form that resolves both inside this repository (where the directory name
# carries a hyphen) and in a standalone installation of the package.
#
# The names come from the package itself, so the adapter and the library
# always share one set of module objects.
from . import (
    add,
    cos,
    divide,
    evaluate_rpn,
    factorial,
    log,
    log10,
    modulo,
    multiply,
    power,
    sin,
    sqrt,
    subtract,
    tan,
)

# The operations carry the logger; the adapter re-exports it so that the
# whole toolkit logs through one logger, as it did when the toolkit was a
# single module at the project root.
from .operations import logger

__all__ = [
    "logger",
    "get_all_tools",
    # The operations are re-exported so that the adapter is a drop-in
    # replacement for the old top-level ``agent_math_toolkit`` module.
    "add",
    "subtract",
    "multiply",
    "divide",
    "power",
    "modulo",
    "sqrt",
    "sin",
    "cos",
    "tan",
    "log",
    "log10",
    "factorial",
    "evaluate_rpn",
]


def get_all_tools() -> list[FunctionTool]:
    """
    Return all math tools as FunctionTool objects for on-demand loading.
    
    Each tool includes category metadata for better retrieval.
    
    Returns:
        list[FunctionTool]: List of math FunctionTool objects
    """
    logger.info("get_all_tools called for math toolkit")
    return [
        FunctionTool.from_defaults(
            fn=add,
            description="Add two numbers together. Use for basic addition and summing values. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=subtract,
            description="Subtract one number from another. Use for finding differences. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=multiply,
            description="Multiply two numbers. Use for scaling, areas, volumes. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=divide,
            description="Divide one number by another. Use for ratios, averages, percentages. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=power,
            description="Raise a number to a power. Use for exponential calculations, squaring, cubing. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=modulo,
            description="Calculate remainder of division. Use for checking divisibility. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=sqrt,
            description="Calculate square root. Use for geometry, statistics, physics. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=sin,
            description="Calculate sine of an angle in radians. Use for trigonometry and wave functions. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=cos,
            description="Calculate cosine of an angle in radians. Use for trigonometry and projections. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=tan,
            description="Calculate tangent of an angle in radians. Use for trigonometry and slopes. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=log,
            description="Calculate natural logarithm (base e). Use for exponential growth and entropy. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=log10,
            description="Calculate base-10 logarithm. Use for pH, decibels, magnitude comparisons. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=factorial,
            description="Calculate factorial. Use for permutations, combinations, probability. Category: Mathematics",
        ),
        FunctionTool.from_defaults(
            fn=evaluate_rpn,
            description="Evaluate Reverse Polish Notation expressions. Use for complex math without parentheses. Category: Mathematics",
        ),
    ]
