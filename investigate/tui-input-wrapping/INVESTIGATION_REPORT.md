# The input bar of the TUI — the text that reaches the end of the view

**Status:** implemented, covered by tests that fail without it.
**Reported by:** the operator, on 2026-11-20 — *"Once the user text reaches the end of the user input view the agent automatically moves to the new line, like it does in the agent question mode"*.

**Probe:** [`probe_input_wrapping.py`](probe_input_wrapping.py) — read-only.  It renders the real layout
and the real panels at the width of a real terminal, and looks for the text of the operator on the
lines of the screen.  It writes nothing and talks to no service.

---

## 1. The request

The operator asked for the text of the command bar to **move to the next line** when it reaches the
end of the view — the way the question of the agent moves to the next line in the agent-question
mode.

The reference is the agent-question mode, and it is an exact one: in that mode the question of the
agent is wrapped by Rich, and the panel grows to hold the wrapped lines.  The text of the operator
was not treated that way at all.

## 2. What the bar was before the change

The text of the operator was **cut at the edge of the view**, with an ellipsis — and the cursor went
with it:

```
│ >>> The operator asked on 2026-11-20 for four things in the command bar of the multi-window      │
```

The question of the agent, in the agent-question mode, was not cut:

```
│ 🤖 AGENT QUESTION: The operator asked on 2026-11-20 for four things in                           │
│ the command bar of the multi-window console, and this text is much            [Enter to confirm] │
│ longer than the bar is wide, so it must be cut or wrapped.                                       │
```

Two things were wrong with the command bar:

* **The text was cut.**  Rich wraps a text inside a panel, but a word that is longer than the
  column is *ellipsized*, not folded — and the text of the operator is one long word as far as Rich
  is concerned when it has no spaces in it.  Everything past the edge of the view was gone.
* **The cursor went with it.**  The cursor is a cell with a style of its own, drawn on the character
  under it.  When that character was past the edge of the view, the cursor was not on the screen at
  all: the operator was typing into the void, and could not see where he was.

The model behind it was the reason.  `components/tui/input_text.py` knew the text as a string of
**logical lines** — the parts between the line breaks of the buffer — and the view was a window over
those.  A logical line that is wider than the bar had no place in that model: it was one line, and
the bar had one line for it.

## 3. What was changed

### 3.1 The text of the bar is seen in lines of the screen, not in logical lines

`components/tui/input_text.py` now knows the text as the **lines of the screen** it takes:

* `wrap_lines(text, width)` — the lines the text takes, and the offset of the first character of
  each one.  A text that reaches the end of the view moves to the next line: the line is broken at
  the last space that fits, and a word that is longer than the view is folded over the lines.  No
  character is lost — the space at a break is eaten by the break, and no word is.
* `cursor_line`, `cursor_column`, `move_cursor_up`, `move_cursor_down`, `visible_window` and
  `visible_line_count` all work in those lines.

The width is a parameter of every one of them, and the default is a width no text of the operator
reaches — so a caller that does not know the width sees the text as it was.

### 3.2 The bar knows how wide it is

`input_text_width()` in `components/tui/layout_manager.py` is the one place that answers *how many
cells the bar gives the text of the operator*:

* the command bar: the width of the terminal, less the border and the padding of the panel, less
  the prompt — **92 cells** at a terminal of 100 columns;
* the agent-question mode: the column of the answer (three quarters of the bar), less the label of
  the answer — **64 cells** at a terminal of 100 columns.

The number is measured, not guessed: the probe of the previous change measured it the same way —
by rendering the panel and finding the number of characters at which the text moved to the next
line.

### 3.3 The bar draws the lines itself

`_input_markup()` renders the lines of the view, one line of the panel each, and the cursor is
drawn on the character under it — in the line the text moved it to.  A line is never wider than the
view, so Rich never wraps it a second time: what the operator sees is what the model says.

The lines after the first are indented by the width of the prompt, so they stand under the text and
not under the prompt.  The answer of the agent-question mode is indented by the width of its label,
the same way.

### 3.4 The cursor walks the lines of the screen

`Up` and `Down` walk the lines of the view — the lines the operator sees — and not the logical
lines of the buffer.  The history is reached at the first line of the view, as it was reached at the
first line of the input.

## 4. How it is verified

`tests/test_tui_multiline_input.py` — 42 tests, in six groups (34 of them from the previous
change):

| group | what it holds |
| :--- | :--- |
| the hot commands | they are shown on an empty bar, hidden while there is text, and back after the last character is deleted |
| the Shift+Enter | there is no line-break key: the sequence is an escape, and the bar does not change by it |
| the view of the input | it grows with the lines, it never shows more than three, and the text above the window is not thrown away |
| **the text that reaches the end of the view** | **it is wrapped, no word is lost, the cursor goes with it, the bar grows with it, and the agent-question mode does the same** |
| the paste | it arrives in one piece, it is put into the bar, a long one shows its last lines, and the text can be edited |
| the cursor | it walks the lines of the input, and the history is still there for the input of one line |

The probe runs the same checks and prints what it sees:

```
$ python investigate/tui-input-wrapping/probe_input_wrapping.py
the terminal is 100 columns wide
the bar gives the text of the operator 92 cells

the text of the operator
   it takes 2 lines of the view
   line 0: 'The operator asked on 2026-11-20 for the text of the comma'
   line 1: 'when it reaches the end of the view, the way the question '

the bar shows
   │ >>> The operator asked on 2026-11-20 for the text of the command bar to move to the next line    │
   │     when it reaches the end of the view, the way the question of the agent does.                 │

the cursor
   the text puts it on line 1
   the screen draws it on row 2

a text of any length
   the view shows 3 lines

everything holds: the text moves to the next line, the cursor goes with it, and the bar takes three lines
```

The gate of the repository stays green:

```
known failures in the baseline : 40
failures in this run            : 40
new failures                    : 0
fixed since the baseline        : 0
```

## 5. What is not in this change

- **There is no Shift+Enter.**  The operator asked for the key on 2026-11-20 and withdrew the
  request the same day: the bar carries no line-break key.  The sequence a terminal sends for it is
  an escape to the reader, and the application drops it — so the text of the operator never changes
  by a key nobody can see.  The lines of the input come from a paste.
- **The trailing line break of the text is dropped when the bar is submitted.**
  `_handle_enter_pressed()` takes `input_buffer.rstrip("\n")`: the line break at the end of the
  text is the end of the message, and it is not a part of it.  The line breaks inside the text are
  kept, and so is the indentation of a pasted block — the text the agent gets is the text the
  operator wrote.
- **The question of the agent is not re-wrapped.**  It is wrapped by Rich, as it was, and it is
  wrapped in the column of the question — which is a different shape from the wrapping of the
  answer, whose lines are indented by the label.
- **A tab in the text is counted as eight cells.**  Rich expands a tab to a tab stop; the model
  counts it as eight cells, which is the width of a tab stop at the start of a line and more than
  the width of a tab stop in the middle of one.  The line may therefore be narrower than it could
  be.
- **The horizontal scroll of a long line is still not there.**  A line is now wrapped, so it is
  never cut — but the operator cannot scroll a line sideways, and the text of a line is seen from
  its beginning.
