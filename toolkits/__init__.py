"""
Toolkits package - Reusable domain-specific toolkit modules.

This package contains self-contained Python modules that can be used both:
1. As standalone libraries by other application modules
2. Through optional LlamaIndex FunctionAgent adapters

Each toolkit package should have its own agent adapter at the project root
(e.g., agent_mikrotik_toolkit.py) that depends on LlamaIndex.

--------------------------------------------------------------------------------
Import alias for ``toolkits/MikroTik-RouterOS/``
--------------------------------------------------------------------------------

The MikroTik RouterOS toolkit lives in ``toolkits/MikroTik-RouterOS/``. The
hyphen in ``MikroTik-RouterOS`` is **not a valid Python identifier**, so that
directory can never be reached with a plain ``import`` statement::

    from toolkits.MikroTik-RouterOS import MikroTikTarget   # SyntaxError

``importlib.import_module("toolkits.MikroTik-RouterOS")`` does work, but it is
awkward to use at every call site and it interacts badly with pytest's default
``prepend`` import mode when test modules live inside the hyphenated
directory.

To keep a clean, valid-identifier import path, this module registers an alias
``toolkits.mikrotik_routeros`` that points at the very same package object::

    from toolkits.mikrotik_routeros import MikroTikTarget   # works
    import toolkits.mikrotik_routeros as mikrotik_routeros  # works

The alias is registered only if the package is actually present and importable,
so ``import toolkits`` never fails when the optional toolkit is absent.

.. note::
   When the ``feature/ssh-toolkit`` branch is merged, it also contributes a
   ``toolkits/__init__.py``. The two versions of this file must be combined
   manually - keep this alias block **and** the SSH-toolkit docstring.

Authoritative spec: ``investigate/MikroTik-RouterOS/MODULE_SPECIFICATION.md``
"""

import importlib
import sys

__all__ = ["mikrotik_routeros"]

#: Dotted path of the real (hyphenated) package directory.
_MIKROTIK_PACKAGE = "toolkits.MikroTik-RouterOS"

#: Dotted path of the valid-identifier alias registered in ``sys.modules``.
_MIKROTIK_ALIAS = __name__ + ".mikrotik_routeros"

try:
    _mikrotik = importlib.import_module(_MIKROTIK_PACKAGE)
except Exception:  # noqa: BLE001 - the toolkit is optional; never break `import toolkits`
    # The package is absent, or one of its optional dependencies is missing.
    # The toolkit is designed to degrade gracefully, so this must stay silent.
    _mikrotik = None
else:
    sys.modules[_MIKROTIK_ALIAS] = _mikrotik
    mikrotik_routeros = _mikrotik
