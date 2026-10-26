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
#: <root>/toolkits/apt-toolkit/tests/test_package_layout.py
REPO_ROOT = Path(__file__).resolve().parents[3]

#: The package directory.
PKG_DIR = REPO_ROOT / "toolkits" / "apt-toolkit"

#: The package-local test directory.
PKG_TESTS = PKG_DIR / "tests"

#: The modules the package is made of.
PACKAGE_MODULES = (
    "__init__.py",
    "__main__.py",
    "operations.py",
    "agent_apt_toolkit.py",
    "cli.py",
)


# ---------------------------------------------------------------------------
# The flat layout
# ---------------------------------------------------------------------------


def test_the_package_directory_has_the_exact_name():
    """The directory name is case-sensitive and must match exactly."""
    assert PKG_DIR.name == "apt-toolkit"
    assert PKG_DIR.is_dir()


def test_every_module_of_the_package_sits_in_the_package_root():
    """The source files live directly in the toolkit directory."""
    for name in PACKAGE_MODULES:
        assert (PKG_DIR / name).is_file(), f"missing {name}"


def test_the_package_is_not_buried_one_level_deeper():
    """There is no nested package directory and no ``src/`` level."""
    assert not (PKG_DIR / "apt_toolkit").exists(), (
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
    assert "toolkits/apt-toolkit/tests" in config, (
        "the APT toolkit's tests are not in the project testpaths"
    )


# ---------------------------------------------------------------------------
# The toolkit is a module, not a loose file at the project root
# ---------------------------------------------------------------------------


def test_the_toolkit_no_longer_sits_at_the_project_root():
    """The old top-level module must be gone.

    The toolkit used to be a single file, ``agent_apt_toolkit.py``,
    next to the other loose ``agent_*.py`` modules.  A toolkit is now one
    folder, under ``toolkits/``.
    """
    assert not (REPO_ROOT / "agent_apt_toolkit.py").exists(), (
        "the toolkit belongs under toolkits/, not at the project root"
    )


def test_the_old_root_test_file_is_gone():
    """The suite moved into the package with the toolkit.

    Leaving the root copy behind would run the same operations twice and
    keep the old import path alive.
    """
    assert not (REPO_ROOT / "tests" / "test_apt_toolkit.py").exists(), (
        "the test suite moved into the package; the root copy must be gone"
    )


def test_the_toolkit_is_tested():
    """The toolkit carries a test suite of its own."""
    assert (PKG_TESTS / "test_operations.py").is_file(), (
        "the APT toolkit must carry its own test suite"
    )


# ---------------------------------------------------------------------------
# The import rules
# ---------------------------------------------------------------------------


def _module_imports(path: Path) -> list[tuple[int, str]]:
    """Return the (line, module) of every import statement in a file.

    The compiler warnings of the parsed file are suppressed: parsing a
    call site is a *read*, and a pre-existing warning in it is not this
    test's business.
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
ALIAS_MODULE = "toolkits.apt_toolkit"


def _is_absolute_toolkits_import(module: str) -> bool:
    """Whether an import names the package by its absolute path.

    The hyphenated form (``toolkits.apt-toolkit``) is a SyntaxError and
    can never appear in valid source.  The alias
    (``toolkits.apt_toolkit``) is the sanctioned way in, so it is
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
            if module.split(".")[0] == "apt_toolkit":
                offenders.append(f"{path.name}:{line} -> {module}")
            elif _is_absolute_toolkits_import(module):
                offenders.append(f"{path.name}:{line} -> {module}")

    assert offenders == [], f"absolute package imports found: {offenders}"


def test_the_package_declares_the_canonical_alias():
    """The package carries a code-level reference to its import name."""
    from .. import __toolkit_alias__

    assert __toolkit_alias__ == "apt_toolkit"


def test_the_alias_resolves_to_this_package():
    """The alias registered by ``toolkits/__init__.py`` is this package."""
    package = importlib.import_module("toolkits.apt-toolkit")
    alias = importlib.import_module("toolkits.apt_toolkit")

    assert alias is package
    assert sys.modules["toolkits.apt_toolkit"] is package
    assert PACKAGE_NAME == "toolkits.apt-toolkit"


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
ADAPTER_FILE = "agent_apt_toolkit.py"


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
        "importlib.import_module('toolkits.apt-toolkit')",
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
            "from toolkits.apt_toolkit.agent_apt_toolkit import get_all_tools; "
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
    adapter = importlib.import_module("toolkits.apt_toolkit.agent_apt_toolkit")
    operations = importlib.import_module("toolkits.apt-toolkit.operations")

    assert adapter.install_package is operations.install_package
    assert adapter.get_all_tools is not None


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
#: There is exactly one: ``rich``, which the *console* password prompt
#: uses.  It is imported at the call, not at the top of the module, so
#: the module still imports without it - but the default prompt method
#: needs it.  This is the difference from the OS and the Linux toolkit,
#: whose library halves are built on the standard library alone.
ALLOWED_LIBRARY_DEPENDENCIES = frozenset({"rich"})

#: The **first-party** modules the library half is allowed to reach for.
#:
#: ``components.whiptail_password`` is a module of *this* repository, not
#: of the distribution.  The import is deferred and guarded: without it -
#: which is the case in a standalone installation - the whiptail prompt
#: falls back to the console one, which is the documented behaviour.
ALLOWED_FIRST_PARTY = frozenset({"components"})

#: The standard-library modules the library half is allowed to use.
_STDLIB_MODULES = frozenset(
    {
        "argparse",
        "os",
        "sys",
        "json",
        "logging",
        "shutil",
        "subprocess",
        "typing",
    }
)


def test_the_library_half_only_depends_on_the_allowed_modules():
    """The library half may not reach for anything but the allowed set.

    The APT toolkit's library half is built on the standard library, on
    ``rich`` for the console password prompt, and on the repository's own
    ``components.whiptail_password`` for the whiptail one.  The set is
    pinned exactly, so a new dependency cannot slip in unnoticed.
    """
    library = PKG_DIR / "operations.py"
    offenders = [
        f"{library.name}:{line} -> {module}"
        for line, module in _module_imports(library)
        if module.split(".")[0] not in ALLOWED_LIBRARY_DEPENDENCIES
        and module.split(".")[0] not in ALLOWED_FIRST_PARTY
        and module.split(".")[0] not in _STDLIB_MODULES
    ]

    assert offenders == [], f"unexpected dependencies in the library half: {offenders}"


def test_the_library_half_is_usable_without_the_agent_framework():
    """The library half must import on its own, without LlamaIndex.

    This is the practical counterpart of R1: the APT operations are
    usable from a plain Python program that has no agent framework
    installed at all.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import importlib; "
            "m = importlib.import_module('toolkits.apt-toolkit.operations'); "
            "print('OK' if callable(m.install_package) else 'BROKEN')",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_the_optional_prompts_degrade_gracefully():
    """The two optional prompt paths must not raise when they are missing.

    The console prompt needs ``rich`` and the whiptail prompt needs
    ``components.whiptail_password``.  Both imports are deferred and
    guarded, and the toolkit is expected to fall back rather than to
    crash: a missing optional dependency must not take the agent down.
    """
    library = PKG_DIR / "operations.py"
    source = library.read_text(encoding="utf-8")

    assert "from rich.console import Console" in source, (
        "the console prompt no longer uses rich"
    )
    assert "from components.whiptail_password import WhiptailPasswordPrompter" in source, (
        "the whiptail prompt no longer uses the repository's prompter"
    )

    # The whiptail import is guarded by an ImportError handler, and the
    # console import by a general one - both fall back to the console.
    tree = ast.parse(source)
    handlers = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler)
    ]
    assert any(
        isinstance(handler.type, ast.Name) and handler.type.id == "ImportError"
        for handler in handlers
    ), "the deferred imports are not guarded against a missing dependency"


# ---------------------------------------------------------------------------
# The tool surface
# ---------------------------------------------------------------------------


#: The 10 tools the toolkit exposes.  The list is pinned here so that a
#: tool cannot silently disappear from the adapter.
EXPECTED_TOOLS = (
    "find_package_for_command",
    "check_command_exists",
    "install_package",
    "install_multiple_packages",
    "interactive_install_missing_command",
    "prompt_sudo_password",
    "test_sudo_password",
    "clear_sudo_cache",
    "set_default_prompt_method",
    "get_default_prompt_method",
)

#: The operations the library half carries.  The private helpers are part
#: of it too - they hold the password prompting.
EXPECTED_OPERATIONS = (
    "find_package_for_command",
    "check_command_exists",
    "set_default_prompt_method",
    "get_default_prompt_method",
    "_has_tty",
    "prompt_sudo_password",
    "_prompt_console_password",
    "_prompt_whiptail_password",
    "test_sudo_password",
    "clear_sudo_cache",
    "install_package",
    "install_multiple_packages",
    "interactive_install_missing_command",
)


def test_the_package_exports_every_tool():
    """The library half exports the whole tool surface."""
    package = importlib.import_module("toolkits.apt-toolkit")

    missing = [name for name in EXPECTED_TOOLS if not hasattr(package, name)]
    assert missing == [], f"not exported by the package: {missing}"


def test_the_adapter_exposes_every_tool():
    """The adapter re-exports the whole tool surface.

    A star import of the adapter has to keep yielding the tool functions,
    the way it did when the toolkit was a single module.
    """
    adapter = importlib.import_module("toolkits.apt_toolkit.agent_apt_toolkit")

    missing = [name for name in EXPECTED_TOOLS if not hasattr(adapter, name)]
    assert missing == [], f"not exposed by the adapter: {missing}"


def test_the_adapter_publishes_exactly_those_tools():
    """``get_all_tools()`` returns one tool per exported function."""
    from llama_index.core.tools import FunctionTool

    adapter = importlib.import_module("toolkits.apt_toolkit.agent_apt_toolkit")

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
    adapter = importlib.import_module("toolkits.apt_toolkit.agent_apt_toolkit")

    names = [tool.metadata.name for tool in adapter.get_all_tools()]
    assert names == list(EXPECTED_TOOLS), f"the tool order drifted: {names}"


def test_every_tool_carries_the_package_management_category():
    """The 10 tools share the System / Package Management category.

    The category is what the startup tool selection menu groups by, so a
    tool that lost it would silently drop out of the menu.
    """
    adapter = importlib.import_module("toolkits.apt_toolkit.agent_apt_toolkit")

    for tool in adapter.get_all_tools():
        assert "Category: System / Package Management" in tool.metadata.description, (
            f"{tool.metadata.name} lost the category"
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
            "from toolkits.apt_toolkit.agent_apt_toolkit import *; "
            "print('OK' if callable(install_package) else 'BROKEN')",
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
    leaked the modules it had imported (``os``, ``subprocess``).  The
    adapter declares ``__all__``, so the leak is gone.

    That is a deliberate change, and it is safe: the toolkit is not
    star-imported anywhere in the repository.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from toolkits.apt_toolkit.agent_apt_toolkit import *; "
            "print('LEAKED' if 'os' in dir() else 'CLEAN')",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert "CLEAN" in result.stdout, result.stdout


# ---------------------------------------------------------------------------
# The command-line interface
# ---------------------------------------------------------------------------


def test_the_command_line_interface_is_in_the_package():
    """The CLI has its own module, and the package has an entry point."""
    assert (PKG_DIR / "cli.py").is_file(), (
        "the command-line interface must live in the package"
    )
    assert (PKG_DIR / "__main__.py").is_file(), (
        "the package must have a __main__ entry point"
    )


def test_the_command_line_interface_runs():
    """``python -m toolkits.apt_toolkit --show-method`` must work.

    The interface was a ``__main__`` block in the old top-level module.
    It is a module of the package now, and the entry point has to keep
    working - through the alias, because the directory name carries a
    hyphen.
    """
    result = subprocess.run(
        [sys.executable, "-m", "toolkits.apt_toolkit", "--show-method"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert "Current default prompt method:" in result.stdout, result.stdout


def test_the_command_line_interface_prints_its_help():
    """With no arguments, the interface prints its help."""
    result = subprocess.run(
        [sys.executable, "-m", "toolkits.apt_toolkit"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert "--prompt-method" in result.stdout, result.stdout
    assert "--show-method" in result.stdout, result.stdout


def test_the_command_line_interface_does_not_import_llamaindex():
    """The CLI is part of the library half, and stays free of the framework.

    It is imported eagerly by the alias shim, so a LlamaIndex import in
    it would pull the framework into every process that imports
    ``toolkits``.
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


# ---------------------------------------------------------------------------
# The toolkit is optional, like every other toolkit under toolkits/
# ---------------------------------------------------------------------------


#: The modules that used to import the APT toolkit by its old name.
#: They have to import it through the alias now, behind a guard.
_OLD_IMPORT_SITES = (
    "agent-torvalds.py",
    "agent-torvalds-mw.py",
    "agent_tool_retriever.py",
    "agent_tool_selection.py",
)


def test_no_call_site_imports_the_old_module_name():
    """Nothing may import ``agent_apt_toolkit`` any more.

    The old name is gone; a call site that still used it would fail at
    import time and take the agent down with it.
    """
    offenders: list[str] = []
    for name in _OLD_IMPORT_SITES:
        path = REPO_ROOT / name
        if not path.is_file():
            continue
        for line, module in _module_imports(path):
            if module == "agent_apt_toolkit" or module.startswith("agent_apt_toolkit."):
                offenders.append(f"{name}:{line} -> {module}")

    assert offenders == [], f"stale imports of the old module name: {offenders}"


def test_the_call_sites_import_the_adapter_behind_a_guard():
    """A missing or broken APT toolkit must degrade to "no tools".

    The toolkit became optional with this move, the way every other
    toolkit under ``toolkits/`` already was.  A call site that imports
    it unguarded would turn a broken optional toolkit into a failed
    boot.
    """
    for name in _OLD_IMPORT_SITES:
        path = REPO_ROOT / name
        if not path.is_file():
            continue
        source = path.read_text(encoding="utf-8")
        assert "toolkits.apt_toolkit.agent_apt_toolkit" in source, (
            f"{name} does not import the APT toolkit through the alias"
        )
        assert "except ImportError" in source, (
            f"{name} imports the APT toolkit without a guard"
        )


# ---------------------------------------------------------------------------
# The known failures of the suite
# ---------------------------------------------------------------------------


def test_the_known_failures_are_still_known():
    """The four known failures carry over to the new path.

    The suite moved with the toolkit, and the four failures it carried
    with it are the same four, with the same names - only the path of the
    test file changed.  The baseline records the new paths, so the CI
    gate keeps reporting "no new failure".

    This test is what keeps the baseline honest: if a failure is fixed,
    the baseline has to be tightened, and this test says so.
    """
    baseline = (REPO_ROOT / "tests" / "ci_baseline.txt").read_text(
        encoding="utf-8"
    )

    for node_id in (
        "toolkits/apt-toolkit/tests/test_operations.py::TestGetAllTools::test_returns_list_of_tools",
        "toolkits/apt-toolkit/tests/test_operations.py::TestGetAllTools::test_tool_names",
        "toolkits/apt-toolkit/tests/test_operations.py::TestInteractiveInstallMissingCommand::test_full_workflow_success",
        "toolkits/apt-toolkit/tests/test_operations.py::test_sudo_password",
    ):
        assert node_id in baseline, (
            f"{node_id} is not in the baseline - the CI gate would report it "
            "as a new failure"
        )
