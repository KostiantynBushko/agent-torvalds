"""
shodan-toolkit
==============

A Python wrapper around the `Shodan <https://www.shodan.io>`_ command-line
interface, designed to expose Shodan's internet-exposure data to
LlamaIndex ``FunctionAgent`` instances.

Quick start::

    from shodan_toolkit import ShodanClient, get_all_tools

    # Structured Python API
    client = ShodanClient()
    results = client.search("apache port:80", limit=5)

    # LlamaIndex tools
    tools = get_all_tools()
    agent = FunctionAgent(tools=tools, llm=llm)

Command-line::

    shodan-toolkit info
    shodan-toolkit search "nginx" --limit 5
    shodan-toolkit doctor

Layout contract
---------------

This directory **is** the package - there is no ``src/`` level and no
nested package directory.  The modules of the toolkit sit next to each
other, and the tests and the examples sit next to them::

    toolkits/
    |-- __init__.py                 # package root + import alias shim
    `-- shodan-toolkit/             # <-- this directory
        |-- __init__.py             # public API surface (this file)
        |-- __main__.py             # `python -m shodan_toolkit` entry point
        |-- agent.py                # FunctionAgent factory
        |-- agent_shodan_toolkit.py # the LlamaIndex adapter - the only
        |                           # LlamaIndex-dependent module in here
        |-- cli.py                  # command-line interface
        |-- client.py               # typed Python API
        |-- config.py               # configuration resolution
        |-- parsers.py              # text -> structured records
        |-- runner.py               # subprocess execution
        |-- tools.py                # LlamaIndex FunctionTool wrappers
        |-- conftest.py             # makes the package importable for pytest
        |-- pyproject.toml          # the standalone distribution
        `-- tests/                  # module-local tests (no __init__.py!)

Import rules
    * Use **relative imports** inside the package (``from .client import ...``).
      They are the only form that works when the package is loaded through
      ``importlib.import_module("toolkits.shodan-toolkit")``.
    * The directory name contains a hyphen, so the package cannot be reached
      with a plain ``import`` statement.  Inside this repository it is
      reached through the alias that ``toolkits/__init__.py`` registers::

          from toolkits.shodan_toolkit import ShodanClient

      Installed as a standalone distribution it keeps the plain
      ``shodan_toolkit`` name::

          from shodan_toolkit import ShodanClient

    * The module-local ``tests/`` directory must **not** contain
      ``__init__.py``, and the suite must run with
      ``--import-mode=importlib`` (set in ``pytest.ini``).
"""

from __future__ import annotations

#: The canonical, import-safe alias for this package.
#:
#: The toolkit lives in a hyphenated directory
#: (``toolkits/shodan-toolkit/``), so it cannot be reached with a plain
#: ``import`` statement.  ``toolkits/__init__.py`` registers the alias
#: ``toolkits.shodan_toolkit`` for it.  This attribute is the
#: **code-level** reference to that canonical name: a static reader - an
#: IDE, an import resolver, a linter, a packaging tool - can find the
#: import path here without having to execute the alias shim.
__toolkit_alias__ = "shodan_toolkit"

__version__ = "0.1.0"

from .agent import (
    DEFAULT_SYSTEM_PROMPT,
    build_agent,
    build_tools,
    shodan_toolkit_context,
)
from .client import ShodanClient
from .config import ShodanConfig, load_config
from .runner import (
    CommandResult,
    ShodanAuthError,
    ShodanCLIError,
    ShodanError,
    ShodanNotInstalledError,
    ShodanRunner,
)
from .tools import (
    TOOL_REGISTRY,
    get_all_tools,
    get_mutating_tools,
    get_readonly_tools,
    get_tools_by_name,
    set_client,
)

__all__ = [
    "__version__",
    # Core
    "ShodanClient",
    "ShodanConfig",
    "load_config",
    # Runner
    "ShodanRunner",
    "CommandResult",
    "ShodanError",
    "ShodanAuthError",
    "ShodanCLIError",
    "ShodanNotInstalledError",
    # Tools
    "get_all_tools",
    "get_readonly_tools",
    "get_mutating_tools",
    "get_tools_by_name",
    "set_client",
    "TOOL_REGISTRY",
    # Agent
    "build_agent",
    "build_tools",
    "shodan_toolkit_context",
    "DEFAULT_SYSTEM_PROMPT",
]
