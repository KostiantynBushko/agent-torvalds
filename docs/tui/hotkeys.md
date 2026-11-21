# Hot-keys for the Torvalds TUI — the panes that scroll, the panes that hide

**Status**: final — this is the documentation of the feature, not a proposal
**Date**: 2026-11-21
**Applies to**: `agent-torvalds-mw.py` (the multi-window console agent)

**Audience**: **Part 1** is written for the operator — it says what the keys
do and how to change them. **Part 2** is written for the developer — it
says how the machinery is built, which files it lives in, and how a new
hot-key is added.

---

# Part 1 — The operator's guide

## 1. The keys at a glance

The TUI has four panes and one command bar.  The hot-keys move the focus
between the panes, scroll what is inside them, and take the two panes of
the sidebar out of the way when they are not needed.

| Key | What it does | Where it is live |
| :--- | :--- | :--- |
| **`Ctrl+T`** | Show or hide the *Agent Telemetry & State* pane | always |
| **`Ctrl+P`** | Show or hide the *Workflow & Tool Progress* pane | always |
| **`Tab`** | Move the focus to the next pane | always |
| **`Shift+Tab`** | Move the focus to the previous pane | always |
| **`Esc`** | Give the focus back to the command bar | always |
| **`Up`** / **`Down`** | Scroll the focused pane by one line | a pane has the focus |
| **`PgUp`** / **`PgDn`** | Scroll the focused pane by one page | a pane has the focus |
| **`Home`** / **`End`** | Go to the top / the bottom of the focused pane | a pane has the focus |

The keys of the command bar are the ones the TUI has always had:

| Key | What it does |
| :--- | :--- |
| **`Enter`** | Send what is written in the command bar; confirm the answer of the agent |
| **`Paste`** | Paste text into the command bar |
| **`Up`** / **`Down`** | Move between the lines of the input, or browse its history |
| **`Left`** / **`Right`** | Move the cursor in the command bar |
| **`Home`** / **`End`** | Jump to the start / the end of the line |
| **`PgUp`** / **`PgDn`** | Scroll the document pane |
| **`Ctrl+C`** / **`Ctrl+D`** | Clear the command bar, or leave the TUI when it is empty |

**The rule that makes it safe**: a printable character always goes into
the command bar, and it takes the focus back with it.  The operator is
never trapped in a pane — he scrolls the progress pane, he types a
character, and he is at the command bar again, with the character in the
buffer.

**The chords are always live.**  `Ctrl+T`, `Ctrl+P`, `Tab`, `Shift+Tab`
and `Esc` work while the operator is typing, because a chord carries no
text and cannot eat what is being written.

**`\keys` shows the whole list**, with the bindings the operator has
today.  It is a command of its own — it is *not* part of `\help`, which
lists the commands.

## 2. The panes of the TUI

```
┌──────────────────────────────────────────────────────────────────────┐
│ ⚡ TORVALDS AGENT   Model: …   Mem: … msgs   HITL: ON   Uptime: …    │  header
├──────────────────────────────────────┬───────────────────────────────┤
│                                      │ ⚡ Workflow & Tool Progress    │
│                                      │                               │
│         Markdown Document Viewer     │   Workflow Iteration: [███] 3/8│
│                                      │                               │
│         (the answer of the agent,    │   Recent Tool Tasks:          │
│          the documents, the logs)    │    ✔ execute_shell_command     │
│                                      │      └ python scripts/ci.py   │
│                                      │                               │
├──────────────────────────────────────┤                               │
│                                      │ ⚡ Agent Telemetry & State     │
│                                      │                               │
│                                      │   Mode      On-Demand         │
│                                      │   Cache     12/40 (30%)       │
│                                      │   Prompt    8,240 tok         │
├──────────────────────────────────────┴───────────────────────────────┤
│ >>> [Enter to send]              [\stats | \tools | \keys | \exit]  │  command bar
└──────────────────────────────────────────────────────────────────────┘
```

* the **document pane** — on the left; the answer of the agent, the
  documents, the output of the commands;
* the **progress pane** — above the sidebar; the workflow iteration and
  the tools the agent runs;
* the **telemetry pane** — below the sidebar; the counters, the size of
  the prompt, the tools the agent has;
* the **command bar** — at the bottom; where the operator types.

## 3. Moving the focus

`Tab` moves the focus to the next pane, and the cycle **wraps around**:

```
command bar → document → progress → telemetry → command bar → …
```

`Shift+Tab` walks the same cycle backwards.  It is a convenience: the
legacy Windows console does not deliver it, and the wrap around means
`Tab` alone is enough to reach every pane.

`Esc` gives the focus back to the command bar.

**A hidden pane is not in the cycle.**  When the telemetry pane is
hidden, `Tab` goes from the progress pane straight back to the command
bar.

### How the selected pane is shown

The pane that has the focus is marked in **three ways at once**, so that
it can never be guessed:

1. **the border of the pane is brighter** — the document pane is `blue`
   and `bright_blue` when it is selected, the progress pane is `cyan` and
   `bright_cyan`, the telemetry pane is `magenta` and `bright_magenta`.
   The *content* of a pane is never dimmed — a dimmed command is a
   command the operator cannot read;
2. **the title carries the marker `▶`**, in front of the icon:

   ```
   not selected:      ⚡ Workflow & Tool Progress
   selected:       ▶  ⚡ Workflow & Tool Progress
   ```

3. **the subtitle says where the operator is** — the scroll position of
   the pane, the way the document pane already says it:
   `▲ Line 6/21 │ ▼ 14 more (PgDn)`.

