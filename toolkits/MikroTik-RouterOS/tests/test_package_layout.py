"""
Tests that assert the layout and packaging contract of the toolkit.

These tests live inside the hyphenated package directory, so they use
**relative** imports (``from .. import ...``).

They are the permanent guard for the rules in MODULE_SPECIFICATION.md
sections 2.2, 3.4 and 4.2. If one of them fails, the repository has broken
a documented contract.

This directory must **not** contain an ``__init__.py`` - see
MODULE_SPECIFICATION.md section 3.4. The suite runs under
``--import-mode=importlib``, which ``pytest.ini`` sets through ``addopts``.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

from .. import __name__ as PACKAGE_NAME

#: The repository root - three levels up from this file:
#: <root>/toolkits/MikroTik-RouterOS/tests/test_package_layout.py
REPO_ROOT = Path(__file__).resolve().parents[3]

#: The package directory.
PKG_DIR = REPO_ROOT / "toolkits" / "MikroTik-RouterOS"

#: The package-local test directory.
PKG_TESTS = PKG_DIR / "tests"


# ---------------------------------------------------------------------------
# Section 2.2 - the naming rules
# ---------------------------------------------------------------------------

def test_the_package_directory_has_the_exact_name():
    """The directory name is case-sensitive and must match exactly."""
    assert PKG_DIR.name == "MikroTik-RouterOS"
    assert PKG_DIR.is_dir()


def test_the_package_root_exists():
    assert (REPO_ROOT / "toolkits").is_dir()
    assert (REPO_ROOT / "toolkits" / "__init__.py").is_file()


def test_every_module_of_the_specification_exists():
    for name in (
        "__init__.py",
        "config.py",
        "models.py",
        "exceptions.py",
        "parser.py",
        "session.py",
        "safety.py",
        "py.typed",
    ):
        assert (PKG_DIR / name).is_file(), f"missing {name}"


# ---------------------------------------------------------------------------
# Section 3.4 - the pytest contract
# ---------------------------------------------------------------------------

def test_the_package_local_test_directory_has_no_init_py():
    """An __init__.py here breaks relative imports and aborts collection."""
    assert not (PKG_TESTS / "__init__.py").exists()


def test_pytest_ini_sets_the_import_mode():
    """pytest 9.1.1 has no 'import-mode' ini option - it must be in addopts."""
    ini = (REPO_ROOT / "pytest.ini").read_text(encoding="utf-8")

    assert "--import-mode=importlib" in ini, (
        "pytest.ini must set '--import-mode=importlib' through addopts; the "
        "'import-mode = importlib' spelling is silently ignored by pytest 9"
    )


def test_pytest_ini_lists_the_package_local_test_directory():
    ini = (REPO_ROOT / "pytest.ini").read_text(encoding="utf-8")

    assert "toolkits/MikroTik-RouterOS/tests" in ini, (
        "pytest.ini must list the package-local test directory in testpaths, "
        "otherwise a bare pytest run never collects those tests"
    )


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
# Section 4.2 - the binding rules
# ---------------------------------------------------------------------------

#: The sanctioned alias. An import through it is valid, even though its
#: root is "toolkits" - the alias is the whole point of the shim.
ALIAS_MODULE = "toolkits.mikrotik_routeros"


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


def _is_absolute_toolkits_import(module: str) -> bool:
    """Whether an import names the package by its absolute path.

    The hyphenated form (``toolkits.MikroTik-RouterOS``) is a SyntaxError
    and can never appear in valid source. The alias
    (``toolkits.mikrotik_routeros``) is the sanctioned way in, so it is
    allowed.
    """
    if not module.startswith("toolkits"):
        return False
    return module != ALIAS_MODULE


#: The agent adapter - the one module of the package that knows about
#: LlamaIndex.  It lives inside the package now, next to the code it
#: adapts, so the LlamaIndex-free rule is scoped to the library half.
ADAPTER_FILE = "agent_mikrotik_toolkit.py"


def _llamaindex_imports_under_the_package() -> list[str]:
    """Return every LlamaIndex import under the package, adapter included."""
    return [
        f"{path}:{line} -> {module}"
        for path in sorted(PKG_DIR.rglob("*.py"))
        for line, module in _module_imports(path)
        if module.split(".")[0] == "llama_index"
    ]


def test_r1_no_llamaindex_import_under_the_package():
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
        "importlib.import_module('toolkits.MikroTik-RouterOS')",
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
            "from toolkits.mikrotik_routeros.agent_mikrotik_toolkit "
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


def test_r2_only_relative_imports_inside_the_package():
    """R2: no absolute 'toolkits' import statement inside the package.

    The absolute form contains the hyphen and is a SyntaxError, so it can
    never work. The check is AST-based, so prose in a docstring that merely
    mentions the path does not trip it.
    """
    offenders = [
        f"{path}:{line} -> {module}"
        for path in sorted(PKG_DIR.rglob("*.py"))
        for line, module in _module_imports(path)
        if _is_absolute_toolkits_import(module)
    ]

    assert offenders == [], f"absolute toolkits imports found: {offenders}"


def test_r3_optional_dependencies_are_imported_lazily():
    """R3: asyncssh / pydantic / routeros_api are not imported at module level.

    The package must import cleanly when the optional dependencies are
    absent, so they are imported *inside* a function or behind a guard. A
    module-level import is an offender; a function-level one is not.
    """
    guarded = ("asyncssh", "pydantic", "routeros_api")
    offenders: list[str] = []

    for path in sorted(PKG_DIR.rglob("*.py")):
        if path.name == "_compat.py":
            # The compatibility layer is the one place that may try to
            # import pydantic at module level - it guards the import with
            # try/except ImportError.
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"))

        # Collect everything that lives inside a function or class body.
        nested: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                for child in ast.walk(node):
                    nested.add(id(child))

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if id(node) in nested:
                # Inside a function or class body - a lazy import.
                continue
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in guarded:
                        offenders.append(f"{path}:{node.lineno} -> {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in guarded:
                    offenders.append(f"{path}:{node.lineno} -> {node.module}")

    assert offenders == [], f"unguarded optional imports found: {offenders}"


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


def test_the_alias_resolves_to_the_same_package_object():
    """The alias must be the *same* object, so there is one instance."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, toolkits; "
            "from toolkits import mikrotik_routeros as alias; "
            "real = sys.modules['toolkits.MikroTik-RouterOS']; "
            "print('SAME' if alias is real else 'DIFFERENT')",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert "SAME" in result.stdout


