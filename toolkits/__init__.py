"""
Toolkits package - Reusable domain-specific toolkit modules.

This package contains self-contained Python modules that can be used both:
1. As standalone libraries by other application modules
2. Through optional LlamaIndex FunctionAgent adapters

Each toolkit package carries its own agent adapter **inside the package** -
``toolkits/MikroTik-RouterOS/agent_mikrotik_toolkit.py``,
``toolkits/shodan-toolkit/agent_shodan_toolkit.py``,
``toolkits/math-toolkit/agent_math_toolkit.py``,
``toolkits/git-toolkit/agent_git_toolkit.py``,
``toolkits/github-toolkit/agent_github_toolkit.py``,
``toolkits/os-toolkit/agent_os_toolkit.py``,
``toolkits/linux-toolkit/agent_linux_toolkit.py``,
``toolkits/apt-toolkit/agent_apt_toolkit.py`` and
``toolkits/windows-toolkit/agent_windows_toolkit.py``.  The
adapter is the only module of a toolkit that depends on LlamaIndex; the
reusable library half around it does not.

--------------------------------------------------------------------------------
Import aliases for the hyphenated toolkit directories
--------------------------------------------------------------------------------

The MikroTik RouterOS toolkit (``toolkits/MikroTik-RouterOS/``), the
Shodan toolkit (``toolkits/shodan-toolkit/``), the math toolkit
(``toolkits/math-toolkit/``), the Git toolkit
(``toolkits/git-toolkit/``), the GitHub toolkit
(``toolkits/github-toolkit/``), the OS toolkit
(``toolkits/os-toolkit/``), the Linux toolkit
(``toolkits/linux-toolkit/``) and the APT toolkit
(``toolkits/apt-toolkit/``) live in directories whose names
contain a hyphen. A hyphen is **not a valid Python identifier**, so those
directories can never be reached with a plain ``import`` statement::

    from toolkits.MikroTik-RouterOS import MikroKitTarget   # SyntaxError
    from toolkits.shodan-toolkit import ShodanClient        # SyntaxError
    from toolkits.math-toolkit import add                   # SyntaxError
    from toolkits.git-toolkit import git_get_status         # SyntaxError
    from toolkits.github-toolkit import github_create_pull_request   # SyntaxError
    from toolkits.os-toolkit import pwd                              # SyntaxError
    from toolkits.linux-toolkit import execute_shell_command         # SyntaxError
    from toolkits.apt-toolkit import install_package                # SyntaxError
    from toolkits.windows-toolkit import execute_shell_command       # SyntaxError

``importlib.import_module("toolkits.MikroTik-RouterOS")`` does work, but it is
awkward to use at every call site and it interacts badly with pytest's default
``prepend`` import mode when test modules live inside the hyphenated
directory.

To keep a clean, valid-identifier import path, this module registers an alias
for each of them that points at the very same package object::

    from toolkits.mikrotik_routeros import MikroTikTarget   # works
    import toolkits.mikrotik_routeros as mikrotik_routeros  # works
    from toolkits.shodan_toolkit import ShodanClient        # works
    from toolkits.math_toolkit import add                   # works
    from toolkits.git_toolkit import git_get_status         # works
    from toolkits.github_toolkit import github_create_pull_request   # works
    from toolkits.os_toolkit import pwd                              # works
    from toolkits.linux_toolkit import execute_shell_command         # works
    from toolkits.apt_toolkit import install_package                # works
    from toolkits.windows_toolkit import execute_shell_command       # works

The aliases are registered only if the package is actually present and
importable, so ``import toolkits`` never fails when an optional toolkit is
absent.

Both toolkits have the same shape: the hyphenated directory **is** the
package, and the alias points straight at it::

    toolkits/MikroTik-RouterOS/   ->  toolkits.mikrotik_routeros
    toolkits/shodan-toolkit/      ->  toolkits.shodan_toolkit
    toolkits/math-toolkit/        ->  toolkits.math_toolkit
    toolkits/git-toolkit/         ->  toolkits.git_toolkit
    toolkits/github-toolkit/      ->  toolkits.github_toolkit
    toolkits/os-toolkit/          ->  toolkits.os_toolkit
    toolkits/linux-toolkit/       ->  toolkits.linux_toolkit
    toolkits/apt-toolkit/         ->  toolkits.apt_toolkit
    toolkits/windows-toolkit/     ->  toolkits.windows_toolkit

The agent adapters are submodules of their toolkit package, so they are
reached through the same alias::

    from toolkits.mikrotik_routeros.agent_mikrotik_toolkit import get_all_tools
    from toolkits.shodan_toolkit.agent_shodan_toolkit import get_all_tools
    from toolkits.math_toolkit.agent_math_toolkit import get_all_tools
    from toolkits.git_toolkit.agent_git_toolkit import get_all_tools
    from toolkits.github_toolkit.agent_github_toolkit import get_all_tools
    from toolkits.os_toolkit.agent_os_toolkit import get_all_tools
    from toolkits.linux_toolkit.agent_linux_toolkit import get_all_tools
    from toolkits.apt_toolkit.agent_apt_toolkit import get_all_tools
    from toolkits.windows_toolkit.agent_windows_toolkit import get_all_tools

Those nine lines are the canonical import paths of the adapters.  The
adapters themselves are **not** published eagerly - see the note below.

--------------------------------------------------------------------------------
Two properties the alias must have
--------------------------------------------------------------------------------

**1. The canonical path has to be a literal.**

The alias paths below are written out in full, as plain string constants.
They used to be computed - ``__name__ + ".mikrotik_routeros"`` - which is
equivalent at run time but *invisible* to every static reader.  An IDE, an
import resolver, a linter or a packaging tool cannot evaluate ``__name__``;
it can only look for a name it can read.  A computed alias therefore looks
exactly like a package that has no import path at all, and such a tool
reports it as a missing reference.  Spelling the path out keeps the
canonical name greppable and statically resolvable.

**2. The alias has to cover the submodules as well.**

Registering only the root module is not enough.  Without the submodule
handling below, this::

    from toolkits.mikrotik_routeros.parser import parse_identity

loads ``parser.py`` a *second* time - once as
``toolkits.MikroTik-RouterOS.parser`` and once as
``toolkits.mikrotik_routeros.parser`` - and the two copies define
*different* ``RouterIdentity`` and ``CommandResult`` classes.  An
``isinstance`` check across that boundary silently fails, and the process
ends up carrying two sets of classes for the same file.  Every submodule is
therefore imported under its real name and the *same* module object is
published under the alias name, so both spellings resolve to one object.

**3. The agent adapter is never published eagerly.**

Publishing a submodule means *importing* it.  The agent adapter imports
LlamaIndex, and the reusable library half of a toolkit must stay usable
without it - so the adapter is skipped by the eager publication below and
is imported on demand, through the alias, by whoever actually needs it.

``import toolkits`` therefore never pulls LlamaIndex into the process, while
``from toolkits.mikrotik_routeros.agent_mikrotik_toolkit import
get_all_tools`` still resolves to exactly one module object.

.. note::
   When the ``feature/ssh-toolkit`` branch is merged, it also contributes a
   ``toolkits/__init__.py``. The two versions of this file must be combined
   manually - keep this alias block **and** the SSH-toolkit docstring.

Authoritative spec: ``investigate/MikroTik-RouterOS/MODULE_SPECIFICATION.md``
"""

