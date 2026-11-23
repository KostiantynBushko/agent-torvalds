# Investigation Report: Where does the command that runs now stand in the workflow pane?

The operator wrote on 2026-11-22:

> I also noticed that sometime the currently executed command in not on top
> of the workflow window but instead it could apear somewhere in the midle
> of the commands so that completed command (tool) in on top and currently
> running is in the midle of the list or in the bottom

The *Workflow & Tool Progress* pane of the TUI lists the tool calls of the
run.  The operator expects the command that runs **now** to be on top of
that pane.  It was not: it stood in the middle of the list, with the
finished commands above it — and, when two calls of the same tool ran at
the same time, the pane reported **the wrong command as running**.

> **A note on the order of the list.**  The list of the tasks that are
> done is a **stack** today, and the task that ran before the current one
> is right below it.  The operator decided that later on the same day —
> *the Recent Tool Task must be shown in the upside-down, so data
> structure that shows recent tool task must be stack and the current
> executed command must be on top of the window the previous task must be
> below currently runned task and so on*.  §16.1 of `docs/tui/hotkeys.md`
> carries the decision, and `investigate/tui-autoscroll/` carries the
> measurement of it.  The code quoted in §3 below is the code of the
> moment: it is the **root cause** of the defect this report is about.

**Probe:** [`probe_running_task_order.py`](probe_running_task_order.py) —
read-only.  It feeds the real `TuiState` the events the workflow really
publishes and prints the pane the operator sees.  It writes nothing.

## 1. The question

Two questions, in one report:

1. **Where does the task that runs now stand in the pane, and why?**
2. **Which command does the pane say is running, when two calls of the
   same tool run at the same time?**

The second question came out of the first: the pane does not only put the
running task in the wrong place — it can put the **wrong task** there.

## 2. The measurement

The probe reproduces four runs and prints the records of the pane and the
pane itself.  Before the fix:

```
1. Three tools, one after the other
the records of the pane:
  0: tool-1     completed  read_file (/etc/hosts)
  1: tool-2     running    execute_shell_command (ls -la /var/log)

the pane, the way the operator sees it:
   [bold green]✔[/bold green] [white]read_file[/white] [dim](0ms)[/dim]
     [dim]└ /etc/hosts[/dim]
   [bold yellow]⠋[/bold yellow] [yellow]execute_shell_command[/yellow] [dim](0.0s)[/dim]
     [dim]└ ls -la /var/log[/dim]

  -> the task that runs now is on top of the pane: NO
```

The running command is the **last** line of the list — the finished
command stands above it.  That is the ordinary case: one tool after the
other.

```
2. Two calls of the same tool, running at the same time
the truth: call-1 (sleep 5) is done; call-2 (whoami) still runs
the records of the pane:
  0: tool-1     running    execute_shell_command (sleep 5)
  1: tool-2     completed  execute_shell_command (whoami)

the pane, the way the operator sees it:
   [bold yellow]⠋[/bold yellow] [yellow]execute_shell_command[/yellow] [dim](0.0s)[/dim]
     [dim]└ sleep 5[/dim]
   [bold green]✔[/bold green] [white]execute_shell_command[/white] [dim](0ms)[/dim]
     [dim]└ whoami[/dim]
```

The pane **spins on `sleep 5` — a command that is done** — and puts the
**tick on `whoami` — a command that still runs**.  The result of the
first call closed the record of the second one, and the first record was
left spinning.

The summary the probe prints, before the fix:

```
  * the task that runs now is on top of the pane in every scenario: NO
  * every call closes its own record, and only its own: NO
```

And after the fix, the same probe, the same four runs:

```
  * the task that runs now is on top of the pane in every scenario: YES
  * every call closes its own record, and only its own: YES
```

## 3. The root cause

Two causes, one in each of the two files of the pane.

