# The command of a tool is cut on the screen of the progress pane

**The operator asked on 2026-11-20.**  The *Workflow & Tool Progress* pane
shows the tool that runs and, under its name, the line that says what it
works on.  That line was cut, and the operator saw:

```
 ✔ execute_shell_command (33ms)
   └ cd ~/projects/agent-torvalds && git stat
```

The rest of the command — `us --short && python -m pytest tests/ -x` — was
gone.  The cut is exactly the part of a command that says what it does.

**The operator asked for the whole command**, and for the command to be
**split** when it does not fit on the screen.

---

## What was measured

The state of the TUI keeps the **whole** command:

```python
# components/tui/state_bridge.py — update_tool_start()
if tool_name == "execute_shell_command":
    details = tool_kwargs.get("command", "")
```

The cut was in the **view**:

```python
# components/tui/progress_view.py — display_detail()
return hide_home(details)[:DETAIL_WIDTH]      # DETAIL_WIDTH = 40
```

So the command was never lost by the agent, and never lost by the state: it
was lost by the pane, on the way to the screen.

The probe asks the real panel, with the real state, at the widths of the
terminals the operator uses, and reports what the screen carries:

```
python investigate/tui-progress-full-command/probe_progress_detail.py
```

The probe was written against the code of the branch, and the checks it
holds are the ones the fix is measured by:

| check | what it asks |
|---|---|
| the whole command is on the screen | every character of the command reaches the screen |
| the command is split to the width of the pane | no line of the detail is wider than the pane |
| the brackets of the command survive | the command on the screen is the command that ran |
| the width is the width of the layout | the number the pane splits to is the number the layout gives it |

---

## What was wrong

### 1. The detail was cut at forty characters

`DETAIL_WIDTH = 40` was a constant.  It was not the width of the pane — the
pane is a third and a half of the width of the terminal, so the pane is 28
cells wide at a terminal of 80 columns, 42 at 120 and 56 at 160.  The cut
was a number of the source, and the pane was a number of the terminal, and
the two had nothing to do with each other.

At a terminal of 80 columns the pane showed 24 cells of text and the cut
was at 40: Rich wrapped the 40 characters over two lines, and the operator
read a command that was cut at an arbitrary place.

### 2. The command was not the command that ran

The detail went into `Text.from_markup()` without being escaped.  A command
carries square brackets of its own, and Rich reads them as markup: **the
text between them was dropped from the screen**.

```
the command:   ls [abc] && echo "x" > out.txt
the pane:      ls  && echo "x" > out.txt
```

The operator was shown a command that was not the one that ran.  This was
not visible in the complaint, and it was found while the cut was being
measured — but it is the same defect: the screen did not carry the command.

### 3. The pane did not know how wide it was

The width of the pane is a share of the width of the terminal, and the
layout is what decides it.  The view was asked for the state alone, so it
had no way of knowing the width of the window it was painted in.

---

## The change

### The whole detail is shown, and it is split to the width of the pane

`display_detail()` no longer cuts.  It hides the home, escapes the text and
splits it:

```python
def display_detail(details: str, width: int) -> str:
    lines = split_detail(hide_home(details), width)
    return ("\n" + " " * DETAIL_PREFIX).join(escape(line) for line in lines)
```

The home is hidden **before** the text is split — a home that is cut in half
is worse than a home that is shown.  The text is escaped, so that the
square brackets of a command are the brackets of a command and not markup.

`split_detail()` puts the words of the detail on the lines as they come:

* a word that does not fit beside what is on the line goes on the next one;
* a word that does not fit on a line of its own is cut — a **path** is cut
  at the separator that fits, so that the name of a folder is not cut in the
  middle;
* the spaces between the words are kept: a command carries spaces that mean
  something, inside a quoted text every one of them counts;
* the line breaks that are in the detail are kept — the detail may be a
  script of more than one line.

Only the spaces at the break of a line are gone.  Nothing else of the command
is lost.

The lines after the first one are indented by the width of the branch that
opens the detail, so that the text of a command that takes several lines
stands under itself and reads as one command.

### The pane knows how wide it is

`progress_pane_width()` in `components/tui/layout_manager.py` computes the
width of the pane the way Rich divides the layout: the remainder of the
division is carried to the next column, and a column that would be narrower
than the minimum gets the minimum.

The check asks the **real** layout for the region of the pane and compares
it with the number that is computed:

```
python -c "..."
--- console  80 actual= 28 computed= 28 match=True
--- console 100 actual= 35 computed= 35 match=True
--- console 120 actual= 42 computed= 42 match=True
--- console 140 actual= 49 computed= 49 match=True
--- console 160 actual= 56 computed= 56 match=True
--- console 200 actual= 70 computed= 70 match=True
```

A Rich that divides its layout another way is caught by the check, and not
by a pane that splits its text in the wrong place.

---

## The evidence that it works

The pane at the widths of the terminals the operator uses:

```
--- a terminal of 80 columns (the pane is 28 cells wide) ---
│    └ cd                  │
│      ~/projects/         │
│      agent-torvalds      │
│      && git status       │
│      --short && python   │
│      -m pytest tests/ -x │

--- a terminal of 120 columns (the pane is 42 cells wide) ---
│    └ cd ~/projects/agent-torvalds &&   │
│      git status --short && python -m   │
│      pytest tests/ -x                  │

--- a terminal of 160 columns (the pane is 56 cells wide) ---
│    └ cd ~/projects/agent-torvalds && git status      │
│      --short && python -m pytest tests/ -x           │
```

The whole command is on the screen at every width, and no line is wider
than the pane.

The check of the change: `tests/test_tui_progress_detail.py` — 24 tests —
and `investigate/tui-progress-full-command/probe_progress_detail.py`, which
drives the real panel from the real state.

The gate of the repository stays green: 40 known failures, 0 new, 0 fixed.

---

## What is **not** in the change

* **The pane does not scroll.**  A command that takes six lines takes six
  lines of the pane, and a pane that is full is cut from the bottom — the
  **newest** task is at the top and is the one that is always seen.  A pane
  that scrolls would need a scrollbar of its own, and the operator did not
  ask for one.

* **The number of the tasks is not changed.**  The pane still shows the six
  most recent ones.

* **The detail of a tool that is not a command is not changed.**  A path is
  shown whole, and it is split in the same way when it is too long.

* **The state is not changed.**  The state keeps the whole command, and it
  keeps the real path of the machine — the pane hides the home of the
  operator and it does that on the screen only.

---

## The files

| file | what changed |
|---|---|
| `components/tui/progress_view.py` | the detail is split instead of cut, and it is escaped |
| `components/tui/layout_manager.py` | the width of the pane is computed the way the layout divides it |
| `components/tui/tui_app.py` | the pane is told how wide it is |
| `tests/test_tui_progress_detail.py` | the check of the change — 24 tests |
| `investigate/tui-progress-full-command/` | this report and the probe |