import importlib
import pkgutil
import sys

#: The canonical, import-safe names of the hyphenated toolkits.
#:
#: The bare module names are listed here as literals so that a static reader
#: can find them; the complete dotted paths live in the ``_..._ALIAS``
#: constants below.
_ALIAS_NAMES = (
    "mikrotik_routeros",
    "shodan_toolkit",
    "math_toolkit",
    "git_toolkit",
    "github_toolkit",
    "os_toolkit",
    "linux_toolkit",
    "apt_toolkit",
    "windows_toolkit",
)

#: The agent adapters of the toolkits, by module name.
#:
#: An adapter is the only module of a toolkit that imports LlamaIndex, so it
#: is **not** published eagerly: publishing a submodule means importing it,
#: and ``import toolkits`` must never pull LlamaIndex into the process.
#:
#: The adapters are still reachable, and still resolve to exactly one
#: module object, through the alias of their own package::
#:
#:     from toolkits.mikrotik_routeros.agent_mikrotik_toolkit import get_all_tools
#:     from toolkits.shodan_toolkit.agent_shodan_toolkit import get_all_tools
#:     from toolkits.math_toolkit.agent_math_toolkit import get_all_tools
#:     from toolkits.git_toolkit.agent_git_toolkit import get_all_tools
#:     from toolkits.github_toolkit.agent_github_toolkit import get_all_tools
#:     from toolkits.os_toolkit.agent_os_toolkit import get_all_tools
#:     from toolkits.linux_toolkit.agent_linux_toolkit import get_all_tools
#:     from toolkits.apt_toolkit.agent_apt_toolkit import get_all_tools
#:     from toolkits.windows_toolkit.agent_windows_toolkit import get_all_tools
_ADAPTER_MODULES = (
    "agent_mikrotik_toolkit",
    "agent_shodan_toolkit",
    "agent_math_toolkit",
    "agent_git_toolkit",
    "agent_github_toolkit",
    "agent_os_toolkit",
    "agent_linux_toolkit",
    "agent_apt_toolkit",
    "agent_windows_toolkit",
)

