"""
Excel XLSX Toolkit - the LlamaIndex agent adapter.

This module is the **agent-facing half** of the Excel toolkit.  It turns
the Excel operations of :mod:`operations` into LlamaIndex ``FunctionTool``
objects, so the agent can call them.

It is the **only** module of the toolkit that knows about LlamaIndex.  The
library half (``operations.py``) stays free of it, so the operations
remain usable - and testable - as a plain Python library.

Importing this adapter
----------------------
The toolkit lives in a hyphenated directory (``toolkits/xlsx-toolkit/``),
which is not a valid Python identifier, so it is reached through the
alias that ``toolkits/__init__.py`` registers::

    from toolkits.xlsx_toolkit.agent_xlsx_toolkit import get_all_tools

The adapter pulls the core package in with a **relative** import
(``from . import ...``), so the adapter and the library share one set of
module objects - there is never a second copy of ``operations.py`` in
memory.

The adapter also re-exports the nine Excel operations, so a star import
keeps working the way it did when the toolkit was a single module::

    from toolkits.xlsx_toolkit.agent_xlsx_toolkit import *

Category: Data / Excel
Retriever Keywords: excel, xlsx, spreadsheet, workbook, worksheet, cells, read, write
"""

from __future__ import annotations

from llama_index.core.tools import FunctionTool

# The core package is imported with a *relative* import.  That is the only
# form that resolves both inside this repository (where the directory name
# carries a hyphen) and in a standalone installation of the package.
#
# The names come from the package itself, so the adapter and the library
# always share one set of module objects.
from . import (
    apply_style,
    copy_sheet,
    create_empty_workbook,
    get_cell_value,
    get_dimensions,
    get_sheet_names,
    read_xlsx_file,
    set_cell_value,
    write_xlsx_file,
)

# The operations carry the logger; the adapter re-exports it so that the
# whole toolkit logs through one logger, as it did when the toolkit was a
# single module at the project root.
from .operations import logger

__all__ = [
    "logger",
    "get_all_tools",
    # The operations are re-exported so that the adapter is a drop-in
    # replacement for the old top-level ``agent_xlsx_toolkit`` module.
    "read_xlsx_file",
    "write_xlsx_file",
    "get_sheet_names",
    "get_cell_value",
    "set_cell_value",
    "get_dimensions",
    "copy_sheet",
    "apply_style",
    "create_empty_workbook",
]


def get_all_tools() -> list[FunctionTool]:
    """
    Return all Excel/XLSX tools as FunctionTool objects for on-demand loading.
    
    Each tool includes category metadata for better retrieval.
    
    Returns:
        list[FunctionTool]: List of Excel FunctionTool objects
    """
    logger.info("get_all_tools called for Excel/XLSX toolkit")
    return [
        FunctionTool.from_defaults(
            fn=read_xlsx_file,
            description="Read data from an Excel .xlsx file. Returns list of dicts with column headers as keys. Category: Data / Excel",
        ),
        FunctionTool.from_defaults(
            fn=write_xlsx_file,
            description="Write data to a new Excel .xlsx file. Accepts list of dictionaries. Category: Data / Excel",
        ),
        FunctionTool.from_defaults(
            fn=get_sheet_names,
            description="List all sheet names in an Excel workbook. Category: Data / Excel",
        ),
        FunctionTool.from_defaults(
            fn=get_cell_value,
            description="Get the value of a specific cell (e.g., A1) in an Excel file. Category: Data / Excel",
        ),
        FunctionTool.from_defaults(
            fn=set_cell_value,
            description="Set the value of a specific cell and save the file. Category: Data / Excel",
        ),
        FunctionTool.from_defaults(
            fn=get_dimensions,
            description="Get the used range dimensions of an Excel sheet. Category: Data / Excel",
        ),
        FunctionTool.from_defaults(
            fn=copy_sheet,
            description="Copy a sheet from one workbook to a new file. Category: Data / Excel",
        ),
        FunctionTool.from_defaults(
            fn=apply_style,
            description="Apply formatting style (bold, color, alignment, border, fill) to a cell range. Category: Data / Excel",
        ),
        FunctionTool.from_defaults(
            fn=create_empty_workbook,
            description="Create a new empty Excel workbook with optional named sheets. Category: Data / Excel",
        ),
    ]