The command bar needs no mark of its own: the typing always goes there,
and the first printable character brings the focus back to it.

## 4. Scrolling a pane

While a pane has the focus, the navigation keys scroll **that** pane
instead of the command bar.

| Key | What it does |
| :--- | :--- |
| `Up` / `Down` | scroll by one line |
| `PgUp` / `PgDn` | scroll by one page |
| `Home` / `End` | go to the top / the bottom |

**While the command bar has the focus**, the keys keep the behaviour they
always had: `PgUp`/`PgDn` scroll the document pane, and `Up`/`Down` move
the cursor in the input and browse its history.

### The progress pane is a log

The list of the tasks of the progress pane reads **oldest first, newest
at the bottom**, and the window sticks to the bottom — so the running
task is the last line on the screen, where the eye already is.

`PgUp` walks back into the history, `PgDn` comes forward.

**The window keeps the operator where he is.**  When a new tool task
arrives while the operator has scrolled up, the window does not jump: it
keeps the task the operator is reading.  The operator who has not
scrolled keeps the newest task.

> The pane used to list the **newest** task first, which made "down" walk
> *into the past* — the opposite of every scrollable thing the operator
> knows.  The list became a log; §16.1 records the decision and how to
> reverse it.

## 5. Hiding a pane

`Ctrl+T` and `Ctrl+P` take the two panes of the sidebar out of the way.

When a pane is hidden, **the space goes to its sibling**: hiding the
telemetry pane gives the whole sidebar to the progress pane.

| | Before | After `Ctrl+T` |
| :--- | :--- | :--- |
| progress pane | 42 × 17 | 42 × 34 |
| telemetry pane | 42 × 17 | *not on the screen* |

The same key brings the pane back, in the place it was.

**The notice of the TUI is not in a pane.**  The messages the TUI gives
the operator — *"Agent is busy processing"*, *"Working in session …"* —
are drawn in the **header**, so a notice is visible whatever the
operator has hidden.

## 6. Changing a binding

The bindings live in the configuration file the agent already has, in a
new `[hotkeys]` section:

| Platform | The file |
| :--- | :--- |
| Linux and the BSDs | `~/.config/torvalds/config.toml` |
| macOS | `~/Library/Application Support/torvalds/config.toml` |
| Windows | `%APPDATA%\torvalds\config.toml` |

`$XDG_CONFIG_HOME` is honoured on **every** platform, and
`$TORVALDS_CONFIG` points at another file.

The section looks like this — **every line is a comment**, so the file
changes nothing until a line is uncommented:

```toml
[hotkeys]
# Show or hide the *Agent Telemetry & State* pane.
# toggle_telemetry = "Ctrl+T"
# Show or hide the *Workflow & Tool Progress* pane.
# toggle_progress = "Ctrl+P"
# Give the focus to the next pane.
# focus_next = "Tab"
# Give the focus to the previous pane.
# focus_previous = "Shift+Tab"
# Give the focus back to the command bar.
# focus_input = "Esc"
# Scroll the focused pane by one line.
# scroll_up = "Up"
# scroll_down = "Down"
# Scroll the focused pane by one page.
# scroll_page_up = "PgUp"
# scroll_page_down = "PgDn"
# The top of the focused pane.
# scroll_home = "Home"
# The bottom of the focused pane.
# scroll_end = "End"
```

### What the operator may do with it

| The file says | The effect |
| :--- | :--- |
| nothing about the action | the **default** stands |
| `toggle_telemetry = "Ctrl+Y"` | the action is bound to `Ctrl+Y` — **and `Ctrl+T` is free again** |
| `focus_previous = ""` | the action is **unbound** — the key is free, the action does nothing |
| `toggle_telemetry = "Ctrl+Alt+Y"` | **refused** — `Alt` belongs to the desktop (§8): a warning, and the default stands |

**The replacement is per action, and it frees the old key.**  There is no
list of bindings to keep in sync: the operator moves one action, and the
key it had is free.

### What is refused, and what happens then

* a chord that does not parse — *"Ctrl+"*, *"Space Bar"* — is **refused**;
* a chord the operating system takes is **refused** (§8);
* a chord that **two actions** ask for is **refused** for the second one.

**A refusal is a warning, never a crash.**  The TUI starts, the default
stands, and the operator is told which setting of which file was refused
and why.  It is the rule the rest of the configuration file already
follows: *a broken file is a warning, not a failed boot*.

### When the change takes effect

The file is read when the agent starts.  A binding therefore takes effect
on the **next start** of the agent.

The `\keys` screen shows the lines **as they are now**, so the operator
can copy them into the file.

## 7. The `\keys` screen

```
\keys
```

The screen lists **every key of the TUI** — the keys of the command bar
and the hot-keys of the panes — in one table, from one source.  It shows
the bindings the operator has today, and the lines to copy into the
configuration file.

The `\keys` screen is a command of its own, and it is **not** part of
`\help`: `\help` is the list of the *commands*, `\keys` is the list of
the *keys*.  A key list that is a copy of the registry is a copy that
goes stale.

The hints of the empty command bar point at it:

```
[\stats | \tools | \projects | \chat-sessions | \keys | \help | \exit]
```

## 8. The keys the operating system takes

The operator is right: **a hot-key that the terminal or the desktop eats
is not a hot-key.**

The reader puts the terminal into *cbreak* mode — and cbreak is **not**
raw mode: `ISIG` and `IXON` are left exactly as they were.  What that
costs:

