"""
GitHub Toolkit - core package.

Home directory for the GitHub toolkit.  This package is the **reusable
library** half of the feature:

* The library half contains **no LlamaIndex imports** so it stays
  independently testable and can be used as a plain library by any Python
  application.
* The LlamaIndex adapter is a **submodule of this package** -
  ``agent_github_toolkit.py`` - and imports this package.  It is the one
  module of the feature that knows about LlamaIndex, and it is imported on
  demand, so importing the library never pulls LlamaIndex in.

Importing this package
----------------------
The directory name contains a hyphen, which is not a valid Python identifier.
Use the alias registered by ``toolkits/__init__.py``::

    from toolkits.github_toolkit import github_create_pull_request

or load it explicitly::

    import importlib
    github_toolkit = importlib.import_module("toolkits.github-toolkit")

Public API
----------

Tier 4 - authentication and configuration
    ``git_check_auth`` / ``git_get_user_info`` / ``git_configure_credentials``

Tier 3 - Pull Request operations
    ``github_create_pull_request`` / ``github_list_pull_requests`` /
    ``github_get_pull_request`` / ``github_update_pull_request`` /
    ``github_close_pull_request`` / ``github_merge_pull_request`` /
    ``github_comment_on_pull_request`` / ``github_review_file_changes`` /
    ``github_get_pull_request_comments`` / ``github_get_pull_request_reviews``

Layout contract
---------------

::

    toolkits/
    |-- __init__.py                 # package root + import alias shim
    `-- github-toolkit/             # <-- this directory
        |-- __init__.py             # public API surface (this file)
        |-- operations.py           # the GitHub operations - the library
        |                           # half, no LlamaIndex import in here
        |-- agent_github_toolkit.py # the LlamaIndex adapter - the only
        |                           # LlamaIndex-dependent module in here
        |-- py.typed                # PEP 561 marker
        `-- tests/                  # module-local tests (no __init__.py!)

Import rules
    * Use **relative imports** inside the package (``from .operations
      import ...``).  They are the only form that works when the package
      is loaded through ``importlib.import_module("toolkits.github-toolkit")``.
    * Nothing in the **library half** of this package may import
      LlamaIndex.  The agent adapter is the single, named exception - it is
      the only module that knows about LlamaIndex, and it is imported on
      demand through the alias::

          from toolkits.github_toolkit.agent_github_toolkit import get_all_tools

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
#: the alias ``toolkits.github_toolkit`` for it.  This attribute is the
#: **code-level** reference to that canonical name: a static reader - an
#: IDE, an import resolver, a linter, a packaging tool - can find the
#: import path here without having to execute the alias shim.
__toolkit_alias__ = "github_toolkit"

# The submodules are imported with *relative* imports.  That is the only
# form that works when the package is loaded through
# ``importlib.import_module("toolkits.github-toolkit")`` - an absolute
# import would contain the hyphen and be a SyntaxError.
from .operations import (
    git_check_auth,
    git_get_user_info,
    git_configure_credentials,
    github_create_pull_request,
    github_list_pull_requests,
    github_get_pull_request,
    github_update_pull_request,
    github_close_pull_request,
    github_merge_pull_request,
    github_comment_on_pull_request,
    github_review_file_changes,
    github_get_pull_request_comments,
    github_get_pull_request_reviews,
)
from .operations import GITHUB_API_BASE, logger

__version__ = "0.1.0"

__all__ = [
    "git_check_auth",
    "git_get_user_info",
    "git_configure_credentials",
    "github_create_pull_request",
    "github_list_pull_requests",
    "github_get_pull_request",
    "github_update_pull_request",
    "github_close_pull_request",
    "github_merge_pull_request",
    "github_comment_on_pull_request",
    "github_review_file_changes",
    "github_get_pull_request_comments",
    "github_get_pull_request_reviews",
    # Constants
    "GITHUB_API_BASE",
    # Logging
    "logger",
    "__version__",
]
