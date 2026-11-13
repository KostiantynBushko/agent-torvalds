# The selection picked up the wrong pane, and the screen blinked

## What the operator reported

> *Please check the copied text from as you can see it is not posible to
> select test from main window only, it also selects content from
> "Workflow & Tools Progress" window.*

and, separately:

> *I have notised that the an entire screen is blinking diring processing
> request*

Two claims, and they have **one** cause.

The text the operator copied is the smoking gun.  It is the answer of the
agent with the furniture of another pane written through the middle of
it:

```
││ Workflow Iteration: [░░░░░░░░░░░░] 0/10 (0%)                                     │
│ available PR tooling.gh is available and authenticated. Let me check for an existing PR and determine the base branch.No existing PR; default          ││                                                                                  ││ branch is master. Let me fetch to ensure the remote is current, and review the full branch diff for the PR description.Branch is a coherent feature    ││ Recent Tool Tasks:                                                               │
```

A terminal hands the operator the **physical** screen, and a selection
is made by *column*.  The border of the "Workflow & Tool Progress" pane
can only end up in the middle of the answer of the agent if the panes
are not where the layout put them — and they are not, because the layout
was drawn for a terminal that is not there.

---

## The finding

### Rich believes the terminal is a different size than it is

The console of the TUI is built with no size at all:

```python
# agent-torvalds-mw.py:574
console = Console()
```

With no size given, Rich asks the terminal — but it asks **the
environment first**:

```python
# rich/console.py:1005 - Console.size
        streams = _STD_STREAMS_OUTPUT if WINDOWS else _STD_STREAMS
        for file_descriptor in streams:
            try:
                width, height = os.get_terminal_size(file_descriptor)
            except (AttributeError, ValueError, OSError):  # Probably not a terminal
                pass
            else:
                break

        columns = self._environ.get("COLUMNS")
        if columns is not None and columns.isdigit():
            width = int(columns)          # ← the environment wins
        lines = self._environ.get("LINES")
        if lines is not None and lines.isdigit():
            height = int(lines)            # ← the environment wins
```

`COLUMNS` and `LINES` are **exported by the shell**, and they are a
snapshot: they carry the size the terminal had when the shell started.
Resize the terminal and they do not follow.

On the machine of the operator they are exported, and they are wrong:

```
$ echo "LINES=[$LINES] COLUMNS=[$COLUMNS]"
LINES=[33] COLUMNS=[229]
```

The terminal is not 229 columns wide.  Rich is told that it is.

So the TUI lays itself out for a 229×33 terminal, and then writes that
layout — 229 columns wide — into a terminal that has fewer columns.
Every row of the layout **folds** at the right edge of the real
terminal, and the second half of the row lands on the row below it.

What the operator sees, reproduced with a 120-column terminal
(`probe_selection_and_flicker.py`, the broken case):

```
│ Recommendation
                           │╰───────────────────────────────────────────────────────────────────────────────╯
│
                           │╭───────────────────────── ℹ️ Agent Telemetry & State ──────────────────────────╮
│ Push the six commits, open the pull request against master, and keep the face-database work on its own branch until the review is done.          ││ Mode                               On-Demand Retriever                        │
│
                           ││ Cache Hits                         0/500 (0%)                                 │
```

The prose of the agent is cut in half by the border of the telemetry
pane, and the pane is pushed out of its column.  The panes are gone.

### The frame does not fit, so the screen scrolls — that is the blink

The Live display writes the whole screen on every frame and never
scrolls it back:

```python
# components/tui/tui_app.py:134
        with Live(
            self.layout,
            console=self.console,
            screen=True,
            auto_refresh=False,
            ...
```

Rich writes the frame from the top of the alternate screen every time
(`Control.home()`, then the whole screen).  A frame of 33 rows × 229
columns, written into a terminal of fewer columns, occupies **twice as
many physical rows** as it has logical ones.  The terminal scrolls to
make room — 33 rows become 66, and the terminal has 40 — so every frame
pushes the screen up by 26 rows.

The picture jumps 26 rows, 15 times a second.  That is the blink.

Measured, over 2.5 seconds of the TUI running in a pty of its own:

| The terminal is 120×40, and | Rich believes | the frame overflows | screen scrolls |
|---|---|---|---|
| stale `LINES`/`COLUMNS` (today) | 229×33 | **yes** | **990** |
| no `LINES`/`COLUMNS` in the environment | 120×40 | no | 2 |
| stale `LINES`/`COLUMNS`, console built the proposed way | 120×40 | no | 2 |

990 scrolls in 2.5 seconds — about 16 per frame, at 15 frames a second.
The screen is redrawn 15 times a second and it moves 26 rows every time.

### The panes are not where the layout put them

The layout is asked, not guessed, where the separator between the
document pane and the sidebar belongs:

```python
# components/tui/layout_manager.py
root["body"].split_row(
    Layout(name="markdown_pane", ratio=65),
    Layout(name="sidebar", ratio=35),
)
```

For a 120-column terminal the separator belongs at **column 77**.  On
the physical screen:

| | the separator is found at | rows with the panes misplaced |
|---|---|---|
| stale `LINES`/`COLUMNS` (today) | column **27** | **13** |
| no `LINES`/`COLUMNS` | column 77 | 0 |
| the proposed console | column 77 | 0 |

The operator selects the columns of the document pane — and the content
of the progress pane is standing in them.

### The log line lands on the alternate screen

