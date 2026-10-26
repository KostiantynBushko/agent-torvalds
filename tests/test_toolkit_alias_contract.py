"""
Contract tests for the toolkit import aliases.

The hyphenated toolkits cannot be reached with a plain ``import``
statement, so ``toolkits/__init__.py`` registers a valid-identifier alias for
each of them::

    toolkits.MikroTik-RouterOS   ->  toolkits.mikrotik_routeros
    toolkits.shodan-toolkit      ->  toolkits.shodan_toolkit
    toolkits.math-toolkit        ->  toolkits.math_toolkit
    toolkits.git-toolkit         ->  toolkits.git_toolkit
    toolkits.github-toolkit      ->  toolkits.github_toolkit
    toolkits.os-toolkit          ->  toolkits.os_toolkit
    toolkits.linux-toolkit       ->  toolkits.linux_toolkit
    toolkits.apt-toolkit         ->  toolkits.apt_toolkit
    toolkits.windows-toolkit     ->  toolkits.windows_toolkit
    toolkits.db-toolkit          ->  toolkits.db_toolkit
    toolkits.xlsx-toolkit        ->  toolkits.xlsx_toolkit

This module pins down the two properties that alias has to have.

**1. The canonical path is a literal.**  The alias used to be computed
(``__name__ + ".mikrotik_routeros"``).  That is equivalent at run time, but
invisible to every *static* reader - an IDE, an import resolver, a linter, a
packaging tool - which can only look for a name it can read.  A computed
alias therefore looks exactly like a package with no import path at all, and
such a tool reports it as a missing reference.

**2. The alias covers the submodules.**  Registering only the root module is
not enough: ``from toolkits.mikrotik_routeros.parser import parse_identity``
used to load ``parser.py`` a *second* time under the alias name.  The two
copies defined *different* ``RouterIdentity`` and ``CommandResult`` classes,
so an ``isinstance`` check across the boundary silently failed.

No network access is required.

Authoritative spec: ``investigate/MikroTik-RouterOS/MODULE_SPECIFICATION.md``
"""

from __future__ import annotations

import ast
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

#: The repository root: ``<root>/tests/<this file>``.
REPO_ROOT = Path(__file__).resolve().parents[1]

#: The alias shim.
ALIAS_SHIM = REPO_ROOT / "toolkits" / "__init__.py"

#: The canonical alias name and the real package it stands for.
MIKROTIK_ALIAS = "mikrotik_routeros"
MIKROTIK_REAL = "toolkits.MikroTik-RouterOS"

SHODAN_ALIAS = "shodan_toolkit"
SHODAN_REAL = "toolkits.shodan-toolkit"

MATH_ALIAS = "math_toolkit"
MATH_REAL = "toolkits.math-toolkit"

GIT_ALIAS = "git_toolkit"
GIT_REAL = "toolkits.git-toolkit"

GITHUB_ALIAS = "github_toolkit"
GITHUB_REAL = "toolkits.github-toolkit"

OS_ALIAS = "os_toolkit"
OS_REAL = "toolkits.os-toolkit"

LINUX_ALIAS = "linux_toolkit"
LINUX_REAL = "toolkits.linux-toolkit"

APT_ALIAS = "apt_toolkit"
APT_REAL = "toolkits.apt-toolkit"

WINDOWS_ALIAS = "windows_toolkit"
WINDOWS_REAL = "toolkits.windows-toolkit"

DB_ALIAS = "db_toolkit"
DB_REAL = "toolkits.db-toolkit"

XLSX_ALIAS = "xlsx_toolkit"
XLSX_REAL = "toolkits.xlsx-toolkit"

