# The command bar of the TUI — the invitation to press Enter

**Status:** implemented, covered by tests that fail without it.
**Reported by:** the operator, on 2026-11-20 — *"I would like to see the invitation to press Enter like it is in the agent question mode and the user's message does not occupy an entire input window"*.

**Probe:** [`probe_command_bar.py`](probe_command_bar.py) — read-only.  It renders the real layout
and the real panels at the width of a real terminal, and looks for the invitation on the lines of
the screen.  It writes nothing and talks to no service.

---

## 1. The request

Two things, in one sentence:

* the **invitation to press Enter** — the way the agent-question mode has it — so that the operator
  sees what Enter does with what he wrote;
* the **message of the operator must not occupy an entire input window** — the invitation needs a
  place of its own, and the text has to leave it.

The reference is the agent-question mode, and it is exact:

```
│ 🤖 AGENT QUESTION: Which one?                                                                    │
│ Answer: hello                                                                 [Enter to confirm] │
```

The agent-question mode is a grid of two columns: the question and the answer on the left, the
invitation on the right, on the line the answer is typed on.

## 2. What the bar was before the change

The command bar had **no invitation at all**, and the text of the operator took the whole width of
the bar:

```
│ >>> the operator asked for the invitation to press enter in the command bar, the way the agent │
```

There was nothing to the right of the text: the bar was a grid of one column while there was text
in it, and the hot commands — the only thing that ever stood on the right — were hidden exactly
then.

The measurements of the bar at a terminal of 100 columns, before the change:

| | before |
| :--- | :--- |
| the width of the text of the operator | 92 cells — the whole bar |
| the column of the hot commands | 33 cells |
| the width of the hot commands | 68 cells |

The last two lines are a defect that is **older than this change** and that this change does not
touch: the hot commands are 68 cells long and their column is 33, so they are wrapped over three
lines, and the footer partition — three lines — keeps the first one.  On the screen the operator
sees `[\stats | \tools | \projects |` and the rest of the list is below the panel.

## 3. What was changed

### 3.1 The bar is a grid of two columns, the way the agent-question mode is

`components/tui/layout_manager.py` — `render_footer()`:

* while there is **text** in the bar, the grid is **75% / 25%**: the text of the operator on the
  left, the invitation on the right — the same split the question of the agent and its answer have
  in the agent-question mode;
* while the bar is **empty**, the grid is the one it always was — **65% / 35%** — and the hot
  commands stand on the right, exactly as visible as they were.  The probe compares the two
  renderings of the empty bar, the old one and the new one, and they are the same line of the
  screen.

The text of the operator therefore has a **column of its own**, and the invitation has another one.
The message does not take the whole window any more.

### 3.2 The invitation stands in the lower right corner of the bar

The invitation is not a line of its own: it is a cell of the right column, and the cell is put on
the **last line of the bar**.

```
│ >>> the operator asked for the invitation to press enter in the command                          │
│     bar, the way the agent question mode has it, and the message of the                          │
│     operator must not occupy the whole window of the input                       [Enter to send] │
```

That is the place the agent-question mode has its own invitation: `[Enter to confirm]` stands on the
line of the answer, under the question, and the answer is typed on the last line of the panel — so
the two invitations are in the same place on the screen, the lower right corner of the bar.

The operator asked for this on 2026-11-20 — *"I also want you to make sure the [Enter to send] is on
the same place as the one for (Agent Question)"* — and the rule was measured before it was changed:

| | the command bar | the agent-question mode |
| :--- | :--- | :--- |
| the column of the invitation | the right 25% | the right 25% |
| the right edge of the invitation | the cell 97 | the cell 97 |
| the rows below the invitation | 1 (the border) | 1 (the border) |

The invitation does not walk with the cursor: it is a fixed cell of the bar, and the operator reads
it in the same corner every time — in the corner the agent-question mode put it.

### 3.3 The width of the text is the width of its column

