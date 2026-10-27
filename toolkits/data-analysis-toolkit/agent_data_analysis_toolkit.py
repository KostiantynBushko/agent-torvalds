"""
Data Analysis Toolkit - the LlamaIndex agent adapter.

This module is the **agent-facing half** of the data analysis toolkit.
It turns the analysis operations of :mod:`operations` into LlamaIndex
``FunctionTool`` objects, so the agent can call them.

It is the **only** module of the toolkit that knows about LlamaIndex.
The library half (``operations.py``) stays free of it, so the
operations remain usable - and testable - as a plain Python library.

Importing this adapter
----------------------
The toolkit lives in a hyphenated directory
(``toolkits/data-analysis-toolkit/``), which is not a valid Python
identifier, so it is reached through the alias that
``toolkits/__init__.py`` registers::

    from toolkits.data_analysis_toolkit.agent_data_analysis_toolkit import get_all_tools

The adapter pulls the core package in with a **relative** import
(``from . import ...``), so the adapter and the library share one set of
module objects - there is never a second copy of ``operations.py`` in
memory.

The adapter also re-exports the thirteen analysis operations, so a star
import keeps working the way it did when the toolkit was a single
module::

    from toolkits.data_analysis_toolkit.agent_data_analysis_toolkit import *

Category: Data / Analysis
Retriever Keywords: pandas, dataframe, analysis, statistics, aggregate, pivot, filter
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

# The operations carry the logger; the adapter re-exports it so that the
# whole toolkit logs through one logger, as it did when the toolkit was a
# single module at the project root.
from .operations import logger

__all__ = [
    "logger",
    "get_all_tools",
    # The operations are re-exported so that the adapter is a drop-in
    # replacement for the old top-level ``agent_data_analysis_toolkit``
    # module.
    "read_excel_to_df",
    "read_csv_to_df",
    "describe_data",
    "filter_data",
    "aggregate_data",
    "pivot_table",
    "detect_missing_data",
    "correlation_matrix",
    "export_dataframe",
    "get_unique_values",
    "sort_data",
    "compute_statistics",
    "get_dataframe_info",
]


def get_all_tools() -> list[FunctionTool]:
    """
    Return all data analysis tools as FunctionTool objects for on-demand loading.
    
    Each tool includes category metadata for better retrieval.
    
    Returns:
        list[FunctionTool]: List of data analysis FunctionTool objects
    """
    logger.info("get_all_tools called for data analysis toolkit")
    return [
        FunctionTool.from_defaults(
            fn=read_excel_to_df,
            description="Load an Excel file and return data as a list of dictionaries. Category: Data / Analysis",
        ),
        FunctionTool.from_defaults(
            fn=read_csv_to_df,
            description="Load a CSV file and return data as a list of dictionaries. Category: Data / Analysis",
        ),
        FunctionTool.from_defaults(
            fn=describe_data,
            description="Generate descriptive statistics summary for all numeric columns. Category: Data / Analysis",
        ),
        FunctionTool.from_defaults(
            fn=filter_data,
            description="Filter rows based on a condition (e.g., '> 100'). Category: Data / Analysis",
        ),
        FunctionTool.from_defaults(
            fn=aggregate_data,
            description="Group data and apply aggregation (sum, mean, count, etc.). Category: Data / Analysis",
        ),
        FunctionTool.from_defaults(
            fn=pivot_table,
            description="Create a pivot table from tabular data. Category: Data / Analysis",
        ),
        FunctionTool.from_defaults(
            fn=detect_missing_data,
            description="Detect and report missing/null values in the data. Category: Data / Analysis",
        ),
        FunctionTool.from_defaults(
            fn=correlation_matrix,
            description="Compute correlation matrix for numeric columns. Category: Data / Analysis",
        ),
        FunctionTool.from_defaults(
            fn=export_dataframe,
            description="Export a list of dictionaries to Excel or CSV file. Category: Data / Analysis",
        ),
        FunctionTool.from_defaults(
            fn=get_unique_values,
            description="Get unique/distinct values in a column. Category: Data / Analysis",
        ),
        FunctionTool.from_defaults(
            fn=sort_data,
            description="Sort data by a specified column. Category: Data / Analysis",
        ),
        FunctionTool.from_defaults(
            fn=compute_statistics,
            description="Compute detailed statistics (mean, median, std, etc.) for a single column. Category: Data / Analysis",
        ),
        FunctionTool.from_defaults(
            fn=get_dataframe_info,
            description="Get DataFrame information including shape, columns, and data types. Category: Data / Analysis",
        ),
    ]
