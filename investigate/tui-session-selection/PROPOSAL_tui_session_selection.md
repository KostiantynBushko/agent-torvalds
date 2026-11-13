# Proposal: the TUI must offer the chats of the database — and let the operator pick one

**Date**: 2026-11-13
**Status**: **Decided and implemented** — the operator approved the
recommended option on 2026-11-13 (*"ok go ahead with your preferred
choice"*), and revised the shape of the startup on the same day (*"go
ahead and make this small change"*).
**Companion to**: `investigation_tui_session_selection.md`,
`probe_session_selection.py`
**Branch**: `fix/tui-rendering` (merges into `fix/tui-terminal-size`)
**Scope**: `agent-torvalds-mw.py`, `chat_manager/session_selector.py`,
`chat_manager/commands/cli.py`, `chat_manager/commands/handler.py`,
`components/tui/chat_history_view.py`, `components/tui/tui_app.py`,
`components/command_registry.py`,
`tests/test_tui_session_selection.py` (new)

---

## 1. What the operator reported

> *by running TUI agent I cannot chose chat from DB the agent does not
> propose select one it just loads the last one*

The investigation confirmed two defects, and the operator approved the
remedy for both:

| | Defect | The remedy |
| :--- | :--- | :--- |
| **D1** | the TUI never proposes the choice — one condition skips it | the TUI asks **inside its own layout**, and the agent waits for the answer |
| **D2** | inside the TUI a session can only be chosen by typing a 36-character id | a numbered picker, like `\tools` |

---

## 2. The shape of the fix

```
   ┌──────────────────────────────────────────────────────────────┐
   │ 1. The question (D1)                                          │
   │                                                              │
   │   The classic console asks in the terminal, before the REPL: │
   │                                                              │
   │     Session selection:                                       │
   │     Available sessions:                                      │
   │       1. objective-control-001  (created 2026-11-09 10:40)   │
   │       ...                                                    │
   │     Select a session [1-27], 'new <name>' to create one...   │
   │                                                              │
   │   The TUI asks inside its own layout:                       │
   │                                                              │
   │     ┌─ 📄 Markdown Document Viewer ────────────────────┐     │
   │     │          💬 Select a Chat Session                │     │
   │     │  How to select:                                  │     │
   │     │   • Type the number of the session and press Enter│    │
   │     │   #  Session            Type     Created        │     │
   │     │   1  objective-control…  custom   2026-11-09 10:40│     │
   │     └──────────────────────────────────────────────────┘     │
   │                                                              │
   │   The agent WAITS.  A question typed before the choice would │
   │   run in the session that was active last - the defect.     │
   └──────────────────────────────────────────────────────────────┘

   ┌──────────────────────────────────────────────────────────────┐
   │ 2. The answer (D2)                                           │
   │                                                              │
   │   before:  \chat-select <36-char-uuid>       (copy/paste)    │
   │   after:   \chat-select        → numbered list in the pane  │
   │             \chat-select 3      → switch to the third one    │
   │                                                              │
   │   The numbering is the same in every list: the startup menu, │
   │   \chat-sessions and the picker all number the sessions the │
   │   same way.                                                  │
   └──────────────────────────────────────────────────────────────┘
```

The two halves are independent: the first is about *when* and *where*
the operator is asked, the second about *how* the answer is given.

---

## 3. The question — where it is asked

### 3.1 The rules live in one place

Two front-ends ask the same question: the classic console, which blocks
on the terminal, and the TUI, which asks in its command bar.  They must
mean the same thing by the same numbers.

The rules therefore live in `chat_manager.session_selector`:

```python
def apply_session_answer(manager, answer) -> tuple[Optional[Session], str]:
```

* a **number** → the session at that position in the list;
* `new <name>` → a new session, created and activated;
* **nothing** → the session that is already active is kept;
* anything else → the menu asks again, and says why.

`select_session_interactively` — the loop of the classic console — uses
it, so there is one implementation of the menu and not two.

### 3.2 The classic console asks in the terminal

Unchanged, and it stays the plain console menu it has always been:

```python
if not use_tui:
    if chat_history_enabled and not args.no_session_select and chat_manager is not None:
        console.print("[cyan]Session selection:[/cyan]")
        select_startup_session(...)
```

The condition lives **inside** the classic branch, and not next to it:
the TUI is not an exception of the classic menu, it is a different
front-end.

### 3.3 The TUI asks inside its layout

The TUI opens on the picker, in the document pane, and the agent waits:

```python
app = TuiApp(
    ...,
    select_session_at_startup=not args.no_session_select,
)
```

While the choice is pending, what the operator types **is** the answer
to the picker — it never reaches the agent.  A question typed before
the choice would run in the session that was active last, which is
the defect the picker came to close.

### 3.4 Why it is asked in the layout, and not in the terminal

The first shape of the fix asked in the terminal, before the layout —
the menu of the classic console, and then the layout.  The operator
asked for the other shape on 2026-11-13.

The reason is the **two phases**: the operator sees a console menu, and
then the screen changes and the menu is gone.  The layout is the place
the operator works, and the question belongs there:

* the picker is in the **document pane**, where the answer of the agent
  goes — the same place `\tools` puts its menu;
* the instructions come **before** the table, because the table of a
  user with many sessions is longer than the pane, and an instruction
  below the fold is an instruction nobody reads;
* the wording follows the context: at the startup the operator types
  the **number alone**, in the middle of a session he types the whole
  command.

---

## 4. The answer — a numbered picker inside the TUI

### 4.1 The numbering

`manager.list_sessions()` returns the sessions of the user ordered by
`created_at` descending, and the classic startup menu already numbers
them in that order.  **The same order is used everywhere**, so the
number the operator sees in one list is the number in every other list.

### 4.2 The picker

`\chat-select` without an argument opens the picker in the document
pane — the same place `\tools` puts its menu, and the same way it asks
for the answer:

```
# 💬 Select a Chat Session

**Sessions:** 27  •  the active one is marked ★

**How to select:**
- Type `\chat-select <number>` in the command bar and press Enter.
- `\chat-select <session_id>` also works — the id is in `\chat-sessions`.

| # | Session | Type | Created |
| ---: | :--- | :--- | :--- |
| 1 | objective-control-001 | custom | 2026-11-09 10:40 |
| ... |
```

The picker is **compact on purpose**: it leaves the id out.  A row of
`\chat-sessions` is 121 characters long in a document pane that is 74
characters wide — the id is folded in the middle of it, and it is
exactly that id that had to be copied by hand.

### 4.3 The resolution

The reference is resolved **before** the switch, in the shared command
layer (`chat_manager/commands/cli.py`):

* a **number** → the session at that position in `list_sessions()`;
* anything else → the session id, **exactly as today**.

The id path is **not** touched: the reference is handed to
`switch_session()` unchanged, so the manager remains the one that
decides whether the session exists and belongs to the user.

---

## 5. The changes, file by file

| Path | Change |
| :--- | :--- |
| `agent-torvalds-mw.py` | the menu of the classic console moves into the classic branch; the TUI is told to ask |
| `chat_manager/session_selector.py` | a new `apply_session_answer` — the rules of the menu, in one place |
| `chat_manager/commands/cli.py` | a new `resolve_session_reference`; `cmd_chat_select` takes a number; the session list carries a `#` column |
| `chat_manager/commands/handler.py` | a bare `\chat-select` prints the numbered list |
| `components/tui/chat_history_view.py` | a new `render_session_picker_markdown`; a new `render_session_chosen_markdown`; the `#` column in the session list; the bare `\chat-select` opens the picker |
| `components/tui/tui_app.py` | the mode in which the agent waits for the session; the picker; the confirmation |
| `components/command_registry.py` | the help text of `\chat-select` |
| `tests/test_tui_session_selection.py` | **new** — the proof of both halves |

---

## 6. The proof

| Check | Result |
| :--- | :--- |
| `tests/test_tui_session_selection.py` | **32 passed** |
| `chat_manager/tests/` | the tests of the classic selector — unchanged, and they pass |
| `scripts/ci_test_gate.py` | **0 new failures** |
| `investigate/tui-session-selection/probe_session_selection.py` | the end-to-end proof: the real agent, on a pty, asked and answered |

The probe is the proof that matters: it runs the **real**
`agent-torvalds-mw.py` and the real `agent-torvalds.py` on a pty of
their own, waits for the question to appear on the screen, answers it
with the number of a session, and looks for the outcome in the byte
stream the operator receives.

---

## 7. What is left alone

* **The classic REPL.**  It asks in the terminal today, and it keeps
  asking.  It gains the number as a second way to name a session.
* **The sessions in the database.**  They are the operator's history.
  The probe answers with the number of the session that is **already
  active**, so it leaves the active session the way it found it; the
  activation bumps the `updated_at` of the sessions and changes nothing
  else.
* **`\chat-sessions`.**  It keeps the full id of every session — the
  operator needs it for `\chat-rename` and `\chat-delete`.  It gains the
  `#` column, so the numbering of the picker is visible there too.
* **The `--no-session-select` flag.**  It still skips the question, in
  both front-ends.