| Chord | Who takes it | Why |
| :--- | :--- | :--- |
| `Ctrl+C` | the **kernel** — SIGINT | `ISIG` is on: the byte raises a signal and never reaches the app |
| `Ctrl+\` | the **kernel** — SIGQUIT | the same |
| `Ctrl+Z` | the **kernel** — SIGTSTP | the same |
| `Ctrl+S` | the **terminal** — XOFF | `IXON` is on by default: the byte is swallowed and **the screen freezes** |
| `Ctrl+Q` | the **terminal** — XON | the same |
| `Ctrl+H` `Ctrl+I` `Ctrl+J` `Ctrl+M` | the terminal's own keys | 0x08 backspace, 0x09 tab, 0x0A/0x0D enter |
| `Alt+<key>` | the **desktop** / the terminal | `Alt+Tab` is the window manager; iTerm2 and Windows Terminal switch tabs on `Alt+arrow` |
| `Ctrl+Shift+T` `Ctrl+Shift+W` `Ctrl+Shift+C` `Ctrl+Shift+V` | Windows Terminal / the shell | reopen tab, close pane, copy, paste |
| `F1` | some terminals | opens the help of the terminal |

**The letters that are left: `A B E F G K L N O P R T U V X Y`.**
(`C`, `D`, `S`, `Q`, `Z` and `W` are excluded as well — `C` and `Z` by
the kernel, `S` and `Q` by the flow control, `D` by the exit path, `W`
by the terminals that close a pane on it.)

The default bindings of §1 use two of them — `Ctrl+T` and `Ctrl+P` — and
three plain keys that no terminal takes: `Tab`, `Shift+Tab` and `Esc`.

**A refusal is a refusal of the *binding*, not of the letter.**  The
operator may bind `Ctrl+Y`, or `Ctrl+G`, or `Ctrl+K` — anything that is
not on the list above.

## 9. When something does not work

| What the operator sees | What it means | What to do |
| :--- | :--- | :--- |
| `Ctrl+T` does nothing | the terminal took the chord, or the binding was changed | try the binding of the `\keys` screen; some terminals intercept `Ctrl+<letter>` themselves |
| the pane does not scroll | the command bar has the focus | press `Tab` until the pane is marked with `▶` |
| the notice is not on the screen | it is in the header, above the panes | look at the header |
| a binding did not change | the file is read at the start | restart the agent |
| a warning about a setting | the chord was refused | read the warning: it says which setting of which file, and why |

---

# Part 2 — The design and the implementation

## 10. What the operator asked for

> *scrolling of the "Workflow & Tool Progress"*
> *hide/show "Agent Telemetry & State"*
> *more will be added so the solution must be easy extended*

Three requirements, and the third one is the one that decides the shape of
the work: **the first hot-key must not cost the second one.**  A solution
that hard-codes "Ctrl+T hides the telemetry pane" into the key handler of
the application is a solution that has to be rewritten for the fourth
hot-key.

So the shape of the work is not "add two hot-keys".  It is **"add the
machinery a hot-key needs, and let the two hot-keys be the first two
entries of it"**.

### 10.1 The decision of the operator, on 2026-11-21

> *I think it must be separate from the help command*

The hot-keys are **not** a section of the `\help` screen.  They get their
own command — `\keys` — and their own table.

The separation is **structural**, not only visual:

| | |
| :--- | :--- |
| `components/command_registry.py` | describes the **commands** |
| `components/tui/hotkeys.py` | describes the **keys** |

`KEYBOARD_SHORTCUTS` and the `keyboard_shortcuts` flag **leave** the
command registry, and the "Keyboard Navigation" block **leaves** the
`\help` screen.  The `\help` screen is the list of the commands; `\keys`
is the list of every key of the TUI — the keys of the command bar and the
hot-keys of the panes, in one table, from one source.

### 10.2 The second decision of the operator, on 2026-11-21

> *please consider that some hot keys are used by OS so we need alternative,
> your choice also regarding focused window we need highlight selected window
> somehow*

Two things in it:

* **the keys the operating system takes are not ours to bind** — the
  kernel, the terminal and the desktop have their share of the keyboard,
  and a hot-key that one of them eats is not a hot-key (§8);
* **the selected pane must be visible** — and how it is shown is my
  choice (§3).

The choice of the keys is mine, and so are the choices of §16.1–§16.3.
Every one of them is written down, so any one of them can be reversed on
its own — and the ones that change what the operator sees (the order of
the task list) are one line of code each.

### 10.3 The third decision of the operator, on 2026-11-21

> *ok I think we can keep it as config under .config/torvalds key and user
> may redefine the default one, the agent must be able to create this config
> file on start-up if not exists*

**The bindings are configuration.**  They live in the file the operator
already has, the operator may replace any of them, and the agent writes
that file on start-up when it is not there.

The last two requirements are **already met** by `components/config.py` —
the file, the template, the start-up call and the "never overwrite" rule
are all in place since October 2026.  What is missing is the section, the
reading of it and the validation — §11.9.

## 11. The shape of the solution

Two layers, and one registry that both of them read.

```
     a key
        │
        ▼
  ┌───────────────────┐   the chords are global: they are live
  │  hotkeys.match()  │   whatever the operator is doing
  └─────────┬─────────┘
            │  the key is claimed
            ▼
  ┌───────────────────┐
  │  an action id     │   "toggle.telemetry", "scroll.progress.down", …
  └─────────┬─────────┘
            │
            ▼
  ┌───────────────────┐   TuiApp._apply_hot_key()
  │  the state changes│   → the state, the layout and the views
  └───────────────────┘

  the same table ──▶ hotkeys.keys_markdown() ──▶ the \keys screen
