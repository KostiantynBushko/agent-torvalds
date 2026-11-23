"""
The task that runs now stands **on top** of the workflow pane, and the
list of the tasks **grows down**.

The operator said on 2026-11-22:

    > I also noticed that sometime the currently executed command in not
    > on top of the workflow window but instead it could apear somewhere
    > in the midle of the commands so that completed command (tool) in on
    > top and currently running is in the midle of the list or in the
    > bottom

and, on the same day, with the words of the decision:

    > please make sure the tool task grow down so that current executed
    > is always on top of the window

and again, on the same day, with the words that say what the list is:

    > the Recent Tool Task must be shown in the upside-down, so
    > data structure that shows recent tool task must be stack and the
    > current executed command must be on top of the window the previous
    > task must be below currently runned task and so on

What the tests hold together:

* **the task that runs now is the first task of the pane** -- and it
  stays there while the operator scrolls the log;
* **the tasks that are done are a stack** -- the newest completion on
  the top, and the task that ran before it right below it: the recent
  tool tasks are shown upside down;
* **the stack grows down** -- a task that is done is pushed on the top
  of the stack, and the tasks that were done before it go **down**;
* **the result of a call closes its own record** -- the workflow runs
  the calls of a turn concurrently, and two calls of the same tool
  carry the same name;
* **the run that is over closes the tasks that still run** -- a task
  that spins on top of the pane for ever is a lie the operator reads.

Run with:
    pytest tests/test_tui_task_order.py -v
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rich.console import Console  # noqa: E402

from components.tui.pane_scroll import PaneScroll  # noqa: E402
from components.tui.progress_view import ProgressView  # noqa: E402
from components.tui.state_bridge import TuiEventAdapter, TuiState  # noqa: E402


class FakeToolOutput:
    """The output of a tool, the way the framework carries it."""

    def __init__(self, content: str = "ok", is_error: bool = False):
        self.content = content
        self.is_error = is_error


class FakeToolCall:
    """The event the workflow writes when a tool starts."""

    def __init__(self, tool_name: str, tool_kwargs: dict, tool_id: str):
        self.tool_name = tool_name
        self.tool_kwargs = tool_kwargs
        self.tool_id = tool_id


class FakeToolCallResult:
    """The event the workflow writes when a tool is done."""

    def __init__(self, tool_name: str, tool_id: str, content: str = "ok"):
        self.tool_name = tool_name
        self.tool_id = tool_id
        self.tool_output = FakeToolOutput(content)


def the_pane(
    state: TuiState,
    height: int = 15,
    scroll: Optional[PaneScroll] = None,
) -> str:
    """The pane of the progress, the way the operator sees it."""
    console = Console(width=60, color_system=None)
    if scroll is None:
        scroll = PaneScroll()
    scroll.height = height
    panel = ProgressView().render(state, width=60, scroll=scroll)
    lines = console.render_lines(panel, console.options.update(width=60))
    return "\n".join("".join(s.text for s in line) for line in lines)


def the_line_of(drawn: str, needle: str) -> int:
    """The number of the line of the pane that carries the text."""
    for index, line in enumerate(drawn.splitlines()):
        if needle in line:
            return index
    return -1


class TestTheRunningTask(unittest.TestCase):
    """The task that runs now is on top of the pane."""

    def _state_with_a_finished_task_and_a_running_one(self) -> TuiState:
        state = TuiState()
        state.update_tool_start("read_file", {"file_path": "/etc/hosts"})
        state.update_tool_end("read_file", "ok")
        state.update_tool_start(
            "execute_shell_command", {"command": "ls -la /var/log"}
        )
        return state

    def test_the_task_that_runs_now_is_the_first_task_of_the_pane(self):
        state = self._state_with_a_finished_task_and_a_running_one()

        drawn = the_pane(state)

        running = the_line_of(drawn, "execute_shell_command")
        finished = the_line_of(drawn, "read_file")
        self.assertNotEqual(running, -1, "the running task is not on the screen")
        self.assertNotEqual(finished, -1, "the finished task is not on the screen")
        self.assertLess(
            running,
            finished,
            "the task that runs now is not on top of the pane",
        )

    def test_the_finished_task_is_below_the_running_one(self):
        state = self._state_with_a_finished_task_and_a_running_one()

        drawn = the_pane(state)

        self.assertLess(
            the_line_of(drawn, "execute_shell_command"),
            the_line_of(drawn, "read_file"),
        )

    def test_the_task_that_runs_now_stays_on_top_when_the_log_is_long(self):
        """The task that runs now is **pinned**: it is drawn above the
        window of the pane, so it is on top of the window even when the
        log is longer than the window."""
        state = TuiState()
        for index in range(10):
            state.update_tool_start(
                "execute_shell_command", {"command": f"command-{index}"}
            )
            state.update_tool_end("execute_shell_command", "ok")
        state.update_tool_start(
            "execute_shell_command", {"command": "the-one-that-runs"}
        )

        drawn = the_pane(state, height=12)

        self.assertIn(
            "the-one-that-runs",
            drawn,
            "the task that runs now is not on the screen of the pane",
        )
        self.assertLess(
            the_line_of(drawn, "the-one-that-runs"),
            the_line_of(drawn, "command-9"),
            "the task that runs now is not on top of the window",
        )

    def test_the_task_that_runs_now_stays_on_top_when_the_operator_scrolls(self):
        """The task that runs now is **pinned**.

        The history that the operator scrolls cannot take it away: it
        is drawn above the window of the pane, and it is on top of it
        whatever the window shows.
        """
        state = TuiState()
        for index in range(10):
            state.update_tool_start(
                "execute_shell_command", {"command": f"command-{index}"}
            )
            state.update_tool_end("execute_shell_command", "ok")
        state.update_tool_start(
            "execute_shell_command", {"command": "the-one-that-runs"}
        )

        scroll = PaneScroll()
        the_pane(state, height=6, scroll=scroll)

        # The end of the stack is the oldest task of the run: the
        # window goes there, and the newest one is not on the screen
        # any more.
        scroll.scroll_end()
        drawn = the_pane(state, height=6, scroll=scroll)

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

    def test_the_task_that_runs_now_is_on_top_when_the_calls_are_parallel(self):
        """The workflow runs the calls of a turn concurrently."""
        state = TuiState()
        state.update_tool_start(
            "execute_shell_command", {"command": "sleep 5"}, tool_id="call-1"
        )
        state.update_tool_start(
            "read_file", {"file_path": "/etc/hosts"}, tool_id="call-2"
        )
        state.update_tool_end("read_file", "ok", tool_id="call-2")

        drawn = the_pane(state)

        self.assertLess(
            the_line_of(drawn, "execute_shell_command"),
            the_line_of(drawn, "read_file"),
            "the task that runs now is not on top of the pane",
        )


class TestTheCallThatIsDone(unittest.TestCase):
    """The result of a call closes its own record."""

    def test_the_result_closes_the_record_of_its_own_call(self):
        state = TuiState()
        state.update_tool_start(
            "execute_shell_command", {"command": "whoami"}, tool_id="call-1"
        )
        state.update_tool_start(
            "execute_shell_command", {"command": "sleep 5"}, tool_id="call-2"
        )

        state.update_tool_end("execute_shell_command", "ok", tool_id="call-1")

        first = state.task_stack.tasks[0]
        second = state.task_stack.tasks[1]
        self.assertEqual(first.status, "completed")
        self.assertEqual(
            second.status,
            "running",
            "the result of a call closed the record of another call",
        )

    def test_two_calls_of_the_same_tool_are_told_apart(self):
        state = TuiState()
        state.update_tool_start(
            "execute_shell_command", {"command": "whoami"}, tool_id="call-1"
        )
        state.update_tool_start(
            "execute_shell_command", {"command": "sleep 5"}, tool_id="call-2"
        )

        state.update_tool_end("execute_shell_command", "ok", tool_id="call-2")

        # The call that is done is pushed on the top of the stack: it
        # is the newest one of the log.
        self.assertEqual(state.task_stack.tasks[0].status, "completed")
        self.assertEqual(state.task_stack.tasks[1].status, "running")

    def test_the_name_is_the_fallback_when_the_event_carries_no_id(self):
        """The events that carry no id are still closed by their name."""
        state = TuiState()
        state.update_tool_start("read_file", {"file_path": "/etc/hosts"})

        state.update_tool_end("read_file", "ok")

        self.assertEqual(state.task_stack.tasks[0].status, "completed")

    def test_the_adapter_hands_the_id_of_the_call_over(self):
        """The id of the call is what the framework carries, and the
        TUI uses it."""
        state = TuiState()
        adapter = TuiEventAdapter(state)

        asyncio.run(
            adapter._handle_tool_call(
                FakeToolCall(
                    "execute_shell_command", {"command": "whoami"}, "call-1"
                )
            )
        )
        asyncio.run(
            adapter._handle_tool_call(
                FakeToolCall(
                    "execute_shell_command", {"command": "sleep 5"}, "call-2"
                )
            )
        )
        asyncio.run(
            adapter._handle_tool_call_result(
                FakeToolCallResult("execute_shell_command", "call-1")
            )
        )

        self.assertEqual(state.task_stack.tasks[0].status, "completed")
        self.assertEqual(state.task_stack.tasks[1].status, "running")

    def test_the_run_that_is_over_closes_the_tasks_that_still_run(self):
        """A task that spins on top of the pane for ever is a lie the
        operator reads."""
        state = TuiState()
        state.update_tool_start(
            "execute_shell_command", {"command": "sleep 5"}, tool_id="call-1"
        )

        state.set_busy(False)

        self.assertEqual(state.task_stack.tasks[0].status, "error")
        self.assertEqual(
            [task for task in state.task_stack.tasks if task.status == "running"],
            [],
            "a task still runs after the run is over",
        )


class TestTheLog(unittest.TestCase):
    """The tasks that are done are a stack."""

    def _state_with_three_finished_tasks(self) -> TuiState:
        state = TuiState()
        for index in range(3):
            state.update_tool_start(
                "execute_shell_command", {"command": f"command-{index}"}
            )
            state.update_tool_end("execute_shell_command", "ok")
        return state

    def test_the_newest_task_is_first_and_the_oldest_is_last(self):
        """The stack is upside down: the newest completion is the first
        one, and the oldest is the last one."""
        state = self._state_with_three_finished_tasks()

        drawn = the_pane(state)

        self.assertLess(
            the_line_of(drawn, "command-2"),
            the_line_of(drawn, "command-0"),
            "the list of the tasks that are done is not a stack",
        )

    def test_the_list_grows_down(self):
        """A task that is done is pushed on the top of the stack.

        The list grows down: the tasks that were done before it go
        **down**, one line further down for every line the new task
        takes.  The list never grows up.
        """
        state = TuiState()
        for index in range(3):
            state.update_tool_start(
                "execute_shell_command",
                {"command": f"command-{index}"},
                tool_id=f"call-{index}",
            )
            state.update_tool_end(
                "execute_shell_command", "ok", tool_id=f"call-{index}"
            )

        scroll = PaneScroll()
        scroll.height = 15
        ProgressView().render(state, width=60, scroll=scroll)
        before = list(scroll.anchors)
        offset_before = scroll.offset_of_anchor(before[0])

        state.update_tool_start(
            "execute_shell_command",
            {"command": "the-newest-one"},
            tool_id="call-new",
        )
        state.update_tool_end(
            "execute_shell_command", "ok", tool_id="call-new"
        )
        ProgressView().render(state, width=60, scroll=scroll)
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
        """The task that is done **last** is the newest one, and the
        newest one is the first one of the stack."""
        state = TuiState()
        state.update_tool_start(
            "execute_shell_command",
            {"command": "the-first-one"},
            tool_id="call-1",
        )
        state.update_tool_start(
            "execute_shell_command",
            {"command": "the-second-one"},
            tool_id="call-2",
        )
        # The first one is done first, and the second one after it.
        state.update_tool_end("execute_shell_command", "ok", tool_id="call-1")
        state.update_tool_end("execute_shell_command", "ok", tool_id="call-2")

        drawn = the_pane(state)

        self.assertLess(
            the_line_of(drawn, "the-second-one"),
            the_line_of(drawn, "the-first-one"),
            "the stack is not in the order of what happened",
        )


if __name__ == "__main__":
    unittest.main()
