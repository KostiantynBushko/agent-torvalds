"""
The *Recent Tool Tasks* list stands at the current position, and it
grows down.

The operator said on 2026-11-22:

    > Recent Tool Tasks must scroll automatically into current position
    > during command execution

and, on the same day, with the words of the decision:

    > please make sure the tool task grow down so that current executed
    > is always on top of the window

and again, on the same day, with the words that say what the list is:

    > the Recent Tool Task must be shown in the upside-down, so
    > data structure that shows recent tool task must be stack and the
    > current executed command must be on top of the window the previous
    > task must be below currently runned task and so on

What the tests hold together:

* **the task that runs now is the head of the pane** -- the command
  that runs is the first thing on the screen, above the commands that
  are done, and it is **pinned**: it stays there while the operator
  scrolls the history;
* **the window is at the current position** -- it follows the **top**
  of the stack, so the newest completion is on the screen, and it is
  there while the work goes on;
* **the list grows down** -- a task that is done is pushed on the top
  of the stack, and the tasks that were done before it go **down**;
* **the operator who scrolled away keeps the task he is reading** --
  the anchor holds his place while the work goes on;
* **the whole of the log is reachable** -- the keys of the pane reach
  the tasks that are not on the screen.

Run with:
    pytest tests/test_tui_current_position.py -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rich.console import Console  # noqa: E402

from components.tui.pane_scroll import PaneScroll  # noqa: E402
from components.tui.progress_view import SPINNER_FRAMES  # noqa: E402
from components.tui.progress_view import ProgressView  # noqa: E402
from components.tui.state_bridge import TuiState  # noqa: E402


def a_state_with_done_tasks(count: int) -> TuiState:
    """A state whose list of the tasks that are done is not empty.

    Args:
        count: The number of the tasks that are done.

    Returns:
        The state.
    """
    state = TuiState()
    for index in range(count):
        state.update_tool_start(
            "execute_shell_command",
            {"command": f"the-done-command-{index}"},
            tool_id=f"done-{index}",
        )
        state.update_tool_end(
            "execute_shell_command", "ok", tool_id=f"done-{index}"
        )
    return state


def the_window(
    state: TuiState,
    height: int = 12,
    scroll: Optional[PaneScroll] = None,
) -> Tuple[list, PaneScroll]:
    """The window of the pane, and the scroll it was drawn with.

    The window is the **log** of the tasks that are done.  The task
    that runs now is **pinned** above it: it is not a part of the
    window, and the history that the operator scrolls cannot take it
    away.

    Args:
        state: The state of the TUI.
        height: The number of lines the pane has on the screen.
        scroll: The scroll of the pane.  A new one when it is not given.

    Returns:
        The window, and the scroll.
    """
    if scroll is None:
        scroll = PaneScroll()
    scroll.height = height
    ProgressView().render(state, width=60, scroll=scroll)
    return scroll.window(), scroll


def the_pane(
    state: TuiState,
    height: int = 12,
    scroll: Optional[PaneScroll] = None,
) -> str:
    """The pane of the progress, the way the operator sees it.

    Args:
        state: The state of the TUI.
        height: The number of lines the pane has on the screen.
        scroll: The scroll of the pane.  A new one when it is not given.

    Returns:
        The text of the pane.
    """
    console = Console(width=60, color_system=None)
    if scroll is None:
        scroll = PaneScroll()
    scroll.height = height
    panel = ProgressView().render(state, width=60, scroll=scroll)
    lines = console.render_lines(panel, console.options.update(width=60))
    return "\n".join("".join(s.text for s in line) for line in lines)


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


class TestTheCurrentPosition(unittest.TestCase):
    """The window is at the current position of the work."""

    def test_the_task_that_runs_now_is_the_head_of_the_pane(self):
        """The command that runs is the first thing on the screen.

        The head of the pane is the **name** of the task that runs now
        -- the line with the spinner -- and its command is the line
        under it.
        """
        state = a_state_with_done_tasks(3)
        state.update_tool_start(
            "execute_shell_command", {"command": "the-one-that-runs"}
        )

        drawn = the_pane(state)

        self.assertIn(
            SPINNER_FRAMES[0],
            drawn,
            "the task that runs now is not on the screen",
        )
        self.assertLess(
            the_line_of(drawn, "the-one-that-runs"),
            the_line_of(drawn, "the-done-command-2"),
            "the task that runs now is not on top of the pane",
        )

    def test_the_task_that_runs_now_is_pinned_above_the_window(self):
        """The task that runs now is not a part of the window.

        It is **pinned** above it: the history that the operator
        scrolls cannot take it away.
        """
        state = a_state_with_done_tasks(3)
        state.update_tool_start(
            "execute_shell_command", {"command": "the-one-that-runs"}
        )

        window, _ = the_window(state)

        self.assertNotIn(
            "the-one-that-runs",
            "\n".join(window),
            "the task that runs now is a part of the window of the log",
        )

    def test_the_task_that_runs_now_stays_on_top_when_the_operator_scrolls(self):
        """The pinned task is on top of the pane whatever he does."""
        state = a_state_with_done_tasks(6)
        state.update_tool_start(
            "execute_shell_command", {"command": "the-one-that-runs"}
        )
        scroll = PaneScroll()
        the_window(state, scroll=scroll)

        # The end of the stack is the oldest task of the run: the
        # window goes there, and the newest one is not on the screen
        # any more.
        scroll.scroll_end()
        drawn = the_pane(state, scroll=scroll)

        self.assertIn(
            "the-one-that-runs",
            drawn,
            "the history took the task that runs now away from the top",
        )
        # The pinned task stands above every line of the window.
        _, anchors = ProgressView().content_lines(state, 46)
        running = state.task_stack.running()[0].id
        first_of_the_window = len(anchors) - len(scroll.anchors)
        self.assertLess(
            max(
                index
                for index, anchor in enumerate(anchors)
                if anchor == running
            ),
            first_of_the_window,
            "the task that runs now is not on top of the window",
        )

    def test_the_window_is_at_the_current_position(self):
        """The window is stuck to the top of the stack.

        The top of the stack is the newest completion: it is the
        current position of the work, and it is on the screen.
        """
        state = a_state_with_done_tasks(3)

        window, scroll = the_window(state)

        self.assertIn(
            "the-done-command-2",
            "\n".join(window),
            "the newest completion is not on the screen",
        )
        self.assertEqual(
            scroll.offset,
            0,
            "the window is not at the current position",
        )

    def test_the_window_stays_at_the_current_position_while_a_command_runs(self):
        """The list grows while a command runs -- and the window follows
        the top of it."""
        state = a_state_with_done_tasks(3)
        scroll = PaneScroll()
        the_window(state, scroll=scroll)

        state.update_tool_start(
            "execute_shell_command", {"command": "the-one-that-runs"}
        )
        state.update_tool_end("execute_shell_command", "ok")
        window, scroll = the_window(state, scroll=scroll)

        self.assertIn(
            "the-one-that-runs",
            "\n".join(window),
            "the window did not scroll into the current position",
        )
        self.assertEqual(scroll.offset, 0)


class TestTheGrowth(unittest.TestCase):
    """The list of the tasks grows down."""

    def test_a_task_that_is_done_is_pushed_on_the_top(self):
        """The list grows down: the tasks that were done before it go
        down, and the new one is right below the task that runs now."""
        state = a_state_with_done_tasks(3)
        scroll = PaneScroll()
        the_window(state, scroll=scroll)
        before = list(scroll.anchors)
        offset_before = scroll.offset_of_anchor(before[0])

        state.update_tool_start(
            "execute_shell_command",
            {"command": "the-newest-one"},
            tool_id="call-new",
        )
        state.update_tool_end("execute_shell_command", "ok", tool_id="call-new")
        window, scroll = the_window(state, scroll=scroll)
        after = list(scroll.anchors)

        self.assertEqual(
            after[len(after) - len(before):],
            before,
            "the list does not grow down: the tasks that were done "
            "before it moved",
        )
        self.assertGreater(
            scroll.offset_of_anchor(before[0]),
            offset_before,
            "the list does not grow down: the tasks that were done "
            "before it did not go down",
        )

    def test_the_newest_completion_is_the_first_one(self):
        """The newest completion is the first one and the oldest is the
        last one: the recent tool tasks are shown upside down."""
        state = a_state_with_done_tasks(3)

        window, _ = the_window(state)
        drawn = "\n".join(window)

        self.assertLess(
            drawn.index("the-done-command-2"),
            drawn.index("the-done-command-0"),
            "the stack is not in the order of what happened",
        )


class TestTheOperator(unittest.TestCase):
    """The operator keeps the place he is at."""

    def test_the_operator_who_scrolled_away_keeps_the_task_he_is_reading(self):
        """The anchor holds his place while the work goes on."""
        state = a_state_with_done_tasks(6)
        scroll = PaneScroll()
        the_window(state, scroll=scroll)

        scroll.scroll_down(4)
        the_window(state, scroll=scroll)
        anchor = scroll.anchor

        state.update_tool_start(
            "execute_shell_command", {"command": "the-one-that-runs"}
        )
        window, scroll = the_window(state, scroll=scroll)

        self.assertEqual(
            scroll.anchor,
            anchor,
            "the window moved while the operator was reading an old task",
        )

    def test_the_whole_of_the_log_is_reachable(self):
        """The keys of the pane reach the tasks that are not on the
        screen.

        The stack carries the newest tasks that are done -- six of them
        -- and the window of the pane shows a few of them at a time.
        The older tasks are **below** the newest one, and the key that
        walks down the window reaches them.
        """
        state = a_state_with_done_tasks(6)
        scroll = PaneScroll()
        the_window(state, height=6, scroll=scroll)

        seen = set()
        for _ in range(40):
            for line in scroll.window():
                if "the-done-command-" in line:
                    seen.add(line.strip())
            scroll.scroll_down(1)

        self.assertEqual(
            len(seen),
            6,
            "the rest of the log is not reachable with the keys of the pane",
        )


if __name__ == "__main__":
    unittest.main()
