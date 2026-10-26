"""
OS/File Toolkit - the LlamaIndex agent adapter.

This module is the **agent-facing half** of the OS toolkit.  It turns the
file-system operations of :mod:`operations` into LlamaIndex
``FunctionTool`` objects, so the agent can call them.

It is the **only** module of the toolkit that knows about LlamaIndex.  The
library half (``operations.py``) stays free of it, so the operations remain
usable - and testable - as a plain Python library.

Importing this adapter
----------------------
The toolkit lives in a hyphenated directory (``toolkits/os-toolkit/``),
which is not a valid Python identifier, so it is reached through the alias
that ``toolkits/__init__.py`` registers::

    from toolkits.os_toolkit.agent_os_toolkit import get_all_tools

The adapter pulls the core package in with a **relative** import
(``from . import ...``), so the adapter and the library share one set of
module objects - there is never a second copy of ``operations.py`` in
memory.

The adapter also re-exports the 11 file-system operations, so a star
import keeps working the way it did when the toolkit was a single module::

    from toolkits.os_toolkit.agent_os_toolkit import *

Category: Operating System / File Operations
Retriever Keywords: file, directory, path, copy, move, delete, create, read, write, system info
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
    check_path_exists,
    cp,
    get_system_info,
    ls,
    mkdir,
    mv,
    pwd,
    read_file,
    rm,
    touch,
    write_file,
)

# The operations carry the logger; the adapter re-exports it so that the
# whole toolkit logs through one logger, as it did when the toolkit was a
# single module at the project root.
from .operations import logger

__all__ = [
    "logger",
    "get_all_tools",
    # The operations are re-exported so that the adapter is a drop-in
    # replacement for the old top-level ``agent_os_toolkit`` module.
    "pwd",
    "ls",
    "touch",
    "check_path_exists",
    "mkdir",
    "rm",
    "cp",
    "mv",
    "read_file",
    "write_file",
    "get_system_info",
]


def get_all_tools() -> list[FunctionTool]:
    """
    Return all OS/File tools as FunctionTool objects for on-demand loading.
    
    Each tool includes category metadata for better retrieval.
    
    Returns:
        list[FunctionTool]: List of OS/File FunctionTool objects
    """
    logger.info("get_all_tools called")
    return [
        FunctionTool.from_defaults(
            fn=pwd,
            description="Get current working directory. Use for checking current location. Category: Operating System",
        ),
        FunctionTool.from_defaults(
            fn=ls,
            description="List files and directories. Use for browsing directory contents. Category: Operating System",
        ),
        FunctionTool.from_defaults(
            fn=touch,
            description="Create an empty file. Use for creating new files or updating timestamps. Category: Operating System",
        ),
        FunctionTool.from_defaults(
            fn=check_path_exists,
            description="Check if a file or directory exists. Use for verifying paths before operations. Category: Operating System",
        ),
        FunctionTool.from_defaults(
            fn=mkdir,
            description="Create a new directory. Use for making folders with automatic parent directory creation. Category: Operating System",
        ),
        FunctionTool.from_defaults(
            fn=rm,
            description="Remove a file or directory. Use with caution - this is destructive and irreversible. Category: Operating System",
        ),
        FunctionTool.from_defaults(
            fn=cp,
            description="Copy a file or directory. Use for duplicating files or backing up data. Category: Operating System",
        ),
        FunctionTool.from_defaults(
            fn=mv,
            description="Move or rename a file or directory. Use for relocating or renaming files. Category: Operating System",
        ),
        FunctionTool.from_defaults(
            fn=read_file,
            description="Read file contents. Use for viewing text files, configs, and logs. Category: Operating System",
        ),
        FunctionTool.from_defaults(
            fn=write_file,
            description="Write content to a file. Use for creating or overwriting files. Category: Operating System",
        ),
        FunctionTool.from_defaults(
            fn=get_system_info,
            description="Get system information. Use for OS details, hardware info, and diagnostics. Category: Operating System",
        ),
    ]
