"""
Tests for the split-verification script.

``investigate/apt-toolkit-module/verify_split.py`` claims that the APT
toolkit was moved without changing anything that matters.  A claim like
that is only worth as much as the evidence behind it, and a check that has
never failed proves nothing.

So the check is driven here with **deliberate drifts** - the kind of
change a reader would not reliably notice - and it has to catch every one
of them:

* a tool description reworded from "for" to "on";
* a parameter default changed;
* a docstring dropped;
* a function body changed;
* two operations swapped;
* a LlamaIndex import sneaking into the library half;
* a tool that went missing;
* an operation that went missing;
* a command-line option whose help text was reworded;
* a command-line option whose choices were narrowed;
* a command-line output message that was reworded;
* a command-line option that went missing.

The real sources are checked as well: they have to produce **no**
failures, or the whole claim is void.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

#: The repository root - three levels up from this file:
#: <root>/toolkits/apt-toolkit/tests/test_split_verification.py
REPO_ROOT = Path(__file__).resolve().parents[3]

#: The script under test.
VERIFY_SPLIT = REPO_ROOT / "investigate" / "apt-toolkit-module" / "verify_split.py"


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
    for one would fail there for a reason that has nothing to do with the
    split.
    """
    return CHECKER.git_show(CHECKER.resolve_original_ref(), CHECKER.ORIGINAL_PATH)


def _operations_source() -> str:
    return (REPO_ROOT / CHECKER.OPERATIONS_PATH).read_text(encoding="utf-8")


def _adapter_source() -> str:
    return (REPO_ROOT / CHECKER.ADAPTER_PATH).read_text(encoding="utf-8")


def _cli_source() -> str:
    return (REPO_ROOT / CHECKER.CLI_PATH).read_text(encoding="utf-8")


def _compare(operations=None, adapter=None, cli=None) -> list[str]:
    """Run the check with the given (possibly drifted) sources."""
    return CHECKER.compare(
        _original_source(),
        _operations_source() if operations is None else operations,
        _adapter_source() if adapter is None else adapter,
        _cli_source() if cli is None else cli,
    )


# ---------------------------------------------------------------------------
# The real sources
# ---------------------------------------------------------------------------


def test_the_real_split_is_behaviour_neutral():
    """The committed original and the new files must not differ."""
    failures = _compare()
    assert failures == [], f"the split is not behaviour-neutral: {failures}"


def test_the_script_itself_reports_success():
    """The script, run as a program, must exit 0.

    The library half, the adapter and the command-line interface are read
    from the working tree, and the original from git, so this is the check
    the way a reviewer would run it.
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
    assert "def find_package_for_command" in original
    assert "def get_all_tools" in original


# ---------------------------------------------------------------------------
# The deliberate drifts - the library half
# ---------------------------------------------------------------------------


def test_it_catches_a_reworded_tool_description():
    """A description that changed from "for" to "on".

    This is the drift the check was written for: a reader comparing the
    two files side by side does not reliably notice a single word.
    """
    adapter = _adapter_source()
    drifted = adapter.replace(
        "Use for resolving missing tools to installable packages",
        "Use on resolving missing tools to installable packages",
    )
    assert drifted != adapter, "the drift did not apply"

    failures = _compare(adapter=drifted)
    assert failures, "a reworded tool description slipped through"
    assert any("description changed" in failure for failure in failures), failures


def test_it_catches_a_changed_parameter_default():
    """A default that changed from 3 to 5.

    The default is part of the schema the model is given, so it is
    behaviour.
    """
    operations = _operations_source()
    drifted = operations.replace(
        "    max_attempts: int = 3,", "    max_attempts: int = 5,", 1
    )
    assert drifted != operations, "the drift did not apply"

    failures = _compare(operations=drifted)
    assert failures, "a changed parameter default slipped through"
    assert any("signature changed" in failure for failure in failures), failures


def test_it_catches_a_dropped_docstring():
    """A docstring that was dropped.

    The docstring is the description the model reads.
    """
    operations = _operations_source()
    drifted = operations.replace(
        "    Find which APT package provides a given command/binary.\n",
        "",
        1,
    )
    assert drifted != operations, "the drift did not apply"

    failures = _compare(operations=drifted)
    assert failures, "a dropped docstring slipped through"
    assert any("docstring changed" in failure for failure in failures), failures


def test_it_catches_a_changed_body():
    """A body that changed under the tool's feet."""
    operations = _operations_source()
    drifted = operations.replace(
        '        "method": "none",\n        "success": False,\n        "candidates": [],\n',
        '        "method": "none",\n        "success": True,\n        "candidates": [],\n',
        1,
    )
    assert drifted != operations, "the drift did not apply"

    failures = _compare(operations=drifted)
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
        "check_command_exists",
        "set_default_prompt_method",
    )
    assert drifted != operations, "the drift did not apply"

    failures = _compare(operations=drifted)
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

    failures = _compare(operations=drifted)
    assert failures, "a LlamaIndex import in the library half slipped through"
    assert any(
        "must not import LlamaIndex" in failure for failure in failures
    ), failures


