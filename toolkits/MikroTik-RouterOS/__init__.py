"""
MikroTik RouterOS Toolkit - core package.

Home directory for the MikroTik RouterOS toolkit. This package is the
**reusable library** half of the feature:

* It contains **no LlamaIndex imports** so it stays independently testable and
  can be used as a plain library by any Python application.
* The LlamaIndex adapter lives at the project root as
  ``agent_mikrotik_toolkit.py`` and imports this package.

Importing this package
----------------------
The directory name contains a hyphen, which is not a valid Python identifier.
Use the alias registered by ``toolkits/__init__.py``::

    from toolkits.mikrotik_routeros import MikroTikTarget

or load it explicitly::

    import importlib
    mikrotik = importlib.import_module("toolkits.MikroTik-RouterOS")

Public API
----------

Configuration
    ``MikroTikTarget``      - validated connection target
    ``TargetRegistry``      - in-memory registry of targets
    ``load_targets``        - tolerant YAML loader for ``mikrotik_targets.yaml``

Models
    ``CommandResult``       - uniform structured result of a RouterOS command
    ``RouterIdentity``      - model / serial / version / uptime / resources
    ``CommandCategory``     - risk enum: READ_ONLY, LOW, MEDIUM, HIGH, CRITICAL

Session
    ``RouterOSSession``     - async context manager driving the SSH transport

Errors
    ``MikroTikError`` and its subclasses (see ``exceptions.py``)

Safety
    ``classify``            - command -> (CommandCategory, reasons)
    ``requires_confirmation`` / ``requires_hitl``

Layout contract
---------------

::

    toolkits/
    |-- __init__.py                 # package root + import alias shim
    `-- MikroTik-RouterOS/          # <-- this directory
        |-- __init__.py             # public API surface (this file)
        |-- _compat.py              # optional-dependency compatibility layer
        |-- config.py               # MikroTikTarget, TargetRegistry, load_targets
        |-- models.py               # CommandResult, RouterIdentity, CommandCategory
        |-- exceptions.py           # typed error hierarchy
        |-- parser.py               # print / detail / identity parsing
        |-- session.py              # RouterOSSession (exec + session transports)
        |-- safety.py               # risk classifier + confirmation policy
        |-- py.typed                # PEP 561 marker
        `-- tests/                  # module-local tests (no __init__.py!)

Import rules
    * Use **relative imports** inside the package (``from .config import ...``).
      They are the only form that works when the package is loaded through
      ``importlib.import_module("toolkits.MikroTik-RouterOS")``.
    * ``asyncssh`` and ``pydantic`` are imported **lazily** or behind a
      ``try/except ImportError`` guard, so that importing this package never
      breaks the agent boot.
    * Nothing in this package may import LlamaIndex.

Test placement
    * The module-local ``tests/`` directory must **not** contain
      ``__init__.py``. With it, pytest resolves the test module against the
      *root* ``tests`` package, relative imports fail with "attempted
      relative import beyond top-level package", and a basename collision
      with a root test file aborts the whole collection.
    * The suite must run with ``--import-mode=importlib`` (set in
      ``pytest.ini``) and the test directory must be listed in ``testpaths``.

Authoritative spec: ``investigate/MikroTik-RouterOS/MODULE_SPECIFICATION.md``
"""

#: The canonical, import-safe alias for this package.
#:
#: The directory name contains a hyphen, so the package cannot be reached
#: with a plain ``import`` statement.  ``toolkits/__init__.py`` registers
#: the alias ``toolkits.mikrotik_routeros`` for it.  This attribute is the
#: **code-level** reference to that canonical name: a static reader - an
#: IDE, an import resolver, a linter, a packaging tool - can find the
#: import path here without having to execute the alias shim.
__toolkit_alias__ = "mikrotik_routeros"

# The submodules are imported with *relative* imports. That is the only
# form that works when the package is loaded through
# ``importlib.import_module("toolkits.MikroTik-RouterOS")`` - an absolute
# import would contain the hyphen and be a SyntaxError.
#
# The fallback below covers the one remaining case: pytest's "prepend"
# import mode, which imports this file as a *top-level* module (because
# "MikroTik-RouterOS" is not a valid identifier) and then fails on the
# relative imports. In that mode there is no parent package, so the
# submodules are loaded by path instead.
try:
    from .config import (
        DEFAULT_TARGETS_PATH,
        ENV_KEY,
        ENV_PASSWORD,
        MikroTikTarget,
        TargetRegistry,
        load_targets,
    )
    from .exceptions import (
        AuthError,
        CommandRejectedError,
        CommandTimeoutError,
        ConnectionError_,
        ERROR_CODES,
        HostKeyError,
        InteractiveInputRequiredError,
        MikroTikError,
        MultilineUnsupportedError,
        NotAuthorizedError,
        PagingError,
        SafeModeError,
    )
    from .models import CommandCategory, CommandResult, RouterIdentity
    from .safety import (
        classify,
        contains_injection_patterns,
        is_management_path_change,
        requires_confirmation,
        requires_hitl,
    )
    from .session import RouterOSSession
