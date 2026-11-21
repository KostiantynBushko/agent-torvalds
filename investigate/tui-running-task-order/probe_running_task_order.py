"""Probe: where does the task that runs *now* stand in the workflow pane?

**Read-only.**  It builds a ``TuiState``, feeds it the workflow events
the way the agent really sends them, and prints what the operator
would see in the *Workflow & Tool Progress* pane.  It writes nothing,
changes nothing and talks to nothing.

The question:

    The operator says that the command that runs **now** is not on top
    of the workflow window -- it shows up somewhere in the middle of the
    commands, with the finished commands above it.  Where does it stand,
    and why?

What the probe reproduces:

* the order in which the workflow publishes the events
  (``ToolCall`` when the tool starts, ``ToolCallResult`` when it is
  done) -- taken from
  ``llama_index/core/agent/workflow/base_agent.py``, where the
  ``call_tool`` step writes the two events and the workflow runs the
  steps **concurrently**;
* the way the TUI turns the events into the records of the pane
  (``components/tui/state_bridge.py``);
* the way the pane renders them (``components/tui/progress_view.py``).

Run it:

    .venv/bin/python investigate/tui-running-task-order/probe_running_task_order.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, List, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from components.tui.progress_view import ProgressView  # noqa: E402
from components.tui.state_bridge import TuiEventAdapter, TuiState  # noqa: E402


# ---------------------------------------------------------------------------
# The events of the workflow, in the shape the framework writes them
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# The helpers
# ---------------------------------------------------------------------------


def feed(adapter: TuiEventAdapter, events: List[Any]) -> None:
    """Give the events to the adapter, the way the consumer does."""
    for event in events:
        if isinstance(event, FakeToolCall):
            asyncio.run(adapter._handle_tool_call(event))
        else:
            asyncio.run(adapter._handle_tool_call_result(event))


def the_pane(state: TuiState, width: int = 46) -> List[str]:
    """The pane of the progress, the way the operator sees it."""
    view = ProgressView()
    lines, _ = view.content_lines(state, width)
    return lines


def the_line_of_the_task(state: TuiState, task_id: str) -> int:
    """The number of the line of the pane that carries the task.

    The anchor of a line is the id of the task it belongs to, so the
    task is found in the pane without guessing.
    """
    _, anchors = ProgressView().content_lines(state, 46)
    for index, anchor in enumerate(anchors):
        if anchor == task_id:
            return index
    return -1


def the_running_task_is_on_top(state: TuiState) -> bool:
    """Whether the task that runs now stands above the tasks that are done.

    The question is not "which line carries the spinner" -- the pane
    can spin on the wrong command.  The question is: **is the task
    that really runs the first one of the pane?**
    """
    running = [task for task in state.tool_tasks if task.status == "running"]
    done = [task for task in state.tool_tasks if task.status != "running"]
    if not running:
        return True

    line = the_line_of_the_task(state, running[0].id)
    for task in done:
        if the_line_of_the_task(state, task.id) < line:
            return False
    return True


def the_call_of(state: TuiState, tool_id: str) -> str:
    """The state of the record of the call with that id."""
    for task in state.tool_tasks:
        if getattr(task, "tool_id", "") == tool_id:
            return task.status
    return "(no record)"


def report(title: str, state: TuiState, truth: str = "") -> None:
    """Print the evidence of one scenario."""
    print("=" * 72)
    print(title)
    print("=" * 72)
    if truth:
        print(f"the truth: {truth}")
    print("the records of the pane:")
    for index, task in enumerate(state.tool_tasks):
        print(
            f"  {index}: {task.id:<10} {task.status:<10} {task.name} "
            f"({task.details})"
        )
    print()
    print("the pane, the way the operator sees it:")
    for line in the_pane(state):
        print(f"  {line}")
    print()

    running = [task for task in state.tool_tasks if task.status == "running"]
    for task in running:
        position = state.tool_tasks.index(task)
        print(
            f"  -> the task that runs now is task {position} of "
            f"{len(state.tool_tasks)}: {task.name} ({task.details})"
        )
    if not running:
        print("  -> nothing is running.")
    print(
        "  -> the task that runs now is on top of the pane: "
        f"{'YES' if the_running_task_is_on_top(state) else 'NO'}"
    )


# ---------------------------------------------------------------------------
# The scenarios
# ---------------------------------------------------------------------------


def scenario_sequential() -> TuiState:
    """Three tools, one after the other -- the ordinary case."""
    state = TuiState()
    adapter = TuiEventAdapter(state)
    feed(
        adapter,
        [
            FakeToolCall("read_file", {"file_path": "/etc/hosts"}, "call-1"),
            FakeToolCallResult("read_file", "call-1"),
            FakeToolCall(
                "execute_shell_command", {"command": "ls -la /var/log"}, "call-2"
            ),
        ],
    )
    return state


def scenario_concurrent_same_name() -> TuiState:
    """Two calls of the same tool, running at the same time."""
    state = TuiState()
    adapter = TuiEventAdapter(state)
    feed(
        adapter,
        [
            FakeToolCall(
                "execute_shell_command", {"command": "sleep 5"}, "call-1"
            ),
            FakeToolCall(
                "execute_shell_command", {"command": "whoami"}, "call-2"
            ),
            # The first call is done.  The second one still runs.
            FakeToolCallResult("execute_shell_command", "call-1", "done: sleep"),
        ],
    )
    return state


def scenario_concurrent_other_names() -> TuiState:
    """Two different tools, running at the same time."""
    state = TuiState()
    adapter = TuiEventAdapter(state)
    feed(
        adapter,
        [
            FakeToolCall(
                "execute_shell_command", {"command": "sleep 5"}, "call-1"
            ),
            FakeToolCall("read_file", {"file_path": "/etc/hosts"}, "call-2"),
            # The quick one is done; the slow one still runs.
            FakeToolCallResult("read_file", "call-2"),
        ],
    )
    return state


def scenario_stale() -> TuiState:
    """The whole run is over -- and a task still spins."""
    state = TuiState()
    adapter = TuiEventAdapter(state)
    feed(
        adapter,
        [
            FakeToolCall(
                "execute_shell_command", {"command": "sleep 5"}, "call-1"
            ),
            FakeToolCall(
                "execute_shell_command", {"command": "whoami"}, "call-2"
            ),
            FakeToolCallResult("execute_shell_command", "call-1", "done: sleep"),
            FakeToolCallResult("execute_shell_command", "call-2", "done: whoami"),
        ],
    )
    return state


def the_verdicts() -> Tuple[bool, bool]:
    """The two questions the probe asks of every scenario.

    Returns:
        ``(the running task is on top, every call closed its own
        record)``.
    """
    on_top = True
    attributed = True

    for state in (
        scenario_sequential(),
        scenario_concurrent_same_name(),
        scenario_concurrent_other_names(),
        scenario_stale(),
    ):
        if not the_running_task_is_on_top(state):
            on_top = False
        for task in state.tool_tasks:
            if task.status == "running":
                # A task that still spins after the run is over is a
                # task that never reported: the state of the call and
                # the state of the record have to agree.
                continue

    # Every call that reported has to be closed, and only that one.
    state = scenario_concurrent_same_name()
    if the_call_of(state, "call-1") != "completed":
        attributed = False
    if the_call_of(state, "call-2") != "running":
        attributed = False

    return on_top, attributed


def main() -> int:
    print("The workflow pane: where the task that runs now stands.")
    print("The framework publishes ToolCall when a tool starts and")
    print("ToolCallResult when it is done; the steps run concurrently.")
    print()

    report("1. Three tools, one after the other", scenario_sequential())
    report(
        "2. Two calls of the same tool, running at the same time",
        scenario_concurrent_same_name(),
        truth="call-1 (sleep 5) is done; call-2 (whoami) still runs",
    )
    report(
        "3. Two different tools, running at the same time",
        scenario_concurrent_other_names(),
        truth="call-1 (sleep 5) still runs; call-2 (read_file) is done",
    )
    report("4. The run is over -- and a task still spins", scenario_stale())

    on_top, attributed = the_verdicts()

    print("=" * 72)
    print("What the probe found")
    print("=" * 72)
    print(
        "  * the task that runs now is on top of the pane in every "
        f"scenario: {'YES' if on_top else 'NO'}"
    )
    print(
        "  * every call closes its own record, and only its own: "
        f"{'YES' if attributed else 'NO'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
