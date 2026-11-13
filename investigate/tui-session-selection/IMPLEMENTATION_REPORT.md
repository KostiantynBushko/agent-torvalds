# Implementation report — the TUI asks which chat session to work in

**Date**: 2026-11-13
**Branch**: `fix/tui-rendering` (merges into `fix/tui-terminal-size`)
**Status**: implemented, verified — **merged**.  The operator approved the
commit and merged it as **PR #96**, which squash-merged the fix into
`master` as `e031ebf` on 2026-11-13.
**Companion to**: `investigation_tui_session_selection.md`,
`PROPOSAL_tui_session_selection.md`, `probe_session_selection.py`

---

## 1. What was implemented

Both defects of the investigation are closed, in the form the operator
approved on 2026-11-13 (*"ok go ahead with your preferred choice"*), and
with the shape of the startup revised the same day (*"go ahead and make
this small change"*).

| # | Defect | How it is closed |
|---|---|---|
| **D1** | the TUI never proposed the choice — one condition skipped it | the TUI opens on the picker, inside its own layout, and **the agent waits** for the answer |
| **D2** | inside the TUI a session could only be chosen by a 36-character id | `\chat-select` without an argument opens a numbered picker; `\chat-select <number>` switches to that session |

---

## 2. D1 — the TUI asks, inside its layout

### 2.1 The picker is in the document pane

```
╭─ 📄 Markdown Document Viewer ─────────────────────────────╮
│                    💬 Select a Chat Session                │
│                                                             │
│  Sessions: 27  •  the active one is marked ★               │
│                                                             │
│  How to select:                                             │
│                                                             │
│   • Type the number of the session and press Enter.         │
│   • Press Enter alone to keep the session that is active now.│
│   • \chat-select <session_id> also works — the id is in     │
│     \chat-sessions.                                         │
│                                                             │
│    #  Session                      Type     Created         │
│    1  objective-control-001        custom   2026-11-09 10:40 │
│    2  agent-torvald-ollama-intern…  custom   2026-11-09 08:03 │
│    4  ★ agent-torvald-project-002  custom   2026-11-08 12:15 │
│    ...                                                        │
╰─────────────────────────────────────────────────────────────╯
```

The instructions come **before** the table: the table of a user with
many sessions is longer than the pane, and an instruction below the
fold is an instruction nobody reads.

The wording follows the context: at the startup the operator types the
**number alone**; in the middle of a session he types the whole
command (`\chat-select 4`).

### 2.2 The agent waits

While the choice is pending, what the operator types **is** the answer
to the picker — it never reaches the agent:

```python
# components/tui/tui_app.py - _handle_enter_pressed
if self._awaiting_session:
    self._handle_session_selection(cmd)
    return
```

A question typed before the choice would run in the session that was
active last — the defect the picker came to close.

### 2.3 The rules of the menu live in one place

Two front-ends ask the same question: the classic console, which blocks
on the terminal, and the TUI, which asks in its command bar.  They must
mean the same thing by the same numbers.

The rules therefore live in `chat_manager/session_selector.py`:

```python
def apply_session_answer(manager, answer) -> tuple[Optional[Session], str]:
```

* a **number** → the session at that position in the list;
* `new <name>` → a new session, created and activated;
* **nothing** → the session that is already active is kept;
* anything else → the menu asks again, and says why.

`select_session_interactively` — the loop of the classic console — uses
it, so there is one implementation of the menu and not two.  Its ten
tests are unchanged, and they pass.

### 2.4 The classic console asks in the terminal

Unchanged, and it stays the plain console menu it has always been.
The condition moved **into** the classic branch:

```python
if not use_tui:
    if chat_history_enabled and not args.no_session_select and chat_manager is not None:
        console.print("[cyan]Session selection:[/cyan]")
        select_startup_session(...)
```

The TUI is not an exception of the classic menu — it is a different
front-end, and it asks in its own way.

---

## 3. D2 — a numbered picker inside the TUI

### 3.1 The numbering

`manager.list_sessions()` returns the sessions of the user ordered by
`created_at` descending, and the classic startup menu already numbers
them in that order.  **The same order is used everywhere**, so the
number the operator sees in one list is the number in every other list:

| where | what it shows |
| :--- | :--- |
| the startup menu of the classic console | `1.`, `2.`, … `* 4.` — the active one is marked |
| `\chat-sessions` | a `#` column |
| the picker of `\chat-select` | a `#` column, and `★` on the active one |
| `\chat-select <number>` | the session at that position |

### 3.2 The picker is compact on purpose

It leaves the id out.  A row of `\chat-sessions` is 121 characters
long in a document pane that is 74 characters wide — the id is folded
in the middle of it, and it is exactly that id that had to be copied by
hand.  A *name* may still wrap (the longest name of the operator's
database makes a row of 82 characters); a name stays readable when it
wraps.

### 3.3 The resolution

The reference is resolved **before** the switch, in the shared command
layer (`chat_manager/commands/cli.py`):

* a **number** → the session at that position in `list_sessions()`;
* anything else → the session id, **exactly as today**.

The id path is not touched: the reference is handed to
`switch_session()` unchanged, so the manager remains the one that
decides whether the session exists and belongs to the user, and the
message of a session that is not found is unchanged.

Because the resolution lives in the shared layer, the classic console
accepts a number too — the parity the commit that introduced the gap
was aiming at.

---

## 4. The changes, file by file

| Path | Change |
| :--- | :--- |
| `agent-torvalds-mw.py` | the menu of the classic console moves into the classic branch; the TUI is told to ask |
| `chat_manager/session_selector.py` | a new `apply_session_answer` — the rules of the menu, in one place; the loop of the classic console uses it |
| `chat_manager/commands/cli.py` | a new `resolve_session_reference`; `cmd_chat_select` takes a number; the session list carries a `#` column |
| `chat_manager/commands/handler.py` | a bare `\chat-select` prints the numbered list |
| `chat_manager/commands/__init__.py` | the resolver is exported |
| `components/tui/chat_history_view.py` | a new `render_session_picker_markdown`; a new `render_session_chosen_markdown`; the `#` column in the session list; the bare `\chat-select` opens the picker |
| `components/tui/tui_app.py` | the mode in which the agent waits for the session; the picker; the confirmation |
| `components/tui/__init__.py` | the new renderer is exported |
| `components/command_registry.py` | the help text of `\chat-select` |
| `tests/test_tui_session_selection.py` | **new** — 32 tests |
| `CHANGELOG.md` | the entry of the change |

---

## 5. The proof

### 5.1 The tests

`tests/test_tui_session_selection.py` — **32 tests**, in four groups:

| Group | What it pins |
| :--- | :--- |
| the number | the number picks the session of that position; it follows the order of the list; a number outside the list is refused; **the id path is untouched** |
| the picker | the sessions are numbered; the active one is marked; the picker carries **no id**; it is narrower than the list it replaces; a row fits the document pane |
| the command of the TUI | a bare `\chat-select` opens the picker; `\chat-select 2` switches; a command that is not a chat command is ignored |
| the question and the wait | **the TUI asks inside its layout** and the classic console asks in the terminal; `--no-session-select` skips both; **a question typed before the choice never reaches the agent**; the number switches the session; an empty answer keeps the current one; an answer that is not understood asks again; `new <name>` creates a session; the agent works after the choice |

Two of them matter most:

* **the buffer of the agent is rebuilt for the session that was picked**,
  and it is bound to the `chat_key` of that session — the real
  `ChatHistoryManager`, with a real (in-memory) backend and a mocked
  database, so nothing is written;
* **a question typed before the choice never reaches the agent** — the
  prompt handler is never called, and the picker stays.

### 5.2 The probe

`investigate/tui-session-selection/probe_session_selection.py` runs the
real `agent-torvalds-mw.py` and the real `agent-torvalds.py` on a pty
of their own, waits for the question to appear on the screen, answers
it with the number of a session, and looks for the outcome in the byte
stream the operator receives.

| | before | after |
|---|---|---|
| the TUI asks the operator | **no** | **yes** |
| the answer switches the session | — | **yes** |
| the classic console asks the operator | yes | yes |
| the answer switches the session | yes | yes |

```
the answer is the number of the session that is active: 4

[TUI  (agent-torvalds-mw.py)]
  the operator was asked   : YES
  the answer was accepted  : YES

[REPL (agent-torvalds.py)]
  the operator was asked   : YES
  the answer was accepted  : YES

========================================================================
FIXED: both modes ask which session to work in, and the answer switches
the session in both.
========================================================================
```

The answer is the number of the session that is **already active**, so
the probe leaves the active session of the operator the way it found
it.  The activation bumps the `updated_at` of the sessions and changes
nothing else.

> The probe answers only **after** the question is on the screen.  The
> TUI puts the terminal into cbreak mode with `TCSAFLUSH` when it
> starts, and a key that arrives before that is discarded on purpose.

### 5.3 The suite

| Check | Result |
| :--- | :--- |
| `tests/test_tui_session_selection.py` | **32 passed** |
| `chat_manager/tests/` | passed — the tests of the classic selector are unchanged |
| `tests/test_multi_window_parity.py` | passed — the existing parity tests are untouched |
| `scripts/ci_test_gate.py` | **0 new failures** — 40 known failures, 40 failures in this run |

---

## 6. What was left alone

- **The classic REPL.**  It asks in the terminal today, and it keeps
  asking.  It gains the number as a second way to name a session.
- **The sessions in the database.**  They are the operator's history.
  The tests write nothing — the database of the tests is mocked.
- **`\chat-sessions`.**  It keeps the full id of every session — the
  operator needs it for `\chat-rename` and `\chat-delete`.  It gains the
  `#` column, so the numbering of the picker is visible there too.
- **The `--no-session-select` flag.**  It still skips the question, in
  both front-ends.
- **The order of the sessions.**  `list_sessions()` orders them by
  `created_at` descending, and it was not changed: the numbering of the
  startup menu, of `\chat-sessions` and of the picker follows it, so
  the operator learns one numbering and not three.