#: The alias of each toolkit and the ``__init__.py`` that must carry a
#: code-level reference to it.
TOOLKITS = (
    (MIKROTIK_ALIAS, MIKROTIK_REAL, REPO_ROOT / "toolkits" / "MikroTik-RouterOS" / "__init__.py"),
    (SHODAN_ALIAS, SHODAN_REAL, REPO_ROOT / "toolkits" / "shodan-toolkit" / "__init__.py"),
    (MATH_ALIAS, MATH_REAL, REPO_ROOT / "toolkits" / "math-toolkit" / "__init__.py"),
    (GIT_ALIAS, GIT_REAL, REPO_ROOT / "toolkits" / "git-toolkit" / "__init__.py"),
    (GITHUB_ALIAS, GITHUB_REAL, REPO_ROOT / "toolkits" / "github-toolkit" / "__init__.py"),
    (OS_ALIAS, OS_REAL, REPO_ROOT / "toolkits" / "os-toolkit" / "__init__.py"),
    (LINUX_ALIAS, LINUX_REAL, REPO_ROOT / "toolkits" / "linux-toolkit" / "__init__.py"),
    (APT_ALIAS, APT_REAL, REPO_ROOT / "toolkits" / "apt-toolkit" / "__init__.py"),
    (WINDOWS_ALIAS, WINDOWS_REAL, REPO_ROOT / "toolkits" / "windows-toolkit" / "__init__.py"),
    (DB_ALIAS, DB_REAL, REPO_ROOT / "toolkits" / "db-toolkit" / "__init__.py"),
    (XLSX_ALIAS, XLSX_REAL, REPO_ROOT / "toolkits" / "xlsx-toolkit" / "__init__.py"),
)

#: The agent adapter of each toolkit: the alias of its package, the module
#: name it carries inside that package, and the file it lives in.
#:
#: The adapter is a **submodule** of the toolkit package.  It is the one
#: module of a toolkit that imports LlamaIndex, so it is never published
#: eagerly - it is imported on demand through the alias.
ADAPTERS = (
    (
        MIKROTIK_ALIAS,
        "agent_mikrotik_toolkit",
        REPO_ROOT / "toolkits" / "MikroTik-RouterOS" / "agent_mikrotik_toolkit.py",
    ),
    (
        SHODAN_ALIAS,
        "agent_shodan_toolkit",
        REPO_ROOT / "toolkits" / "shodan-toolkit" / "agent_shodan_toolkit.py",
    ),
    (
        MATH_ALIAS,
        "agent_math_toolkit",
        REPO_ROOT / "toolkits" / "math-toolkit" / "agent_math_toolkit.py",
    ),
    (
        GIT_ALIAS,
        "agent_git_toolkit",
        REPO_ROOT / "toolkits" / "git-toolkit" / "agent_git_toolkit.py",
    ),
    (
        GITHUB_ALIAS,
        "agent_github_toolkit",
        REPO_ROOT / "toolkits" / "github-toolkit" / "agent_github_toolkit.py",
    ),
    (
        OS_ALIAS,
        "agent_os_toolkit",
        REPO_ROOT / "toolkits" / "os-toolkit" / "agent_os_toolkit.py",
    ),
    (
        LINUX_ALIAS,
        "agent_linux_toolkit",
        REPO_ROOT / "toolkits" / "linux-toolkit" / "agent_linux_toolkit.py",
    ),
    (
        APT_ALIAS,
        "agent_apt_toolkit",
        REPO_ROOT / "toolkits" / "apt-toolkit" / "agent_apt_toolkit.py",
    ),
    (
        WINDOWS_ALIAS,
        "agent_windows_toolkit",
        REPO_ROOT / "toolkits" / "windows-toolkit" / "agent_windows_toolkit.py",
    ),
    (
        DB_ALIAS,
        "agent_db_toolkit",
        REPO_ROOT / "toolkits" / "db-toolkit" / "agent_db_toolkit.py",
    ),
    (
        XLSX_ALIAS,
        "agent_xlsx_toolkit",
        REPO_ROOT / "toolkits" / "xlsx-toolkit" / "agent_xlsx_toolkit.py",
    ),
)

#: The adapter module names, for the checks that have to skip them.
ADAPTER_MODULES = tuple(name for _, name, _ in ADAPTERS)

#: The modules the shim never publishes eagerly.
#
#: The **adapters** import LlamaIndex, and ``import toolkits`` must
#: never pull the framework into the process.  The **``__main__``
#: modules** are executed, not imported: publishing one puts it in
#: ``sys.modules``, and ``runpy`` then refuses to execute it, so
#: ``python -m <toolkit>`` breaks.
NEVER_PUBLISHED = ADAPTER_MODULES + ("__main__",)


