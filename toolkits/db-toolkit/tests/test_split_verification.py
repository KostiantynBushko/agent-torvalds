"""
Tests for the split-verification script.

``investigate/db-toolkit-module/verify_split.py`` claims that the
database toolkit was moved without changing anything that matters.  A
claim like that is only worth as much as the evidence behind it, and a
check that has never failed proves nothing.

So the check is driven here with **deliberate drifts** - the kind of
change a reader would not reliably notice - and it has to catch every one
of them:

* a tool description reworded from "for" to "on";
* a docstring dropped;
* a function body changed;
* two operations swapped;
* a LlamaIndex import sneaking into the library half;
* a tool that went missing;
* an operation that went missing;
* the module-level logger lost;
* the import-time configuration load lost;
* a dependency of the library half dropped.

The real sources are checked as well: they have to produce **no**
failures, or the whole claim is void.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

#: The repository root - three levels up from this file:
#: <root>/toolkits/db-toolkit/tests/test_split_verification.py
REPO_ROOT = Path(__file__).resolve().parents[3]

#: The script under test.
VERIFY_SPLIT = (
    REPO_ROOT / "investigate" / "db-toolkit-module" / "verify_split.py"
)


def _load_checker():
    """Import the verification script by path.

    The script lives under ``investigate/``, which is not a package, so it
    is loaded from its file.
    """
    spec = importlib.util.spec_from_file_location("verify_split", VERIFY_SPLIT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: The checker, loaded once for the whole module.
CHECKER = _load_checker()


def _original_source() -> str:
    """The committed original, straight from git.

    The reference is *found* rather than assumed: a CI checkout is a
    detached HEAD that has no ``master`` branch, so a check that asked
    for one would fail there for a reason that has nothing to do with
    the split.
    """
    return CHECKER.git_show(CHECKER.resolve_original_ref(), CHECKER.ORIGINAL_PATH)


def _operations_source() -> str:
    return (REPO_ROOT / CHECKER.OPERATIONS_PATH).read_text(encoding="utf-8")


def _adapter_source() -> str:
    return (REPO_ROOT / CHECKER.ADAPTER_PATH).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The real sources
# ---------------------------------------------------------------------------


def test_the_real_split_is_behaviour_neutral():
    """The committed original and the new files must not differ."""
    failures = CHECKER.compare(
        _original_source(), _operations_source(), _adapter_source()
    )
    assert failures == [], f"the split is not behaviour-neutral: {failures}"


def test_the_script_itself_reports_success():
    """The script, run as a program, must exit 0.

    The library half and the adapter are read from the working tree, and
    the original from git, so this is the check the way a reviewer would
    run it.
    """
    result = subprocess.run(
        [sys.executable, str(VERIFY_SPLIT)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "The split is behaviour-neutral." in result.stdout


def test_the_original_is_found_without_a_named_branch():
    """The check must find the original where no branch is named.

    A CI checkout is a detached HEAD: it has no ``master`` branch and
    the file itself is gone from the tree, so the only place the
    original can come from is the history - the state the file was in
    just before it was deleted.
    """
    ref = CHECKER.resolve_original_ref()
    assert ref, "no reference was found"

    original = CHECKER.git_show(ref, CHECKER.ORIGINAL_PATH)
    assert "def run_postgres_query" in original
    assert "def get_all_tools" in original


# ---------------------------------------------------------------------------
# The deliberate drifts
# ---------------------------------------------------------------------------


def test_it_catches_a_reworded_tool_description():
    """A description that changed from "for" to "on".

    This is the drift the check was written for: a reader comparing the
    two files side by side does not reliably notice a single word.
    """
    adapter = _adapter_source()
    drifted = adapter.replace(
        "Use for SELECT, DDL, DML on Postgres.",
        "Use on SELECT, DDL, DML on Postgres.",
    )
    assert drifted != adapter, "the drift did not apply"

    failures = CHECKER.compare(
        _original_source(), _operations_source(), drifted
    )
    assert failures, "a reworded tool description slipped through"
    assert any("description changed" in failure for failure in failures), failures


def test_it_catches_a_dropped_docstring():
    """A docstring that was dropped.

    The docstring is the description the model reads.
    """
    operations = _operations_source()
    drifted = operations.replace(
        "    Run a SQL query on PostgreSQL and return rows as a list of dictionaries.\n    \n",
        "",
    )
    assert drifted != operations, "the drift did not apply"

    failures = CHECKER.compare(
        _original_source(), drifted, _adapter_source()
    )
    assert failures, "a dropped docstring slipped through"
    assert any("docstring changed" in failure for failure in failures), failures


def test_it_catches_a_changed_body():
    """A body that changed under the tool's feet."""
    operations = _operations_source()
    drifted = operations.replace(
        '        return f"Error running PostgreSQL query: {str(e)}"',
        '        return f"Error: {str(e)}"',
        1,
    )
    assert drifted != operations, "the drift did not apply"

    failures = CHECKER.compare(
        _original_source(), drifted, _adapter_source()
    )
    assert failures, "a changed body slipped through"
    assert any("body changed" in failure for failure in failures), failures


