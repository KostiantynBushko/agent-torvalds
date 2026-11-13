# Implementation report — the TUI must ask the terminal for its size, and keep the log off the screen

**Date**: 2026-11-13
**Branch**: `fix/tui-terminal-size`
**Status**: implemented, verified — **merged**.  The operator approved the
commit and merged it as **PR #95**, which squash-merged the fix into
`master` as `1f8c52e` on 2026-11-13.
**Companion to**: `investigation_tui_selection_and_flicker.md`, `PROPOSAL_tui_terminal_size.md`

---

## 1. What was implemented

The two defects of the investigation are closed.

| # | Defect | How it is closed |
|---|---|---|
| **D1** | Rich believed the `LINES` and the `COLUMNS` the shell exported, and laid the layout out for a terminal that is not there | `components/tui/terminal_size.py::build_console()` — the console is built with an environment that carries neither, so `Console.size` asks the terminal |
| **D2** | the log of the agent landed on the alternate screen and scrolled it | `components/tui/log_routing.py::log_to_file()` — the terminal handlers of the root logger are gone for the time of the TUI, and a file handler takes their place |

The operator decided on 2026-11-13: *"the log must go into file, not
painted over"*.  The second defect is closed that way: the log goes into
the file, and nothing is painted over.

## 2. The new modules

### 2.1 `components/tui/terminal_size.py`

| Function | Purpose |
|---|---|
| `console_environ(environ=None)` | the environment without `COLUMNS` and without `LINES` |
| `build_console(environ=None, **kwargs)` | a `Console` that asks the terminal for its size |

Nothing is forced: the size is asked of the terminal on every access,
so the layout follows the terminal when it is resized.

### 2.2 `components/tui/log_routing.py`

| Function | Purpose |
|---|---|
| `terminal_handlers(root=None)` | the handlers that write to the terminal — every stream handler that is not a file handler |
| `resolve_tui_log_config(config=None, environ=None)` | the log file the TUI writes into: the one the operator configured, or the default of the project |
| `log_to_file(config=None, level=None, root=None)` | the context manager that keeps the log off the terminal |

The file handler is built **before** the terminal handlers go away: a
warning about a log file that cannot be opened has to reach the
operator, and the terminal is the only place it can.

## 3. The wiring

| Path | Change |
|---|---|
| `components/tui/terminal_size.py` | **new** — the console that asks the terminal |
| `components/tui/log_routing.py` | **new** — the log goes into the file while the TUI is up |
| `components/tui/tui_app.py` | the console is built with `build_console()`; the Live display runs inside `log_to_file(self.log_config)` |
| `components/tui/markdown_view.py` | the console of the view is built with `build_console()`; the capture console has a height of its own, so the `LINES` of the environment cannot reach it either |
| `components/tui/__init__.py` | the new modules are exported |
| `agent-torvalds-mw.py` | `console = build_console()`; the log configuration of the operator is handed to the TUI |
| `tests/test_tui_terminal_size.py` | **new** — 13 checks |
| `tests/test_tui_log_routing.py` | **new** — 12 checks |

## 4. The proof

The probe runs the TUI four times in a pty of its own — 120×40 — and
replays the byte stream through a terminal emulator.

| | before | after |
|---|---|---|
| the size Rich believes | 229×33 | **120×40** |
| the frame overflows the terminal | yes | **no** |
| screen scrolls in 2.5 s | **988** | **0** |
| the pane separator on the screen | column **27** | **column 77** |
| rows with the panes misplaced | **14** | **0** |
| the log of the agent on the screen | 6 lines, 12 scrolls | **0 lines, 0 scrolls** |
| the log of the agent in the file | — | **6 lines** |

```
.venv/bin/python investigate/tui-selection-and-flicker/probe_selection_and_flicker.py
```

| Check | Result |
|---|---|
| `tests/test_tui_terminal_size.py` | 13 passed |
| `tests/test_tui_log_routing.py` | 12 passed |
| the suite | 39 failed, 3076 passed, 10 skipped, 1 error — the same 39 failures and the same 1 error the repository carried before the change, file for file |

## 5. What was left alone

- **The whole screen is repainted on every frame.**  Rich's Live
  display in the alternate screen writes the entire screen 15 times a
  second.  Rich offers no diffing for the alternate screen, and a diff
  of the layout would be a project of its own.
- **The width of the markdown is estimated** (`0.62 × width` instead of
  the measured width of the pane).  It is off by two columns at most,
  and it only makes the `PgUp`/`PgDn` counter drift.
- **The classic REPL of `agent-torvalds.py`.**  It has the same
  console, and the same wrong width, but it prints into the scrollback
  instead of drawing a screen: the lines wrap early, and nothing is
  misplaced.
- **A `print()` is not a log.**  A tool that writes to `stdout` still
  reaches the screen — the routing covers the *log*, which is what the
  agent writes while it works.  The git toolkit prints to `stdout` in
  debug mode only (`DEBUG` in the environment), and the agent does not
  print in normal operation.