def _module_level_strings(path: Path) -> list[str]:
    """Return the string literals assigned at module level in *path*.

    The module docstring is excluded: prose that merely *mentions* a name
    is not a reference to it, which is exactly the distinction that made
    the computed alias invisible to a static reader.
    """
    tree = ast.parse(path.read_text())
    body = list(tree.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]

    values: list[str] = []
    for node in body:
        candidates = []
        if isinstance(node, ast.Assign):
            candidates = list(node.value.elts) if isinstance(node.value, ast.Tuple) else [node.value]
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            candidates = [node.value]
        for value in candidates:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                values.append(value.value)
    return values


# ---------------------------------------------------------------------------
# 1. The canonical path is a literal
# ---------------------------------------------------------------------------


class TestStaticReference:
    """A static reader has to be able to find the canonical import path."""

    def test_the_alias_shim_exists(self):
        """The shim is the file that registers the aliases."""
        assert ALIAS_SHIM.is_file()

    @pytest.mark.parametrize(
        "dotted",
        [
            f"toolkits.{MIKROTIK_ALIAS}",
            f"toolkits.{SHODAN_ALIAS}",
            f"toolkits.{MATH_ALIAS}",
            f"toolkits.{GIT_ALIAS}",
            f"toolkits.{GITHUB_ALIAS}",
            f"toolkits.{OS_ALIAS}",
            f"toolkits.{LINUX_ALIAS}",
            f"toolkits.{APT_ALIAS}",
            f"toolkits.{WINDOWS_ALIAS}",
            f"toolkits.{DB_ALIAS}",
            f"toolkits.{XLSX_ALIAS}",
        ],
    )
    def test_the_canonical_dotted_path_is_a_literal(self, dotted):
        """The full dotted path must be written out, not computed."""
        source = ALIAS_SHIM.read_text()
        assert f'"{dotted}"' in source, (
            f"{dotted} is not a literal in {ALIAS_SHIM.name}; a computed alias is "
            "invisible to a static reader"
        )

    @pytest.mark.parametrize(
        "alias",
        [
            MIKROTIK_ALIAS,
            SHODAN_ALIAS,
            MATH_ALIAS,
            GIT_ALIAS,
            GITHUB_ALIAS,
            OS_ALIAS,
            LINUX_ALIAS,
            APT_ALIAS,
            WINDOWS_ALIAS,
            DB_ALIAS,
            XLSX_ALIAS,
        ],
    )
    def test_the_bare_alias_name_is_a_literal(self, alias):
        """The bare module name must be greppable as well."""
        assert f'"{alias}"' in ALIAS_SHIM.read_text()

    @pytest.mark.parametrize("alias,real,init_file", TOOLKITS)
    def test_the_package_carries_a_code_level_reference(self, alias, real, init_file):
        """The toolkit's own ``__init__.py`` must name its canonical alias."""
        assert init_file.is_file(), init_file
        assert alias in _module_level_strings(init_file), (
            f"{init_file} carries no code-level reference to {alias!r}"
        )

    @pytest.mark.parametrize(
        "constant,expected",
        [
            ("_MIKROTIK_ALIAS", f"toolkits.{MIKROTIK_ALIAS}"),
            ("_SHODAN_ALIAS", f"toolkits.{SHODAN_ALIAS}"),
            ("_MATH_ALIAS", f"toolkits.{MATH_ALIAS}"),
            ("_GIT_ALIAS", f"toolkits.{GIT_ALIAS}"),
            ("_GITHUB_ALIAS", f"toolkits.{GITHUB_ALIAS}"),
            ("_OS_ALIAS", f"toolkits.{OS_ALIAS}"),
            ("_LINUX_ALIAS", f"toolkits.{LINUX_ALIAS}"),
            ("_APT_ALIAS", f"toolkits.{APT_ALIAS}"),
            ("_WINDOWS_ALIAS", f"toolkits.{WINDOWS_ALIAS}"),
            ("_DB_ALIAS", f"toolkits.{DB_ALIAS}"),
            ("_XLSX_ALIAS", f"toolkits.{XLSX_ALIAS}"),
        ],
    )
    def test_the_alias_is_not_computed(self, constant, expected):
        """The old ``__name__ + ".alias"`` form must not come back.

        The check is made on the *code*, not on the file text: the module
        docstring describes the old form on purpose.
        """
        tree = ast.parse(ALIAS_SHIM.read_text())
        assigned = None
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == constant:
                        assigned = node.value
        assert assigned is not None, f"{constant} is not assigned at module level"
        assert isinstance(assigned, ast.Constant), (
            f"{constant} is computed, not a literal; a static reader cannot "
            "resolve a computed alias"
        )
        assert assigned.value == expected


