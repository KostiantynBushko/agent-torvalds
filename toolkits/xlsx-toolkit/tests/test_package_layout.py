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
import warnings
from pathlib import Path

from .. import __name__ as PACKAGE_NAME

#: The repository root - three levels up from this file:
#: <root>/toolkits/xlsx-toolkit/tests/test_package_layout.py
REPO_ROOT = Path(__file__).resolve().parents[3]

#: The package directory.
PKG_DIR = REPO_ROOT / "toolkits" / "xlsx-toolkit"

#: The package-local test directory.
PKG_TESTS = PKG_DIR / "tests"

#: The modules the package is made of.
PACKAGE_MODULES = (
    "__init__.py",
    "operations.py",
    "agent_xlsx_toolkit.py",
)


# ---------------------------------------------------------------------------
# The flat layout
# ---------------------------------------------------------------------------


def test_the_package_directory_has_the_exact_name():
    """The directory name is case-sensitive and must match exactly."""
    assert PKG_DIR.name == "xlsx-toolkit"
    assert PKG_DIR.is_dir()


def test_every_module_of_the_package_sits_in_the_package_root():
    """The source files live directly in the toolkit directory."""
    for name in PACKAGE_MODULES:
        assert (PKG_DIR / name).is_file(), f"missing {name}"