def test_it_catches_a_tool_that_went_missing():
    """A tool that was dropped from the adapter."""
    adapter = _adapter_source()
    drifted = adapter.replace(
        """        FunctionTool.from_defaults(
            fn=get_default_prompt_method,
            description="Get the current default password prompt method. Use to check which method is configured. Category: System / Package Management",
        ),
""",
        "",
    )
    assert drifted != adapter, "the drift did not apply"

    failures = _compare(adapter=drifted)
    assert failures, "a missing tool slipped through"
    assert any("tool names or their order changed" in f for f in failures), failures


def test_it_catches_an_operation_that_went_missing():
    """An operation that was dropped from the library half."""
    operations = _operations_source()
    drifted = operations.replace(
        "def clear_sudo_cache() -> Dict[str, Any]:",
        "def _removed_operation() -> Dict[str, Any]:",
    )
    assert drifted != operations, "the drift did not apply"

    failures = _compare(operations=drifted)
    assert failures, "a missing operation slipped through"
    assert any("the library half holds" in f for f in failures), failures


# ---------------------------------------------------------------------------
# The deliberate drifts - the command-line interface
# ---------------------------------------------------------------------------


def test_it_catches_a_reworded_command_line_option():
    """The help text of an option that was reworded.

    The command-line interface is behaviour too: it is what an operator
    reads when they ask the toolkit what it can do.
    """
    cli = _cli_source()
    drifted = cli.replace(
        'help="Set the default password prompt method (console, whiptail, env_var, parameter)",',
        'help="Choose the default password prompt method (console, whiptail, env_var, parameter)",',
    )
    assert drifted != cli, "the drift did not apply"

    failures = _compare(cli=drifted)
    assert failures, "a reworded command-line option slipped through"
    assert any(
        "options of the command-line interface changed" in f for f in failures
    ), failures


def test_it_catches_narrowed_command_line_choices():
    """An option whose choices were narrowed."""
    cli = _cli_source()
    drifted = cli.replace(
        'choices=["console", "whiptail", "env_var", "parameter"],',
        'choices=["console", "whiptail"],',
    )
    assert drifted != cli, "the drift did not apply"

    failures = _compare(cli=drifted)
    assert failures, "narrowed command-line choices slipped through"
    assert any(
        "options of the command-line interface changed" in f for f in failures
    ), failures


def test_it_catches_a_reworded_command_line_message():
    """An output message that was reworded."""
    cli = _cli_source()
    drifted = cli.replace(
        'print(f"Current default prompt method: {get_default_prompt_method()}")',
        'print(f"Current method: {get_default_prompt_method()}")',
    )
    assert drifted != cli, "the drift did not apply"

    failures = _compare(cli=drifted)
    assert failures, "a reworded command-line message slipped through"
    assert any(
        "output of the command-line interface changed" in f for f in failures
    ), failures


def test_it_catches_a_dropped_command_line_option():
    """An option that went missing."""
    cli = _cli_source()
    drifted = cli.replace(
        """    parser.add_argument(
        "--show-method",
        action="store_true",
        help="Show the current default prompt method and exit",
    )
""",
        "",
    )
    assert drifted != cli, "the drift did not apply"

    failures = _compare(cli=drifted)
    assert failures, "a dropped command-line option slipped through"
    assert any(
        "options of the command-line interface changed" in f for f in failures
    ), failures


def test_it_catches_a_lost_section_header():
    """A section header that went missing.

    The original module carried a map of itself in its section headers -
    "# 1. Package Resolution" and so on.  They belong to the code they
    head, so the split has to keep all of them.

    This is not a hypothetical: the first cut of the split lost every
    header, because the script that cut the file took the code by AST
    node range, and the comments around it were not part of any node.
    """
    operations = _operations_source()
    drifted = operations.replace(
        "# 3. Package Installation\n", "", 1
    )
    assert drifted != operations, "the drift did not apply"

    failures = _compare(operations=drifted)
    assert failures, "a lost section header slipped through"
    assert any("section headers changed" in f for f in failures), failures


def test_it_catches_a_renumbered_section_header():
    """A section header that was renumbered."""
    operations = _operations_source()
    drifted = operations.replace(
        "# 3. Package Installation\n", "# 9. Package Installation\n", 1
    )
    assert drifted != operations, "the drift did not apply"

    failures = _compare(operations=drifted)
    assert failures, "a renumbered section header slipped through"
    assert any("section headers changed" in f for f in failures), failures


def test_it_catches_a_lost_module_level_comment():
    """A module-level comment of the library half that went missing."""
    operations = _operations_source()
    drifted = operations.replace(
        "# Module-level sudo password cache (session-scoped)\n", "", 1
    )
    assert drifted != operations, "the drift did not apply"

    failures = _compare(operations=drifted)
    assert failures, "a lost module-level comment slipped through"
    assert any("lost the comment" in f for f in failures), failures


def test_it_catches_a_lost_command_line_interface():
    """The whole interface going missing.

    The original carried the interface as a ``__main__`` block.  If the
    block is gone, the interface is gone with it - and that is a change
    of behaviour, not a detail.
    """
    original = _original_source()
    drifted = original.replace('if __name__ == "__main__":', "if False:")
    assert drifted != original, "the drift did not apply"

    failures = CHECKER.compare(
        drifted, _operations_source(), _adapter_source(), _cli_source()
    )
    assert failures, "a lost command-line interface slipped through"
    assert any("__main__ block" in f for f in failures), failures
