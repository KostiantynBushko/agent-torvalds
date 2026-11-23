# The hot-keys of the TUI — the panes that scroll, the panes that hide

**The operator asked on 2026-11-21** for three things:

> *scrolling of the "Workflow & Tool Progress"*
> *hide/show "Agent Telemetry & State"*
> *more will be added so the solution must be easy extended*

and then for the three decisions that shape the work:

> *I think it must be separate from the help command*
> *please consider that some hot keys are used by OS so we need alternative,
> your choice also regarding focused window we need highlight selected window
> somehow*
> *ok I think we can keep it as config under .config/torvalds key and user
> may redefine the default one, the agent must be able to create this config
> file on start-up if not exists*

The design is written down in **[docs/tui/hotkeys.md](../../../docs/tui/hotkeys.md)**.
This report is the evidence: what was measured, what was built, and what
the tests hold together.

---

## What was measured

### The reader could not name a chord

The operator wants a hot-key, and the reader is what turns the bytes of
the terminal into the names the application acts upon.  It could not name
one:

| what the operator presses | what arrives | what the reader said |
| :--- | :--- | :--- |
| `Ctrl+A` … `Ctrl+Z` | the raw control byte `0x01`…`0x1A` | *nothing* — the byte is not printable, and `_handle_key` dropped it |
| `Ctrl+Up` | `ESC [ 1 ; 5 A` | `"UP"` — **the modifier was thrown away** in `_decode_csi` |
| `F1` … `F12` | `ESC [ 11 ~` … | `"ESCAPE"` — **wrong** |
| `Alt+A` | `ESC a` | `"ESCAPE"` — **the character was lost** |

`_decode_csi()` looked at the **final byte only**: the modifier part of
`ESC [ 1 ; 5 A` was parsed into `params` and then thrown away, so
`Ctrl+Up` was *indistinguishable* from `Up`.

**There was no key that could carry a hot-key.**  Not because the
terminal cannot send one, but because the reader did not name one.  So
step one was the reader — and every solution that skips it ends up
taking a key away from the operator's typing.

### The overflow of the progress pane was invisible

Measured with the real pane, at a terminal of 120 columns (the pane is
42 cells wide, 17 lines tall — 15 lines of content):

```
 0 | ╭───── ⚡ Workflow & Tool Progress ──────╮
 1 | │ Workflow Iteration: [████░░░░░░░░] 3/8 │
 2 | │ (37%)                                  │
 3 | │                                        │
 4 | │ Recent Tool Tasks:                     │
 5 | │  ✔ execute_shell_command (0ms)         │
 6 | │    └ python scripts/ci_test_gate.py    │
 7 | │      --write-baseline                  │
 …
15 | │  ✔ read_file (0ms)                     │   ← cut off
16 | │    └ ~/projects/          │   ← cut off
17 | │      agent-torvalds/components/tui/    │   ← cut off
```

**Six lines of content were cut off** — and they were the lines of the
*oldest* task, because the pane listed the newest task first.  The
command `git status --short && python -m pytest tests/ -x --tb=short`
ran, and **there was no way to see it.**  PR #106 made the command whole
when it is shown; this is the other half of that work: the command must
also be *reachable*.

### The notification lived in the pane that is asked to hide

`TelemetryView.render()` drew the notification banner as the last row of
its table.  Hiding the telemetry pane would therefore have **silenced
every message the TUI gives the operator** — including the message that
says the pane is hidden.

### The keys the operating system takes

The reader puts the terminal into *cbreak* mode — and cbreak is **not**
raw mode: `ISIG` and `IXON` are left exactly as they were.

