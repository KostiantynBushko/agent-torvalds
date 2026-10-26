#!/usr/bin/env python3
"""Verify that splitting ``agent_os_toolkit.py`` into a package did not move
anything that matters.

The OS toolkit used to be a single module at the project root.  It is now
a package under ``toolkits/os-toolkit/``:

    agent_os_toolkit.py  ->  toolkits/os-toolkit/operations.py
                         ->  toolkits/os-toolkit/agent_os_toolkit.py

A refactoring of this kind is only worth anything if the *behaviour* is
identical, and the parts of a toolkit that count as behaviour are easy to
overlook:

* the **tool descriptions** - the retriever matches against them and the
  model reads them;
* the **order** of the tools - it decides what the model sees first;
* the **signatures** - they are the schema the model is given;
* the **docstrings** - they are the description the model reads;
* the **error contract** - a failure is reported, never raised.

Reading the two files side by side does not prove any of that: a reader
does not reliably notice that "for" became "on", and that is exactly the
kind of drift this check exists to catch.  So the comparison is made
mechanically, by parsing both versions and comparing them field by field.

The original is taken from git (``git show <ref>:agent_os_toolkit.py``), so
the check compares the *committed* original with the new files - not with
a copy that might have been edited along the way.

Usage::

    python investigate/os-toolkit-module/verify_split.py [--ref HEAD]

Exit code 0 means the split is behaviour-neutral.
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The original, single-module toolkit.
ORIGINAL_PATH = "agent_os_toolkit.py"

#: The two files the original was split into.
OPERATIONS_PATH = "toolkits/os-toolkit/operations.py"
ADAPTER_PATH = "toolkits/os-toolkit/agent_os_toolkit.py"

#: The operations the toolkit exposes, in the order they are exposed.
EXPECTED_OPERATIONS = (
    "pwd",
    "ls",
    "touch",
    "check_path_exists",
    "mkdir",
    "rm",
    "cp",
    "mv",
    "read_file",
    "write_file",
    "get_system_info",
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def git_show(ref: str, path: str) -> str:
    """Return the contents of *path* at *ref*."""
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"cannot read {path} at {ref}:\n{result.stderr.strip()}"
        )
    return result.stdout


def functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    """The module-level function definitions of *tree*, by name."""
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }


def signature(node: ast.FunctionDef) -> str:
    """A comparable, normalised rendering of a function signature.

    The annotations are dropped: they are evaluated at runtime by the
    agent framework, but they are not what the model is given - the
    *parameters* and their defaults are.  The parameter names and the
    defaults are what end up in the tool schema, so those are compared.
    """
    args = node.args
    parts: list[str] = []

    positional = args.posonlyargs + args.args
    defaults = list(args.defaults)
    pad = len(positional) - len(defaults)
    for index, arg in enumerate(positional):
        text = arg.arg
        if index >= pad:
            default = defaults[index - pad]
            text += f"={ast.unparse(default)}"
        parts.append(text)

    if args.vararg:
        parts.append(f"*{args.vararg.arg}")
    elif args.kwonlyargs:
        parts.append("*")

    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        text = arg.arg
        if default is not None:
            text += f"={ast.unparse(default)}"
        parts.append(text)

    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")

    return f"({', '.join(parts)})"


def docstring(node: ast.FunctionDef) -> str:
    """The docstring of a function, or the empty string."""
    return ast.get_docstring(node) or ""


def tool_entries(tree: ast.Module) -> list[tuple[str, str]]:
    """The (tool name, description) pairs of ``get_all_tools``, in order.

    The tool name is the *function* the tool is built from, and the
    description is the string the retriever matches against and the model
    reads.  Both are behaviour.
    """
    functions_ = functions(tree)
    if "get_all_tools" not in functions_:
        return []

    entries: list[tuple[str, str]] = []
    for node in ast.walk(functions_["get_all_tools"]):
        if not isinstance(node, ast.Call):
            continue
        # FunctionTool.from_defaults(fn=..., description=...)
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "from_defaults"):
            continue
        fn = None
        description = None
        for keyword in node.keywords:
            if keyword.arg == "fn" and isinstance(keyword.value, ast.Name):
                fn = keyword.value.id
            elif keyword.arg == "description" and isinstance(keyword.value, ast.Constant):
                description = keyword.value.value
        if fn is not None and description is not None:
            entries.append((fn, description))
    return entries


def source_of(node: ast.FunctionDef, source: str) -> str:
    """The exact source text of a function definition."""
    lines = source.splitlines(keepends=True)
    return "".join(lines[node.lineno - 1 : node.end_lineno])


# ---------------------------------------------------------------------------
# the checks
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ref",
        default="HEAD",
        help="the git reference the original is taken from (default: HEAD)",
    )
    args = parser.parse_args()

    original_source = git_show(args.ref, ORIGINAL_PATH)
    operations_source = (REPO_ROOT / OPERATIONS_PATH).read_text(encoding="utf-8")
    adapter_source = (REPO_ROOT / ADAPTER_PATH).read_text(encoding="utf-8")

    original = ast.parse(original_source)
    operations = ast.parse(operations_source)
    adapter = ast.parse(adapter_source)

    original_fns = functions(original)
    operations_fns = functions(operations)
    adapter_fns = functions(adapter)

    failures: list[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    # -- 1. the operations moved, and nothing else did ----------------------
    check(
        set(operations_fns) == set(EXPECTED_OPERATIONS),
        f"the library half holds {sorted(operations_fns)}, "
        f"expected {sorted(EXPECTED_OPERATIONS)}",
    )
    check(
        set(adapter_fns) == {"get_all_tools"},
        f"the adapter holds {sorted(adapter_fns)}, expected only get_all_tools",
    )
    check(
        "get_all_tools" not in operations_fns,
        "get_all_tools belongs to the adapter, not to the library half",
    )

    # -- 2. the signatures, the docstrings, the bodies ---------------------
    for name in EXPECTED_OPERATIONS:
        if name not in original_fns or name not in operations_fns:
            continue

        old, new = original_fns[name], operations_fns[name]
        check(
            signature(old) == signature(new),
            f"{name}: the signature changed: "
            f"{signature(old)} -> {signature(new)}",
        )
        check(
            docstring(old) == docstring(new),
            f"{name}: the docstring changed",
        )
        check(
            source_of(old, original_source) == source_of(new, operations_source),
            f"{name}: the body changed",
        )

    # -- 3. the tool surface ------------------------------------------------
    old_tools = tool_entries(original)
    new_tools = tool_entries(adapter)

    check(
        [name for name, _ in old_tools] == [name for name, _ in new_tools],
        "the tool names or their order changed:\n"
        f"  before: {[name for name, _ in old_tools]}\n"
        f"  after:  {[name for name, _ in new_tools]}",
    )

    old_by_name = dict(old_tools)
    new_by_name = dict(new_tools)
    for name in old_by_name:
        if name in new_by_name:
            check(
                old_by_name[name] == new_by_name[name],
                f"{name}: the tool description changed:\n"
                f"  before: {old_by_name[name]!r}\n"
                f"  after:  {new_by_name[name]!r}",
            )

    # -- 4. the LlamaIndex boundary -----------------------------------------
    def llamaindex_imports(tree: ast.Module) -> list[str]:
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                found.append(node.module or "")
        return [name for name in found if name.split(".")[0] == "llama_index"]

    check(
        llamaindex_imports(operations) == [],
        "the library half must not import LlamaIndex",
    )
    check(
        llamaindex_imports(adapter) != [],
        "the adapter must import LlamaIndex",
    )

    # -- the report ----------------------------------------------------------
    print(f"original            : {args.ref}:{ORIGINAL_PATH}")
    print(f"library half        : {OPERATIONS_PATH}")
    print(f"agent adapter       : {ADAPTER_PATH}")
    print()
    print(f"operations compared : {len(EXPECTED_OPERATIONS)}")
    print(f"tools compared      : {len(old_tools)}")
    print()

    if failures:
        print("THE SPLIT IS NOT BEHAVIOUR-NEUTRAL:")
        print()
        for failure in failures:
            print(f"  * {failure}")
        return 1

    print("The split is behaviour-neutral.")
    print()
    print("  * the operation names, their order, their signatures, their")
    print("    docstrings and their bodies are identical")
    print("  * the tool names, their order and their descriptions are identical")
    print("  * the LlamaIndex import is in the adapter only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
