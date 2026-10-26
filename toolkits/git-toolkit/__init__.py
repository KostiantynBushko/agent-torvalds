"""
Git Toolkit - core package.

Home directory for the Git toolkit.  This package is the **reusable
library** half of the feature:

* The library half contains **no LlamaIndex imports** so it stays
  independently testable and can be used as a plain library by any Python
  application.
* The LlamaIndex adapter is a **submodule of this package** -
  ``agent_git_toolkit.py`` - and imports this package.  It is the one
  module of the feature that knows about LlamaIndex, and it is imported on
  demand, so importing the library never pulls LlamaIndex in.

Importing this package
----------------------
The directory name contains a hyphen, which is not a valid Python identifier.
Use the alias registered by ``toolkits/__init__.py``::

    from toolkits.git_toolkit import git_get_status, git_commit

or load it explicitly::

    import importlib
    git_toolkit = importlib.import_module("toolkits.git-toolkit")

Public API
----------

Tier 1 - basic operations
    ``git_get_latest_commit`` / ``git_init_repo`` / ``git_add_files`` /
    ``git_commit`` / ``git_get_status`` / ``git_generate_changelog`` /
    ``git_get_recent_changes`` / ``git_update_changelog`` / ``git_get_email`` /
    ``git_init_and_commit`` / ``git_add_all_changes``

Tier 2 - remote operations
    ``git_remote_add`` / ``git_push`` / ``git_remote_get`` /
    ``git_set_upstream`` / ``git_pull`` / ``git_fetch``

Tier 3 - branch management
    ``git_branch_list`` / ``git_branch_create`` / ``git_branch_checkout`` /
    ``git_branch_delete`` / ``git_branch_rename``

Tier 4 - diff & sync
    ``git_diff`` / ``git_diff_staged`` / ``git_merge`` / ``git_rebase`` /
    ``git_log_compare``

Layout contract
---------------

::

    toolkits/
    |-- __init__.py                 # package root + import alias shim
    `-- git-toolkit/                # <-- this directory
        |-- __init__.py             # public API surface (this file)
        |-- operations.py            # the Git operations - the library half,
        |                           # no LlamaIndex import in here
        |-- agent_git_toolkit.py    # the LlamaIndex adapter - the only
        |                           # LlamaIndex-dependent module in here
        |-- py.typed                # PEP 561 marker
        `-- tests/                  # module-local tests (no __init__.py!)

Import rules
    * Use **relative imports** inside the package (``from .operations
      import ...``).  They are the only form that works when the package
      is loaded through ``importlib.import_module("toolkits.git-toolkit")``.
    * Nothing in the **library half** of this package may import
      LlamaIndex.  The agent adapter is the single, named exception - it is
      the only module that knows about LlamaIndex, and it is imported on
      demand through the alias::

          from toolkits.git_toolkit.agent_git_toolkit import get_all_tools

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
#: with a plain ``import`` statement.  ``toolkits/__init__.py`` registers
#: the alias ``toolkits.git_toolkit`` for it.  This attribute is the
#: **code-level** reference to that canonical name: a static reader - an
#: IDE, an import resolver, a linter, a packaging tool - can find the
#: import path here without having to execute the alias shim.
__toolkit_alias__ = "git_toolkit"

# The submodules are imported with *relative* imports.  That is the only
# form that works when the package is loaded through
# ``importlib.import_module("toolkits.git-toolkit")`` - an absolute import
# would contain the hyphen and be a SyntaxError.
from .operations import (
    git_get_latest_commit,
    git_init_repo,
    git_add_files,
    git_commit,
    git_get_status,
    git_generate_changelog,
    git_get_recent_changes,
    git_update_changelog,
    git_get_email,
    git_init_and_commit,
    git_add_all_changes,
    git_remote_add,
    git_push,
    git_remote_get,
    git_set_upstream,
    git_pull,
    git_fetch,
    git_branch_list,
    git_branch_create,
    git_branch_checkout,
    git_branch_delete,
    git_branch_rename,
    git_diff,
    git_diff_staged,
    git_merge,
    git_rebase,
    git_log_compare,
)
from .operations import logger

__version__ = "0.1.0"

__all__ = [
    "git_get_latest_commit",
    "git_init_repo",
    "git_add_files",
    "git_commit",
    "git_get_status",
    "git_generate_changelog",
    "git_get_recent_changes",
    "git_update_changelog",
    "git_get_email",
    "git_init_and_commit",
    "git_add_all_changes",
    "git_remote_add",
    "git_push",
    "git_remote_get",
    "git_set_upstream",
    "git_pull",
    "git_fetch",
    "git_branch_list",
    "git_branch_create",
    "git_branch_checkout",
    "git_branch_delete",
    "git_branch_rename",
    "git_diff",
    "git_diff_staged",
    "git_merge",
    "git_rebase",
    "git_log_compare",
    # Logging
    "logger",
    "__version__",
]
