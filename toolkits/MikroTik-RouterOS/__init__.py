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

--------------------------------------------------------------------------------
Intended public API (Phase 1)
--------------------------------------------------------------------------------

This module must export the following names. Until Phase 1 lands they are
declared here as documentation only and are **not** importable yet.

Configuration
    ``MikroTikTarget``      - validated connection target (pydantic v2 model)
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

--------------------------------------------------------------------------------
Layout contract
--------------------------------------------------------------------------------

    toolkits/
    |-- __init__.py                 # package root + import alias shim
    `-- MikroTik-RouterOS/          # <-- this directory
        |-- __init__.py             # public API surface (this file)
        |-- config.py               # MikroTikTarget, TargetRegistry, load_targets
        |-- models.py               # CommandResult, RouterIdentity, CommandCategory
        |-- exceptions.py           # typed error hierarchy
        |-- parser.py               # print / detail / identity parsing
        |-- session.py              # RouterOSSession (exec + session transports)
        |-- safety.py               # risk classifier + confirmation policy
        `-- tests/                  # optional module-local tests
            (no __init__.py here - see the spec, section 3.4)

Import rules
    * Use **relative imports** inside the package (``from .config import ...``).
      They are the only form that works when the package is loaded through
      ``importlib.import_module("toolkits.MikroTik-RouterOS")``.
    * ``asyncssh`` and ``pydantic`` must be imported **lazily** (inside the
      function that needs them) or behind a ``try/except ImportError`` guard,
      so that importing this package never breaks the agent boot.
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

__version__ = "0.1.0"

# Phase 1 populates this list once the submodules exist.
# TODO(Phase 1): replace with the real public API re-exports.
__all__: list[str] = []