# ---------------------------------------------------------------------------
# 2. The alias covers the submodules
# ---------------------------------------------------------------------------


class TestSingleInstance:
    """There must be exactly one instance of every module in memory."""

    @pytest.mark.parametrize("alias,real,init_file", TOOLKITS)
    def test_the_alias_is_the_same_object(self, alias, real, init_file):
        """The alias and the real package are one object, not a copy."""
        # Importing the real package imports its parent, and the parent is
        # the shim that registers the alias.
        package = importlib.import_module(real)
        assert sys.modules[f"toolkits.{alias}"] is package

    @pytest.mark.parametrize("alias,real,init_file", TOOLKITS)
    def test_no_submodule_is_loaded_twice(self, alias, real, init_file):
        """Every submodule resolves to the same object through both spellings."""
        package = importlib.import_module(real)
        package_path = getattr(package, "__path__", None)
        assert package_path, f"{real} is not a package"

        import pkgutil

        checked = 0
        for info in pkgutil.iter_modules(package_path):
            if info.name in NEVER_PUBLISHED:
                # The adapters are imported on demand, never eagerly - they
                # pull in LlamaIndex.  A __main__ module is executed, not
                # imported.  Both get their own test below.
                continue
            real_module = importlib.import_module(f"{real}.{info.name}")
            alias_module = sys.modules.get(f"toolkits.{alias}.{info.name}")
            assert alias_module is not None, (
                f"toolkits.{alias}.{info.name} was not published under the alias"
            )
            assert alias_module is real_module, (
                f"{info.name} exists twice: {real_module} and {alias_module}"
            )
            checked += 1
        assert checked > 0, f"{real} exposes no submodule to check"

    def test_importing_a_submodule_through_the_alias_does_not_copy_it(self):
        """The exact import that used to create a second copy."""
        from toolkits.mikrotik_routeros.parser import parse_identity

        real_parser = importlib.import_module(f"{MIKROTIK_REAL}.parser")
        assert parse_identity is real_parser.parse_identity

    @pytest.mark.parametrize("alias,adapter,path", ADAPTERS)
    def test_the_adapter_is_reachable_through_the_alias(self, alias, adapter, path):
        """The adapter resolves to one object through its package alias."""
        assert path.is_file(), f"{path} does not exist"

        module = importlib.import_module(f"toolkits.{alias}.{adapter}")
        assert sys.modules[f"toolkits.{alias}.{adapter}"] is module

        # And the *other* spelling must not produce a second copy.
        assert importlib.import_module(module.__name__) is module

    def test_importing_toolkits_does_not_import_llamaindex(self):
        """``import toolkits`` must not drag LlamaIndex into the process.

        The adapters are the only LlamaIndex-dependent modules of a
        toolkit, and they are published on demand rather than eagerly.
        """
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys, toolkits; "
                "print('LEAK' if 'llama_index' in sys.modules else 'CLEAN')",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )

        assert result.returncode == 0, result.stderr
        assert "CLEAN" in result.stdout, result.stdout

    def test_the_alias_does_not_add_a_second_set_of_classes(self):
        """One file, one class - not two classes with the same name."""
        from toolkits.mikrotik_routeros import (
            CommandCategory,
            CommandResult,
            MikroTikError,
            RouterIdentity,
        )

        models = importlib.import_module(f"{MIKROTIK_REAL}.models")
        exceptions = importlib.import_module(f"{MIKROTIK_REAL}.exceptions")

        assert RouterIdentity is models.RouterIdentity
        assert CommandResult is models.CommandResult
        assert CommandCategory is models.CommandCategory
        assert MikroTikError is exceptions.MikroTikError