#: The modules that are never published eagerly, whatever package they
#: sit in.
#:
#: A ``__main__`` module is meant to be **executed**, not imported.  If
#: the shim publishes it under the alias, ``runpy`` finds it in
#: ``sys.modules`` and refuses to execute it - so ``python -m
#: <toolkit>`` breaks with a RuntimeWarning.  The Shodan toolkit and the
#: APT toolkit both carry a ``__main__`` entry point, and both were
#: affected.
NEVER_PUBLISHED = ("__main__",)

#: Dotted path of the real (hyphenated) package directory.
_MIKROTIK_PACKAGE = "toolkits.MikroTik-RouterOS"

#: Dotted path of the valid-identifier alias registered in ``sys.modules``.
_MIKROTIK_ALIAS = "toolkits.mikrotik_routeros"


#: Dotted path of the real (hyphenated) package directory.
_SHODAN_PACKAGE = "toolkits.shodan-toolkit"

#: Dotted path of the valid-identifier alias registered in ``sys.modules``.
_SHODAN_ALIAS = "toolkits.shodan_toolkit"


#: Dotted path of the real (hyphenated) package directory.
_MATH_PACKAGE = "toolkits.math-toolkit"

#: Dotted path of the valid-identifier alias registered in ``sys.modules``.
_MATH_ALIAS = "toolkits.math_toolkit"


#: Dotted path of the real (hyphenated) package directory.
_GIT_PACKAGE = "toolkits.git-toolkit"

#: Dotted path of the valid-identifier alias registered in ``sys.modules``.
_GIT_ALIAS = "toolkits.git_toolkit"


#: Dotted path of the real (hyphenated) package directory.
_GITHUB_PACKAGE = "toolkits.github-toolkit"

#: Dotted path of the valid-identifier alias registered in ``sys.modules``.
_GITHUB_ALIAS = "toolkits.github_toolkit"


#: Dotted path of the real (hyphenated) package directory.
_OS_PACKAGE = "toolkits.os-toolkit"

#: Dotted path of the valid-identifier alias registered in ``sys.modules``.
_OS_ALIAS = "toolkits.os_toolkit"


#: Dotted path of the real (hyphenated) package directory.
_LINUX_PACKAGE = "toolkits.linux-toolkit"

#: Dotted path of the valid-identifier alias registered in ``sys.modules``.
_LINUX_ALIAS = "toolkits.linux_toolkit"


#: Dotted path of the real (hyphenated) package directory.
_APT_PACKAGE = "toolkits.apt-toolkit"

#: Dotted path of the valid-identifier alias registered in ``sys.modules``.
_APT_ALIAS = "toolkits.apt_toolkit"


