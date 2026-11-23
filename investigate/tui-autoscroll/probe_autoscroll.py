"""
The *Recent Tool Tasks* list and the position of the window during the
execution of a command.

**The operator said on 2026-11-22:**

    > please make sure the tool task grow down so that current executed
    > is always on top of the window

and, on the same day, with the words that say what the list is:

    > the Recent Tool Task must be shown in the upside-down, so
    > data structure that shows recent tool task must be stack and the
    > current executed command must be on top of the window the previous
    > task must be below currently runned task and so on

The *Workflow & Tool Progress* pane carries the list of the tool tasks
of the run.  The request is about **two** things at once:

* the recent tool tasks are shown **upside down** -- the structure that
  carries them is a **stack**: the newest task is on the top of it, the
  task that ran before it is right below it, and the one before that
  is below that;
* the task that **runs now is always on top of the window** -- the
  command that runs is the first thing on the screen, and it stays
  there while the operator scrolls the history.

The pane answers both with three parts: the task that runs now is
**pinned** above the window of the pane, the window carries the
**stack** of the tasks that are done -- the newest completion first --
and the window is stuck to the **top** of that stack, which is the
current position of the work.

The stack grows **down**: a task that is done is pushed on the top of
the stack, and the tasks that were done before it go down, one line
further down for every line the new task takes.

The probe answers six questions:

  1. **Is the task that runs now on top of the pane?**

  2. **Does it stay on top while the operator scrolls the history?**

  3. **Is the task that ran before it directly below it?**

  4. **Does the list grow down?**  A task that is done goes on the top
     of the stack, and the tasks that were done before it go down.

  5. **Is the window at the current position?**  The newest completion
     is on the screen, at the top of the window, and the window
     follows it while the work goes on.

  6. **Does the window keep the place of the operator?**  The operator
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
from components.tui.tool_arguments import format_arguments  # noqa: E402

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
    """A state whose stack of the tasks that are done is longer than the pane.

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
    for task in state.task_stack.tasks:
        if command in format_arguments(task.arguments):
            return task.id
    return ""


def the_lines_of_the_task(state: TuiState, task_id: str) -> List[int]:
    """The lines of the content that belong to a task.

    The anchor of a line is the id of the task the line belongs to, so
    the lines of a task are found without guessing.

    Args:
        state: The state of the TUI.
        task_id: The id of the task.

    Returns:
        The numbers of the lines of the task.
    """
    _, anchors = ProgressView().content_lines(state, 46)
    return [
        index for index, anchor in enumerate(anchors) if anchor == task_id
    ]


def the_offset_of_the_task(state: TuiState, task_id: str) -> int:
    """The number of the line of the window that carries the task.

    The window is the stack of the tasks that are done.  The offset of
    a task is the measure of where it stands in it: a task that goes
    **down** has a bigger offset.

    Args:
        state: The state of the TUI.
        task_id: The id of the task.

    Returns:
        The offset of the task, and -1 when it is not on the screen.
    """
    scroll = state.scroll_of("progress")
    if not scroll.anchors or task_id not in scroll.anchors:
        return -1
    return scroll.anchors.index(task_id)


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


def check_the_previous_task_is_below_the_running_one() -> Tuple[bool, str]:
    """The task that ran before it is right below it.

    The recent tool tasks are shown upside down: the newest completion
    is the first one of the stack, and the task that ran before it is
    right below the task that runs now.

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
    state.update_tool_start(
        "execute_shell_command", {"command": SHORT_COMMAND}, tool_id="run-1"
    )
    the_pane_of(state)

    running = state.task_stack.running()[0].id
    previous = state.task_stack.done()[0].id
    running_lines = the_lines_of_the_task(state, running)
    previous_lines = the_lines_of_the_task(state, previous)

    directly_below = bool(running_lines and previous_lines) and (
        min(previous_lines) == max(running_lines) + 1
    )
    report = (
        f"the task that ran before is right below the one that runs: "
        f"{directly_below}\n"
        f"  the lines of the task that runs: {running_lines}\n"
        f"  the lines of the task that ran before: {previous_lines}"
    )
    return directly_below, report


def check_the_list_grows_down() -> Tuple[bool, str]:
    """The list of the tasks grows down.

    A task that is done is pushed on the top of the stack, and the
    tasks that were done before it go **down** -- one line further
    down for every line the new task takes.  The list never grows up.

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
    before = the_offset_of_the_task(state, anchor)

    # A new task runs and is done: it is pushed on the top of the
    # stack, and the task that was done before it goes down.
    state.update_tool_start(
        "execute_shell_command", {"command": "the-newest-command"},
        tool_id="new-1",
    )
    state.update_tool_end("execute_shell_command", "ok", tool_id="new-1")
    the_pane_of(state)

    after = the_offset_of_the_task(state, anchor)
    newest = the_id_of_the_task(state, "the-newest-command")
    scroll = state.scroll_of("progress")
    on_top = bool(newest) and bool(scroll.anchors) and scroll.anchors[0] == newest
    grows_down = before != -1 and after > before

    report = (
        f"the list of the tasks grows down: {grows_down}\n"
        f"  the offset of the task that was done first: {before} before, "
        f"{after} after\n"
        f"  the new task is on the top of the stack: {on_top}"
    )
    return grows_down and on_top, report


def check_the_window_is_at_the_current_position() -> Tuple[bool, str]:
    """The window is at the current position of the work.

    The window is stuck to the top of the stack: the newest completion
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
    newest = state.task_stack.done()[0]
    # The detail of a command is split over several lines, and the
    # whole of it is never on one line: the first word of it is what
    # the operator reads.
    words = format_arguments(newest.arguments).split()
    head = words[0] if words else ""
    at_the_position = (
        newest.id in scroll.anchors
        and scroll.anchors.index(newest.id) == 0
        and scroll.offset == 0
        and head in window
    )
    report = (
        f"the window is at the current position: {at_the_position}\n"
        f"  the offset of the window: {scroll.offset} of "
        f"{scroll.total_lines} lines\n"
        f"  the newest completion is on the screen: {head in window}"
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
        ("the task that ran before is right below the one that runs",
         check_the_previous_task_is_below_the_running_one),
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
