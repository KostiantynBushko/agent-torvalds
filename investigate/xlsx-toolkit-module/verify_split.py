#!/usr/bin/env python3
"""Verify that splitting ``agent_xlsx_toolkit.py`` into a package did not
move anything that matters.

The Excel toolkit used to be a single module at the project root.  It is
now a package under ``toolkits/xlsx-toolkit/``:

    agent_xlsx_toolkit.py  ->  toolkits/xlsx-toolkit/operations.py
                       ->  toolkits/xlsx-toolkit/agent_xlsx_toolkit.py

A refactoring of this kind is only worth anything if the *behaviour* is
identical, and the parts of a toolkit that count as behaviour are easy to
overlook:

* the **tool descriptions** - the retriever matches against them and the
  model reads them;
* the **order** of the tools - it decides what the model sees first;
* the **signatures** - they are the schema the model is given;
* the **docstrings** - they are the description the model reads;
* the **error contract** - a failure is reported, never raised;
* the **module-level state** - the logger, and the openpyxl imports the
  operations are built on.

Reading the two files side by side does not prove any of that: a reader
does not reliably notice that "for" became "on", and that is exactly the
kind of drift this check exists to catch.  So the comparison is made
mechanically, by parsing both versions and comparing them field by field.

The original is taken from git, so the check compares the *committed*
original with the new files - not with a copy that might have been edited
along the way.

The reference is **found, not assumed**.  The original is the file as it
was committed before it was deleted, so the check asks git where that
still lives: a named ref that still carries the file (``master``,
``origin/master``, ...), and otherwise the parent of the commit that
deleted it.  A hard-coded ``master`` would have been a trap - a CI
checkout is a detached HEAD without that branch, and the check would have
failed there for a reason that has nothing to do with the split.

Usage::

    python investigate/xlsx-toolkit-module/verify_split.py [--ref <ref>]

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
ORIGINAL_PATH = "agent_xlsx_toolkit.py"

#: The two files the original was split into.
OPERATIONS_PATH = "toolkits/xlsx-toolkit/operations.py"
ADAPTER_PATH = "toolkits/xlsx-toolkit/agent_xlsx_toolkit.py"

#: The operations the toolkit exposes, in the order they are exposed.
EXPECTED_OPERATIONS = (
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

#: The module-level statements the library half has to carry.
EXPECTED_MODULE_STATEMENTS = (
    "logger = logging.getLogger(__name__)",
)

#: The third-party modules the library half is allowed to depend on.
#:
#: The Excel toolkit is built on ``openpyxl`` - the Excel file format is
#: the file format, so an Excel operation is an Excel operation whether
#: or not an agent framework is installed.
EXPECTED_LIBRARY_DEPENDENCIES = frozenset({"openpyxl"})

#: The standard-library modules the library half is allowed to use.
EXPECTED_STDLIB_DEPENDENCIES = frozenset({"os", "logging", "typing"})


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


def git(args: list[str]) -> subprocess.CompletedProcess:
    """Run a git command in the repository and return the result."""
    return subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )


def file_exists_at(ref: str, path: str) -> bool:
    """Whether *path* exists in the tree of *ref*."""
    return git(["cat-file", "-e", f"{ref}:{path}"]).returncode == 0


def deletion_commits(path: str) -> list[str]:
    """The commits that deleted *path*, newest first."""
    result = git(["log", "--all", "--diff-filter=D", "--format=%H", "--", path])
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def resolve_original_ref(path: str = ORIGINAL_PATH) -> str:
    """Return a git reference at which the original *path* still exists.

    The original is the file as it was committed *before* it was deleted,
    so the search is:

    1. the named refs that are likely to carry it - the branch the
       refactoring was based on, and its remote counterpart;
    2. otherwise, the parent of the commit that deleted it - which is
       exactly the state the file was in when it was removed.

    The second step is what makes the check work in CI, where the
    checkout is a detached HEAD that carries neither a ``master`` branch
    nor the file itself.
    """
    for ref in ("master", "origin/master", "main", "origin/main"):
        if file_exists_at(ref, path):
            return ref

    for commit in deletion_commits(path):
        parent = f"{commit}^"
        if file_exists_at(parent, path):
            return parent

    raise SystemExit(
        f"cannot find {path} in the git history.\n"
        f"Fetch the full history (git fetch --unshallow) and try again."
    )


def functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    """The module-level function definitions of *tree*, by name."""
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }


def function_order(tree: ast.Module) -> list[str]:
    """The names of the module-level functions, in the order they appear."""
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    ]


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


def imported_modules(tree: ast.Module) -> list[str]:
    """The root names of every module the source imports."""
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # a relative import - it names no module
                continue
            found.append(node.module or "")
    return [name.split(".")[0] for name in found]


# ---------------------------------------------------------------------------
# the checks
# ---------------------------------------------------------------------------


def compare(
    original_source: str, operations_source: str, adapter_source: str
) -> list[str]:
    """Return the list of differences between the original and the split.

    An empty list means the split is behaviour-neutral.  The function is
    pure - it takes the three sources and returns the failures - so it can
    be driven with deliberately broken sources, which is how the check
    itself is tested.
    """
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

    # -- 2. the order of the operations ------------------------------------
    # The order is part of what the model sees, and it is what decides
    # the order of the tools in the adapter.
    original_order = [
        name for name in function_order(original) if name in EXPECTED_OPERATIONS
    ]
    operations_order = [
        name for name in function_order(operations) if name in EXPECTED_OPERATIONS
    ]
    check(
        original_order == operations_order,
        "the order of the operations changed:\n"
        f"  before: {original_order}\n"
        f"  after:  {operations_order}",
    )

    # -- 3. the signatures, the docstrings, the bodies ---------------------
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

    # -- 4. the tool surface ------------------------------------------------
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

    # -- 5. the LlamaIndex boundary -----------------------------------------
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

    # -- 6. the module-level state ------------------------------------------
    # The original carried a module-level logger.  The library half has
    # to carry it too - the adapter re-exports it, and the operations
    # log through it.
    for statement in EXPECTED_MODULE_STATEMENTS:
        check(
            statement in operations_source,
            f"the library half lost the module-level statement: {statement}",
        )
        check(
            statement in original_source,
            f"the original did not carry the module-level statement "
            f"{statement!r} - the comparison is no longer the one it was "
            "written for",
        )

    # -- 7. the dependency profile ------------------------------------------
    # The library half is built on openpyxl - the Excel file format is the
    # file format - and on the standard library, and on nothing else.  The
    # set is pinned, so a new dependency cannot slip in unnoticed.
    library_dependencies = set(imported_modules(operations))
    unexpected = (
        library_dependencies
        - EXPECTED_LIBRARY_DEPENDENCIES
        - EXPECTED_STDLIB_DEPENDENCIES
    )
    check(
        not unexpected,
        f"the library half has unexpected dependencies: {sorted(unexpected)}",
    )
    missing = EXPECTED_LIBRARY_DEPENDENCIES - library_dependencies
    check(
        not missing,
        f"the library half lost its dependencies: {sorted(missing)}",
    )

    # -- 8. the openpyxl imports the operations are built on ----------------
    # The operations read and write .xlsx files through openpyxl.  The
    # check pins the two imports, so a lost one is caught before it
    # breaks a tool at run time.
    for statement in (
        "from openpyxl import load_workbook, Workbook",
        "from openpyxl.styles import Font, Alignment, Border, Side, PatternFill",
    ):
        check(
            statement in operations_source,
            f"the library half lost the openpyxl import: {statement}",
        )
        check(
            statement in original_source,
            f"the original did not carry the openpyxl import {statement!r} - "
            "the comparison is no longer the one it was written for",
        )

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ref",
        default=None,
        help=(
            "the git reference the original is taken from "
            "(default: the reference is found automatically)"
        ),
    )
    args = parser.parse_args()

    ref = args.ref or resolve_original_ref()

    original_source = git_show(ref, ORIGINAL_PATH)
    operations_source = (REPO_ROOT / OPERATIONS_PATH).read_text(encoding="utf-8")
    adapter_source = (REPO_ROOT / ADAPTER_PATH).read_text(encoding="utf-8")

    failures = compare(original_source, operations_source, adapter_source)

    # -- the report ----------------------------------------------------------
    print(f"original            : {ref}:{ORIGINAL_PATH}")
    print(f"library half        : {OPERATIONS_PATH}")
    print(f"agent adapter       : {ADAPTER_PATH}")
    print()
    print(f"operations compared : {len(EXPECTED_OPERATIONS)}")
    print(f"tools compared      : {len(tool_entries(ast.parse(original_source)))}")
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
    print("  * the openpyxl imports moved with the operations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