#: Dotted path of the real (hyphenated) package directory.
_WINDOWS_PACKAGE = "toolkits.windows-toolkit"

#: Dotted path of the valid-identifier alias registered in ``sys.modules``.
_WINDOWS_ALIAS = "toolkits.windows_toolkit"


def _publish_submodules(real_dotted: str, alias_dotted: str, package) -> None:
    """Publish every submodule of *package* under the alias namespace.

    Each submodule is imported under its **real** name and the very same
    module object is then published under the alias name.  Both spellings
    therefore resolve to one object, and the classes a submodule defines
    stay identical no matter which spelling imported them.

    A submodule that cannot be imported - typically because an optional
    dependency is missing - is skipped: the toolkit is designed to degrade
    gracefully, so this must stay silent.

    The agent adapters are skipped as well.  They import LlamaIndex, and the
    library half of a toolkit has to stay usable without it; they are
    imported on demand through the alias instead.

    Args:
        real_dotted: The dotted path of the real (hyphenated) package.
        alias_dotted: The dotted path of the valid-identifier alias.
        package: The already imported real package.
    """
    package_path = getattr(package, "__path__", None)
    if not package_path:
        return

    for info in pkgutil.iter_modules(package_path):
        if info.name in _ADAPTER_MODULES:
            # Imported on demand, never eagerly - see _ADAPTER_MODULES.
            continue
        if info.name in NEVER_PUBLISHED:
            # A __main__ module is executed, not imported - see
            # NEVER_PUBLISHED.
            continue
        try:
            module = importlib.import_module(f"{real_dotted}.{info.name}")
        except Exception:  # noqa: BLE001 - an optional dependency may be missing
            continue
        sys.modules[f"{alias_dotted}.{info.name}"] = module


def _register_alias(real_dotted: str, alias_dotted: str):
    """Import *real_dotted* and publish it under *alias_dotted*.

    Args:
        real_dotted: The dotted path of the real (hyphenated) package.
        alias_dotted: The dotted path of the valid-identifier alias.

    Returns:
        The imported package, or ``None`` when it is absent or broken.
    """
    try:
        package = importlib.import_module(real_dotted)
    except Exception:  # noqa: BLE001 - the toolkit is optional; never break `import toolkits`
        # The package is absent, or one of its optional dependencies is missing.
        # The toolkit is designed to degrade gracefully, so this must stay silent.
        return None

    sys.modules[alias_dotted] = package
    _publish_submodules(real_dotted, alias_dotted, package)
    return package


_mikrotik = _register_alias(_MIKROTIK_PACKAGE, _MIKROTIK_ALIAS)
if _mikrotik is not None:
    mikrotik_routeros = _mikrotik


_shodan = _register_alias(_SHODAN_PACKAGE, _SHODAN_ALIAS)
if _shodan is not None:
    shodan_toolkit = _shodan


_math = _register_alias(_MATH_PACKAGE, _MATH_ALIAS)
if _math is not None:
    math_toolkit = _math


_git = _register_alias(_GIT_PACKAGE, _GIT_ALIAS)
if _git is not None:
    git_toolkit = _git


_github = _register_alias(_GITHUB_PACKAGE, _GITHUB_ALIAS)
if _github is not None:
    github_toolkit = _github


_os = _register_alias(_OS_PACKAGE, _OS_ALIAS)
if _os is not None:
    os_toolkit = _os


_linux = _register_alias(_LINUX_PACKAGE, _LINUX_ALIAS)
if _linux is not None:
    linux_toolkit = _linux


_apt = _register_alias(_APT_PACKAGE, _APT_ALIAS)
if _apt is not None:
    apt_toolkit = _apt


_windows = _register_alias(_WINDOWS_PACKAGE, _WINDOWS_ALIAS)
if _windows is not None:
    windows_toolkit = _windows


#: The aliases that are actually available.  ``from toolkits import *`` must
#: not fail when an optional toolkit is missing, so the exported names are
#: the ones that were really registered.
__all__ = [name for name in _ALIAS_NAMES if name in globals()]
