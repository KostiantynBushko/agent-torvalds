"""
Database Toolkit - the LlamaIndex agent adapter.

This module is the **agent-facing half** of the database toolkit.  It turns
the SQL operations of :mod:`operations` into LlamaIndex ``FunctionTool``
objects, so the agent can call them.

It is the **only** module of the toolkit that knows about LlamaIndex.  The
library half (``operations.py``) stays free of it, so the operations
remain usable - and testable - as a plain Python library.

Importing this adapter
----------------------
The toolkit lives in a hyphenated directory (``toolkits/db-toolkit/``),
which is not a valid Python identifier, so it is reached through the
alias that ``toolkits/__init__.py`` registers::

    from toolkits.db_toolkit.agent_db_toolkit import get_all_tools

The adapter pulls the core package in with a **relative** import
(``from . import ...``), so the adapter and the library share one set of
module objects - there is never a second copy of ``operations.py`` in
memory.

The adapter also re-exports the two database operations, so a star import
keeps working the way it did when the toolkit was a single module::

    from toolkits.db_toolkit.agent_db_toolkit import *

Category: Database
Retriever Keywords: sql, postgres, mysql, query, database, schema, rows
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
    run_mysql_query,
    run_postgres_query,
)

# The operations carry the logger; the adapter re-exports it so that the
# whole toolkit logs through one logger, as it did when the toolkit was a
# single module at the project root.
from .operations import logger

__all__ = [
    "logger",
    "get_all_tools",
    # The operations are re-exported so that the adapter is a drop-in
    # replacement for the old top-level ``agent_db_toolkit`` module.
    "run_postgres_query",
    "run_mysql_query",
]


def get_all_tools() -> list[FunctionTool]:
    """
    Return all database tools as FunctionTool objects for on-demand loading.
    
    Each tool includes category metadata for better retrieval.
    
    Returns:
        list[FunctionTool]: List of database FunctionTool objects
    """
    logger.info("get_all_tools called for database toolkit")
    return [
        FunctionTool.from_defaults(
            fn=run_postgres_query,
            description="Run a SQL query on PostgreSQL. Use for SELECT, DDL, DML on Postgres. Category: Database",
        ),
        FunctionTool.from_defaults(
            fn=run_mysql_query,
            description="Run a SQL query on MySQL. Use for SELECT, DDL, DML on MySQL. Category: Database",
        ),
    ]