def test_the_package_imports_with_no_optional_dependencies():
    """R4: the package must import with zero optional dependencies.

    The check runs in a subprocess with 'pydantic', 'asyncssh' and
    'routeros_api' blocked by a meta-path finder.
    """
    script = """
import sys
from importlib.abc import MetaPathFinder


class Blocker(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".")[0]
        if root in ("pydantic", "asyncssh", "routeros_api"):
            raise ImportError("blocked: " + fullname)
        return None


sys.meta_path.insert(0, Blocker())

import importlib

pkg = importlib.import_module("toolkits.MikroTik-RouterOS")
assert pkg.__version__ == "0.1.0"
assert hasattr(pkg, "MikroTikTarget")
assert hasattr(pkg, "RouterOSSession")
assert hasattr(pkg, "classify")

# The target model must still work without pydantic.
target = pkg.MikroTikTarget(id="r1", host="10.0.0.1")
assert target.port == 22
assert target.id == "r1"

# And the safety classifier must still work.
category, reasons = pkg.classify("/system/resource/print")
assert category.value == "READ_ONLY", (category, reasons)

print("OK")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_the_package_declares_a_version():
    """R8: the package version is exposed as __version__."""
    from .. import __version__

    assert __version__ == "0.1.0"


def test_the_package_name_is_the_hyphenated_one():
    """The package's own __name__ keeps the hyphen - the alias is what changes."""
    assert PACKAGE_NAME == "toolkits.MikroTik-RouterOS"
