# Implementation report — the TUI asks which chat session to work in

**Date**: 2026-11-13
**Branch**: `fix/tui-rendering` (merges into `fix/tui-terminal-size`)
**Status**: implemented, verified — **not committed** (Rule 2: awaiting the
operator's approval)
**Companion to**: `investigation_tui_session_selection.md`,
`PROPOSAL_tui_session_selection.md`, `probe_session_selection.py`

---

## 1. What was implemented

Both defects of the investigation are closed, in the form the operator
approved on 2026-11-13 (*"ok go ahead with your preferred choice"*).

| # | Defect | How it is closed |
|---|---|---|
| **D1** | the TUI never proposed the startup choice — one condition skipped it | `agent-torvalds-mw.py` — the condition `and not use_tui` is dropped; the menu runs before the layout takes the screen |
| **D2** | inside the TUI a session could only be chosen by a 36-character id | `\chat-select` without an argument opens a numbered picker; `\chat-select <number>` switches to that session |

---

## 2. D1 — the startup menu in the TUI

### 2.1 The change

One condition, in `agent-torvalds-mw.py`:

```python
# before
if not args.no_session_select and not use_tui:

# after
if not args.no_session_select:
```

Nothing else moves.  The menu is the **same menu** the classic
orchestrator shows — `chat_manager.session_selector`, which was already
covered by `chat_manager/tests/test_session_selector.py`.

### 2.2 Why the terminal is free at that point

| line | what happens |
| :--- | :--- |
| 1656 | the session menu runs here |
| 1669 | `if not use_tui:` → the classic REPL |
| 1802 | `await app.run()` → the `Live` display takes the alternate screen |

At line 1656 the `Live` display has not started, the alternate screen
has not been entered, and the non-blocking input reader of the TUI is
not reading.  The terminal is an ordinary console.

The **same file** already blocks on `input()` in front of the TUI — the
`--select` tool picker runs in both modes with no guard at all.

### 2.3 What the operator sees

```
$ python agent-torvalds-mw.py

Initializing chat history manager...
Chat session: agent-torvald-project-002 (custom)
Session selection:
Active session: 'agent-torvald-project-002'
Available sessions:
    1. objective-control-001  (created 2026-11-09 10:40)
    2. agent-torvald-ollama-internal-server-error-500  (created 2026-11-09 08:03)
    ...
  * 4. agent-torvald-project-002  (created 2026-11-08 12:15)
    ...
  * = currently active
Select a session [1-27], 'new <name>' to create one, or Enter to keep the current one:
> 4
Active chat session: agent-torvald-project-002
```

Pressing Enter keeps the session that was active — the behaviour of
today, for the operator who does not want to choose.

The picked session is the one the agent binds to: the memory buffer is
built from the `chat_key` of the active session *after* the menu
(`create_agent` → `get_memory_buffer`), and `switch_session()` drops the
cached buffer, so the history of the picked session is the history the
model sees.

---

## 3. D2 — a numbered picker inside the TUI

### 3.1 The numbering

`manager.list_sessions()` returns the sessions of the user ordered by
`created_at` descending, and the classic startup menu already numbers
them in that order.  **The same order is used everywhere**, so the
number the operator sees in one list is the number in every other list:

| where | what it shows |
| :--- | :--- |
| the startup menu | `1.`, `2.`, … `* 4.` — the active one is marked |
| `\chat-sessions` | a `#` column |
| the picker of `\chat-select` | a `#` column, and `★` on the active one |
| `\chat-select <number>` | the session at that position |

### 3.2 The picker

`\chat-select` without an argument opens the picker in the document
pane — the same place `\tools` puts its menu, and the same way it asks
for the answer:

```
# 💬 Select a Chat Session

**Sessions:** 27  •  the active one is marked ★

| # | Session | Type | Created |
| ---: | :--- | :--- | :--- |
| 1 | objective-control-001 | custom | 2026-11-09 10:40 |
| 2 | agent-torvald-ollama-internal-server-error-500 | custom | 2026-11-09 08:03 |
| ... |
| 4 | ★ agent-torvald-project-002 | custom | 2026-11-08 12:15 |
| ... |

**How to select:**
- Type `\chat-select <number>` in the command bar and press Enter.
- `\chat-select <session_id>` also works — the id is in `\chat-sessions`.
```

A notification in the status bar tells the operator where the answer
goes: *"Type `\chat-select <number>` in the command bar and press
Enter."*

The picker is **compact on purpose**: it leaves the id out.  A row of
`\chat-sessions` is 121 characters long in a document pane that is 74
characters wide — the id is folded in the middle of it, and it is
exactly that id that had to be copied by hand.  A *name* may still wrap
(the longest name of the operator's database makes a row of 82
characters); a name stays readable when it wraps.

### 3.3 The resolution

The reference is resolved **before** the switch, in the shared command
layer (`chat_manager/commands/cli.py`):

* a **number** → the session at that position in `list_sessions()`;
* anything else → the session id, **exactly as today**.

The id path is untouched: the reference is handed to `switch_session()`
unchanged, so the manager remains the one that decides whether the
session exists and belongs to the user, and the message of a session
that is not found is unchanged.

A number that is not in the list is refused with a message that says
what the list holds:

```
There is no session 99 - the list holds 27 session(s).
```

Because the resolution lives in the shared layer, the classic console
accepts a number too — the parity the commit that introduced the gap
was aiming at.

---

## 4. The changes, file by file

| Path | Change |
| :--- | :--- |
| `agent-torvalds-mw.py` | the `not use_tui` condition is dropped; the hint of the classic REPL names the number |
| `chat_manager/commands/cli.py` | a new `resolve_session_reference`; `cmd_chat_select` takes a number; the session list carries a `#` column |
| `chat_manager/commands/handler.py` | a bare `\chat-select` prints the numbered list |
| `chat_manager/commands/__init__.py` | the resolver is exported |
| `components/tui/chat_history_view.py` | a new `render_session_picker_markdown`; the `#` column in the session list; the bare `\chat-select` opens the picker |
| `components/tui/tui_app.py` | the notification that tells the operator where to type the number |
| `components/tui/__init__.py` | the new renderer is exported |
| `components/command_registry.py` | the help text of `\chat-select` |
| `tests/test_tui_session_selection.py` | **new** — 23 tests |
| `CHANGELOG.md` | the entry of the change |

---

## 5. The proof

### 5.1 The tests

`tests/test_tui_session_selection.py` — **23 tests**, in four groups:

| Group | What it pins |
| :--- | :--- |
| the number | the number picks the session of that position; it follows the order of the list; a number outside the list is refused; **the id path is untouched** |
| the picker | the sessions are numbered; the active one is marked; the picker carries **no id**; it is narrower than the list it replaces; a row fits the document pane |
| the command of the TUI | a bare `\chat-select` opens the picker; `\chat-select 2` switches; a command that is not a chat command is ignored |
| the startup | **the TUI offers the menu**; `--no-session-select` still skips it; the classic console offers it too; the menu runs **before** the layout takes the screen |

The last group is the one that would have caught the defect: it runs
`main()` of the orchestrator with everything heavy mocked, and asserts
that the menu is offered — and that it is offered *before* the `Live`
display starts.

The test that the agent follows the session that was picked uses the
real `ChatHistoryManager` with a real (in-memory) backend and a mocked
database: the buffer is rebuilt, and it is bound to the `chat_key` of
the new session.

### 5.2 The probe

`investigate/tui-session-selection/probe_session_selection.py` runs the
real `agent-torvalds-mw.py` and the real `agent-torvalds.py` on a pty
of their own and looks for the markers of the menu in the byte stream
the operator receives.

| | before | after |
|---|---|---|
| the TUI proposes the choice | **no** | **yes** |
| the classic REPL proposes the choice | yes | yes |
| both modes loaded the same session | yes | yes |

```
[TUI  (agent-torvalds-mw.py)]
  menu proposed        : YES
  markers found        : ['Session selection:', 'Available sessions:', 'Select a session [1-']

[REPL (agent-torvalds.py)]
  menu proposed        : YES
  markers found        : ['Session selection:', 'Available sessions:', 'Select a session [1-']

  both modes loaded the same session: YES

========================================================================
FIXED: both modes propose the choice - the TUI asks which session to work
in, exactly as the classic REPL does.
========================================================================
```

### 5.3 The suite

| Check | Result |
| :--- | :--- |
| `tests/test_tui_session_selection.py` | **23 passed** |
| `chat_manager/tests/` | 289 passed |
| `tests/test_multi_window_parity.py` | passed — the existing parity tests are untouched |
| `scripts/ci_test_gate.py` | **0 new failures** — 40 known failures, 40 failures in this run, 3110 passed |

---

## 6. What was left alone

- **The classic REPL.**  It proposes the menu today, and it keeps it.
  It gains the number as a second way to name a session.
- **The 27 sessions in the database.**  They are the operator's history.
  The probe reads; the tests write nothing — the database of the tests
  is mocked.
- **`\chat-sessions`.**  It keeps the full id of every session — the
  operator needs it for `\chat-rename` and `\chat-delete`.  It gains the
  `#` column, so the numbering of the picker is visible there too.
- **The `--no-session-select` flag.**  It still skips the menu, in both
  modes.
- **The order of the sessions.**  `list_sessions()` orders them by
  `created_at` descending, and it was not changed: the numbering of the
  startup menu, of `\chat-sessions` and of the picker follows it, so
  the operator learns one numbering and not three.
