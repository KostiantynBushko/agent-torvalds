"""
Tests that assert the layout and packaging contract of the toolkit.

The toolkit directory **is** the package: there is no ``src/`` level and
no nested package directory.  These tests are the permanent guard for that
rule - if the package is ever buried one level deeper again, or if the
LlamaIndex-free rule of the library half is broken, they fail.

They live inside the hyphenated package directory, so they use
**relative** imports (``from .. import ...``).

The suite runs under ``--import-mode=importlib``, which ``pytest.ini``
sets through ``addopts``.
"""

from __future__ import annotations

import ast
import importlib
import subprocess
import sys
from pathlib import Path

from .. import __name__ as PACKAGE_NAME

#: The repository root - three levels up from this file:
#: <root>/toolkits/math-toolkit/tests/test_package_layout.py
REPO_ROOT = Path(__file__).resolve().parents[3]

#: The package directory.
PKG_DIR = REPO_ROOT / "toolkits" / "math-toolkit"

#: The package-local test directory.
PKG_TESTS = PKG_DIR / "tests"

#: The modules the package is made of.
PACKAGE_MODULES = (
    "__init__.py",
    "operations.py",
    "agent_math_toolkit.py",
)


# ---------------------------------------------------------------------------
# The flat layout
# ---------------------------------------------------------------------------


def test_the_package_directory_has_the_exact_name():
    """The directory name is case-sensitive and must match exactly."""
    assert PKG_DIR.name == "math-toolkit"
    assert PKG_DIR.is_dir()


def test_every_module_of_the_package_sits_in_the_package_root():
    """The source files live directly in the toolkit directory."""
    for name in PACKAGE_MODULES:
        assert (PKG_DIR / name).is_file(), f"missing {name}"


def test_the_package_is_not_buried_one_level_deeper():
    """There is no nested package directory and no ``src/`` level."""
    assert not (PKG_DIR / "math_toolkit").exists(), (
        "the package must be the toolkit directory itself, not a directory "
        "inside it"
    )
    assert not (PKG_DIR / "src").exists(), (
        "the package must not sit under a src/ level"
    )


def test_the_package_has_no_stray_modules():
    """Only the modules of the package may live in the package root."""
    found = {
        path.name
        for path in PKG_DIR.glob("*.py")
        if path.name not in PACKAGE_MODULES
    }
    assert found == set(), f"unexpected modules in the package root: {sorted(found)}"


def test_the_package_local_test_directory_has_no_init_py():
    """An __init__.py here breaks the relative imports and aborts collection."""
    assert not (PKG_TESTS / "__init__.py").exists()


def test_the_package_local_tests_are_collected_by_a_bare_pytest_run():
    """A bare pytest run must pick the package-local tests up."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "--no-header"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=600,
    )

    assert "test_package_layout.py" in result.stdout, (
        "the package-local tests were not collected by a bare pytest run"
    )


# ---------------------------------------------------------------------------
# The toolkit is a module, not a loose file at the project root
# ---------------------------------------------------------------------------


def test_the_toolkit_no_longer_sits_at_the_project_root():
    """The old top-level module must be gone.

    The toolkit used to be a single file, ``agent_math_toolkit.py``, next
    to 20 other loose ``agent_*.py`` modules.  A toolkit is now one
    folder, under ``toolkits/``.
    """
    assert not (REPO_ROOT / "agent_math_toolkit.py").exists(), (
        "the toolkit belongs under toolkits/, not at the project root"
    )


def test_the_old_root_test_file_is_gone():
    """The test suite moved into the package."""
    assert not (REPO_ROOT / "tests" / "test_math_toolkit.py").exists(), (
        "the math toolkit tests belong to the toolkit package"
    )


# ---------------------------------------------------------------------------
# The import rules
# ---------------------------------------------------------------------------


def _module_imports(path: Path) -> list[tuple[int, str]]:
    """Return the (line, module) of every import statement in a file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            found.append((node.lineno, node.module or ""))

    return found


#: The sanctioned alias.  An import through it is valid, even though its
#: root is "toolkits" - the alias is the whole point of the shim.
ALIAS_MODULE = "toolkits.math_toolkit"


def _is_absolute_toolkits_import(module: str) -> bool:
    """Whether an import names the package by its absolute path.

    The hyphenated form (``toolkits.math-toolkit``) is a SyntaxError and
    can never appear in valid source.  The alias
    (``toolkits.math_toolkit``) is the sanctioned way in, so it is
    allowed.
    """
    if not module.startswith("toolkits"):
        return False
    return module != ALIAS_MODULE


