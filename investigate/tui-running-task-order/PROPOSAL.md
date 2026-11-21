# Proposal: the task that runs now stands on top of the workflow pane

**The operator said on 2026-11-22:**

> I also noticed that sometime the currently executed command in not on top
> of the workflow window but instead it could apear somewhere in the midle
> of the commands so that completed command (tool) in on top and currently
> running is in the midle of the list or in the bottom

## What is asked

The command that runs **now** stands **on top** of the *Workflow & Tool
Progress* pane — always, and where the operator sees it first.

## What is measured

`probe_running_task_order.py` (read-only) reproduces the events the
framework publishes and prints the pane the operator sees:

1. **The task that runs now is never on top.**  The list is in the order
   the tasks *started*; the finished ones stand above the one that is
   still going.  In the ordinary case — one tool after the other — the
   running command is the **last** line of the list.
2. **Two calls of the same tool at the same time are told apart by their
   name only.**  The result of the first call closes the record of the
   second one, and the first record spins **forever**.  The pane then
   shows the command that runs as *finished*, and the command that is
   done as *running*.

## The cause

* `components/tui/state_bridge.py` — `update_tool_end()` looks for the
  record by **name**.  The framework carries a `tool_id` on every
  `ToolCall` and every `ToolCallResult` (the stats handler already uses
  it: *"the workflow runs tool calls concurrently, so the id keeps
  concurrent calls to the same tool apart"*).  The TUI ignores it.
* `components/tui/progress_view.py` — the tasks are drawn in the order
  they started, and the running one is one of them.

## The proposal

1. **The result closes its own record.**  The `tool_id` of the event
   finds the record; the name is only the fallback, for the events that
   carry no id.

2. **The task that runs now is pinned on top of the pane.**  It is drawn
   above the scrollable window, so it is on top of the window and stays
   there while the operator scrolls the log.

3. **The log of the tasks that are done stays a log** — the oldest
   completion first, the newest at the bottom, the window stuck to the
   bottom.  The decision of 2026-11-21 (§16.1 of `docs/tui/hotkeys.md`)
   is not reversed: "down" still walks *forward* in time.

## What is *not* in this change

* The order of the **finished** tasks is not changed: they are a log.
* The **classic console** is not touched: the defect is in the TUI.
* The pane does not grow a section of its own for the running task: the
  running task is the **first line of the list of the tasks**, and the
  list below it is the log.
