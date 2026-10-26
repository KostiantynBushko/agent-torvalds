"""
Linux Toolkit - core package.

Home directory for the Linux toolkit.  This package is the **reusable
library** half of the feature:

* The library half contains **no LlamaIndex imports** so it stays
  independently testable and can be used as a plain library by any Python
  application.
* The LlamaIndex adapter is a **submodule of this package** -
  ``agent_linux_toolkit.py`` - and imports this package.  It is the one
  module of the feature that knows about LlamaIndex, and it is imported on
  demand, so importing the library never pulls LlamaIndex in.

This toolkit is the second one in the series whose library half depends on
the **standard library only** - ``subprocess``, ``os``, ``logging`` and
``typing``.  There is no third-party dependency at all, so the shell
operations are usable in any Python that exists.

Importing this package
----------------------
The directory name contains a hyphen, which is not a valid Python identifier.
Use the alias registered by ``toolkits/__init__.py``::

    from toolkits.linux_toolkit import execute_shell_command, get_system_info

or load it explicitly::

    import importlib
    linux_toolkit = importlib.import_module("toolkits.linux-toolkit")

Public API
----------

Command execution
    ``execute_shell_command`` / ``execute_multiple_commands``

Output handling
    ``parse_command_output``

Inspection
    ``get_system_info`` / ``check_file_permissions``

Environment
    ``run_command_with_env``

.. note::
   ``get_system_info`` also exists in the **OS toolkit**
   (``toolkits.os-toolkit/``).  The two are different functions with
   different shapes - this one shells out to ``uname``/``lscpu``/``free``/
   ``df`` and returns their output as strings, the OS one reads
   ``platform`` directly and returns a dictionary of structured fields.
   Both toolkits are loaded into the same process on Linux, so the tool
   menu carries the name twice.  That duplicate is **pre-existing** - it
   is on ``master`` too, and the move neither creates nor changes it.

Layout contract
---------------

::

    toolkits/
    |-- __init__.py                 # package root + import alias shim
    `-- linux-toolkit/              # <-- this directory
        |-- __init__.py             # public API surface (this file)
        |-- operations.py           # the shell and system operations - the
        |                           # library half, no LlamaIndex import
        |                           # in here
        |-- agent_linux_toolkit.py  # the LlamaIndex adapter - the only
        |                           # LlamaIndex-dependent module in here
        |-- py.typed                # PEP 561 marker
        `-- tests/                  # module-local tests (no __init__.py!)

Import rules
    * Use **relative imports** inside the package (``from .operations
      import ...``).  They are the only form that works when the package
      is loaded through ``importlib.import_module("toolkits.linux-toolkit")``.
    * Nothing in the **library half** of this package may import
      LlamaIndex.  The agent adapter is the single, named exception - it is
      the only module that knows about LlamaIndex, and it is imported on
      demand through the alias::

          from toolkits.linux_toolkit.agent_linux_toolkit import get_all_tools

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
#: alias ``toolkits.linux_toolkit`` for it.  This attribute is the
#: **code-level** reference to that canonical name: a static reader - an
#: IDE, an import resolver, a linter, a packaging tool - can find the
#: import path here without having to execute the alias shim.
__toolkit_alias__ = "linux_toolkit"

# The submodules are imported with *relative* imports.  That is the only
# form that works when the package is loaded through
# ``importlib.import_module("toolkits.linux-toolkit")`` - an absolute import
# would contain the hyphen and be a SyntaxError.
from .operations import (
    check_file_permissions,
    execute_multiple_commands,
    execute_shell_command,
    get_system_info,
    parse_command_output,
    run_command_with_env,
)
from .operations import logger

__version__ = "0.1.0"

__all__ = [
    # Command execution
    "execute_shell_command",
    "execute_multiple_commands",
    # Output handling
    "parse_command_output",
    # Inspection
    "get_system_info",
    "check_file_permissions",
    # Environment
    "run_command_with_env",
    # Logging
    "logger",
    "__version__",
]
