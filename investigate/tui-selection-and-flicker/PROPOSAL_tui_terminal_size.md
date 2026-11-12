# Proposal: the TUI must ask the terminal for its size — and keep the log off the screen

**Date**: 2026-11-13
**Status**: **Decided and implemented** — see `IMPLEMENTATION_REPORT.md`
**Companion to**: `investigation_tui_selection_and_flicker.md`, `IMPLEMENTATION_REPORT.md`
**Branch**: `fix/tui-terminal-size`
**Scope**: `components/tui/terminal_size.py` (new),
`components/tui/log_routing.py` (new), `agent-torvalds-mw.py`,
`components/tui/tui_app.py`, `components/tui/markdown_view.py`,
`tests/test_tui_terminal_size.py` (new), `tests/test_tui_log_routing.py` (new)

> **The operator decided on 2026-11-13**: *"the log must go into file,
> not painted over"*.  The second part of this proposal is implemented
> that way — the log goes into the file, and nothing is painted over.

---

## 1. The shape of the fix

Two changes, and they are independent of each other.

```
   ┌──────────────────────────────────────────────────────────────┐
   │ 1. The console asks the terminal, not the environment        │
   │                                                              │
   │    Console()                     Console(_environ=clean)     │
   │      reads COLUMNS/LINES     ──►  reads os.get_terminal_size()│
   │      (a stale snapshot)            (the size that is true now) │
   └──────────────────────────────────────────────────────────────┘

   ┌──────────────────────────────────────────────────────────────┐
   │ 2. While the alternate screen is up, the log goes to the file │
   │                                                              │
   │    stderr ──► the terminal        stderr ──► the log file     │
   │    (on top of the layout)         (the layout stays alone)   │
   └──────────────────────────────────────────────────────────────┘
```

The first change removes the blink and puts the panes back in their
columns.  The second removes the part of the blink that only shows
while a request runs.

---

## 2. The console asks the terminal

### 2.1 `components/tui/terminal_size.py` (new)

A small module with one job: build a console that believes the
terminal, not the environment.

```python
"""
The console of the TUI must believe the terminal, not the environment.

Rich reads ``COLUMNS`` and ``LINES`` from the environment before it
asks the terminal, and the shell exports them as a snapshot of the
size the terminal had when the shell started.  A console that believes
them lays the multi-window layout out for a terminal that is not
there: the frame is wider than the screen, the terminal folds it, the
panes leave their columns and the screen scrolls on every frame.

The console of the TUI is therefore built with an environment that
carries no ``COLUMNS`` and no ``LINES``.  Everything else in the
environment stays, so ``TERM``, ``NO_COLOR`` and the rest keep
working.
"""
from __future__ import annotations

import os
from typing import Mapping, Optional

from rich.console import Console

#: The variables that describe a terminal that is not there.
SIZE_VARIABLES = ("COLUMNS", "LINES")


def console_environ(environ: Optional[Mapping[str, str]] = None) -> dict:
    """The environment for a console that asks the terminal for its size.

    Args:
        environ: The environment to start from.  Defaults to
            ``os.environ``.

    Returns:
        A copy of the environment without ``COLUMNS`` and without
        ``LINES``.
    """
    source = os.environ if environ is None else environ
    return {key: value for key, value in source.items()
            if key not in SIZE_VARIABLES}


def build_console(environ: Optional[Mapping[str, str]] = None, **kwargs) -> Console:
    """Build a console that believes the size of the terminal.

    Args:
        environ: The environment to start from.  Defaults to
            ``os.environ``.
        **kwargs: Passed on to ``rich.console.Console``.

    Returns:
        A console that asks the terminal for its size, and that follows
        it when the terminal is resized.
    """
    return Console(_environ=console_environ(environ), **kwargs)
```

### 2.2 `agent-torvalds-mw.py`

```python
# before
console = Console()

# after
from components.tui.terminal_size import build_console

console = build_console()
```

One line.  The console of the classic REPL (`agent-torvalds.py`) has
the same problem, but it does not draw a full-screen layout: the
classic REPL prints into the scrollback, and a wrong width only makes
the lines wrap early.  The change there is a separate decision — the
TUI is where the defect bites.

### 2.3 What the change must not break