def test_the_package_is_not_buried_one_level_deeper():
    """There is no nested package directory and no ``src/`` level."""
    assert not (PKG_DIR / "xlsx_toolkit").exists(), (
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


def test_the_package_is_listed_in_the_project_testpaths():
    """A bare pytest run must reach the package-local tests.

    The package lives in a directory that is not a test directory of its
    own, so ``pytest.ini`` has to list it explicitly - otherwise the
    suite is only ever run by hand.
    """
    config = (REPO_ROOT / "pytest.ini").read_text(encoding="utf-8")
    assert "toolkits/xlsx-toolkit/tests" in config, (
        "the Excel toolkit's tests are not in the project testpaths"
    )


# ---------------------------------------------------------------------------
# The toolkit is a module, not a loose file at the project root
# ---------------------------------------------------------------------------


def test_the_toolkit_no_longer_sits_at_the_project_root():
    """The old top-level module must be gone.

    The toolkit used to be a single file, ``agent_xlsx_toolkit.py``, next
    to the other loose ``agent_*.py`` modules.  A toolkit is now one
    folder, under ``toolkits/``.
    """
    assert not (REPO_ROOT / "agent_xlsx_toolkit.py").exists(), (
        "the toolkit belongs under toolkits/, not at the project root"
    )


def test_the_toolkit_is_tested():
    """The toolkit carries a test suite of its own.

    The Excel toolkit had a suite at the project root; it moved with it.
    """
    assert (PKG_TESTS / "test_operations.py").is_file(), (
        "the Excel toolkit must carry its own test suite"
    )


def test_the_package_carries_the_pep_561_marker():
    """The package declares itself as typed."""
    assert (PKG_DIR / "py.typed").is_file(), "the py.typed marker is missing"


# ---------------------------------------------------------------------------
# The import rules
# ---------------------------------------------------------------------------


def _module_imports(path: Path) -> list[tuple[int, str]]:
    """Return the (line, module) of every import statement in a file.

    The compiler warnings of the parsed file are suppressed: parsing a
    call site is a *read*, and a pre-existing warning in it (an invalid
    escape sequence in ``agent-torvalds.py``) is not this test's
    business.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
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
ALIAS_MODULE = "toolkits.xlsx_toolkit"


def _is_absolute_toolkits_import(module: str) -> bool:
    """Whether an import names the package by its absolute path.

    The hyphenated form (``toolkits.xlsx-toolkit``) is a SyntaxError and
    can never appear in valid source.  The alias
    (``toolkits.xlsx_toolkit``) is the sanctioned way in, so it is
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
            if module.split(".")[0] == "xlsx_toolkit":
                offenders.append(f"{path.name}:{line} -> {module}")
            elif _is_absolute_toolkits_import(module):
                offenders.append(f"{path.name}:{line} -> {module}")

    assert offenders == [], f"absolute package imports found: {offenders}"


def test_the_package_declares_the_canonical_alias():
    """The package carries a code-level reference to its import name."""
    from .. import __toolkit_alias__

    assert __toolkit_alias__ == "xlsx_toolkit"


def test_the_alias_resolves_to_this_package():
    """The alias registered by ``toolkits/__init__.py`` is this package."""
    package = importlib.import_module("toolkits.xlsx-toolkit")
    alias = importlib.import_module("toolkits.xlsx_toolkit")

    assert alias is package
    assert sys.modules["toolkits.xlsx_toolkit"] is package
    assert PACKAGE_NAME == "toolkits.xlsx-toolkit"


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
ADAPTER_FILE = "agent_xlsx_toolkit.py"


def _llamaindex_imports_under_the_package() -> list[str]:
    """Return every LlamaIndex import under the package, adapter included.

    The package-local ``tests/`` directory is skipped: the rule is about
    the *modules of the toolkit*, and a test that asserts the adapter
    returns ``FunctionTool`` objects has to name that class.
    """
    return [
        f"{path}:{line} -> {module}"
        for path in sorted(PKG_DIR.rglob("*.py"))
        if PKG_TESTS not in path.parents
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
        "importlib.import_module('toolkits.xlsx-toolkit')",
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
            "from toolkits.xlsx_toolkit.agent_xlsx_toolkit import get_all_tools; "
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
    """The adapter must not load a second copy of ``operations``."""
    adapter = importlib.import_module("toolkits.xlsx_toolkit.agent_xlsx_toolkit")
    operations = importlib.import_module("toolkits.xlsx-toolkit.operations")

    assert adapter.read_xlsx_file is operations.read_xlsx_file
    assert adapter.write_xlsx_file is operations.write_xlsx_file


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


# ---------------------------------------------------------------------------
# The library half keeps its own dependency profile
# ---------------------------------------------------------------------------


#: The third-party modules the library half is allowed to depend on.
#:
#: The Excel toolkit is built on ``openpyxl`` - the Excel file format is
#: the file format, so an Excel operation is an Excel operation whether
#: or not an agent framework is installed.
ALLOWED_LIBRARY_DEPENDENCIES = frozenset({"openpyxl"})


#: The standard-library modules the library half is allowed to use.
_STDLIB_MODULES = frozenset(
    {
        "os",
        "logging",
        "typing",
    }
)


def test_the_library_half_only_depends_on_the_expected_modules():
    """The library half may not reach for anything else.

    The set is pinned rather than merely "no LlamaIndex", so a new
    dependency cannot slip in unnoticed - and openpyxl cannot quietly
    disappear either.
    """
    library = PKG_DIR / "operations.py"
    found = {
        module.split(".")[0]
        for _, module in _module_imports(library)
        if module
    }
    offenders = {
        name
        for name in found
        if name not in ALLOWED_LIBRARY_DEPENDENCIES and name not in _STDLIB_MODULES
    }

    assert offenders == set(), f"unexpected dependencies in the library half: {offenders}"


def test_the_library_half_keeps_its_third_party_dependencies():
    """openpyxl is what the library half is built on."""
    library = PKG_DIR / "operations.py"
    found = {
        module.split(".")[0]
        for _, module in _module_imports(library)
        if module
    }
    missing = ALLOWED_LIBRARY_DEPENDENCIES - found

    assert missing == set(), f"the library half lost its dependencies: {sorted(missing)}"


def test_the_library_half_keeps_both_openpyxl_imports():
    """Both openpyxl imports have to stay.

    The workbook is read through ``load_workbook`` and ``Workbook``, and
    the styling is applied through the five classes of
    ``openpyxl.styles``.  A lost import is a broken tool at run time.
    """
    source = (PKG_DIR / "operations.py").read_text(encoding="utf-8")
    assert "from openpyxl import load_workbook, Workbook" in source
    assert (
        "from openpyxl.styles import Font, Alignment, Border, Side, PatternFill"
        in source
    )


def test_the_library_half_is_usable_without_the_agent_framework():
    """The library half must import on its own, without LlamaIndex.

    This is the practical counterpart of R1: the Excel operations are
    usable from a plain Python program that has no agent framework
    installed at all.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import importlib; "
            "m = importlib.import_module('toolkits.xlsx-toolkit.operations'); "
            "print('OK' if callable(m.read_xlsx_file) else 'BROKEN')",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


# ---------------------------------------------------------------------------
# The tool surface
# ---------------------------------------------------------------------------


#: The 9 tools the toolkit exposes.  The list is pinned here so that a
#: tool cannot silently disappear from the adapter.
EXPECTED_TOOLS = (
    "read_xlsx_file",
    "write_xlsx_file",
    "get_sheet_names",
    "get_cell_value",
    "set_cell_value",
    "get_dimensions",
    "copy_sheet",
    "apply_style",
    "create_empty_workbook",
)


def test_the_package_exports_every_tool():
    """The library half exports the whole tool surface."""
    package = importlib.import_module("toolkits.xlsx-toolkit")

    missing = [name for name in EXPECTED_TOOLS if not hasattr(package, name)]
    assert missing == [], f"not exported by the package: {missing}"


def test_the_adapter_exposes_every_tool():
    """The adapter re-exports the whole tool surface.

    A star import of the adapter has to keep yielding the tool functions,
    the way it did when the toolkit was a single module.
    """
    adapter = importlib.import_module("toolkits.xlsx_toolkit.agent_xlsx_toolkit")

    missing = [name for name in EXPECTED_TOOLS if not hasattr(adapter, name)]
    assert missing == [], f"not exposed by the adapter: {missing}"


def test_the_adapter_publishes_exactly_those_tools():
    """``get_all_tools()`` returns one tool per exported function."""
    from llama_index.core.tools import FunctionTool

    adapter = importlib.import_module("toolkits.xlsx_toolkit.agent_xlsx_toolkit")

    tools = adapter.get_all_tools()
    assert len(tools) == len(EXPECTED_TOOLS), (
        f"expected {len(EXPECTED_TOOLS)} tools, got {len(tools)}"
    )
    assert all(isinstance(tool, FunctionTool) for tool in tools)

    names = {tool.metadata.name for tool in tools}
    assert names == set(EXPECTED_TOOLS), (
        f"the tool names drifted: {sorted(names ^ set(EXPECTED_TOOLS))}"
    )


def test_the_tool_order_is_stable():
    """The order of the tools is part of what the model sees.

    It is pinned here as well as in the split-verification script, so a
    reordering cannot slip in unnoticed.
    """
    adapter = importlib.import_module("toolkits.xlsx_toolkit.agent_xlsx_toolkit")

    names = [tool.metadata.name for tool in adapter.get_all_tools()]
    assert names == list(EXPECTED_TOOLS), f"the tool order drifted: {names}"


def test_every_tool_carries_the_excel_category():
    """The 9 tools share the Data / Excel category.

    The category is what the startup tool selection menu groups by, so a
    tool that lost it would silently drop out of the menu.
    """
    adapter = importlib.import_module("toolkits.xlsx_toolkit.agent_xlsx_toolkit")

    for tool in adapter.get_all_tools():
        assert "Category: Data / Excel" in tool.metadata.description, (
            f"{tool.metadata.name} lost the Data / Excel category"
        )


def test_the_star_import_of_the_adapter_still_works():
    """``from ... import *`` must bring in the tool functions.

    The toolkit used to be a single module, so a star import of it was
    the natural way to reach the functions.  That has to keep working.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from toolkits.xlsx_toolkit.agent_xlsx_toolkit import *; "
            "print('OK' if callable(read_xlsx_file) else 'BROKEN')",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_the_star_import_yields_exactly_the_tool_surface():
    """The star import publishes the tools - and nothing else.

    The old top-level module had no ``__all__``, so its star import also
    leaked the modules it had imported (``os``, ``logging``, ``openpyxl``).
    The adapter declares ``__all__``, so the leak is gone.

    That is a deliberate change, and it is safe: the retriever and the
    selection menu import the adapter by name, and they use none of the
    leaked names.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from toolkits.xlsx_toolkit.agent_xlsx_toolkit import *; "
            "print('LEAKED' if 'openpyxl' in dir() else 'CLEAN')",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert "CLEAN" in result.stdout, result.stdout


# ---------------------------------------------------------------------------
# The toolkit is optional, like every other toolkit under toolkits/
# ---------------------------------------------------------------------------


#: The modules that used to import the Excel toolkit by its old name.
#: They have to import it through the alias now, behind a guard.
_OLD_IMPORT_SITES = (
    "agent-torvalds.py",
    "agent-torvalds-mw.py",
    "agent_tool_retriever.py",
    "agent_tool_selection.py",
    "agent-torvalds-cpp.py",
)


def test_no_call_site_imports_the_old_module_name():
    """Nothing may import ``agent_xlsx_toolkit`` any more.

    The old name is gone; a call site that still used it would fail at
    import time and take the agent down with it.
    """
    offenders: list[str] = []
    for name in _OLD_IMPORT_SITES:
        path = REPO_ROOT / name
        if not path.is_file():
            continue
        for line, module in _module_imports(path):
            if module == "agent_xlsx_toolkit" or module.startswith("agent_xlsx_toolkit."):
                offenders.append(f"{name}:{line} -> {module}")

    assert offenders == [], f"stale imports of the old module name: {offenders}"


def test_the_call_sites_import_the_adapter_behind_a_guard():
    """A missing or broken Excel toolkit must degrade to "no tools".

    The toolkit became optional with this move, the way every other
    toolkit under ``toolkits/`` already was.  A call site that imports
    it unguarded would turn a broken optional toolkit into a failed
    boot.
    """
    sites = ("agent_tool_retriever.py", "agent_tool_selection.py")

    for name in sites:
        path = REPO_ROOT / name
        if not path.is_file():
            continue
        source = path.read_text(encoding="utf-8")
        assert "toolkits.xlsx_toolkit.agent_xlsx_toolkit" in source, (
            f"{name} does not import the Excel toolkit through the alias"
        )
        assert "except ImportError" in source, (
            f"{name} imports the Excel toolkit without a guard"
        )