```

### 11.1 The registry — `components/tui/hotkeys.py` (new)

```python
@dataclass(frozen=True)
class HotKey:
    keys: str          # "CTRL_T", "TAB", "SHIFT_TAB", "ESCAPE", "PGUP"
    action: str        # "toggle.telemetry"
    description: str   # what the \keys screen says about it
    scope: str         # "global" | "pane"
```

The table is a tuple of these, and **it is the only place a binding is
written down**.  `match()` finds the binding of a key, and
`keys_markdown()` renders the table for the `\keys` screen.

**The table is the only list.**  `KEYBOARD_SHORTCUTS` in
`components/command_registry.py` is a hard-coded tuple today; it moves
into this registry, together with the new hot-keys.  The keys of the
command bar and the hot-keys of the panes are then **one table**, and
`\keys` renders all of it.  The `\help` screen keeps the commands and
nothing else — a key list that is a copy is a copy that goes stale.

### 11.2 The `\keys` command

`\keys` is a TUI-only command (`feature=FEATURE_TUI`), registered in the
command registry like every other command — so it is **named** in the
`\help` screen, as a command, with its description.  Its **content**
comes from the hot-key registry:

```
# Keys of the Torvalds TUI

## The command bar
- **Enter** — Submit the prompt, or confirm the answer of the agent
- **PgUp** / **PgDn** — Scroll the document pane
- **Up** / **Down** — Move in the input, or browse its history
- ...

## The hot-keys
- **Ctrl+T** — Show or hide the *Agent Telemetry & State* pane
- **Ctrl+P** — Show or hide the *Workflow & Tool Progress* pane
- **Tab** / **Shift+Tab** — Move the focus to the next / the previous pane
- **Esc** — Give the focus back to the command bar
```

The command is dispatched in `TuiApp._handle_enter_pressed()`, the way
`\stats` and `\tools` are: the document pane shows the screen.

**The footer points at it.**  The hints of the empty command bar carry
`\keys` — and the `PgUp/PgDn: Scroll` tail they carry today gives way
to it, because the place where the keys are listed is now a command of
its own:

```
[\stats | \tools | \projects | \chat-sessions | \keys | \help | \exit]
```

### 11.3 The set of bindings

**Every key of this table is free of the steal list of §8** — that is
the rule the table is built by, and the test in §14 checks it.

**Global** — live at all times, including while the operator types:

| Key | Action | What the operator sees |
| :--- | :--- | :--- |
| `Ctrl+T` | `toggle.telemetry` | the *Agent Telemetry & State* pane appears or disappears |
| `Ctrl+P` | `toggle.progress` | the *Workflow & Tool Progress* pane appears or disappears |
| `Tab` | `focus.next` | the focus moves to the next pane, and wraps around |
| `Shift+Tab` | `focus.previous` | the focus moves to the previous pane — **where the terminal delivers it**; the cycle wraps, so this key is a convenience and not a necessity |
| `Esc` | `focus.input` | the focus goes back to the command bar |

**Pane-scoped** — live only while a pane has the focus:

| Key | Action |
| :--- | :--- |
| `Up` / `Down` | scroll the focused pane by one line |
| `PgUp` / `PgDn` | scroll the focused pane by a page |
| `Home` / `End` | the top / the bottom of the focused pane |

**Why these and not others:**

* **`Ctrl+T` and `Ctrl+P`** are two chords from the letters that are
  left (§8), and they are mnemonics — *T*elemetry, *P*rogress.  The
  application already uses `Ctrl+C` and `Ctrl+D`, so the letters the
  operator's fingers already know are taken.
* **`Tab`** is the most discoverable key there is, and it costs nothing
  today: the reader names it `TAB`, the application drops it, and it is
  not a printable character, so it cannot eat what the operator types.
* **`Shift+Tab`** is a convenience: the legacy Windows console does not
  deliver it, so **the cycle wraps** and one key is enough.
* **`Esc`** is the key that closes a mode in every interface the operator
  knows.  (It is also the prefix of `Alt` in the terminal — so `Alt` is
  not a candidate for anything, §8.)
* **No `Alt` and no `Ctrl+S`/`Ctrl+Q`/`Ctrl+C`/`Ctrl+Z`** — the operating
  system has them.

### 11.4 The rule that makes it safe

> **A printable character always goes into the input, and it takes the
> focus back.**

The operator is never trapped in a pane.  He scrolls the progress pane,
he types a character, and he is at the command bar again — with the
character in the buffer.  This is the rule that makes a pane focus safe
in an application whose command bar is always on the screen.

The chords are global for the same reason: a chord carries no text, so it
cannot eat what the operator is writing.

### 11.5 The focus, and how the selected pane is shown

`focus ∈ {input, document, progress, telemetry}`.

* `input` is the default — **nothing changes for the operator who uses no
  hot-key at all**.  `PgUp`/`PgDn` still scroll the document, `Up`/`Down`
  still move the cursor and browse the history.
* `Tab` cycles the focus through the panes that are **visible** — a hidden
  pane is not in the cycle — and wraps around.
* `Esc` gives the focus back to the command bar.
* **A printable character gives the focus back too** (§11.4) — the
  operator is never trapped in a pane.

**The selected pane is shown, not guessed.**  Three marks, together:

1. **The border of the selected pane is bright**; the panes that are not
   selected keep the colour they have today:

   | pane | not selected | selected |
   | :--- | :--- | :--- |
   | *Markdown Document Viewer* | `blue` | `bright_blue` |
   | *Workflow & Tool Progress* | `cyan` | `bright_cyan` |
   | *Agent Telemetry & State* | `magenta` | `bright_magenta` |

   The **content** of a pane is never dimmed — a dimmed command is a
   command the operator cannot read.

2. **The title of the selected pane carries the marker `▶`**, in front of
   its icon.  The title is centred in the top border of the panel, as it
   is today:

   ```
   not selected:      ⚡ Workflow & Tool Progress
   selected:       ▶  ⚡ Workflow & Tool Progress
   ```

3. **The subtitle of the selected pane says where the operator is** — the
   scroll position, the way the document pane already says it:
   `▲ Line 6/21 │ ▼ 14 more (PgDn)`.

The command bar needs no mark of its own: the typing always goes there,
and the first printable character brings the focus back to it.

### 11.6 The scroll — `components/tui/pane_scroll.py` (new)

Each scrollable pane carries its own scroll state:

```python
@dataclass
class PaneScroll:
    offset: int = 0        # the first visible line
    total_lines: int = 0   # the lines the content has
    anchor: str = ""       # the id of the item at the top of the window
