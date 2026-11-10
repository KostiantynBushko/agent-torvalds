# The typed text was invisible

## What the operator reported

> *after agent response sometime by typint I do not see what is typed
> looks like it is hidded even after leaving agent app the typing in
> terminal is hidden*

Three claims, and they are three different things:

| The claim | What it was |
|---|---|
| *after the agent's response* | the HITL panel of the footer — the question of the agent, and the line the answer is typed on |
| *I do not see what is typed* | the answer line was **cropped away**. The text was in the application the whole time; it was never on the screen |
| *even after leaving the agent app* | the terminal was left with the echo off — the state belongs to the *terminal*, not to the process, so it outlived the agent |

The middle one is the defect that was reported. The last one is a
separate weakness of the same area, and it is narrower than it sounds:
the terminal is given back on every ordinary exit.

| Path | File | Evidence |
|---|---|---|
| `probe_hidden_input.py` | The probe — it renders the TUI the way the app does, and it checks the terminal against a pty of its own, so it never touches the terminal of the operator. | Before the fix: *"the operator sees it: NO"*, exit 1. After: exit 0. |

---

## The finding

### The answer line was never on the screen

The footer of the TUI is a partition of the layout, and its height is
fixed:

```python
root.split_column(
    Layout(name="header", size=3),
    Layout(name="body", ratio=1),
    Layout(name="footer", size=3),     # ← three lines
)
```

Three lines is a border, **one** line of content, and a border.  The
command bar fits in one line of content:

```
╭──────────────────────────────────────────╮
│ >>>                                      │
╰──────────────────────────────────────────╯
```

The HITL panel does not fit.  It carries two lines of content — the
question of the agent, and the line the answer is typed on:

```python
left_content = Text.from_markup(
    f"[bold bright_yellow]🤖 AGENT QUESTION:[/bold bright_yellow] [white]{safe_prompt}[/white]\n"
    f"[bold bright_cyan]{answer_label}[/bold bright_cyan][white]{cursor_rendered}[/white]"
)
```

A panel that is taller than the partition it lives in is **cropped from
the bottom** — and the answer is the last line of the panel.  So the
answer was the first thing to go:

```
--- the footer of the TUI, with a question waiting ---
   │ 🤖 AGENT QUESTION: Which file should I read?                            │
```

The line the operator types on was not on the screen.  The operator
typed, and the application had the text the whole time — it was drawn
into a region that was three lines tall, and the second line of it was
cut off.

The height the panel needs, measured:

| Terminal width | Short question | A question that wraps |
|---|---|---|
| 80 | 5 lines | 10 lines |
| 120 | 4 lines | 7 lines |
| 160 | 4 lines | 6 lines |

A fixed height could not have been right: the question is agent text,
and its length is not known in advance.

### The typed text was read as markup

The HITL panel put the typed text into the markup of Rich without
escaping it:

```python
cursor_rendered = f"{before_cur}[black on bright_yellow]{cur_char}[/black on bright_yellow]{after_cur}"
```

Rich reads square brackets as markup, so the text between them was
swallowed.  The command bar — the same text, one branch up — escaped it
correctly:

```python
cursor_rendered = (
    f"{escape(before_cur)}"
    f"[black on green]{escape(cur_char)}[/black on green]"
    f"{escape(after_cur)}"
)
```

What the operator saw:

| Typed | On the screen |
|---|---|
| `rm -rf [a-z]` | `Answer: rm -rf` |
| `a[b]c` | `Answer: ac` |

And a bracket that closes a tag Rich never opened takes the panel down
with a `MarkupError`.

### The terminal was left mute when the agent did not exit on its own

The reader puts the terminal into cbreak mode, and cbreak switches the
echo off — the TUI draws the typed text itself:

```python
self._old_termios = termios.tcgetattr(self._fd)
tty.setcbreak(self._fd)
```

The state belongs to the **terminal**, not to the process.  A terminal
that is left in cbreak mode shows nothing of what is typed, and it stays
that way after the agent is gone.

The ordinary exits give the terminal back — measured, with the real app
in a pty:

| The agent is left with | The terminal afterwards |
|---|---|
| `\exit`, Ctrl-D | echo on |
| Ctrl-C (SIGINT) | echo on |
| `kill` (SIGTERM) | echo on |
| `kill -9` (SIGKILL) | **echo off** |

SIGKILL cannot be caught, so no program can answer for it.  But an exit
that no handler runs — an exception outside the loop, an exit that
skips the cleanup — was not covered either: the reader had no safety
net of its own.

---

## The change

### The footer gets the room the panel needs

`components/tui/layout_manager.py` measures the panel and gives the
partition that many lines, while a question is waiting:

```python
def footer_height(console: Console, panel: Panel) -> int:
    options = console.options.update(height=None)
    return len(console.render_lines(panel, options))


def fit_footer(layout, console, panel, hitl_active=False) -> int:
    if hitl_active:
        needed = max(FOOTER_HEIGHT, footer_height(console, panel))
    else:
        needed = FOOTER_HEIGHT
    layout["footer"].size = needed
    return needed
```

The command bar keeps the height it has always had — one line of
content, and the hints beside it are as long as they have been.  Only
the HITL panel claims room, and it gives it back when the answer is
in.

The answer line is now on the screen:

```
--- the footer of the TUI, with a question waiting ---
   │ 🤖 AGENT QUESTION: Which file should I read?                                                 │
   │ Answer: rm -rf [a-z] now                                                  [Enter to confirm] │
```

### The typed text is escaped

The HITL branch escapes the typed text, exactly as the command bar
does.  What is typed is now what is seen:

```
--- typed b'[/]' ---
   input_buffer in the app : 'ZZQQ [a-z][/]'
   'ZZQQ' on screen        : True
   '[a-z]' on screen       : True
   | │ Answer: ZZQQ [a-z][/]                                                    │
```

and the panel no longer falls over.

### The terminal is given back

`components/tui/input_reader.py` registers its own `stop()` with
`atexit`, so every exit that runs the atexit handlers gives the
terminal back — an exception outside the loop, an exit that skips the
cleanup, a `sys.exit()` from anywhere.

```python
atexit.register(self.stop)
```

---

## The proof

| Check | Before | After |
|---|---|---|
| `probe_hidden_input.py` | *the operator sees it: NO* — exit 1 | exit 0 |
| `tests/test_tui_footer.py` | the file does not exist | 14 passed, 1 skipped |
| The suite | 39 failed, 2899 passed, 9 skipped, 1 error | 39 failed, **2913 passed**, 10 skipped, 1 error |

The 39 failures and the 1 error are the ones the repository already
carries — the set is the same before and after the change, file for
file.  The 14 new tests are the ones in `tests/test_tui_footer.py`; the
one skip is the check that needs a real terminal, and pytest does not
run in one.

---

## What was left alone

- **The hints of the command bar are cut short.**  The hints
  (`\stats | \tools | \projects | …`) are longer than the column they
  sit in, and the footer has one line of content.  That was true before
  the change and it is true now: the command bar keeps the height it
  has always had.  It is a separate matter, and it changes the look of
  the screen for everybody.
- **A `kill -9` still leaves the terminal mute.**  SIGKILL cannot be
  caught.  The operator who ends the agent that way gets a mute
  terminal, and `stty sane` gives it back.