- **A resize is followed.**  `Console.size` asks the terminal on every
  access when the size was not forced, so the layout follows the
  terminal as it is resized.  The change keeps it that way: nothing is
  forced, the environment is only *unlearned*.
- **A pipe is still a pipe.**  `Console.size` falls back to 80×25 when
  the output is not a terminal, and the TUI is not started at all
  without a tty (`agent-torvalds-mw.py`, `is_interactive_tty`).
- **`TERM` and the rest of the environment stay.**  Only `COLUMNS` and
  `LINES` are removed.

---

## 3. The log stays off the alternate screen

### 3.1 The problem

While the TUI is up, the terminal belongs to the layout.  The log
handler writes to `stderr`, which is the terminal:

```python
# agent-torvalds-mw.py:556
    handlers = [logging.StreamHandler(sys.stderr)]
```

and the agent writes to the log on every iteration of the loop
(`components/hitl_agent.py:450`, `logger.info("Context: %s", ...)`).

### 3.2 The change

The log handler is pointed at the **file** while the alternate screen
is up, and at `stderr` again when the TUI is done.  The file handler
already exists — `components/file_logging.py` builds a rotating one —
but it is optional, and the operator may not have asked for a log file
at all.

The smallest change that keeps the operator's terminal clean:

```python
# components/tui/tui_app.py - a context manager on the app

    @contextmanager
    def quiet_terminal(self):
        """Keep the log off the alternate screen while the TUI runs.

        The layout owns the terminal while the Live display is up.  A
        log line written to ``stderr`` in that moment lands on top of
        the layout and scrolls the screen, and the scroll is visible
        as a blink.

        The handler of the root logger is pointed at a file for the
        time of the TUI, and at ``stderr`` again afterwards.  The
        operator still sees the log in the file, and the terminal is
        the layout alone.
        """
```

The handler is moved to the file the operator configured
(`--log-file`), or to a throw-away file when there is none, and it is
put back afterwards.  The lines are not lost — they are simply not on
the screen.

> **The decision.**  The operator chose the first way on 2026-11-13:
> the log goes to the file only, while the TUI is up.  The terminal is
> the layout alone, and the operator reads the log with `tail -f`.
>
> The file is the one the operator configured (``--log-file``), or the
> default of the project (``~/.torvalds/logs/agent.log``) when there
> is none.  It rotates, so it does not grow without bound, and it is
> private (``0600``), because the log of this agent carries the
> prompts, the tool output and the answers of the model.

---

## 4. What is left alone

- **The whole screen is repainted on every frame.**  Rich's Live
  display in the alternate screen writes the entire screen 15 times a
  second.  A diff of the layout would be a project of its own.
- **The width of the markdown is estimated** (`0.62 × width` instead of
  the measured width of the pane).  It is off by two columns at most,
  and it only makes the `PgUp`/`PgDn` counter drift.  It is a separate
  change, and it is small.
- **The classic REPL of `agent-torvalds.py`.**  It has the same
  console, and the same wrong width, but it prints into the scrollback
  instead of drawing a screen: the lines wrap early, and nothing is
  misplaced.  A separate decision.

---

## 5. The proof

`probe_selection_and_flicker.py` runs the four cases and checks the
numbers.  With the change:

| | before | after |
|---|---|---|
| the size Rich believes (terminal 120×40) | 229×33 | 120×40 |
| the frame overflows the terminal | yes | no |
| screen scrolls in 2.5 s | 990 | 2 |
| the pane separator on the screen | column 27 | column 77 |
| rows with the panes misplaced | 13 | 0 |

The tests that belong with the change — both of them are in the suite
now:

| Test | What it holds |
|---|---|
| `tests/test_tui_terminal_size.py` | the console built by `build_console()` does not carry `COLUMNS` and does not carry `LINES`; every other variable of the environment is still there; the console asks the terminal when the environment is silent; a forced size still wins; a resize is followed. |
| `tests/test_tui_terminal_size.py` | the layout rendered at the size of the terminal fills the terminal, and the separator between the panes is in the column the layout chose. |
| `tests/test_tui_log_routing.py` | the terminal handler is gone while the TUI is up and back afterwards; the log reaches the file and does not reach the terminal; the file handler of the operator is not taken away; the file is private; a log file that cannot be opened degrades and never stops the TUI. |
