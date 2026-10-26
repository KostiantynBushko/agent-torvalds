"""
Excel XLSX Toolkit - core package.

Home directory for the Excel toolkit.  This package is the **reusable
library** half of the feature:

* The library half contains **no LlamaIndex imports** so it stays
  independently testable and can be used as a plain library by any Python
  application.
* The LlamaIndex adapter is a **submodule of this package** -
  ``agent_xlsx_toolkit.py`` - and imports this package.  It is the one
  module of the feature that knows about LlamaIndex, and it is imported on
  demand, so importing the library never pulls LlamaIndex in.

The library half depends on ``openpyxl`` - the Excel file format is the
file format - and on the standard library, and on nothing else.

Importing this package
----------------------
The directory name contains a hyphen, which is not a valid Python identifier.
Use the alias registered by ``toolkits/__init__.py``::

    from toolkits.xlsx_toolkit import read_xlsx_file, write_xlsx_file

or load it explicitly::

    import importlib
    xlsx_toolkit = importlib.import_module("toolkits.xlsx-toolkit")

Public API
----------

Reading and writing
    ``read_xlsx_file`` / ``write_xlsx_file``

Sheets
    ``get_sheet_names`` / ``copy_sheet`` / ``get_dimensions``

Cells
    ``get_cell_value`` / ``set_cell_value``

Formatting and workbooks
    ``apply_style`` / ``create_empty_workbook``

Layout contract
---------------

::

    toolkits/
    |-- __init__.py                 # package root + import alias shim
    `-- xlsx-toolkit/                # <-- this directory
        |-- __init__.py             # public API surface (this file)
        |-- operations.py           # the nine Excel operations - the
        |                           # library half, no LlamaIndex import
        |                           # in here
        |-- agent_xlsx_toolkit.py   # the LlamaIndex adapter - the only
        |                           # LlamaIndex-dependent module in here
        |-- py.typed                # PEP 561 marker
        `-- tests/                  # module-local tests (no __init__.py!)

Import rules
    * Use **relative imports** inside the package (``from .operations
      import ...``).  They are the only form that works when the package
      is loaded through ``importlib.import_module("toolkits.xlsx-toolkit")``.
    * Nothing in the **library half** of this package may import
      LlamaIndex.  The agent adapter is the single, named exception - it is
      the only module that knows about LlamaIndex, and it is imported on
      demand through the alias::

          from toolkits.xlsx_toolkit.agent_xlsx_toolkit import get_all_tools

Test placement
    * The module-local ``tests/`` directory must **not** contain
      ``__init__.py``.  With it, pytest resolves the test module against
      the *root* ``tests`` package, the relative imports fail with
      "attempted relative import beyond top-level package", and a basename
      collision with a root test file aborts the whole collection.
    * The suite must run with ``--import-mode=importlib`` (set in
      ``pytest.ini``) and the test directory must be listed in
      ``testpaths``.
"""

from __future__ import annotations

#: The canonical, import-safe alias for this package.
#:
#: The directory name contains a hyphen, so the package cannot be reached
#: with a plain ``import`` statement.  ``toolkits/__init__.py`` registers the
#: alias ``toolkits.xlsx_toolkit`` for it.  This attribute is the
#: **code-level** reference to that canonical name: a static reader - an
#: IDE, an import resolver, a linter, a packaging tool - can find the
#: import path here without having to execute the alias shim.
__toolkit_alias__ = "xlsx_toolkit"

# The submodules are imported with *relative* imports.  That is the only
# form that works when the package is loaded through
# ``importlib.import_module("toolkits.xlsx-toolkit")`` - an absolute import
# would contain the hyphen and be a SyntaxError.
from .operations import (
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
from .operations import logger

__version__ = "0.1.0"

__all__ = [
    # Reading and writing
    "read_xlsx_file",
    "write_xlsx_file",
    # Sheets
    "get_sheet_names",
    "copy_sheet",
    "get_dimensions",
    # Cells
    "get_cell_value",
    "set_cell_value",
    # Formatting and workbooks
    "apply_style",
    "create_empty_workbook",
    # Logging
    "logger",
    "__version__",
]