| chord | who takes it | why |
| :--- | :--- | :--- |
| `Ctrl+C` | the **kernel** — SIGINT | `ISIG` is on: the byte raises a signal and never reaches the app |
| `Ctrl+\` | the **kernel** — SIGQUIT | the same |
| `Ctrl+Z` | the **kernel** — SIGTSTP | the same |
| `Ctrl+S` | the **terminal** — XOFF | `IXON` is on: the byte is swallowed and **the screen freezes** |
| `Ctrl+Q` | the **terminal** — XON | the same |
| `Ctrl+H` `Ctrl+I` `Ctrl+J` `Ctrl+M` | the terminal's own keys | 0x08 backspace, 0x09 tab, 0x0A/0x0D enter |
| `Alt+<key>` | the **desktop** / the terminal | `Alt+Tab` is the window manager; iTerm2 and Windows Terminal switch tabs on `Alt+arrow` |

**The letters that are left: `A B E F G K L N O P R T U V X Y`.**

The probe measures the reader against that list, and the test refuses
any binding that the operating system would eat — so a hot-key that the
kernel, the terminal or the desktop would swallow can never be added.

---

## What was built

### The reader names the modified keys

`components/tui/input_reader.py` names what the terminal sends:

| the operator presses | the reader says |
| :--- | :--- |
| `Ctrl+A` … `Ctrl+Z` | `CTRL_A` … `CTRL_Z` |
| `Ctrl+Up` | `CTRL_UP` |
| `Shift+Down` | `SHIFT_DOWN` |
| `Ctrl+Alt+Right` | `CTRL_ALT_RIGHT` |
| `F1` … `F20` | `F1` … `F20` |
| `Alt+a` | `ALT_a` |

The four bytes that another key already claimed keep their name:
`Ctrl+H` is still `BACKSPACE`, `Ctrl+I` is still `TAB`, and `Ctrl+J`
and `Ctrl+M` are still `ENTER`.

**The Shift+Enter is still not a key of the command bar.**  The operator
decided on 2026-11-20 that the bar carries no line break key.  The
reader may now *name* the sequence, and the application still drops it:
the text of the operator never changes by a key nobody can see.

### The registry — one table, one screen

`components/tui/hotkeys.py` holds the table of the keys of the TUI: the
keys of the command bar (`scope="bar"`) and the hot-keys of the panes
(`scope="global"` and `scope="pane"`).  It is **the only list** — the
`\keys` screen is rendered from it, and the `Keyboard Navigation` block
**left** the `\help` screen.

`KEYBOARD_SHORTCUTS` and the `keyboard_shortcuts` flag left the command
registry: the registry describes the **commands**, and the hot-keys
describe the **keys**.

### The bindings are configuration

The `[hotkeys]` section of `~/.config/torvalds/config.toml` — the file
the operator already has.  The settings join the **module-level**
`SETTINGS` of `components/config.py`, because **both agents read and
write the same schema**: a section that one of them did not know would
be reported by it as *"the section [hotkeys] is not known to the agent"*
at every start-up.

Two findings of the prototype went into the code:

1. `Config.default_template()` walked the module constant `SETTINGS`
   and not `self.settings` — a `Config` that was given its own settings
   wrote a template that **did not match them**.  It walks the instance
   now.
2. The settings that read the file and the settings that write the
   template must be **the same list**: the prototype read the file with
   the three hot-key settings alone, and the agent then reported **the
   sections it had written itself** as *"not known to the agent"*.

### The scroll of a pane

`components/tui/pane_scroll.py` holds the scroll state of a pane: the
offset of the window, the number of lines the content has, the **anchor**
— the id of the item at the top of the window — and whether the window
follows the end of the content.

**The list is a log.**  The oldest task first, the newest at the bottom,
and the window stuck to the bottom: "down" walks *forward* in time, the
way it does in every scrollable thing the operator knows, and the
running task is the last line on the screen, where the eye already is.

**The anchor keeps the operator where he is.**  A new task that arrives
while the operator is reading an old one does not move his window.

**The height is the one the layout really uses** —
`layout.map[layout["progress_pane"]].region.height`, less the two lines
of the border.  It is the same principle as `progress_pane_width()` in
PR #106: *the number is the one the layout really uses*, not the one the
source guesses.

### The pane that has the focus is marked

Three marks, together, so that it can never be guessed:

1. the **border is brighter** — `cyan` becomes `bright_cyan`, `magenta`
   becomes `bright_magenta`, and the *content* is never dimmed;
2. the **title carries the marker `▶`**, in front of the icon;
3. the **subtitle says where the operator is** — `▲ 10/21 │ ▼ 9 more`.

### The notice moved to the header

The notification is drawn in the **header**, which grows by one line
while a notice is up — the mechanism `fit_footer()` already uses for the
footer.  A notice is then visible whatever the operator has hidden.

---

## The probe

The probe drives the **real** application — the real state, the real
layout, the real panels — with the keys the operator presses, and it
draws what the operator would see:

```
python investigate/tui-hotkeys/probe_hotkeys.py
```

It shows the reader and the names it gives the keys, the table of the
bindings, the focus and the marks that show it, the scroll of the log,
the hidden pane and the space its sibling takes, the refusals of the
configuration file, and the `\keys` screen.

---

## The tests

| file | what it holds together |
| :--- | :--- |
| `tests/test_tui_input_reader.py` | the reader names the modified keys: `Ctrl+A` is `CTRL_A`, `Ctrl+H` is still `BACKSPACE`, `Ctrl+Up` is not `UP`, `F5` is `F5`, `Alt+a` is `ALT_a` |
| `tests/test_tui_hotkeys.py` | the settings of the file and the actions of the registry agree; the chords the operating system takes are refused; a refusal is a warning and not a crash; a printable character always goes into the input and takes the focus back; a paste is never taken by a hot-key; the `\keys` screen names every binding, and the `\help` screen names none |
| `tests/test_tui_pane_scroll.py` | the window is clamped to the content; the anchor keeps the operator on his task; the window follows the end of the log; the list is a log; the hidden pane leaves the layout and its sibling takes the space; the focused pane carries the brighter border and the marker |
| `tests/test_help_command.py` | the `\help` screen carries the **commands only** — the test that asserted the presence of the "Keyboard Navigation" block now asserts its **absence**, so that nobody puts it back by accident |

**The gate does not move**: `tests/ci_baseline.txt` carries the known
failures, and the feature adds **0 new** failures and fixes **0**.

---

## The decisions

The decisions of the operator and the choices that follow them are
written down in **[docs/tui/hotkeys.md §16](../../../docs/tui/hotkeys.md)**,
so that any one of them can be reversed on its own — and the ones that
change what the operator sees (the order of the task list) are one line
of code each.
