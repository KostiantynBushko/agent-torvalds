"""
Linux Toolkit - the LlamaIndex agent adapter.

This module is the **agent-facing half** of the Linux toolkit.  It turns
the shell-execution and system-inspection operations of
:mod:`operations` into LlamaIndex ``FunctionTool`` objects, so the agent
can call them.

It is the **only** module of the toolkit that knows about LlamaIndex.  The
library half (``operations.py``) stays free of it, so the operations
remain usable - and testable - as a plain Python library.

Importing this adapter
----------------------
The toolkit lives in a hyphenated directory (``toolkits/linux-toolkit/``),
which is not a valid Python identifier, so it is reached through the alias
that ``toolkits/__init__.py`` registers::

    from toolkits.linux_toolkit.agent_linux_toolkit import get_all_tools

The adapter pulls the core package in with a **relative** import
(``from . import ...``), so the adapter and the library share one set of
module objects - there is never a second copy of ``operations.py`` in
memory.

The adapter also re-exports the six Linux operations, so a star import
keeps working the way it did when the toolkit was a single module::

    from toolkits.linux_toolkit.agent_linux_toolkit import *

Category: System
Retriever Keywords: shell, command, linux, execute, system, permissions, environment
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
    check_file_permissions,
    execute_multiple_commands,
    execute_shell_command,
    get_system_info,
    parse_command_output,
    run_command_with_env,
)

# The operations carry the logger; the adapter re-exports it so that the
# whole toolkit logs through one logger, as it did when the toolkit was a
# single module at the project root.
from .operations import logger

__all__ = [
    "logger",
    "get_all_tools",
    # The operations are re-exported so that the adapter is a drop-in
    # replacement for the old top-level ``agent_linux_toolkit`` module.
    "execute_shell_command",
    "execute_multiple_commands",
    "parse_command_output",
    "get_system_info",
    "check_file_permissions",
    "run_command_with_env",
]


def get_all_tools() -> list[FunctionTool]:
    """
    Return all Linux tools as FunctionTool objects for on-demand loading.
    
    Each tool includes category metadata for better retrieval.
    
    Returns:
        list[FunctionTool]: List of Linux FunctionTool objects
    """
    return [
        FunctionTool.from_defaults(
            fn=execute_shell_command,
            description="Execute a shell command. Use for running any terminal command with timeout and working directory support. Category: System",
        ),
        FunctionTool.from_defaults(
            fn=execute_multiple_commands,
            description="Execute multiple shell commands sequentially. Use for batch operations and command pipelines. Category: System",
        ),
        FunctionTool.from_defaults(
            fn=parse_command_output,
            description="Parse command output into structured format. Use for splitting output into lines and extracting metadata. Category: System",
        ),
        FunctionTool.from_defaults(
            fn=get_system_info,
            description="Get system information including OS, CPU, memory, and disk. Use for diagnostics and monitoring. Category: System",
        ),
        FunctionTool.from_defaults(
            fn=check_file_permissions,
            description="Check file permissions, owner, and group. Use for inspecting file access rights. Category: System",
        ),
        FunctionTool.from_defaults(
            fn=run_command_with_env,
            description="Execute command with custom environment variables. Use for isolated execution contexts. Category: System",
        ),
    ]