except ImportError:  # pragma: no cover - only in pytest "prepend" mode
    import importlib.util as _importlib_util
    import sys as _sys
    from pathlib import Path as _Path

    _HERE = _Path(__file__).resolve().parent

    # Give the submodules a parent package so that *their* relative imports
    # resolve too. Without this, "from .models import ..." inside safety.py
    # would fail for exactly the same reason.
    #
    # The parent is named "_mikrotik_standalone" rather than __name__:
    # pytest imports this file under the name "__init__", and "__init__" is
    # not a usable package name ("'__init__' is not a package").
    _PACKAGE = "_mikrotik_standalone"
    __package__ = _PACKAGE
    _standalone = _sys.modules[__name__]
    # A module is only a "package" for the import system if it has a
    # __path__. Without this, "from ._compat import ..." inside config.py
    # fails with "'_mikrotik_standalone' is not a package".
    _standalone.__path__ = [str(_HERE)]
    _sys.modules.setdefault(_PACKAGE, _standalone)

    def _load_sibling(_name):
        """Load a submodule by file path, for a package with no parent."""
        _full = f"{_PACKAGE}.{_name}"
        if _full in _sys.modules:
            return _sys.modules[_full]
        _spec = _importlib_util.spec_from_file_location(
            _full, _HERE / f"{_name}.py", submodule_search_locations=None
        )
        _module = _importlib_util.module_from_spec(_spec)
        _sys.modules[_full] = _module
        _spec.loader.exec_module(_module)
        return _module

    _config = _load_sibling("config")
    _exceptions = _load_sibling("exceptions")
    _models = _load_sibling("models")
    _safety = _load_sibling("safety")
    _session = _load_sibling("session")

    DEFAULT_TARGETS_PATH = _config.DEFAULT_TARGETS_PATH
    ENV_KEY = _config.ENV_KEY
    ENV_PASSWORD = _config.ENV_PASSWORD
    MikroTikTarget = _config.MikroTikTarget
    TargetRegistry = _config.TargetRegistry
    load_targets = _config.load_targets

    AuthError = _exceptions.AuthError
    CommandRejectedError = _exceptions.CommandRejectedError
    CommandTimeoutError = _exceptions.CommandTimeoutError
    ConnectionError_ = _exceptions.ConnectionError_
    ERROR_CODES = _exceptions.ERROR_CODES
    HostKeyError = _exceptions.HostKeyError
    InteractiveInputRequiredError = _exceptions.InteractiveInputRequiredError
    MikroTikError = _exceptions.MikroTikError
    MultilineUnsupportedError = _exceptions.MultilineUnsupportedError
    NotAuthorizedError = _exceptions.NotAuthorizedError
    PagingError = _exceptions.PagingError
    SafeModeError = _exceptions.SafeModeError

    CommandCategory = _models.CommandCategory
    CommandResult = _models.CommandResult
    RouterIdentity = _models.RouterIdentity

    classify = _safety.classify
    contains_injection_patterns = _safety.contains_injection_patterns
    is_management_path_change = _safety.is_management_path_change
    requires_confirmation = _safety.requires_confirmation
    requires_hitl = _safety.requires_hitl

    RouterOSSession = _session.RouterOSSession

__version__ = "0.1.0"

__all__ = [
    # Configuration
    "MikroTikTarget",
    "TargetRegistry",
    "load_targets",
    "DEFAULT_TARGETS_PATH",
    "ENV_PASSWORD",
    "ENV_KEY",
    # Models
    "CommandResult",
    "CommandCategory",
    "RouterIdentity",
    # Session
    "RouterOSSession",
    # Errors
    "MikroTikError",
    "AuthError",
    "HostKeyError",
    "ConnectionError_",
    "CommandTimeoutError",
    "CommandRejectedError",
    "MultilineUnsupportedError",
    "InteractiveInputRequiredError",
    "SafeModeError",
    "PagingError",
    "NotAuthorizedError",
    "ERROR_CODES",
    # Safety
    "classify",
    "requires_confirmation",
    "requires_hitl",
    "contains_injection_patterns",
    "is_management_path_change",
    "__version__",
]
