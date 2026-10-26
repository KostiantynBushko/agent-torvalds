"""
APT Toolkit - the LlamaIndex agent adapter.

This module is the **agent-facing half** of the APT toolkit.  It turns the
package-resolution, sudo-handling and installation operations of
:mod:`operations` into LlamaIndex ``FunctionTool`` objects, so the agent
can call them.

It is the **only** module of the toolkit that knows about LlamaIndex.  The
library half (``operations.py``) stays free of it, so the operations
remain usable - and testable - as a plain Python library.

Importing this adapter
----------------------
The toolkit lives in a hyphenated directory (``toolkits/apt-toolkit/``),
which is not a valid Python identifier, so it is reached through the alias
that ``toolkits/__init__.py`` registers::

    from toolkits.apt_toolkit.agent_apt_toolkit import get_all_tools

The adapter pulls the core package in with a **relative** import
(``from . import ...``), so the adapter and the library share one set of
module objects - there is never a second copy of ``operations.py`` in
memory.

The adapter also re-exports the operations, so a star import keeps
working the way it did when the toolkit was a single module::

    from toolkits.apt_toolkit.agent_apt_toolkit import *

Category: System / Package Management
Retriever Keywords: apt, package, install, debian, ubuntu, sudo, missing, dependency
"""

from __future__ import annotations

from llama_index.core.tools import FunctionTool

# The core package is imported with a *relative* import.  That is the only
# form that resolves both inside this repository (where the directory name
# carries a hyphen) and in a standalone installation of the package.
#
# The names come from the package itself, so the adapter and the library
# always share one set of module objects.
from .operations import (
    check_command_exists,
    clear_sudo_cache,
    find_package_for_command,
    get_default_prompt_method,
    install_multiple_packages,
    install_package,
    interactive_install_missing_command,
    prompt_sudo_password,
    set_default_prompt_method,
    test_sudo_password,
)

# The operations carry the logger; the adapter re-exports it so that the
# whole toolkit logs through one logger, as it did when the toolkit was a
# single module at the project root.
from .operations import logger

__all__ = [
    "logger",
    "get_all_tools",
    # The operations are re-exported so that the adapter is a drop-in
    # replacement for the old top-level ``agent_apt_toolkit`` module.
    "find_package_for_command",
    "check_command_exists",
    "prompt_sudo_password",
    "test_sudo_password",
    "clear_sudo_cache",
    "install_package",
    "install_multiple_packages",
    "interactive_install_missing_command",
    "set_default_prompt_method",
    "get_default_prompt_method",
]


# ---------------------------------------------------------------------------
# 5. Tool Registry
# ---------------------------------------------------------------------------

def get_all_tools() -> list[FunctionTool]:
    """
    Return all APT package tools as FunctionTool objects for on-demand loading.

    Each tool includes category metadata for better retrieval.

    Returns:
        list[FunctionTool]: List of APT FunctionTool objects
    """
    logger.info("get_all_tools called")
    return [
        FunctionTool.from_defaults(
            fn=find_package_for_command,
            description="Find which APT package provides a given command/binary. Use for resolving missing tools to installable packages. Category: System / Package Management",
        ),
        FunctionTool.from_defaults(
            fn=check_command_exists,
            description="Check if a command/binary is available in the system PATH. Use for verifying tool availability. Category: System / Package Management",
        ),
        FunctionTool.from_defaults(
            fn=install_package,
            description="Install an APT package with sudo handling. Use for installing system packages on Debian/Ubuntu. Supports 'console' and 'whiptail' password methods. Category: System / Package Management",
        ),
        FunctionTool.from_defaults(
            fn=install_multiple_packages,
            description="Install multiple APT packages sequentially. Use for batch installations. Supports 'console' and 'whiptail' password methods. Category: System / Package Management",
        ),
        FunctionTool.from_defaults(
            fn=interactive_install_missing_command,
            description="End-to-end workflow: detect missing command, resolve to package, and install it. Use for automatic dependency resolution. Supports 'console' and 'whiptail' password methods. Category: System / Package Management",
        ),
        FunctionTool.from_defaults(
            fn=prompt_sudo_password,
            description="Obtain sudo password using multiple fallback strategies (env var, cache, console, whiptail). Use for credential handling in package installation. Category: System / Package Management",
        ),
        FunctionTool.from_defaults(
            fn=test_sudo_password,
            description="Test if a sudo password is valid. Use for credential verification. Category: System / Package Management",
        ),
        FunctionTool.from_defaults(
            fn=clear_sudo_cache,
            description="Clear the cached sudo password. Use for security or when password changes. Category: System / Package Management",
        ),
        FunctionTool.from_defaults(
            fn=set_default_prompt_method,
            description="Set the default password prompt method ('console' or 'whiptail') for the session. Use to switch between stdin and whiptail dialogs. Category: System / Package Management",
        ),
        FunctionTool.from_defaults(
            fn=get_default_prompt_method,
            description="Get the current default password prompt method. Use to check which method is configured. Category: System / Package Management",
        ),
    ]

def get_all_tools() -> list[FunctionTool]:
    """
    Return all APT package tools as FunctionTool objects for on-demand loading.

    Each tool includes category metadata for better retrieval.

    Returns:
        list[FunctionTool]: List of APT FunctionTool objects
    """
    logger.info("get_all_tools called")
    return [
        FunctionTool.from_defaults(
            fn=find_package_for_command,
            description="Find which APT package provides a given command/binary. Use for resolving missing tools to installable packages. Category: System / Package Management",
        ),
        FunctionTool.from_defaults(
            fn=check_command_exists,
            description="Check if a command/binary is available in the system PATH. Use for verifying tool availability. Category: System / Package Management",
        ),
        FunctionTool.from_defaults(
            fn=install_package,
            description="Install an APT package with sudo handling. Use for installing system packages on Debian/Ubuntu. Supports 'console' and 'whiptail' password methods. Category: System / Package Management",
        ),
        FunctionTool.from_defaults(
            fn=install_multiple_packages,
            description="Install multiple APT packages sequentially. Use for batch installations. Supports 'console' and 'whiptail' password methods. Category: System / Package Management",
        ),
        FunctionTool.from_defaults(
            fn=interactive_install_missing_command,
            description="End-to-end workflow: detect missing command, resolve to package, and install it. Use for automatic dependency resolution. Supports 'console' and 'whiptail' password methods. Category: System / Package Management",
        ),
        FunctionTool.from_defaults(
            fn=prompt_sudo_password,
            description="Obtain sudo password using multiple fallback strategies (env var, cache, console, whiptail). Use for credential handling in package installation. Category: System / Package Management",
        ),
        FunctionTool.from_defaults(
            fn=test_sudo_password,
            description="Test if a sudo password is valid. Use for credential verification. Category: System / Package Management",
        ),
        FunctionTool.from_defaults(
            fn=clear_sudo_cache,
            description="Clear the cached sudo password. Use for security or when password changes. Category: System / Package Management",
        ),
        FunctionTool.from_defaults(
            fn=set_default_prompt_method,
            description="Set the default password prompt method ('console' or 'whiptail') for the session. Use to switch between stdin and whiptail dialogs. Category: System / Package Management",
        ),
        FunctionTool.from_defaults(
            fn=get_default_prompt_method,
            description="Get the current default password prompt method. Use to check which method is configured. Category: System / Package Management",
        ),
    ]

