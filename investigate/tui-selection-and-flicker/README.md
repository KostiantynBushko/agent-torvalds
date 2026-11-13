# The selection picked up the wrong pane, and the screen blinked

**Investigation of the multi-window console (`agent-torvalds-mw.py`)** —
the operator reported that a selection in the document pane also picks
up the content of the "Workflow & Tool Progress" pane, and that the
whole screen blinks while a request is processed.

**Date**: 2026-11-13
**Status**: Investigated **and implemented** — see `IMPLEMENTATION_REPORT.md`.
The change is on the branch `fix/tui-terminal-size`, **not committed**
(Rule 2: awaiting the operator's approval).

---

## The finding in one paragraph

Rich's `Console.size` prefers the `COLUMNS` and `LINES` environment
variables over the real terminal size, and the shell exports them as a
stale snapshot.  The TUI therefore laid itself out for a terminal that
is not there: the frame was wider than the screen, the terminal folded
it, the panes left their columns — and the screen scrolled 26 rows on
every frame, 15 times a second.  That is the blink, and it is also why
the selection crossed the panes.  A second, independent defect put the
log of the agent on the alternate screen, which is the part of the
blink that shows only while a request runs.

The numbers, measured with the probe:

| | today | with the proposed console |
|---|---|---|
| the size Rich believes (terminal 120×40) | 229×33 | 120×40 |
| the frame overflows the terminal | yes | no |
| screen scrolls in 2.5 s | 990 | 2 |
| the pane separator on the screen | column 27 | column 77 |
| rows with the panes misplaced | 13 | 0 |

---

## The files

| File | What it is |
|---|---|
| `investigation_tui_selection_and_flicker.md` | **The investigation.**  What the operator reported, what the cause is, how it was measured, and what was left alone. |
| `PROPOSAL_tui_terminal_size.md` | **The proposal.**  The change, in two independent parts: the console asks the terminal, and the log stays off the alternate screen. |
| `IMPLEMENTATION_REPORT.md` | **What was implemented**, where it went, and the proof. |
| `probe_selection_and_flicker.py` | **The probe.**  Runs the TUI four times in a pty of its own and checks the numbers.  Exit 0 when the defect reproduces *and* the fix holds. |
| `repro/capture_pty.py` | Runs the TUI on a pty of a fixed size and records the bytes it writes. |
| `repro/tui_child.py` | The TUI itself with a stub agent, so a request can be watched without a model. |
| `repro/term_emulator.py` | A small ANSI terminal emulator: it replays the bytes and shows the screen the operator would have seen. |

---

## How to run it

The probe — it never touches the terminal of the operator:

```bash
.venv/bin/python investigate/tui-selection-and-flicker/probe_selection_and_flicker.py
```

The tests of the change:

```bash
.venv/bin/python -m pytest tests/test_tui_terminal_size.py tests/test_tui_log_routing.py -v
```

A capture that can be looked at by hand:

```bash
cd investigate/tui-selection-and-flicker/repro
../../../.venv/bin/python capture_pty.py --out /tmp/capture.bin --seconds 3 --mode request --rows 40 --cols 120 --clear-env
../../../.venv/bin/python term_emulator.py /tmp/capture.bin --rows 40 --cols 120
```

Drop `--clear-env` and pass `--stale-lines 33 --stale-cols 229` to see
the defect; add `--legacy-console` to use the console of before the
change.
