"""
No function may read a name that does not exist.

A `NameError` in a code path that is only taken in one mode of the agent
is invisible until somebody runs that mode.  The multi-window agent has a
**classic REPL** mode and a **TUI** mode, and a name that is only read in
the REPL mode is not touched by a test that starts the TUI.

This test closes that hole: it reads the source of every function of both
orchestrators and checks that every global it reads exists in its module.
It is a **static** check — it does not run the code — so it covers the
paths no test enters.

Run with:
    pytest tests/test_no_undefined_globals.py -v
"""
import ast
import builtins
import importlib.util
import inspect
import logging
import sys
import textwrap
import unittest
from pathlib import Path

# Ensure the repository root is on the path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ORCHESTRATORS = ("agent-torvalds.py", "agent-torvalds-mw.py")


def _load(name: str, path: Path):
    """Load a script-style module by path."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _names_the_function_defines(function) -> set[str]:
    """The names the function defines: its arguments and its assignments."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    definition = tree.body[0]

    local: set[str] = set()

    for argument in (
        list(definition.args.posonlyargs)
        + list(definition.args.args)
        + list(definition.args.kwonlyargs)
    ):
        local.add(argument.arg)
    if definition.args.vararg:
        local.add(definition.args.vararg.arg)
    if definition.args.kwarg:
        local.add(definition.args.kwarg.arg)

    for node in ast.walk(definition):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            local.add(node.id)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            local.add(node.name)
        if isinstance(node, ast.ExceptHandler) and node.name:
            local.add(node.name)
        if isinstance(node, ast.Lambda):
            for argument in (
                list(node.args.posonlyargs)
                + list(node.args.args)
                + list(node.args.kwonlyargs)
            ):
                local.add(argument.arg)
            if node.args.vararg:
                local.add(node.args.vararg.arg)
            if node.args.kwarg:
                local.add(node.args.kwarg.arg)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                local.add((alias.asname or alias.name).split(".")[0])

    return local


def _names_the_function_reads(function) -> set[str]:
    """The names the function reads."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }


def _undefined_globals(module, function) -> set[str]:
    """The globals the function reads that the module does not have."""
    reads = _names_the_function_reads(function)
    defined = _names_the_function_defines(function)
    known = set(dir(builtins)) | set(dir(module))
    return reads - defined - known


class TestNoUndefinedGlobals(unittest.TestCase):
    """Every global a function reads must exist in its module."""

    def setUp(self):
        # The orchestrators configure the root logger at import time.
        root = logging.getLogger()
        self._handlers = list(root.handlers)
        self._level = root.level
        self.addCleanup(self._restore)

    def _restore(self):
        root = logging.getLogger()
        root.handlers.clear()
        root.handlers.extend(self._handlers)
        root.setLevel(self._level)

    def _check(self, filename: str) -> None:
        module = _load(f"undefined_globals_{filename.replace('.', '_')}",
                       ROOT / filename)

        checked = 0
        for attribute in dir(module):
            candidate = getattr(module, attribute)
            if not inspect.isfunction(candidate):
                continue
            if candidate.__module__ != module.__name__:
                continue
            checked += 1
            missing = _undefined_globals(module, candidate)
            self.assertEqual(
                missing,
                set(),
                f"{filename}: {attribute}() reads names that do not "
                f"exist: {sorted(missing)}",
            )
        self.assertGreater(checked, 0, f"{filename}: no function was checked")

    def test_the_classic_orchestrator(self):
        self._check("agent-torvalds.py")

    def test_the_multi_window_orchestrator(self):
        self._check("agent-torvalds-mw.py")

    def test_the_file_logging_names_reach_the_multi_window_repl(self):
        """The classic REPL of the multi-window agent must know the config.

        The REPL announces the log file, and the name it reads must be a
        **parameter** of it — not a global that only the TUI path defines.
        """
        module = _load("undefined_globals_mw_repl", ROOT / "agent-torvalds-mw.py")
        signature = inspect.signature(module.run_classic_repl)
        self.assertIn("file_config", signature.parameters)


if __name__ == "__main__":
    unittest.main()