`input_text_width()` is the one place that answers *how many cells the bar gives the text of the
operator*.  It is now the width of the column of the text — three quarters of the bar, less the
prompt: **68 cells** at a terminal of 100 columns, where it was 92.

The number is measured, not guessed, and the model and the screen agree: the text is wrapped by
`wrap_lines()` at that width, and the column is 72 cells wide, so a line never reaches into the
column of the invitation and Rich never wraps it a second time.

The agent-question mode is untouched: the answer of the operator keeps its column of 75% and its
own invitation, `[Enter to confirm]`.

### 3.4 The words of the invitation

The command bar says `[Enter to send]` — Enter sends the text of the operator to the agent.  The
agent-question mode keeps `[Enter to confirm]` — Enter confirms the answer of the operator.  The
two invitations are the same kind of thing, and they say what they do.

## 4. How it is verified

`tests/test_tui_command_bar.py` — 10 tests, in two groups:

| group | what it holds |
| :--- | :--- |
| the invitation | it is on the screen while there is text, it is not on an empty bar, it stands in the lower right corner of the bar, it stays in its corner when the cursor walks up, and the agent-question mode keeps its own — in the same place |
| the message and the window | the text has a column of its own, it is wrapped before the column of the invitation, the bar is not cropped by it, and the hot commands are exactly as visible as they were |

One test of `tests/test_tui_multiline_input.py` was changed: it asserted that the text of the
operator takes the whole width of the bar while the hot commands are gone.  That is not true any
more — and it is not true *because the operator asked for it*.  The test now asserts that the
column of the text is wider than the column the hot commands had.

The probe runs the same checks and prints what it sees:

```
$ python investigate/tui-command-bar-invitation/probe_command_bar.py
the terminal is 100 columns wide
the bar gives the text of the operator 68 cells

the bar with text in it
   │ >>> hello                                                                        [Enter to send] │

a text of three lines
   row 1: │ >>> the operator asked for the invitation to press enter in the command                          │
   row 2: │     bar, the way the agent question mode has it, and the message of the                          │
   row 3: │     operator must not occupy the whole window of the input                       [Enter to send] │
   the cursor is on row 3
   the invitation is on row 3

the message and the window
   the bar is 96 cells wide
   the text of the operator has 72 cells of it
   the invitation has 24 cells of it
   the text is wrapped at 68 cells

the empty bar
   │ >>>                                                               [\stats | \tools | \projects | │

the agent-question mode
   │ 🤖 AGENT QUESTION: Which one?                                                                    │
   │ Answer: hello                                                                 [Enter to confirm] │

everything holds: the invitation is on the screen, it stands in the lower right corner of the bar -- the place the agent-question mode has its own invitation -- the message leaves the window alone, and the hot commands are where they were
```

The gate of the repository stays green:

```
known failures in the baseline : 40
failures in this run            : 40
new failures                    : 0
fixed since the baseline        : 0
```

## 5. What is not in this change

- **The hot commands are still cropped on a narrow terminal.**  They are 68 cells long, their column
  is a third of the bar, and the footer keeps one line of the three they take.  The defect is older
  than this change — it was measured before it, and the change was made so that it does not grow:
  the empty bar is rendered by the same grid as before, and the probe compares the two renderings.
  Giving the hot commands a line of their own would grow the bar by one line while it is empty,
  and that is a change of the shape of the screen that the operator did not ask for.
- **The invitation does not appear on an empty bar.**  There is nothing to send, and an invitation
  that is always on the screen is an invitation that is not true half of the time.
- **There is no line-break key.**  The operator withdrew the Shift+Enter on 2026-11-20 — the bar
  carries no key that adds a line, and the lines of the input come from a paste.  It is described in
  [`investigate/tui-input-wrapping/INVESTIGATION_REPORT.md`](../tui-input-wrapping/INVESTIGATION_REPORT.md).
- **The busy prompt.**  While the agent is busy the prompt is `>>> (busy) `, and the text of the
  operator has eleven cells less — the column of the text is the same, the prompt is longer.
