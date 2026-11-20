# The input bar of the TUI — one line, or three

**Status:** implemented, covered by tests that fail without it.
**Reported by:** the operator, on 2026-11-20 — a description of a multi-line input for
the command bar of the multi-window console.

**Probe:** [`probe_multiline_input.py`](probe_multiline_input.py) — read-only.  It
renders the real layout, drives the real reader from a pseudo-terminal, and puts the
keys it reports into the real application.  It writes nothing and talks to no service.

---

## 1. The request

The operator asked for four things in the command bar of the TUI:

1. the helper (hot) commands on the right go away while there is text in the bar, and
   they come back when the text is gone;
2. Shift+Enter adds a line to the input, and the view of the input grows with it — up
   to three lines.  **The operator withdrew this one on 2026-11-20: the bar carries
   no Shift+Enter at all**, and the lines of the input come from a paste;
3. a paste arrives in one piece; a paste that is longer than three lines shows its last
   lines, and the operator can walk the cursor into the text and edit it;
4. deleting the last character brings the helper commands back.

The helper commands are the ones the bar carries on its right:

```
[\stats | \tools | \projects | \chat-sessions | \help | \exit | PgUp/PgDn:
```

## 2. What the bar was before the change

The command bar was one line of text, and the reader was a reader of keystrokes:

* `components/tui/layout_manager.py` rendered the input as a single line — the text
  before the cursor, the cursor, the text after it — and put the helper commands in the
  right column of the same row.  There was no room for a second line: the footer
  partition is three lines tall (a border, one line of content, a border), and a panel
  that is taller than its partition is cropped from the bottom.
* `components/tui/input_reader.py` read the terminal one character at a time.  The
  escape sequences it knew were the cursor keys and the editing keys; Shift+Enter was
  not among them, and a terminal that sends it was read as a bare `ESCAPE` plus the
  rest of the sequence as ordinary characters.
* A paste was not a paste.  The terminal was never asked to mark the pastes, so a
  pasted text arrived as the text itself: **every newline in it was an ENTER**, and the
  command bar submitted the first line of what the operator pasted.  The rest of the
  paste was then read as a command of its own.

The last one is the defect that made the other three impossible: as long as a newline
in the input means "submit", there is no way to type a question that has more than one
line.

## 3. What was changed

### 3.1 The terminal is asked to mark the pastes

`components/tui/input_reader.py` writes `ESC [ ? 2004 h` to the terminal when it
starts, and gives the mode back (`ESC [ ? 2004 l`) when it stops — the mode belongs to
the terminal, and the next program that runs in it has to find it as it was.

With the mode on, a paste arrives between two markers: `ESC [ 200 ~` and
`ESC [ 201 ~`.  The reader collects the text between them and hands it over **in one
piece**, as a `PastedText` — a string of its own kind, so the caller can tell a paste
from a key that was typed.  A paste that is longer than the buffer of the reader
arrives in pieces; the reader keeps what it has until the closing marker arrives, and
a paste that never closes is given up on after two idle seconds — otherwise it would
swallow everything the operator types after it.

The control characters of a paste are dropped: the terminal acts on them, and a pasted
text is not allowed to move the cursor of the TUI or to change the state of the
terminal.

### 3.2 The reader reads a control sequence as a whole

The reader reads a control sequence as a whole — the parameter bytes, the
intermediate bytes and the final byte — instead of guessing at them.  The keys that
were known before are known still, and a sequence that carries no key the reader
knows is an escape, which the application drops.

**The Shift+Enter is not among the keys.**  The operator asked for it on 2026-11-20
and withdrew the request the same day: the bar carries no line-break key, and the
lines of the input come from a paste.  The sequence a terminal sends for the
Shift+Enter is an escape to the reader, and the bar does not change by a key nobody
can see.

### 3.3 The input is a text, and the view is a window over it

`components/tui/input_text.py` is new, and it is the one place that knows how the text
of the bar is *seen*:

* the buffer is flat — a string with newlines in it;
* the view shows at most three lines.  When the text holds more lines than that, the
  view is a window over the text: it follows the cursor, and the cursor is kept at the
  bottom of the window.

