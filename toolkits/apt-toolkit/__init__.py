"""
APT Toolkit - core package.

Home directory for the APT toolkit.  This package is the **reusable
library** half of the feature:

* The library half contains **no LlamaIndex imports** so it stays
  independently testable and can be used as a plain library by any Python
  application.
* The LlamaIndex adapter is a **submodule of this package** -
  ``agent_apt_toolkit.py`` - and imports this package.  It is the one
  module of the feature that knows about LlamaIndex, and it is imported on
  demand, so importing the library never pulls LlamaIndex in.

Importing this package
----------------------
The directory name contains a hyphen, which is not a valid Python identifier.
Use the alias registered by ``toolkits/__init__.py``::

    from toolkits.apt_toolkit import install_package, find_package_for_command

or load it explicitly::

    import importlib
    apt_toolkit = importlib.import_module("toolkits.apt-toolkit")

Public API
----------

Package resolution
    ``find_package_for_command`` / ``check_command_exists``

Installation
    ``install_package`` / ``install_multiple_packages`` /
    ``interactive_install_missing_command``

Sudo handling
    ``prompt_sudo_password`` / ``test_sudo_password`` /
    ``clear_sudo_cache``

Prompt method
    ``set_default_prompt_method`` / ``get_default_prompt_method``

Layout contract
---------------

::

    toolkits/
    |-- __init__.py                 # package root + import alias shim
    `-- apt-toolkit/                # <-- this directory
        |-- __init__.py             # public API surface (this file)
        |-- operations.py           # the package-resolution, sudo-handling
        |                           # and installation operations - the
        |                           # library half, no LlamaIndex import
        |                           # in here
        |-- agent_apt_toolkit.py    # the LlamaIndex adapter - the only
        |                           # LlamaIndex-dependent module in here
        |-- cli.py                  # the command-line interface
        |-- __main__.py             # ``python -m toolkits.apt_toolkit``
        |-- py.typed                # PEP 561 marker
        `-- tests/                  # module-local tests (no __init__.py!)

Import rules
    * Use **relative imports** inside the package (``from .operations
      import ...``).  They are the only form that works when the package
      is loaded through ``importlib.import_module("toolkits.apt-toolkit")``.
    * Nothing in the **library half** of this package may import
      LlamaIndex.  The agent adapter is the single, named exception - it is
      the only module that knows about LlamaIndex, and it is imported on
      demand through the alias::

          from toolkits.apt_toolkit.agent_apt_toolkit import get_all_tools

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
#: alias ``toolkits.apt_toolkit`` for it.  This attribute is the
#: **code-level** reference to that canonical name: a static reader - an
#: IDE, an import resolver, a linter, a packaging tool - can find the
#: import path here without having to execute the alias shim.
__toolkit_alias__ = "apt_toolkit"

# The submodules are imported with *relative* imports.  That is the only
# form that works when the package is loaded through
# ``importlib.import_module("toolkits.apt-toolkit")`` - an absolute import
# would contain the hyphen and be a SyntaxError.
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
from .operations import logger

__version__ = "0.1.0"

__all__ = [
    # Package resolution
    "find_package_for_command",
    "check_command_exists",
    # Installation
    "install_package",
    "install_multiple_packages",
    "interactive_install_missing_command",
    # Sudo handling
    "prompt_sudo_password",
    "test_sudo_password",
    "clear_sudo_cache",
    # Prompt method
    "set_default_prompt_method",
    "get_default_prompt_method",
    # Logging
    "logger",
    "__version__",
]
