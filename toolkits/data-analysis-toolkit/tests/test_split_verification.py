"""
Tests for the split-verification script.

``investigate/data-analysis-toolkit-module/verify_split.py`` claims that
the data analysis toolkit was moved without changing anything that
matters.  A claim like that is only worth as much as the evidence behind
it, and a check that has never failed proves nothing.

So the check is driven here with **deliberate drifts** - the kind of
change a reader would not reliably notice - and it has to catch every one
of them:

* a tool description reworded from "an" to "the";
* a docstring dropped;
* a function body changed;
* a parameter default changed;
* two operations swapped;
* a LlamaIndex import sneaking into the library half;
* a tool that went missing;
* an operation that went missing;
* the module-level logger lost;
* a dependency of the library half dropped;
* an unexpected dependency added to the library half;
* one of the two data imports lost;
* the tool registry moving to the library half;
* a dependency the original did not have gained.

The real sources are checked as well: they have to produce **no**
failures, or the whole claim is void.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

#: The repository root - three levels up from this file:
#: <root>/toolkits/data-analysis-toolkit/tests/test_split_verification.py
REPO_ROOT = Path(__file__).resolve().parents[3]

#: The script under test.
VERIFY_SPLIT = (
    REPO_ROOT / "investigate" / "data-analysis-toolkit-module" / "verify_split.py"
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
    assert "def read_excel_to_df" in original
    assert "def get_all_tools" in original


# ---------------------------------------------------------------------------
# The deliberate drifts
# ---------------------------------------------------------------------------


def test_it_catches_a_reworded_tool_description():
    """A description that changed from "an" to "the".

    This is the drift the check was written for: a reader comparing the
    two files side by side does not reliably notice a single word.
    """
    adapter = _adapter_source()
    drifted = adapter.replace(
        "Load an Excel file and return data as a list of dictionaries.",
        "Load the Excel file and return data as a list of dictionaries.",
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
        "    Load an Excel file and return data as a list of dictionaries.\n    \n",
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
        '        return f"Error reading Excel file: {str(e)}"',
        '        return f"Error: {str(e)}"',
        1,
    )
    assert drifted != operations, "the drift did not apply"

    failures = CHECKER.compare(
        _original_source(), drifted, _adapter_source()
    )
    assert failures, "a changed body slipped through"
    assert any("body changed" in failure for failure in failures), failures


def test_it_catches_a_changed_parameter_default():
    """A default that changed.

    The default is part of the schema the model is given, and a reader
    comparing two files does not reliably notice it.
    """
    operations = _operations_source()
    drifted = operations.replace(
        'def export_dataframe(path: str, data: list, sheet_name: str = "Sheet1", '
        'file_type: str = "xlsx") -> str:',
        'def export_dataframe(path: str, data: list, sheet_name: str = "Sheet2", '
        'file_type: str = "xlsx") -> str:',
        1,
    )
    assert drifted != operations, "the drift did not apply"

    failures = CHECKER.compare(
        _original_source(), drifted, _adapter_source()
    )
    assert failures, "a changed parameter default slipped through"
    assert any("signature changed" in failure for failure in failures), failures


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
        "read_excel_to_df",
        "read_csv_to_df",
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
            fn=get_dataframe_info,
            description="Get DataFrame information including shape, columns, and data types. Category: Data / Analysis",
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
        "def get_unique_values(df_or_path: str, column: str, sheet_name: str = None) -> list:",
        "def _removed_operation(df_or_path: str, column: str, sheet_name: str = None) -> list:",
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
    assert any("module-level" in failure for failure in failures), failures


def test_it_catches_a_lost_dependency():
    """A dependency of the library half that quietly disappeared.

    The library half is built on pandas - the DataFrame is the data
    model - so without it every operation breaks at run time.
    """
    operations = _operations_source()
    drifted = operations.replace("import pandas as pd\n", "", 1)
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
        "import logging\nimport requests\n",
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


def test_it_catches_a_lost_numpy_import():
    """One of the two data imports lost.

    The DataFrame is ``pd``, and the numeric column inference of the
    pivot table is ``np``.  Only the pandas import goes here, so pandas
    is still a dependency - the *statement* is what is missing, and that
    is the narrower drift the statement check exists for.
    """
    operations = _operations_source()
    drifted = operations.replace("import numpy as np\n", "", 1)
    assert drifted != operations, "the drift did not apply"

    failures = CHECKER.compare(
        _original_source(), drifted, _adapter_source()
    )
    assert failures, "a lost numpy import slipped through"
    assert any("lost the import" in failure for failure in failures), failures


def test_it_catches_the_tool_registry_moving_to_the_library_half():
    """``get_all_tools`` in the wrong half.

    The registry needs LlamaIndex, so it belongs to the adapter.  A
    library half that grew one would import the framework, and the
    LlamaIndex-free rule would be broken with it.
    """
    operations = _operations_source()
    drifted = operations.replace(
        "logger = logging.getLogger(__name__)\n",
        "logger = logging.getLogger(__name__)\n\n\ndef get_all_tools() -> list:\n    return []\n",
        1,
    )
    assert drifted != operations, "the drift did not apply"

    failures = CHECKER.compare(
        _original_source(), drifted, _adapter_source()
    )
    assert failures, "the tool registry in the wrong half slipped through"
    assert any(
        "belongs to the adapter" in failure for failure in failures
    ), failures


def test_it_catches_a_dependency_the_original_did_not_have():
    """The library half growing a dependency the original never had.

    The difference between the two dependency sets is pinned to the two
    documented ones - the LlamaIndex import that moved to the adapter and
    the unused ``json`` import that was dropped.  Anything else is a
    drift.
    """
    operations = _operations_source()
    drifted = operations.replace(
        "import logging\n",
        "import logging\nimport sqlite3\n",
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
