"""
The *Recent Tool Tasks* list and the position of the window during the
execution of a command.

**The operator said on 2026-11-22:**

    > please make sure the tool task grow down so that current executed
    > is always on top of the window

The *Workflow & Tool Progress* pane carries the list of the tool tasks
of the run.  The request is about **two** things at once:

* the list **grows down** -- a task that is done is appended at the
  bottom of the list, the tasks that were done before it do not move,
  and "down" walks forward in time;
* the task that **runs now is always on top of the window** -- the
  command that runs is the first thing on the screen, and it stays
  there while the operator scrolls the history.

The pane answers both with two parts: the task that runs now is
**pinned** above the window of the pane, and the window carries the
list of the tasks that are done -- a log, the oldest completion first,
the newest at the bottom -- and it is stuck to the tail of that log.

The probe answers five questions:

  1. **Is the task that runs now on top of the pane?**

  2. **Does it stay on top while the operator scrolls the history?**

  3. **Does the list of the tasks grow down?**

  4. **Is the window at the current position?**  The newest completion
     is on the screen, and the window follows it while the work goes
     on.

  5. **Does the window keep the place of the operator?**  The operator
     who scrolled away keeps the task he is reading.

Usage:
    python investigate/tui-autoscroll/probe_autoscroll.py

The exit code is 0 when every check holds, 1 when one does not.

The probe writes nothing and talks to no service.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Tuple

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from rich.console import Console  # noqa: E402

from components.tui.layout_manager import (  # noqa: E402
    build_torvalds_layout,
    pane_content_height,
    progress_pane_width,
)
from components.tui.progress_view import ProgressView  # noqa: E402
from components.tui.state_bridge import TuiState  # noqa: E402

#: The width of the terminal of the operator.
WIDTH = 229

#: The height of the terminal of the operator.
HEIGHT = 50

#: The command that runs now in the capture of the operator: a heredoc
#: that carries a document.  It takes nine lines on the screen.
LONG_COMMAND = (
    "cd ~/projects/agent-torvalds && timeout 900 .venv/bin/python - <<'PY'\n"
    "from pathlib import Path\n"
    "entry = '''\n"
    "- **The command bar carries no mark.**  So the TUI showed no mark at all\n"
    "  until the operator pressed `Tab` -- and the mark that was meant to\n"
    "  answer *which pane is the selected one* appeared only after the\n"
    "  operator had found it himself.\n"
    "'''\n"
    "path.write_text(text, encoding='utf-8')\n"
    "PY"
)

#: A short command, the kind that fits on one line.
SHORT_COMMAND = (
    "cd ~/projects/agent-torvalds && .venv/bin/python scripts/ci_test_gate.py"
)


# ---------------------------------------------------------------------------
# The helpers
# ---------------------------------------------------------------------------


def the_pane_of(state: TuiState) -> str:
    """The pane, the way the terminal renders it.

    The pane is drawn in the real layout, at the width and the height
    of the terminal of the operator, and the text that is on the screen
    is the text of the region of the pane.

    Args:
        state: The state of the TUI.

    Returns:
        The text of the pane.
    """
    layout = build_torvalds_layout()
    console = Console(width=WIDTH, height=HEIGHT, color_system=None)
    console.render_lines(layout, console.options.update_dimensions(WIDTH, HEIGHT))
    scroll = state.scroll_of("progress")
    scroll.height = pane_content_height(layout, "progress_pane")
    panel = ProgressView().render(
        state, width=progress_pane_width(WIDTH), scroll=scroll
    )
    layout["progress_pane"].update(panel)
    lines = console.render_lines(
        layout, console.options.update_dimensions(WIDTH, HEIGHT)
    )
    region = layout.map[layout["progress_pane"]].region
    return "\n".join(
        "".join(segment.text for segment in line)
        for line in lines[region.y : region.y + region.height]
    )


def the_line_of(drawn: str, needle: str) -> int:
    """The number of the line of the pane that carries the text.

    Args:
        drawn: The text of the pane.
        needle: The text to look for.

    Returns:
        The number of the line, and -1 when there is none.
    """
    for index, line in enumerate(drawn.splitlines()):
        if needle in line:
            return index
    return -1


def a_state_with_a_long_log(tasks: int = 12) -> TuiState:
    """A state whose list of the tasks that are done is longer than the pane.

    Args:
        tasks: The number of the tasks that are done.

    Returns:
        The state.
    """
    state = TuiState()
    for index in range(tasks):
        state.update_tool_start(
            "execute_shell_command",
            {"command": f"the-old-command-{index} " + "x" * 120},
            tool_id=f"old-{index}",
        )
        state.update_tool_end(
            "execute_shell_command", "done", tool_id=f"old-{index}"
        )
    return state


def the_id_of_the_task(state: TuiState, command: str) -> str:
    """The id of the task that runs the command.

    Args:
        state: The state of the TUI.
        command: The command of the task.

    Returns:
        The id of the task, and an empty string when there is none.
    """
    for task in state.tool_tasks:
        if command in task.details:
            return task.id
    return ""


def the_done_tasks_above(state: TuiState, anchor: str) -> int:
    """The number of the lines of the tasks that are done above a task.

    The count is the measure of the **growth** of the list: a list
    that grows down keeps the count, and a list that grows up -- the
    newest completion first -- pushes the tasks that were done before
    it further down.

    Args:
        state: The state of the TUI.
        anchor: The id of the task to count above.

    Returns:
        The number of the lines of the tasks that are done above it.
    """
    scroll = state.scroll_of("progress")
    done = {
        task.id
        for task in state.tool_tasks
        if task.status != "running"
    }
    if not scroll.anchors or anchor not in scroll.anchors:
        return -1

    index = scroll.anchors.index(anchor)
    return sum(1 for value in scroll.anchors[:index] if value in done)


# ---------------------------------------------------------------------------
# The measurement
# ---------------------------------------------------------------------------


def check_the_task_that_runs_now_is_on_top_of_the_pane() -> Tuple[bool, str]:
    """The task that runs now is on top of the pane.

    The operator has to see the command that runs -- and it has to be
    the first thing on the screen, above the commands that are done.

    Returns:
        Whether the check holds, and the report of the measurement.
    """
    state = TuiState()
    state.update_tool_start(
        "execute_shell_command", {"command": SHORT_COMMAND}, tool_id="run-1"
    )
    drawn = the_pane_of(state)

    running = the_line_of(drawn, "ci_test_gate.py")
    header = the_line_of(drawn, "Recent Tool Tasks:")
    on_top = running > header and running != -1
    report = (
        f"the task that runs now is on top of the pane: {on_top}\n"
        f"  the header of the list: line {header}\n"
        f"  the command that runs: line {running}"
    )
    return on_top, report


def check_it_stays_on_top_while_the_operator_scrolls() -> Tuple[bool, str]:
    """The task that runs now stays on top while the operator scrolls.

    The task that runs now is **pinned**: it is drawn above the window
    of the pane, so the history that the operator scrolls cannot take
    it away.

    Returns:
        Whether the check holds, and the report of the measurement.
    """
    state = a_state_with_a_long_log()
    state.update_tool_start(
        "execute_shell_command", {"command": SHORT_COMMAND}, tool_id="run-1"
    )
    scroll = state.scroll_of("progress")
    the_pane_of(state)

    scroll.scroll_end()
    drawn = the_pane_of(state)

    running = the_line_of(drawn, "ci_test_gate.py")
    header = the_line_of(drawn, "Recent Tool Tasks:")
    on_top = running > header and running != -1
    report = (
        f"the task that runs now stays on top of the pane: {on_top}\n"
        f"  the offset of the window: {scroll.offset} of "
        f"{scroll.total_lines} lines\n"
        f"  the command that runs: line {running}"
    )
    return on_top, report


def check_the_list_grows_down() -> Tuple[bool, str]:
    """The list of the tasks grows down.

    A task that is done is appended at the bottom of the list, and the
    tasks that were done before it do not move: the list grows down,
    and "down" walks forward in time.

    Returns:
        Whether the check holds, and the report of the measurement.
    """
    state = TuiState()
    for index in range(3):
        state.update_tool_start(
            "execute_shell_command",
            {"command": f"the-done-command-{index}"},
            tool_id=f"done-{index}",
        )
        state.update_tool_end(
            "execute_shell_command", "ok", tool_id=f"done-{index}"
        )
    the_pane_of(state)

    anchor = the_id_of_the_task(state, "the-done-command-0")
    before = the_done_tasks_above(state, anchor)

    # A new task runs and is done: it is appended at the bottom of the
    # list, and the task that was done before it does not move.
    state.update_tool_start(
        "execute_shell_command", {"command": "the-newest-command"},
        tool_id="new-1",
    )
    state.update_tool_end("execute_shell_command", "ok", tool_id="new-1")
    the_pane_of(state)

    after = the_done_tasks_above(state, anchor)
    grows_down = before == after and before != -1

    report = (
        f"the list of the tasks grows down: {grows_down}\n"
        f"  the lines of the done tasks above the first one: "
        f"{before} before, {after} after"
    )
    return grows_down, report


def check_the_window_is_at_the_current_position() -> Tuple[bool, str]:
    """The window is at the current position of the work.

    The window is stuck to the tail of the log: the newest completion
    is on the screen, and the window follows it while the work goes on.

    Returns:
        Whether the check holds, and the report of the measurement.
    """
    state = a_state_with_a_long_log()
    scroll = state.scroll_of("progress")
    the_pane_of(state)

    state.update_tool_start(
        "execute_shell_command", {"command": SHORT_COMMAND}, tool_id="run-1"
    )
    the_pane_of(state)

    window = "\n".join(scroll.window())
    at_the_position = "the-old-command-11" in window
    report = (
        f"the window is at the current position: {at_the_position}\n"
        f"  the offset of the window: {scroll.offset} of "
        f"{scroll.total_lines} lines\n"
        f"  the newest completion is on the screen: "
        f"{'the-old-command-11' in window}"
    )
    return at_the_position, report


def check_the_window_keeps_the_place_of_the_operator() -> Tuple[bool, str]:
    """The operator who scrolled away keeps the task he is reading.

    Returns:
        Whether the check holds, and the report of the measurement.
    """
    state = a_state_with_a_long_log()
    scroll = state.scroll_of("progress")
    the_pane_of(state)

    scroll.scroll_down(5)
    the_pane_of(state)
    before = scroll.anchor

    state.update_tool_start(
        "execute_shell_command", {"command": SHORT_COMMAND}, tool_id="run-1"
    )
    the_pane_of(state)
    held = before == scroll.anchor and scroll.offset > 0

    report = (
        f"the operator who scrolled away keeps the task he is reading: {held}\n"
        f"  the anchor before: {before!r}\n"
        f"  the anchor after: {scroll.anchor!r}\n"
        f"  the offset of the window: {scroll.offset}"
    )
    return held, report


# ---------------------------------------------------------------------------
# The screen the operator sees
# ---------------------------------------------------------------------------


def show_the_screen_of_the_operator() -> None:
    """Show the pane while a command runs."""
    print("=" * 78)
    print("The pane while a long command runs:")
    print("=" * 78)
    state = a_state_with_a_long_log()
    state.update_tool_start(
        "execute_shell_command", {"command": LONG_COMMAND}, tool_id="run-1"
    )
    print(the_pane_of(state))
    print()

    print("=" * 78)
    print("The pane while a short command runs:")
    print("=" * 78)
    state = a_state_with_a_long_log()
    state.update_tool_start(
        "execute_shell_command", {"command": SHORT_COMMAND}, tool_id="run-1"
    )
    print(the_pane_of(state))
    print()


def main() -> int:
    """Run every check and report what holds."""
    show_the_screen_of_the_operator()

    checks = (
        ("the task that runs now is on top of the pane",
         check_the_task_that_runs_now_is_on_top_of_the_pane),
        ("the task that runs now stays on top while the operator scrolls",
         check_it_stays_on_top_while_the_operator_scrolls),
        ("the list of the tasks grows down",
         check_the_list_grows_down),
        ("the window is at the current position",
         check_the_window_is_at_the_current_position),
        ("the window keeps the place of the operator",
         check_the_window_keeps_the_place_of_the_operator),
    )

    failed = 0
    print("=" * 78)
    for name, check in checks:
        ok, report = check()
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
        for line in str(report).split("\n"):
            print(f"        {line}")
        if not ok:
            failed += 1
    print("=" * 78)

    if failed:
        print(f"{failed} check(s) do not hold.")
        return 1
    print("Every check holds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