def test_the_package_uses_relative_imports():
    """No module may import the package by its absolute name.

    The package directory contains a hyphen, so the absolute name is not
    importable - and a relative import is the only form that resolves
    both inside this repository and in a standalone installation.
    """
    offenders: list[str] = []
    for path in sorted(PKG_DIR.glob("*.py")):
        for line, module in _module_imports(path):
            if module.split(".")[0] == "math_toolkit":
                offenders.append(f"{path.name}:{line} -> {module}")
            elif _is_absolute_toolkits_import(module):
                offenders.append(f"{path.name}:{line} -> {module}")

    assert offenders == [], f"absolute package imports found: {offenders}"


def test_the_package_declares_the_canonical_alias():
    """The package carries a code-level reference to its import name."""
    from .. import __toolkit_alias__

    assert __toolkit_alias__ == "math_toolkit"


def test_the_alias_resolves_to_this_package():
    """The alias registered by ``toolkits/__init__.py`` is this package."""
    package = importlib.import_module("toolkits.math-toolkit")
    alias = importlib.import_module("toolkits.math_toolkit")

    assert alias is package
    assert sys.modules["toolkits.math_toolkit"] is package
    assert PACKAGE_NAME == "toolkits.math-toolkit"


def test_the_package_declares_a_version():
    """The package version is exposed as __version__."""
    from .. import __version__

    assert __version__ == "0.1.0"


# ---------------------------------------------------------------------------
# The LlamaIndex boundary
# ---------------------------------------------------------------------------


#: The agent adapter - the one module of the package that knows about
#: LlamaIndex.  It lives inside the package now, next to the code it
#: adapts, so the LlamaIndex-free rule is scoped to the library half.
ADAPTER_FILE = "agent_math_toolkit.py"


def _llamaindex_imports_under_the_package() -> list[str]:
    """Return every LlamaIndex import under the package, adapter included."""
    return [
        f"{path}:{line} -> {module}"
        for path in sorted(PKG_DIR.rglob("*.py"))
        for line, module in _module_imports(path)
        if module.split(".")[0] == "llama_index"
    ]


def test_r1_no_llamaindex_import_in_the_library_half():
    """R1: the library half of the package must not import LlamaIndex.

    The agent adapter is the single, named exception: it is the only
    module of the feature that knows about LlamaIndex, and it lives inside
    the package now.  The exception is narrow - a LlamaIndex import in
    *any other* module still fails this test.

    The check is AST-based, so prose in a docstring that merely mentions
    the module name does not trip it - only a real import statement does.
    """
    adapter_prefix = str(PKG_DIR / ADAPTER_FILE)
    offenders = [
        entry
        for entry in _llamaindex_imports_under_the_package()
        if not entry.startswith(adapter_prefix)
    ]

    assert offenders == [], f"LlamaIndex imports found: {offenders}"


def test_r1b_the_adapter_is_the_only_llamaindex_dependent_module():
    """The adapter must exist, and it must be the one that imports it."""
    assert (PKG_DIR / ADAPTER_FILE).is_file(), (
        f"the agent adapter must live in the package: {PKG_DIR / ADAPTER_FILE}"
    )

    adapter_prefix = str(PKG_DIR / ADAPTER_FILE)
    adapter_imports = [
        entry
        for entry in _llamaindex_imports_under_the_package()
        if entry.startswith(adapter_prefix)
    ]

    assert adapter_imports, "the adapter does not import LlamaIndex any more"


def test_r1c_importing_the_library_does_not_import_llamaindex():
    """The behavioural guarantee behind R1.

    Importing the toolkit package - or the alias shim - must not pull
    LlamaIndex into the process.  The adapter is imported on demand, by
    whoever actually needs it.
    """
    statements = (
        "import toolkits",
        "import importlib, toolkits; "
        "importlib.import_module('toolkits.math-toolkit')",
    )

    for statement in statements:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"import sys; {statement}; "
                "print('LEAK' if 'llama_index' in sys.modules else 'CLEAN')",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )

        assert result.returncode == 0, result.stderr
        assert "CLEAN" in result.stdout, f"{statement} pulled in LlamaIndex"


def test_the_adapter_is_reachable_through_the_alias():
    """The adapter is a submodule of the package, reached through the alias."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from toolkits.math_toolkit.agent_math_toolkit "
            "import get_all_tools; "
            "print('OK' if callable(get_all_tools) else 'BROKEN')",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_the_adapter_and_the_library_share_one_module_object():
    """The adapter must not load a second copy of ``operations``.

    The adapter pulls the library in with a relative import, so the
    functions it exposes are the very same objects the library defines.
    """
    adapter = importlib.import_module("toolkits.math_toolkit.agent_math_toolkit")
    operations = importlib.import_module("toolkits.math-toolkit.operations")

    assert adapter.add is operations.add
    assert adapter.evaluate_rpn is operations.evaluate_rpn


def test_r5_importing_toolkits_never_raises():
    """R5: 'import toolkits' must succeed even if the toolkit is broken."""
    result = subprocess.run(
        [sys.executable, "-c", "import toolkits; print('OK')"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