class TestInstanceIdentity:
    """A value produced through the alias must satisfy the real classes."""

    IDENTITY_OUTPUT = """\
                   uptime: 3d4h5m6s
                  version: 7.19.4 (stable)
             serial-number: HEX0123456789
                   model: RB5009UG+S+
"""

    def test_a_parsed_identity_satisfies_the_package_class(self):
        """``isinstance`` across the alias boundary must hold."""
        from toolkits.mikrotik_routeros import RouterIdentity
        from toolkits.mikrotik_routeros.parser import parse_identity

        identity = parse_identity(self.IDENTITY_OUTPUT)
        assert isinstance(identity, RouterIdentity)

    def test_the_parsed_identity_comes_from_the_real_module(self):
        """The value must not carry the alias namespace as its origin."""
        from toolkits.mikrotik_routeros.parser import parse_identity

        identity = parse_identity(self.IDENTITY_OUTPUT)
        assert type(identity).__module__ == f"{MIKROTIK_REAL}.models"


# ---------------------------------------------------------------------------
# 3. The shim keeps its degradation contract
# ---------------------------------------------------------------------------


class TestNeverPublished:
    """Some modules must never be published eagerly.

    The shim publishes every submodule of a toolkit under the toolkit's
    alias, so that both spellings resolve to one module object.  Two
    kinds of module are excluded:

    * the **agent adapters** - they import LlamaIndex, and ``import
      toolkits`` must never pull the framework into the process;
    * the **``__main__`` modules** - a ``__main__`` module is executed,
      not imported.  Publishing it puts it in ``sys.modules``, and
      ``runpy`` then refuses to execute it, so ``python -m <toolkit>``
      breaks with a RuntimeWarning.
    """

    def test_the_shim_declares_the_never_published_modules(self):
        """The exclusion has to be written down, not implied."""
        source = ALIAS_SHIM.read_text()
        assert "NEVER_PUBLISHED" in source, (
            "the shim does not declare which modules are never published"
        )
        assert '"__main__"' in source, (
            "the __main__ module is not excluded from the eager publication"
        )

    @pytest.mark.parametrize("alias,real,init_file", TOOLKITS)
    def test_no_main_module_is_published(self, alias, real, init_file):
        """No ``__main__`` module may sit in ``sys.modules`` under an alias."""
        importlib.import_module(real)

        published = f"toolkits.{alias}.__main__"
        assert published not in sys.modules, (
            f"{published} was published eagerly; \"python -m\" would refuse "
            "to execute it"
        )

    def test_the_entry_point_of_a_toolkit_with_one_still_works(self):
        """``python -m <toolkit>`` has to work.

        The APT toolkit carries a ``__main__`` entry point for its
        command-line interface, and the Shodan toolkit carries one for
        its own.  Both were broken by the eager publication.
        """
        for module, argument in (
            ("toolkits.apt_toolkit", "--show-method"),
            ("toolkits.shodan_toolkit", "--help"),
        ):
            result = subprocess.run(
                [sys.executable, "-m", module, argument],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=120,
            )

            assert result.returncode == 0, (
                f"python -m {module} {argument} failed:\n{result.stderr}"
            )
            assert "RuntimeWarning" not in result.stderr, result.stderr


class TestDegradation:
    """``import toolkits`` must never raise, whatever the state of a toolkit."""

    def test_importing_the_package_works(self):
        """The shim imports cleanly."""
        toolkits = importlib.import_module("toolkits")
        assert toolkits is not None

    def test_the_exported_names_are_the_registered_ones(self):
        """``from toolkits import *`` must not name a missing alias."""
        toolkits = importlib.import_module("toolkits")
        for name in toolkits.__all__:
            assert hasattr(toolkits, name), name

    def test_a_broken_toolkit_does_not_break_the_import(self):
        """A package that explodes on import must not break ``import toolkits``."""
        code = """
import sys, types
import importlib.abc, importlib.machinery

class Loader(importlib.abc.Loader):
    def create_module(self, spec):
        return None
    def exec_module(self, module):
        raise RuntimeError("boom")

class Finder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "toolkits.MikroTik-RouterOS":
            return importlib.machinery.ModuleSpec(fullname, Loader())
        return None

sys.meta_path.insert(0, Finder())
import toolkits
print("OK")
"""
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert proc.returncode == 0, proc.stderr


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-v"]))