def _swap_two_functions(source: str, first: str, second: str) -> str:
    """Return *source* with the bodies of *first* and *second* exchanged.

    The two definitions are cut out of the text and put back in each
    other's place, so the file still holds exactly the same operations -
    only their order changed.
    """
    import ast

    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)

    blocks = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in (first, second):
            blocks[node.name] = "".join(lines[node.lineno - 1 : node.end_lineno])

    assert first in blocks and second in blocks, "the functions to swap were not found"

    swapped = source.replace(blocks[first], "@@FIRST@@", 1)
    swapped = swapped.replace(blocks[second], blocks[first], 1)
    swapped = swapped.replace("@@FIRST@@", blocks[second], 1)
    return swapped


def test_it_catches_two_operations_swapped():
    """Two operations in the wrong order.

    The order decides what the model sees first.  The drift keeps every
    operation - only their order changes - so the set check passes and
    the order check is the one that has to catch it.
    """
    operations = _operations_source()
    drifted = _swap_two_functions(
        operations,
        "run_postgres_query",
        "run_mysql_query",
    )
    assert drifted != operations, "the drift did not apply"

    failures = CHECKER.compare(
        _original_source(), drifted, _adapter_source()
    )
    assert failures, "a swapped operation slipped through"
    assert any("order of the operations changed" in f for f in failures), failures


def test_it_catches_a_llamaindex_import_in_the_library_half():
    """LlamaIndex sneaking into the library half.

    The library half has to stay usable without the agent framework.
    """
    operations = _operations_source()
    drifted = operations.replace(
        "import logging\n",
        "import logging\n\nfrom llama_index.core.tools import FunctionTool\n",
        1,
    )
    assert drifted != operations, "the drift did not apply"

    failures = CHECKER.compare(
        _original_source(), drifted, _adapter_source()
    )
    assert failures, "a LlamaIndex import in the library half slipped through"
    assert any(
        "must not import LlamaIndex" in failure for failure in failures
    ), failures


def test_it_catches_a_tool_that_went_missing():
    """A tool that was dropped from the adapter."""
    adapter = _adapter_source()
    drifted = adapter.replace(
        """        FunctionTool.from_defaults(
            fn=run_mysql_query,
            description="Run a SQL query on MySQL. Use for SELECT, DDL, DML on MySQL. Category: Database",
        ),
""",
        "",
    )
    assert drifted != adapter, "the drift did not apply"

    failures = CHECKER.compare(
        _original_source(), _operations_source(), drifted
    )
    assert failures, "a missing tool slipped through"
    assert any("tool names or their order changed" in f for f in failures), failures


def test_it_catches_an_operation_that_went_missing():
    """An operation that was dropped from the library half."""
    operations = _operations_source()
    drifted = operations.replace(
        "def run_mysql_query(query: str) -> list[dict]:",
        "def _removed_operation(query: str) -> list[dict]:",
    )
    assert drifted != operations, "the drift did not apply"

    failures = CHECKER.compare(
        _original_source(), drifted, _adapter_source()
    )
    assert failures, "a missing operation slipped through"


def test_it_catches_a_lost_module_level_logger():
    """The module-level logger gone from the library half.

    The operations log through it and the adapter re-exports it, so its
    loss is a change of behaviour even though no function body moved.
    """
    operations = _operations_source()
    drifted = operations.replace(
        "logger = logging.getLogger(__name__)",
        "logger = logging.getLogger('something-else')",
        1,
    )
    assert drifted != operations, "the drift did not apply"

    failures = CHECKER.compare(
        _original_source(), drifted, _adapter_source()
    )
    assert failures, "a lost module-level logger slipped through"
    assert any("module-level logger" in failure for failure in failures), failures


def test_it_catches_a_lost_import_time_configuration_load():
    """The configuration no longer read at import time.

    The database toolkit loads its configuration when the module is
    imported, and the operations use the loaded values.  A library half
    that loads it lazily would behave differently for every caller that
    imports the module - so the drift has to be caught.
    """
    operations = _operations_source()
    drifted = operations.replace(
        "_cfg = _load_config()",
        "_cfg = {}",
        1,
    )
    assert drifted != operations, "the drift did not apply"

    failures = CHECKER.compare(
        _original_source(), drifted, _adapter_source()
    )
    assert failures, "a lost import-time configuration load slipped through"
    assert any(
        "import-time configuration load" in failure for failure in failures
    ), failures


def test_it_catches_a_lost_dependency():
    """A dependency of the library half that quietly disappeared.

    The library half is built on the two database drivers and on PyYAML.
    A driver that is no longer imported would break the operation that
    uses it - so the exact set of dependencies is pinned.
    """
    operations = _operations_source()
    drifted = operations.replace("import mysql.connector\n", "", 1)
    assert drifted != operations, "the drift did not apply"

    failures = CHECKER.compare(
        _original_source(), drifted, _adapter_source()
    )
    assert failures, "a lost dependency slipped through"
    assert any("lost its dependencies" in failure for failure in failures), failures


def test_it_catches_an_unexpected_dependency():
    """A new dependency that slipped into the library half."""
    operations = _operations_source()
    drifted = operations.replace(
        "import logging\n",
        "import logging\nimport numpy\n",
        1,
    )
    assert drifted != operations, "the drift did not apply"

    failures = CHECKER.compare(
        _original_source(), drifted, _adapter_source()
    )
    assert failures, "an unexpected dependency slipped through"
    assert any(
        "unexpected dependencies" in failure for failure in failures
    ), failures
