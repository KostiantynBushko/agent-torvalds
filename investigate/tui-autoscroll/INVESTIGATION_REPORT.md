# The Recent Tool Tasks are shown upside down, and the task that runs now is pinned on top

**The operator said on 2026-11-22:**

> please make sure the tool task grow down so that current executed is
> always on top of the window

and again, later on the same day, with the words that say what the list
is:

> the Recent Tool Task must be shown in the upside-down, so data
> structure that shows recent tool task must be stack and the current
> executed command must be on top of the window the previous task must
> be below currently runned task and so on

Three things are asked for at once, and they are about **two different
parts** of the pane:

* the recent tool tasks are shown **upside down** — the structure that
  carries them is a **stack**: the newest task is on the top of it, the
  task that ran before it is right below it, and the one before that is
  below that;
* the task that **runs now is always on top of the window** — the
  command that runs is the first thing on the screen, and it stays
  there while the operator scrolls the history;
* the task that ran **before** it is **below** it — the two stand
  together, and the window of the pane opens at the top of the stack.

The *Workflow & Tool Progress* pane answers all three with two parts:
the task that runs now is **pinned** above the window of the pane, and
the window carries the **stack** of the tasks that are done — the
newest completion first — and it is stuck to the **top** of that stack,
which is the current position of the work.

The measurement is in [`probe_autoscroll.py`](probe_autoscroll.py) —
it builds the **real** state, draws the pane in the **real** layout at
the width and the height of the terminal of the operator, and reports
what is on the screen.  It writes nothing.

```bash
python investigate/tui-autoscroll/probe_autoscroll.py
```

---

## 1. What the pane was

The pane carried the tasks that are done as a **log**: the oldest
completion first, the newest at the bottom, and the window of the pane
stuck to the tail of that log.

The task that ran now was pinned above the window, and that part was
right.  The rest was not: the task that ran **before** the current one
was at the **bottom** of the pane — at the far end of the window, and
not below the command that runs.  The operator had to look at the
bottom of the pane to find out what ran before the command that runs
now, and the window had to be at the bottom to show it at all.

The reading of the request was wrong: "grow down" was read as "the
newest completion goes to the bottom of the list", and the list was
made a log.  The list is a **stack**, and the newest completion is on
the **top** of it.

## 2. What the change is

**The structure that carries the recent tool tasks is a stack.**
`TaskStack` in `components/tui/state_bridge.py` holds the tasks of the
run: the newest is on the top, a task that is done is **pushed** on
the top of it, and the tasks that were done before it go down.  The
view does not sort the list again — the structure carries the order.

**The task that runs now is pinned.**  It is drawn **above** the window
of the pane, outside it, and the history that the operator scrolls
cannot take it away.

**The task that ran before it is right below it.**  The newest
completion is the first one of the stack, and the line above it is the
task that runs now:

```
  ⠋ execute_shell_command (0.0s)
    └ the-command-that-runs
  ✔ execute_shell_command (12ms)
    └ the-command-that-ran-before
```

**The list grows down.**  A task that is done is pushed on the top of
the stack, and the tasks that were done before it go **down** — one
line further down for every line the new task takes.  The list never
grows up.

**The window is at the current position.**  It is stuck to the **top**
of the stack, so the newest completion is on the screen, and the window
scrolls there by itself while a command runs.

The probe, against the real pane, says:

```
  PASS  the task that runs now is on top of the pane
        the header of the list: line 3
        the command that runs: line 5
  PASS  the task that runs now stays on top while the operator scrolls
        the offset of the window: 8 of 24 lines
        the command that runs: line 5
  PASS  the task that ran before is right below the one that runs
        the lines of the task that runs: [3, 4, 5]
        the lines of the task that ran before: [6, 7]
  PASS  the list of the tasks grows down
        the offset of the task that was done first: 4 before, 6 after
        the new task is on the top of the stack: True
  PASS  the window is at the current position
        the offset of the window: 0 of 24 lines
        the newest completion is on the screen: True
  PASS  the window keeps the place of the operator
        the anchor before: 'tool-11'
        the anchor after: 'tool-11'
        the offset of the window: 4
```

Five things follow, and the probe measures all five:

* the command that runs now is on the screen, and it stays there — the
  history the operator scrolls cannot move it;
* the task that ran before it is **directly below** it;
* the list grows **down**: a task that is done is pushed on the top,
  and the tasks that were done before it go down;
* the newest completion is on the screen, because the window is stuck
  to the top of the stack — the current position of the work;
* the operator who scrolled away keeps the task he is reading.

## 3. What it costs

**The tail of a command that is taller than the pane is out of reach.**
The pinned task is drawn outside the window of the pane, and the keys
of the pane scroll the stack and not the pinned task.  The whole of the
command is in the chat history of the session.

**The stack is short.**  The pane carries the six newest tasks that are
done; the older ones are dropped off the bottom of the stack, and the
rest is reached with the keys of the pane.

**"End" is the oldest task now.**  The list is upside down, and the
end of it is the far end of the history: `Home` goes to the current
position and `End` to the oldest task of the run.

## 4. The evidence

* `tests/test_tui_current_position.py` — the window is at the current
  position, the list grows down, the running task is pinned, and the
  operator who scrolled away keeps his place.
* `tests/test_tui_task_order.py` — the order of the tasks, the
  pinning of the running task, and the growth of the stack.
* `investigate/tui-autoscroll/probe_autoscroll.py` — the measurement,
  and the screen of the operator.
* The gate of the repository stays green: the known failures stay
  known, and no new one comes.