```

* **The content is rendered to lines and sliced** — the pattern
  `MarkdownView` already uses (`capture()` → `splitlines()` → slice →
  `Text.from_ansi()`).  The slice is `[offset : offset + height]`.
* **The height comes from the layout map of the last drawn frame** —
  `layout.map[layout["progress_pane"]].region.height`.  This is the same
  principle as `progress_pane_width()` in PR #106: *the number is the one
  the layout really uses*, not the one the source guesses.
* **The list is a log: the oldest first, the newest at the bottom, and
  the window stuck to the bottom.**  The pane lists the **newest** task
  first today, which makes "down" walk *into the past* — the opposite of
  every scrollable thing the operator knows.  As a log, `PgUp` goes back
  in the history and `PgDn` comes forward, and the running task is the
  last line on the screen, where the eye already is.  (§16.1 — this is a
  decision, and it is one line of code to reverse.)
* **The anchor keeps the operator where he is.**  A new tool task is
  inserted at the end of the log, and the window is stuck to the end —
  so the operator who has scrolled up keeps the task he is reading, and
  the operator who has not keeps the newest one.
* **The subtitle says where the operator is** — `▲ 6/21` and
  `▼ 14 more`, the pattern the document pane already uses.  The operator
  is never lost in a pane.

### 11.7 Hide / show

`Layout.visible = False` collapses a pane, and the space goes to its
sibling.  **Verified** with the real layout at 120×40:

```
before   progress_pane 42×17    telemetry_pane 42×17
after    progress_pane 42×34    telemetry_pane (not in the map)
```

So hiding the telemetry pane gives the whole sidebar to the progress pane
— with **no rebuild of the layout tree** and **no new ratios**.  The
visibility is applied from the state on every frame, so it is idempotent
and survives a resize.

### 11.8 The notification moves to the header

The notification is drawn in the telemetry pane (§11.10).  It moves to the
**header**, which grows by one line while a notice is up — the mechanism
`fit_footer()` already uses for the footer.  A notice is then visible
whatever the operator has hidden.

### 11.9 The configuration file — where the chords come from

The operator's decision, on 2026-11-21 (§10.3).

**The file already exists.**  `components/config.py` has been in the
project since the operator asked for it on 2026-10-29:

```
Linux and the BSDs   ~/.config/torvalds/config.toml
macOS                ~/Library/Application Support/torvalds/config.toml
Windows              %APPDATA%\torvalds\config.toml
```

* `$XDG_CONFIG_HOME` is honoured on **every** platform;
* `$TORVALDS_CONFIG` points at another file — for the tests, and for an
  operator who keeps the configuration of several machines in one place;
* the format is **TOML** — `tomllib` is in the standard library since
  Python 3.11, so it costs no dependency;
* the precedence is already the chain the hot-keys need:
  **flag > environment variable > the file > the default**;
* **a file that cannot be read is a warning, not a failed boot.**

And **both agents already create the file when it is not there**:
`config.ensure_default()` runs at the start-up of `agent-torvalds.py`
and of `agent-torvalds-mw.py`.  It writes the **template** — every line
of it is a comment, so the file changes nothing about the way the agent
runs — it creates the directory when it is missing, it writes the file
with the mode `0600`, and it **never overwrites** a file that is there.

**So two of the three requirements are met by the machinery that is
already in place.  What is missing is the section, and the reading of
it.**

#### The section

The section is written out in §6 — the same lines, with the same
descriptions.

**What the operator may do with it** is written out in §6 as well: the
default stands when the file says nothing, a value replaces the default
of that action and frees the old key, an empty value unbinds the action,
and a chord the operating system takes, a chord that does not parse and
a chord that two actions ask for are **refused**, with a warning, and
the default stands.

#### What is refused, and what happens then

Every value is checked by the hot-keys module, which owns the list of
the keys the operating system takes (§8):

* a chord that does not parse — *"Ctrl+"*, *"Space Bar"* — is **refused**;
* a chord the operating system takes is **refused** (§8);
* a chord that **two actions** ask for is **refused** for the second one.

**A refusal is a warning, never a crash.**  The TUI starts, the default
stands, and the operator is told which setting of which file was refused
and why.  It is the rule the rest of the configuration file already
follows: *a broken file is a warning, not a failed boot*.

#### Where the settings live

| what | where |
| :--- | :--- |
| the **settings** — the key names, the defaults, the descriptions | `components/config.py`, in `SETTINGS` |
| the **actions** — what a chord does, its scope, the matcher | `components/tui/hotkeys.py` |
| the **file** | `~/.config/torvalds/config.toml` |

The two lists must agree — one setting for one action — and **a test
holds them together**: a setting without an action is a key the operator
can set and that does nothing, and an action without a setting is a
hot-key the operator cannot change.

The settings live in `components/config.py` because that is where the
**schema of the file** lives, and because **both agents read the file**:
a `[hotkeys]` section that the classic agent did not know would be
reported by it as *"the section [hotkeys] is not known to the agent"* at
every start-up.

#### Two findings of the prototype

The mechanism was tried against the real `Config` before it was written
down.  It works — the file is created when it is absent, the value of
the file beats the default, an empty value unbinds the action, a typo is
reported and the default stands.  Two things came out of it:

**1. The template is built from the module constant, not from the
instance.**  `Config.default_template()` iterates `SETTINGS` — the
module-level tuple — and not `self.settings`.  A `Config` that was given
its own settings therefore writes a template that **does not match
them**, and the `[hotkeys]` section would be missing from the file the
agent creates.

> *Fix:* `default_template()` iterates `self.settings.values()`.  It is
> one line, and the output is identical for the default case — the
> dictionary keeps the order of the tuple.

**2. The settings that read the file and the settings that write the
template must be the same list.**  The prototype read the file with the
three hot-key settings alone, and the agent then reported **the sections
it had written itself** as *"not known to the agent"*:

```
the section [llm] of /tmp/…/config.toml is not known to the agent — it is ignored
```

The hot-key settings therefore join the **module-level `SETTINGS`** and
not a list passed to one instance: both agents read and write the same
schema, and neither of them complains about the other.

#### The file that is already there is not touched

`ensure_default()` writes the template only when the file is **absent**.
The file of an operator who already has one — and every operator of this
project has one since October 2026 — is **never** rewritten: their
comments, their order and their settings are worth more than a fresh copy
of the defaults.

So the `[hotkeys]` section is added **by hand**.  To make that easy, the
`\keys` screen shows **the lines to copy**, with the chords the operator
has today.

#### The TUI says it

The classic agent tells the operator when the template was created
(*"The configuration template was created at …"*).  **The TUI creates the
file silently today** — the message would be lost in the screen the TUI
takes over.  The TUI shows it in the **notification** instead (§11.8).

## 12. What is there today

### 12.1 The command bar owns every printable character

`_handle_key()` in `components/tui/tui_app.py` is one flat chain of
`if key == "..."` — the key is compared with a name, and the name is
acted upon.  There is no table, no registry, and no priority: **every
printable character belongs to the input**, and the input is the only
thing that can be typed into.

### 12.2 The navigation keys are already spoken for

| Key | What it does today |
| :--- | :--- |
| `PgUp` / `PgDn` | scroll the **document** pane |
| `Up` / `Down` | move the cursor in the input; browse its history |
| `Left` / `Right` / `Home` / `End` | move the cursor in the input |
| `Enter` | submit |
| `Ctrl+C` / `Ctrl+D` | cancel the input, or exit |

**Every plain navigation key is taken.**  A hot-key that uses one of them
takes it away from the operator — and the operator who is typing a command
must never lose a key.

### 12.3 The finding that decides the shape of the work

**There is no key that can carry a hot-key today.**  Not because the
terminal cannot send one, but because **the reader does not name one**:

| What the operator presses | What arrives | What the reader says |
| :--- | :--- | :--- |
| `Ctrl+A` … `Ctrl+Z` | the raw control byte `0x01`…`0x1A` | *nothing* — the byte is dropped in `_handle_key` (it is not printable) |
| `Ctrl+Up` | `ESC [ 1 ; 5 A` | `"UP"` — **the modifier is thrown away** in `_decode_csi` |
| `F1` … `F12` | `ESC [ 11 ~` … | `"ESCAPE"` — **wrong** |
| `Alt+A` | `ESC a` | `"ESCAPE"` — **the character is lost** |

The reader only ever names the *unmodified* keys
(`components/tui/input_reader.py`, module docstring):

```
ENTER, BACKSPACE, DELETE, TAB, ESCAPE,
UP, DOWN, LEFT, RIGHT, PGUP, PGDN, HOME, END,
CTRL_C, CTRL_D
```

(Two more the reader already names and the application never uses:
`SHIFT_TAB` and `CTRL_ENTER`.  `Shift+Tab` is therefore **free** — it
needs no change in the reader.)

`_decode_csi()` looks at the **final byte only** — the modifier part of
`ESC [ 1 ; 5 A` is parsed into `params` and then thrown away, so
`Ctrl+Up` is *indistinguishable* from `Up`.

**So step one is the reader: it must learn to name the modified keys.**
Without that there is nothing to bind, and every proposal that skips it
ends up taking a key away from the operator's typing.

### 12.4 The four Ctrl letters that do not exist

A terminal does not send these as `Ctrl+<letter>` — they are the control
codes themselves, and the reader has already claimed them:

| Chord | What the terminal really sends | Already claimed as |
| :--- | :--- | :--- |
| `Ctrl+H` | `0x08` | `BACKSPACE` |
| `Ctrl+I` | `0x09` | `TAB` |
| `Ctrl+J` | `0x0A` | `ENTER` |
| `Ctrl+M` | `0x0D` | `ENTER` |

The list of the letters that are really available is in §8 — it is
shorter than it looks, because the kernel and the terminal take their
share.

### 12.5 The pane that is asked about overflows, and the overflow is invisible

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
 8 | │  ✔ list_directory (0ms)                │
 9 | │  ✔ execute_shell_command (0ms)         │
10 | │    └ grep -rn 'scroll_offset'          │
11 | │      components/ | head -50            │
12 | │  ✔ execute_shell_command (0ms)         │
13 | │    └ docker compose up -d --build      │
14 | │      postgres redis                    │
   ── the pane ends here ──
15 | │  ✔ read_file (0ms)                     │   ← cut off
16 | │    └ ~/projects/          │   ← cut off
17 | │      agent-torvalds/components/tui/    │   ← cut off
18 | │      progress_view.py                  │   ← cut off
19 | │  ✔ execute_shell_command (0ms)         │   ← cut off
20 | │    └ git status --short && python -m   │   ← cut off
21 | │      pytest tests/ -x --tb=short       │   ← cut off
```

**Six lines of content are cut off** — and they are the lines of the
*oldest* task, because the pane lists the newest task first.  The command
`git status --short && python -m pytest tests/ -x --tb=short` ran, and
**there is no way to see it.**  PR #106 made the command whole when it is
shown; this is the other half of that work: the command must also be
*reachable*.

### 12.6 The keys the operating system takes

The operator is right: **a hot-key that the terminal or the desktop
eats is not a hot-key.**  The full list is in §8 — the reader puts the
terminal into cbreak mode, and cbreak is *not* raw mode.

**A finding worth a line of its own:** the reader maps 0x03 to
`"CTRL_C"`, and the application has a branch for it — *cancel the
input, or exit when the buffer is empty*.  **On POSIX that branch never
runs**, because the kernel raises SIGINT before the byte is read: `Ctrl+C`
ends the TUI instead of clearing the bar.  The behaviour is not changed
by this feature; it is recorded here.

### 12.7 The notification lives in the pane that is asked to hide

`TelemetryView.render()` draws the notification banner as the last row of
its table (`components/tui/telemetry_view.py`).  Hiding the telemetry
pane would therefore **silence every message the TUI gives the operator**
— including the message that says the pane is hidden.

## 13. The files

**New**

| File | What it holds |
| :--- | :--- |
| `components/tui/hotkeys.py` | the table, `match()`, `keys_markdown()` |
| `components/tui/pane_scroll.py` | `PaneScroll` — the offset, the anchor, the clamping |
| `tests/test_tui_hotkeys.py` | the matcher, the routing, the priority over the input |
| `tests/test_tui_pane_scroll.py` | the offset, the anchor, the clamping, the hidden pane |

**Changed**

| File | What changes |
| :--- | :--- |
| `components/tui/input_reader.py` | name the modified keys: `CTRL_A`…`CTRL_Z`, `F1`…`F12`, the modifiers of the arrows, `ALT_<letter>` |
| `components/tui/state_bridge.py` | the focus, the hidden panes, the scroll of each pane |
| `components/tui/tui_app.py` | the routing, the actions, the visibility, the focus border |
| `components/tui/progress_view.py` | the content is rendered to lines and sliced |
| `components/tui/telemetry_view.py` | the same; the notification leaves for the header |
| `components/tui/layout_manager.py` | the header carries the notice |
| `components/command_registry.py` | the `\keys` command is registered; `KEYBOARD_SHORTCUTS` and the `keyboard_shortcuts` flag **leave** the registry — the keys belong to `hotkeys.py` |
| `components/config.py` | the `[hotkeys]` settings join `SETTINGS` — the key names, the defaults, the descriptions (§11.9) |
| `agent-torvalds.py`, `agent-torvalds-mw.py` | the `keyboard_shortcuts` flag leaves the calls of the help screen — the keys are not in it |

The TUI **says** that the configuration file was created (§11.9): the
application reads `config.created` and shows it in the header, so the
message is not lost in the screen the TUI takes over.

## 14. How a new hot-key is added

The whole point of the registry: **a new hot-key is a row and a method.**

```python
# 1. the row — components/tui/hotkeys.py
HotKey(
    keys="CTRL_S",
    action="toggle.sidebar",
    description="Show or hide the whole sidebar",
    scope=SCOPE_GLOBAL,
),

# 2. the method — components/tui/tui_app.py
def _hotkey_toggle_sidebar(self) -> None:
    self.state.hidden_panes.symmetric_difference_update({"progress_pane", "telemetry_pane"})
```

The `\keys` screen, the footer hints and the tests of the registry pick it
up by themselves.  **No other file changes.**

## 15. The tests

* `tests/test_tui_hotkeys.py`
  * **the settings of the file and the actions of the registry agree** —
    one for one, and a setting without an action is a failure (§11.9);
  * **an empty value unbinds** the action, and the key is free again;
  * **a chord the operating system takes is refused** (§8), and the
    default stands;
  * **two actions that ask for the same chord** — the second one is
    refused;
  * **a value that cannot be parsed** — the default stands and the TUI
    still starts;
  * the value of the file wins over the default;
  * **the template carries the `[hotkeys]` section**, commented out, and
    the file the agent creates is the file it can read back — the
    sections of the template are never reported as unknown (§11.9);
  * **no binding of the table uses a chord the terminal takes** — the
    list of §8 (`Ctrl+C`, `Ctrl+S`, `Ctrl+Q`, `Ctrl+Z`, `Ctrl+H`,
    `Ctrl+I`, `Ctrl+J`, `Ctrl+M`, `Alt+…`) is refused by the test, so a
    hot-key that the operating system would eat can never be added;
  * a chord that is not bound goes to the input untouched;
  * a printable character always goes to the input, and it takes the focus
    back;
  * a chord is live while the operator is typing;
  * a pane key is live only while its pane has the focus;
  * the pager keys scroll the document when the focus is on the input
    (today's behaviour, unchanged);
  * `hitl_active` and the session picker: only the global chords are live,
    the answer of the operator keeps every other key;
  * a paste is never taken by a hot-key;
  * the table of the registry has no duplicate keys;
  * the `\keys` screen names every binding of the table, and only those;
  * the `\help` screen names **no** binding — the keys are not in it.
* `tests/test_tui_pane_scroll.py`
  * the offset is clamped to the content;
  * the anchor keeps the window on the same task when a new task arrives;
  * the hidden pane leaves the map, and the sibling takes the space;
  * the focused pane is drawn with the brighter border and the `▶`
    marker, and the panes that are not selected are not;
* `tests/test_tui_input_reader.py` (extended)
  * `Ctrl+A` is `CTRL_A`; `Ctrl+H` is still `BACKSPACE`;
  * `Ctrl+Up` is not `UP`; `F5` is `F5`; `Alt+a` is `ALT_a`.
* `tests/test_help_command.py` (changed)
  * the `\help` screen carries the **commands only** — the "Keyboard
    Navigation" block is gone, and the test that asserted its presence is
    rewritten to assert its **absence**, so that nobody puts it back by
    accident;
  * the `\keys` command is listed in the `\help` screen of the TUI, and
    it is not listed in the classic console.

**The gate must not move**: `tests/ci_baseline.txt` lists the known
failures — 40 node ids, the number the changelog carries.  The feature
adds **0 new** failures and fixes **0**.

## 16. The decisions

**16.1 The direction of the scroll in the progress pane.**  *Decided: the
list becomes a log.*  The oldest task first, the newest at the bottom, the
window stuck to the bottom.  The pane lists the newest task first today,
which makes "down" walk *into the past* — a hot-key that scrolls the
"wrong way" is a hot-key the operator has to learn twice.  As a log,
`PgUp` goes back in the history, `PgDn` comes forward, and the running
task is the last line on the screen.

*To reverse it:* one line — the order of the task list in
`progress_view.py` — and the window is stuck to the top instead of the
bottom.

**16.2 The keys of the focus.**  *Decided: `Tab` and `Shift+Tab`, with the
cycle wrapping around.*  `Tab` is the most discoverable key there is, it
costs nothing today (the reader names it, the application drops it), and
it is not a printable character — it cannot eat what the operator types.
`Shift+Tab` is a convenience where the terminal delivers it; the wrap
around means one key is enough.  The readline pair (`Ctrl+N`/`Ctrl+P`) was
rejected: `Ctrl+P` is wanted for *P*rogress, and the history is already on
`Up`/`Down`.

**16.3 The document pane in the focus cycle.**  *Decided: it is in the
cycle.*  It has its own scroll today (`PgUp`/`PgDn`), and a pane that can
be scrolled but cannot be selected is a pane the operator cannot reach
with the keys.  The cycle is *input → document → progress → telemetry →
input*, skipping the panes that are hidden.

**16.4 Where the hot-keys are advertised.**  *Resolved on 2026-11-21* — the
hot-keys are **not** in the `\help` screen.  They have their own command,
`\keys` (§10.1, §11.2), and the hints of the empty command bar point at it.

**16.5 Which keys may be bound at all.**  *Decided: the ones the operating
system does not take* (§8).  The safe letters are
`A B E F G K L N O P R T U V X Y`, and the set of §11.3 uses two of them
plus three plain keys.  The test in §15 refuses any binding that the
terminal, the kernel or the desktop would eat.

**16.6 How the selected pane is shown.**  *Decided: the bright border, the
`▶` marker in the title, and the scroll position in the subtitle*
(§11.5).  The content of a pane is never dimmed.

**16.7 Where the bindings live.**  *Decided: in the file the operator
already has* — `~/.config/torvalds/config.toml`, a new `[hotkeys]`
section (§11.9).  The alternative — a second file, `hotkeys.toml` beside
it — would have been one file more to explain, and the settings of the
agent belong in one place.  The start-up call that creates the file is
already there in both agents; the TUI only has to start **saying** it.

**16.8 What the operator may change.**  *Decided: one action at a time, and
the old key is freed.*  A value replaces the default of that action; an
empty value unbinds it; a chord the operating system takes, a chord that
does not parse and a chord that two actions ask for are **refused**, with
a warning, and the default stands.  A refusal never stops the TUI.

## 17. The plan of the work

1. **The reader names the modified keys** (`input_reader.py` + tests).
   Nothing else can start before this.
2. **The registry** (`hotkeys.py` + tests) — the table, the matcher, the
   help.  No behaviour changes yet.
3. **The settings of the file** (`config.py` + tests) — the `[hotkeys]`
   section, the reading of it, the validation, and the lines to copy that
   the `\keys` screen shows.  The chords are read from the file; the
   defaults are the ones of §11.3.  It includes the two findings of
   §11.9: `default_template()` must walk the settings of the instance,
   and the section joins the module-level `SETTINGS`.
4. **The focus and the state** (`state_bridge.py`) — the focus, the
   hidden panes, the scroll.
5. **The scroll of the progress pane** (`pane_scroll.py`,
   `progress_view.py`, `tui_app.py` + tests) — the first hot-key that is
   really asked for.
6. **The hide/show** (`tui_app.py`, `layout_manager.py` + tests) — and
   the notification moves to the header with it.
7. **The `\keys` command** (`command_registry.py`, `tui_app.py`) — the
   registry rendered into its own screen, and the `\help` screen left
   with the commands only.
8. The changelog, the readme, and the gate.

Each step is a commit of its own, and each one leaves the TUI working.
