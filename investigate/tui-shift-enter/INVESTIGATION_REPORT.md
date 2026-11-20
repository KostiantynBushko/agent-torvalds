# The Shift+Enter of the TUI — the line break the operator adds

**Status:** implemented, covered by tests that fail without it.
**Reported by:** the operator, on 2026-11-20 — the item that was left open with the change of the
wrapping of the text of the bar, and closed on the same day: *"ok close the item 2"*.

**Probe:** [`probe_shift_enter.py`](probe_shift_enter.py) — read-only.  It types the bytes of the
Shift+Enter into a real pseudo-terminal and asks the reader what it saw, renders the real bar at the
width of a real terminal, and asks the application what the agent was given.  It writes nothing and
talks to no service.

---

## 1. The item

The change of 2026-11-20 — the text of the command bar moves to the next line — left two things
open, and both were written down in
[`investigate/tui-input-wrapping/INVESTIGATION_REPORT.md`](../tui-input-wrapping/INVESTIGATION_REPORT.md):

* **the Shift+Enter of a terminal that sends another sequence.**  The reader knew the Shift+Enter of
  xterm (`ESC [ 13 ; 2 ~`) and of the kitty keyboard protocol (`ESC [ 27 ; 2 ; 13 ~`), and reported
  every other sequence as an escape — which the application drops silently;
* **the trailing line break of a Shift+Enter was eaten when the bar was submitted.**
  `_handle_enter_pressed()` took `input_buffer.strip()`, and the strip took the line break the
  operator had added at the end of the text — and the indentation of a pasted block with it.

## 2. What the reader was before the change

The reader matched the **exact string** of the parameters of a control sequence against a table:

```python
_CSI_TILDE_KEYS = {
    ...
    "13;2": "SHIFT_ENTER",
    "27;2;13": "SHIFT_ENTER",
}
```

A table of exact strings knows only the forms that were written down when it was made.  The
terminals do not agree on one form: the key is 13 and the modifier is 2 in all of them, but the
order, the form and the number of the parameters are not the same.

| the sequence | the terminal | before | after |
| :--- | :--- | :--- | :--- |
| `ESC [ 13 ; 2 ~` | xterm | `SHIFT_ENTER` | `SHIFT_ENTER` |
| `ESC [ 27 ; 2 ; 13 ~` | the kitty keyboard protocol | `SHIFT_ENTER` | `SHIFT_ENTER` |
| `ESC [ 13 ; 2 u` | the CSI u form | `SHIFT_ENTER` | `SHIFT_ENTER` |
| `ESC [ 2 ; 13 ~` | the parameters in the other order | **`ESCAPE`** | `SHIFT_ENTER` |
| `ESC [ 13 ; 2 ; 3 ~` | a terminal that adds a parameter | **`ESCAPE`** | `SHIFT_ENTER` |
| `ESC [ 13 ; 5 u` | Ctrl+Enter | `CTRL_ENTER` | `CTRL_ENTER` |

The two rows in bold are the defect: the sequence was read by the reader, and thrown away as an
escape.  The operator typed Shift+Enter and nothing happened.

## 3. What was changed

### 3.1 The parameters are read, not matched as a string

`components/tui/input_reader.py` — `_is_shift_enter(params)`:

> The key is 13 and the modifier is 2 in every form — but the order the two are written in is not
> the same, and a table of exact strings knows only the forms that were written down when it was
> made.

The parameters are split on the `;`, the numbers are read, and the sequence is a Shift+Enter when
it names the key 13 **and** the modifier 2 — in any order, with any number of parameters.  The
exact-string tables keep the keys they know; the Shift+Enter is decided before they are consulted,
so the Ctrl+Enter (`ESC [ 13 ; 5 u`) is still the Ctrl+Enter.

### 3.2 The text the agent gets is the text the operator wrote

`components/tui/tui_app.py` — `_handle_enter_pressed()`:

* `text` — the text of the bar without the **trailing line breaks**.  The line break that the last
  Shift+Enter left is the empty last line of the bar, and it is not a part of the message.  The
  line breaks *inside* the text, and the indentation of a pasted block, are.
* `cmd` — `text.strip()`.  The command that is *matched* is the text without the spaces around it:
  `\exit ` is the `\exit` command, and a text of spaces is not a command at all.

The agent is given `text`, and the history holds `text` — so a pasted block comes back whole when
the operator walks the cursor up to it.

## 4. How it is verified

`tests/test_tui_multiline_input.py` — 50 tests, 8 of them new:

| the test | what it holds |
| :--- | :--- |
| the reader reports the CSI u form of Shift+Enter | the sequence of the form the reader knew |
| the reader reports Shift+Enter in any order | the parameters are read, not matched as a string |
| the reader reports Shift+Enter with a parameter more | a terminal that adds a parameter of its own |
| the Ctrl+Enter is still the Ctrl+Enter | the generalization did not take the other modifiers |
| the indentation of a pasted block reaches the agent | the text is not stripped on its way |
| the line break of a Shift+Enter is not a part of the message | the empty last line of the bar is not a part of the text |
| the line breaks inside the text are kept | only the last line break is the empty last line |
| a command with spaces around it is still matched | `\exit ` is the `\exit` command |

Three of them fail without the change — the reader of the other order, the reader of the extra
parameter, and the indentation of the pasted block.

The probe runs the same checks and prints what it sees:

```
$ python investigate/tui-shift-enter/probe_shift_enter.py
the Shift+Enter of the terminals
   xterm                            b'\x1b[13;2~'      -> ['SHIFT_ENTER']
   the kitty keyboard protocol      b'\x1b[27;2;13~'   -> ['SHIFT_ENTER']
   the CSI u form                   b'\x1b[13;2u'      -> ['SHIFT_ENTER']
   the parameters in the other order b'\x1b[2;13~'      -> ['SHIFT_ENTER']
   a parameter more                 b'\x1b[13;2;3~'    -> ['SHIFT_ENTER']

the bar with two lines
   │ >>> first                                                                                        │
   │     second                                                                       [Enter to send] │

the text the agent gets
   '    def f():\n        return 1'

everything holds: every terminal is known, the bar shows the line the operator added, and the agent gets the text as it was written
```

The gate of the repository stays green: 40 known failures, 0 new, 0 fixed.

## 5. What is not in this change

- **A terminal that sends the same bytes for Shift+Enter and for Enter.**  There is nothing the
  reader can do with that: the two keys arrive the same way, and the terminal has to be told to
  send a sequence of its own.  In the kitty terminal that is a line of its configuration
  (`map Shift+Enter send_csiu 13;2u`); in xterm it is `setkey Shift-Enter \e[13;2u` in the file of
  the resources.  The reader now knows every form that is sent — but it cannot invent one.
- **The answer of the agent-question mode is still stripped.**  The answer to a question is a word
  or a line, and the "yes" of an answer is compared as a word; the answer is not a code block.
- **The plain Enter of the CSI u form (`ESC [ 13 u`) is still unknown.**  The TUI does not ask the
  terminal for the kitty keyboard protocol, so the plain Enter arrives as the carriage return it
  always was.
- **The line break at the end of the text is still dropped.**  The operator cannot tell a line break
  that ends the message from one that ends the last line of the bar, and the last one is dropped.