**The order of the list.**  `components/tui/progress_view.py` drew the
tasks in the order they **started** — `state.tool_tasks[-TASKS_SHOWN:]`,
the oldest first.  The decision of 2026-11-21 was that the list is a
log, and the log is right for the tasks that are **done**.  But the task
that runs now is not a part of the history: it belongs at the top, where
the operator looks first.

**The record that is closed.**  `components/tui/state_bridge.py` —
`update_tool_end()` looked for the record of the call by **name**:

```python
for record in reversed(self.tool_tasks):
    if record.name == tool_name and record.status == "running":
```

The framework carries a `tool_id` on every `ToolCall` and every
`ToolCallResult`
(`llama_index/core/agent/workflow/base_agent.py`, the `call_tool` step),
and the workflow runs the calls of a turn **concurrently**.  Two calls
of the same tool carry the same name — so the result of one call closed
the record of the other one.  The stats handler already knows this and
uses the id:

```python
# Pass the tool_id: the workflow runs tool calls concurrently,
# so the id keeps concurrent calls to the same tool apart.
self.stats_handler.begin_tool_call(tool_name, tool_id=event.tool_id)
```

The TUI did not.

## 4. The fix

**The result closes its own record.**  `ToolExecutionRecord` carries the
`tool_id` of the call; `update_tool_end()` finds the record by that id,
and the name is only the fallback for the events that carry no id.  The
adapter hands the id of the event over.

**The task that runs now is pinned on top of the pane.**  The pane has
three parts now: the **head** (the bar of the iteration and the name of
the list), the **running** task, and the **log** of the tasks that are
done.  The running task is drawn *above the window of the pane*, so it
is on top of the window — and it stays there while the operator scrolls
the log.

**The log is a log.**  The tasks that are done are ordered by the moment
they were done: the oldest completion first, the newest at the bottom,
the window stuck to the bottom.  "Down" still walks *forward* in time —
the decision of 2026-11-21 (§16.1 of `docs/tui/hotkeys.md`) is not
reversed.

**Nothing spins for ever.**  When the run is over, the tasks that still
run are closed: a task that spins on top of the pane for ever is a lie
the operator reads.

## 5. Verification

* `tests/test_tui_task_order.py` — 11 tests: the running task is the
  first task of the pane, it stays on top when the log is longer than
  the window, it is on top when the calls run in parallel, the result of
  a call closes its own record, the name is the fallback, the log is the
  order of what happened, and the run that is over closes the tasks that
  still run.
  **Nine of the eleven fail without the fix** — the two that pass are
  the ones that assert what was already right (the fallback by name, and
  the order of a log of tasks that ran one after the other).
* The gate: `scripts/ci_test_gate.py` — **40 known failures, 0 new, 0
  fixed**.
* The probe, before and after: the numbers are in §2.

## 6. What is *not* in this change, and why

* **The classic console is not touched.**  The defect is in the TUI: the
  console has no pane of tasks.
* **The order of the tasks that are done is not reversed.**  The log
  stays a log — the operator decided that on 2026-11-21, and the
  complaint is about the task that runs, not about the history.
* **The pane does not grow a section of its own.**  The running task is
  the first line of the list of the tasks; the log follows it.  A new
  header would cost a line of a pane that is 15 lines tall.
* **The number of the tasks the pane shows is not changed** — six of
  them, in the log.
* **The tasks that run at the same time are all shown**, in the order
  they started.  The pane does not pretend that one of them is *the*
  running task.

## 7. The recommendation to the operator

The change is in the working copy, on the branch `feature/tui-hotkeys`,
next to the focus mark of the document pane.  It is **not committed**:
the diff is there for the review.

The operator should look at one thing: the running task is **pinned** —
it is drawn above the window of the pane and does not scroll away.  The
cost of that is one line of the pane: the log shows one task less while
a command runs.  The other way — the running task inside the scrollable
list — is what the operator asked to get rid of, and it cannot be kept:
the running task would scroll out of the window as soon as the log is
longer than the pane.
