"""
Contract tests for the toolkit import aliases.

The two hyphenated toolkits cannot be reached with a plain ``import``
statement, so ``toolkits/__init__.py`` registers a valid-identifier alias for
each of them::

    toolkits.MikroTik-RouterOS   ->  toolkits.mikrotik_routeros
    toolkits.shodan-toolkit/...  ->  toolkits.shodan_toolkit

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
SHODAN_REAL = "toolkits.shodan-toolkit.src.shodan_toolkit"

#: The alias of each toolkit and the ``__init__.py`` that must carry a
#: code-level reference to it.
TOOLKITS = (
    (MIKROTIK_ALIAS, MIKROTIK_REAL, REPO_ROOT / "toolkits" / "MikroTik-RouterOS" / "__init__.py"),
    (SHODAN_ALIAS, SHODAN_REAL, REPO_ROOT / "toolkits" / "shodan-toolkit" / "src" / "shodan_toolkit" / "__init__.py"),
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
        REPO_ROOT
        / "toolkits"
        / "shodan-toolkit"
        / "src"
        / "shodan_toolkit"
        / "agent_shodan_toolkit.py",
    ),
)

#: The adapter module names, for the checks that have to skip them.
ADAPTER_MODULES = tuple(name for _, name, _ in ADAPTERS)


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

    @pytest.mark.parametrize("dotted", [f"toolkits.{MIKROTIK_ALIAS}", f"toolkits.{SHODAN_ALIAS}"])
    def test_the_canonical_dotted_path_is_a_literal(self, dotted):
        """The full dotted path must be written out, not computed."""
        source = ALIAS_SHIM.read_text()
        assert f'"{dotted}"' in source, (
            f"{dotted} is not a literal in {ALIAS_SHIM.name}; a computed alias is "
            "invisible to a static reader"
        )

    @pytest.mark.parametrize("alias", [MIKROTIK_ALIAS, SHODAN_ALIAS])
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
            if info.name in ADAPTER_MODULES:
                # The adapters are imported on demand, never eagerly - they
                # pull in LlamaIndex.  They get their own test below.
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
