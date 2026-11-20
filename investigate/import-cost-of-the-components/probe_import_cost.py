"""
Measure what the import of a component of the agent costs.

The question this probe answers: a program that wants *one* small
module of the TUI — the input reader, which needs nothing but the
standard library — pays for the whole of llama_index.  How much?

The probe is read-only: it measures, prints and returns.  It writes
nothing and talks to no service, and it can be run twice.

Every import is measured in a **fresh interpreter**, because an import
that has already happened is not measured again — the second import of
a module in the same process costs nothing, and the number would be a
lie.

Run with:
    python investigate/import-cost-of-the-components/probe_import_cost.py
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

#: The budget the helper of the multiline input test has for the reader
#: to reach the terminal.  The parent types the keys after this many
#: seconds, whatever the reader is doing.
TYPING_BUDGET = 1.2

#: The imports that are measured, and what they are for.
IMPORTS = (
    ("components.tui.input_reader", "what the reader of the terminal pays"),
    ("components.tui.input_text", "the text of the input bar"),
    ("components.tui.layout_manager", "the layout of the screen"),
    ("components.tui.tui_app", "the application itself"),
    ("components.tui.tool_selection_view", "the tools of llama_index"),
    ("components.tui", "the package of the TUI"),
    ("components", "the package of the components"),
)


def time_of(statement, repeats=3):
    """How long a statement takes in a fresh interpreter.

    Args:
        statement: The Python that is run.
        repeats: How many interpreters are used.

    Returns:
        A pair of the fastest of the runs in seconds, and the error
        of the last run when it failed.
    """
    fastest = None
    error = None

    for _ in range(repeats):
        started = time.perf_counter()
        result = subprocess.run(
            [sys.executable, "-c", statement],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
        elapsed = time.perf_counter() - started
        if result.returncode != 0:
            error = result.stderr.strip().splitlines()[-1:] or ["failed"]
            continue
        if fastest is None or elapsed < fastest:
            fastest = elapsed

    return fastest, error


def import_time_of(module):
    """The import tree of a module, the slowest importers first.

    Args:
        module: The module that is imported.

    Returns:
        A list of (cumulative seconds, name) pairs, the slowest first.
    """
    result = subprocess.run(
        [sys.executable, "-X", "importtime", "-c",
         f"import sys; sys.path.insert(0, {str(ROOT)!r}); import {module}"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )

    rows = []
    for line in result.stderr.splitlines():
        if not line.startswith("import time:"):
            continue
        parts = line.split("|")
        if len(parts) != 3:
            continue
        try:
            cumulative = int(parts[1])
        except ValueError:
            continue
        rows.append((cumulative, parts[2].strip()))

    rows.sort(reverse=True)
    return rows


def main():
    """Print the measurement."""
    print("The import of one module of the agent")
    print("=" * 72)
    print(f"root: {ROOT.name}")
    print()

    print(f"1. The cost of every import, against the {TYPING_BUDGET} s budget")
    print("-" * 72)
    print(f"{'import':<38} {'seconds':>9}  {'of the budget':>13}")
    for module, _why in IMPORTS:
        elapsed, error = time_of(
            f"import sys; sys.path.insert(0, {str(ROOT)!r}); "
            f"import {module}"
        )
        if elapsed is None:
            print(f"{module:<38} {'FAILED':>9}  {error}")
            continue
        share = elapsed / TYPING_BUDGET
        print(f"{module:<38} {elapsed:>9.3f}  {share:>12.1%}")
    print()

    print("2. What the reader of the terminal pays for")
    print("-" * 72)
    elapsed, _ = time_of(
        f"import sys; sys.path.insert(0, {str(ROOT)!r}); "
        "from components.tui.input_reader import NonBlockingInputReader"
    )
    print(f"   the import of the reader      : {elapsed:.3f} s")
    print(f"   the budget before the keys    : {TYPING_BUDGET:.3f} s")
    print(f"   the margin                    : {TYPING_BUDGET - elapsed:.3f} s")
    print()

    print("3. Where the time goes in the reader's import")
    print("-" * 72)
    rows = import_time_of("components.tui.input_reader")
    print(f"   {'cumulative':>12}  module")
    for cumulative, name in rows[:10]:
        print(f"   {cumulative / 1_000_000:>9.3f} s  {name}")
    print()

    print("4. The price of the tools of llama_index")
    print("-" * 72)
    elapsed, _ = time_of(
        f"import sys; sys.path.insert(0, {str(ROOT)!r}); "
        "from components.tui.tool_selection_view import discover_all_tools"
    )
    reader, _ = time_of(
        f"import sys; sys.path.insert(0, {str(ROOT)!r}); "
        "from components.tui.input_reader import NonBlockingInputReader"
    )
    print(f"   the reader                    : {reader:.3f} s")
    print(f"   the tools of llama_index      : {elapsed:.3f} s")
    if reader:
        print(f"   the ratio                     : {elapsed / reader:.0f} to 1")
    print()
    print("The reader needs nothing but the standard library.  It does not")
    print("speak to llama_index, and it does not pay for it.")


if __name__ == "__main__":
    main()