That single rule gives the three behaviours the operator asked for:

* **The lines of the input extend the view.**  One line of text is one line of the
  bar; a second line makes the bar two lines tall; a third makes it three.  A fourth
  line does not make the bar taller — the window scrolls, and the cursor stays
  visible.  The lines come from a paste: there is no line-break key.
* **A long paste shows its last lines.**  The cursor is at the end of a pasted text,
  and the window follows the cursor to the end of it.
* **The text can be edited.**  The window is a window: the text above it is still in
  the buffer, the cursor walks into it (Up and Down walk the lines of the input, and
  reach the history at the first and the last line), and the text is edited there.

The footer partition grows with the bar: `fit_footer()` takes the number of lines the
input shows and gives the partition that many lines more than it had.

### 3.4 The helper commands go away while there is text

`render_footer()` puts the helper commands in the right column of the bar while the
bar is empty.  As soon as there is text in it, the column is not drawn at all and the
input takes the whole width of the bar — the width belongs to what the operator is
writing.  The commands come back when the last character is deleted, because the bar
is empty again.

## 4. How it is verified

`tests/test_tui_multiline_input.py` — 34 tests, in five groups:

| group | what it holds |
| :--- | :--- |
| the hot commands | they are shown on an empty bar, hidden while there is text, and back after the last character is deleted |
| the Shift+Enter | there is no line-break key: the sequence is an escape, and the bar does not change by it |
| the view of the input | it grows with the lines, it never shows more than three, and the text above the window is not thrown away |
| the paste | it arrives in one piece, it is put into the bar, a long one shows its last lines, and the text can be edited |
| the cursor | it walks the lines of the input, and the history is still there for the input of one line |

The reader is driven from a pseudo-terminal, the way the terminal drives it: the
sequences are written into a pty and the keys the reader reports are collected from
the other end.

The probe runs the same checks and prints what it sees:

```
$ python investigate/tui-multiline-input/probe_multiline_input.py
the hot commands of the bar
   with an empty bar   : shown
   with text in the bar : hidden
   after the last character is deleted : shown

the Shift+Enter
   the reader reports : ['ESCAPE']
   the input holds     : 'ab'
   the bar shows       :
     ╭──────────────────────────────────────────────────────────────────────────────────╮
     │ >>> ab                                                                       │
     ╰──────────────────────────────────────────────────────────────────────────────────╯

the paste
   the paste arrives in 1 piece(s)
   the terminal is asked to mark the pastes : yes
   the terminal is given back              : yes
   the bar shows       :
     ╭──────────────────────────────────────────────────────────────────────────────────╮
     │ >>> line 8                                                                   │
     │     line 9                                                                   │
     │     line 10                                                                  │
     ╰──────────────────────────────────────────────────────────────────────────────────╯
   the window holds    : ['line 8', 'line 9', 'line 10']
   the cursor is on the last line : True
   the cursor walked back to the line 7
   the text above the window can be edited : True

everything holds: the bar takes three lines, and the hot commands come and go with the text
```

The gate of the repository stays green:

```
known failures in the baseline : 40
failures in this run            : 40
new failures                    : 0
fixed since the baseline        : 0
```

## 5. What is not in this change

- **The classic console does not take three lines.**  The REPL of
  `components/console_input_module.py` reads with `input()`, and the multi-line input
  is a property of the TUI, whose bar draws the text itself.  The helper commands are
  in the TUI footer as well, so there was nothing to hide there.
- **The paste mode is asked for on POSIX.**  On Windows the mode is a property of the
  console, and writing it needs the console handle of the output.  The reader detects
  the markers of a paste there — but it does not ask for the mode, and a paste on
  Windows arrives as plain text.
- **The horizontal scroll of a long line is not there.**  A line of the input that is
  wider than the bar is cut at the edge of the screen, as it was before.
- **The window of the input has no scroll of its own.**  It follows the cursor, and
  the cursor is the only way through the text — PgUp and PgDn still scroll the
  document pane.
