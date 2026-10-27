"""
Data Analysis Toolkit - core package.

Home directory for the data analysis toolkit.  This package is the
**reusable library** half of the feature:

* The library half contains **no LlamaIndex imports** so it stays
  independently testable and can be used as a plain library by any Python
  application.
* The LlamaIndex adapter is a **submodule of this package** -
  ``agent_data_analysis_toolkit.py`` - and imports this package.  It is
  the one module of the feature that knows about LlamaIndex, and it is
  imported on demand, so importing the library never pulls LlamaIndex in.

The library half depends on ``pandas`` - the DataFrame is the data
model - and on ``numpy`` - the numeric column inference of the pivot
table - and on the standard library, and on nothing else.  ``openpyxl``
is needed at *run time*, not at import time: pandas reaches for it when
a workbook is actually read or written.

Importing this package
----------------------
The directory name contains a hyphen, which is not a valid Python identifier.
Use the alias registered by ``toolkits/__init__.py``::

    from toolkits.data_analysis_toolkit import read_excel_to_df, filter_data

or load it explicitly::

    import importlib
    data_analysis_toolkit = importlib.import_module("toolkits.data-analysis-toolkit")

Public API
----------

Loading
    ``read_excel_to_df`` / ``read_csv_to_df``

Summaries
    ``describe_data`` / ``get_dataframe_info`` / ``compute_statistics``

Selecting and reshaping
    ``filter_data`` / ``sort_data`` / ``get_unique_values``

Aggregating
    ``aggregate_data`` / ``pivot_table`` / ``correlation_matrix`` /
    ``detect_missing_data``

Exporting
    ``export_dataframe``

Layout contract
---------------

::

    toolkits/
    |-- __init__.py                 # package root + import alias shim
    `-- data-analysis-toolkit/      # <-- this directory
        |-- __init__.py             # public API surface (this file)
        |-- operations.py           # the thirteen analysis operations -
        |                           # the library half, no LlamaIndex
        |                           # import in here
        |-- agent_data_analysis_toolkit.py
        |                           # the LlamaIndex adapter - the only
        |                           # LlamaIndex-dependent module in here
        |-- py.typed                # PEP 561 marker
        `-- tests/                  # module-local tests (no __init__.py!)

Import rules
    * Use **relative imports** inside the package (``from .operations
      import ...``).  They are the only form that works when the package
      is loaded through ``importlib.import_module("toolkits.data-analysis-toolkit")``.
    * Nothing in the **library half** of this package may import
      LlamaIndex.  The agent adapter is the single, named exception - it is
      the only module that knows about LlamaIndex, and it is imported on
      demand through the alias::

          from toolkits.data_analysis_toolkit.agent_data_analysis_toolkit import get_all_tools

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
#: alias ``toolkits.data_analysis_toolkit`` for it.  This attribute is the
#: **code-level** reference to that canonical name: a static reader - an
#: IDE, an import resolver, a linter, a packaging tool - can find the
#: import path here without having to execute the alias shim.
__toolkit_alias__ = "data_analysis_toolkit"

# The submodules are imported with *relative* imports.  That is the only
# form that works when the package is loaded through
# ``importlib.import_module("toolkits.data-analysis-toolkit")`` - an
# absolute import would contain the hyphen and be a SyntaxError.
from .operations import (
    aggregate_data,
    compute_statistics,
    correlation_matrix,
    describe_data,
    detect_missing_data,
    export_dataframe,
    filter_data,
    get_dataframe_info,
    get_unique_values,
    pivot_table,
    read_csv_to_df,
    read_excel_to_df,
    sort_data,
)
from .operations import logger

__version__ = "0.1.0"

__all__ = [
    # Loading
    "read_excel_to_df",
    "read_csv_to_df",
    # Summaries
    "describe_data",
    "get_dataframe_info",
    "compute_statistics",
    # Selecting and reshaping
    "filter_data",
    "sort_data",
    "get_unique_values",
    # Aggregating
    "aggregate_data",
    "pivot_table",
    "correlation_matrix",
    "detect_missing_data",
    # Exporting
    "export_dataframe",
    # Logging
    "logger",
    "__version__",
]