The second, independent defect.  The TUI runs on the **alternate
screen**, and Rich is told not to redirect the standard streams:

```python
# components/tui/tui_app.py:138
            screen=True,
            auto_refresh=False,
            redirect_stdout=False,
            redirect_stderr=False,
```

The logging handler writes to `stderr` — the real one, the one of the
terminal:

```python
# agent-torvalds-mw.py:556
    handlers = [logging.StreamHandler(sys.stderr)]
```

And the agent logs on **every iteration** of the loop:

```python
# components/hitl_agent.py:450
        logger.info(
            "Context: %s",
            describe_context(...),
        )
```

The line is written straight onto the alternate screen, between two
frames.  It scrolls the screen, it sits on top of the layout, and the
next frame paints over it — but the scroll already happened.

Measured: the same 2.5 seconds, with and without the chatter:

| | screen scrolls | frames with foreign output |
|---|---|---|
| nothing else writes to the terminal | 2 | 1 |
| the agent logs while it works | **14** | **5** |

Twelve scrolls for twelve lines of log.  This is the part of the blink
that is visible **only during a request** — which is exactly when the
operator noticed it.

### The width of the markdown is guessed

A smaller thing, and it is not the cause of anything here.  The
document pane is rendered to a text of its own, at a width that is
*estimated* rather than measured:

```python
# components/tui/markdown_view.py:109
        estimated_width = max(40, int(self.console.width * 0.62))
```

The real width of the pane is `0.65 × width − 4`:

| terminal | the pane | its content | the estimate | the error |
|---|---|---|---|---|
| 80 | 51 | 47 | 49 | +2 |
| 120 | 77 | 73 | 74 | +1 |
| 160 | 103 | 99 | 99 | 0 |
| 229 | 147 | 143 | 141 | −2 |

A text that is two columns too wide is wrapped again by Rich when it is
put into the panel, and the count of lines the `PgUp`/`PgDn` indicator
reports drifts from the truth.  Cosmetic, and it is left alone.

---

## The proof

| Check | Before | After |
|---|---|---|
| `probe_selection_and_flicker.py` | the defect reproduces and the fix does **not** hold — exit 1 | *the defect reproduces and the fix holds* — exit 0 |
| `tests/test_tui_terminal_size.py` | the file does not exist | 13 passed |
| `tests/test_tui_log_routing.py` | the file does not exist | 12 passed |
| the size Rich believes (terminal 120×40) | 229×33 | 120×40 |
| the frame overflows the terminal | yes | no |
| screen scrolls in 2.5 s | 990 | 2 |
| the pane separator on the screen | column 27 | column 77 |
| rows with the panes misplaced | 13 | 0 |

The probe never touches the terminal of the operator.  The TUI runs in a
pty of its own, the byte stream it produces is recorded, and the stream
is replayed through a terminal emulator
(`repro/term_emulator.py`) that shows the screen the operator would
have seen.

| File | What it is |
|---|---|
| `probe_selection_and_flicker.py` | The probe.  Four runs — the old console with the stale environment, the old console without it, the production TUI with the stale environment, and the production TUI with the agent logging — measured and checked. |
| `repro/capture_pty.py` | Runs the TUI on a pty of a fixed size and records the bytes. |
| `repro/tui_child.py` | The TUI itself, with a stub agent, so the request can be watched without a model. |
| `repro/term_emulator.py` | A small ANSI terminal emulator: it replays the bytes and shows the screen. |

Run it:

```bash
.venv/bin/python investigate/tui-selection-and-flicker/probe_selection_and_flicker.py
```

---

## The change

See `PROPOSAL_tui_terminal_size.md` for the proposal and
`IMPLEMENTATION_REPORT.md` for what was implemented.  In short:

1. **The console asks the terminal, not the environment.**  The console
   of the TUI is built with an environment that carries no `LINES` and
   no `COLUMNS`, so `Console.size` falls through to
   `os.get_terminal_size()` — the size that is true *now*, and that
   follows a resize.  (`components/tui/terminal_size.py`)
2. **The log does not land on the alternate screen.**  While the TUI is
   up, the terminal handlers of the root logger are gone and a file
   handler takes their place.  The operator decided on 2026-11-13:
   *"the log must go into file, not painted over"*.
   (`components/tui/log_routing.py`)

The numbers, after the change:

| | before | after |
|---|---|---|
| the size Rich believes (terminal 120×40) | 229×33 | **120×40** |
| the frame overflows the terminal | yes | **no** |
| screen scrolls in 2.5 s | 990 | **0** |
| the pane separator on the screen | column 27 | **column 77** |
| rows with the panes misplaced | 13 | **0** |
| the log of the agent on the screen | 6 lines, 12 scrolls | **0 lines, 0 scrolls** |
| the log of the agent in the file | — | **6 lines** |

---

## What was left alone

- **The whole screen is repainted on every frame.**  Rich's Live
  display in the alternate screen writes the entire screen 15 times a
  second — 12 KB a frame, 180 KB a second.  It is what makes the
  blink *bright* rather than *faint*.  Rich offers no diffing for the
  alternate screen, and a diff of the layout would be a project of its
  own.
- **The document pane is cropped, not scrolled into view.**  `PgUp` and
  `PgDn` move through a buffer that was rendered at a guessed width.
  The width is the thing that is wrong, not the mechanism.
- **The stale `LINES`/`COLUMNS` of the shell.**  They are the shell's
  business; the application should not believe them.
