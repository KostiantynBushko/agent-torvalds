# The Recent Tool Tasks list grows down, and the task that runs now is pinned on top

**The operator said on 2026-11-22:**

> please make sure the tool task grow down so that current executed is
> always on top of the window

Two things are asked for at once, and they are about **two different
parts** of the pane:

* the list of the tasks **grows down** — a task that is done is
  appended at the bottom of the list, the tasks that were done before
  it do not move, and "down" walks forward in time;
* the task that **runs now is always on top of the window** — the
  command that runs is the first thing on the screen, and it stays
  there while the operator scrolls the history.

The *Workflow & Tool Progress* pane answers both with two parts: the
task that runs now is **pinned** above the window of the pane, and the
window carries the log of the tasks that are done — oldest completion
first, newest at the bottom — and it is stuck to the tail of that log.

The measurement is in [`probe_autoscroll.py`](probe_autoscroll.py) —
it builds the **real** state, draws the pane in the **real** layout at
the width and the height of the terminal of the operator, and reports
what is on the screen.  It writes nothing.

```bash
python investigate/tui-autoscroll/probe_autoscroll.py
```

---

## 1. What the pane was

The pane was changed earlier the same day, on the reading of the
request *Recent Tool Tasks must scroll automatically into current
position during command execution*: the list of the tasks was written
**newest first**, the task that runs now was the **head** of it, and
the window of the pane followed that head.

The measurement found two things wrong with it.

**The list grew up.**  A task that is done was inserted at the **top**
of the list of the tasks that are done, and the tasks that were done
before it were pushed down.  The probe says:

```
  FAIL  the list of the tasks grows down
        the lines of the done tasks above the first one: 4 before, 6 after
```

Four lines were above the first task before the new one arrived, and
six after it: the list grew **upward**, and "down" walked *into the
past* — the opposite of every scrollable thing the operator knows.

**The history could take the running task away.**  The task that runs
now was carried by the window of the pane, so the window that the
operator scrolls took it off the screen:

```
  FAIL  the task that runs now stays on top while the operator scrolls
        the task that runs now stays on top of the pane: False
          the offset of the window: 6 of 26 lines
          the command that runs: line -1
```

The line is `-1`: the command that runs was **not on the screen** any
more.  The operator asked for it to be **always** on top.

## 2. What the change is

**The task that runs now is pinned.**  It is drawn **above** the window
of the pane, outside it, and the history that the operator scrolls
cannot take it away.

**The list of the tasks that are done is a log, and it grows down.**
The oldest completion first, the newest at the bottom, and the window
is stuck to the tail of the log: the newest completion is on the
screen, and the window scrolls there by itself while a command runs.

The probe, against the same pane, says:

```
  PASS  the task that runs now is on top of the pane
  PASS  the task that runs now stays on top while the operator scrolls
  PASS  the list of the tasks grows down
        the lines of the done tasks above the first one: 0 before, 0 after
  PASS  the window is at the current position
  PASS  the window keeps the place of the operator
```

Three things follow, and the probe measures all three:

* the command that runs now is on the screen, and it stays there —
  the history the operator scrolls cannot move it;
* the list grows **down**: a task that is done is appended at the
  bottom, and the tasks that were done before it do not move;
* "down" walks forward in time again, and the newest completion is on
  the screen, because the window is stuck to the tail of the log.

## 3. What it costs

**The tail of a command that is taller than the pane is out of reach.**
The pinned task is drawn outside the window of the pane, and the keys
of the pane scroll the log and not the pinned task.  The whole of the
command is in the chat history of the session.

**The list is a log, and the log is short.**  The pane carries the six
newest tasks that are done; the older ones are dropped, and the log
grows at the bottom of the window.

## 4. The evidence

* `tests/test_tui_current_position.py` — the window is at the current
  position, the list grows down, the running task is pinned, and the
  operator who scrolled away keeps his place.
* `tests/test_tui_task_order.py` — the order of the tasks, the
  pinning of the running task, and the growth of the list.
* `investigate/tui-autoscroll/probe_autoscroll.py` — the measurement,
  and the screen of the operator.
* The gate of the repository stays green: the known failures stay
  known, and no new one comes.
