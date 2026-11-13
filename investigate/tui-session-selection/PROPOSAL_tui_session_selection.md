# Proposal: the TUI must offer the chats of the database — and let the operator pick one

**Date**: 2026-11-13
**Status**: **Decided** — the operator approved the recommended option on
2026-11-13: *"ok go ahead with your preferred choice"*
**Companion to**: `investigation_tui_session_selection.md`,
`probe_session_selection.py`
**Branch**: `fix/tui-rendering` (merges into `fix/tui-terminal-size`)
**Scope**: `agent-torvalds-mw.py`, `chat_manager/commands/cli.py`,
`chat_manager/commands/handler.py`, `components/tui/chat_history_view.py`,
`components/tui/tui_app.py`, `components/command_registry.py`,
`tests/test_tui_session_selection.py` (new)

---

## 1. What the operator reported

> *by running TUI agent I cannot chose chat from DB the agent does not
> propose select one it just loads the last one*

The investigation confirmed two defects, and the operator approved the
remedy for both:

| | Defect | The remedy |
| :--- | :--- | :--- |
| **D1** | the TUI never proposes the startup choice — one condition skips it | the menu runs before the layout takes the screen |
| **D2** | inside the TUI a session can only be chosen by typing a 36-character UUID | a numbered picker, like `\tools` |

The operator chose the recommended option, which is **1(a) + 2(b)**:

* **at startup** — the plain console menu of the classic REPL, printed
  before the Rich layout takes the screen;
* **while the TUI is up** — `\chat-select` without an argument opens a
  numbered list in the document pane, and `\chat-select <number>`
  switches to it.

---

## 2. The shape of the fix

```
   ┌──────────────────────────────────────────────────────────────┐
   │ 1. The startup choice (D1)                                   │
   │                                                              │
   │   before:  TUI  →  loads the last session, says nothing      │
   │   after:   menu → operator picks → TUI opens on that session│
   │                                                              │
   │   The menu runs BEFORE the Live display takes the screen, so │
   │   the terminal is still an ordinary console.                 │
   └──────────────────────────────────────────────────────────────┘

   ┌──────────────────────────────────────────────────────────────┐
   │ 2. The choice inside the TUI (D2)                            │
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

The two halves are independent: the first is about *when* the operator is
asked, the second about *how* the answer is given.

---

## 3. D1 — the startup menu in the TUI

### 3.1 The change

One condition, in `agent-torvalds-mw.py`:

```python
# before
if not args.no_session_select and not use_tui:

# after
if not args.no_session_select:
```

Nothing else moves.  The menu is the **same menu** the classic
orchestrator shows — `chat_manager.session_selector`, which is already
covered by `chat_manager/tests/test_session_selector.py`.

### 3.2 Why it is safe

The reason a blocking console prompt is avoided in TUI mode is that the
TUI owns the terminal.  **That reason does not apply here**: the menu
runs at line 1656 and the TUI takes the alternate screen at line 1802.
At menu time the terminal is still an ordinary console.

The same file already blocks on `input()` in front of the TUI — the
`--select` tool picker runs in both modes with no guard at all.

### 3.3 What the operator sees

```
$ python agent-torvalds-mw.py

Initializing chat history manager...
Chat session: <the session that was active last>
Session selection:
Available sessions:
  * 1. <the session that was active last> [custom] (created 2026-11-08 12:15)
    2. <another session> [custom] (created 2026-11-09 10:40)
    ...
Select a session [1-27], 'new <name>' to create one, or Enter to keep the current one:
> 2
Active chat session: <another session>

        ← the layout now takes the whole screen
```

Pressing Enter keeps the session that was active — the behaviour of
today, for the operator who does not want to choose.

The session that was picked is the one the agent binds to: the memory
buffer is built from the active session's `chat_key` **after** the menu
(`create_agent` → `get_memory_buffer`), and `switch_session()` drops
the cached buffer, so the picked session is the one that is loaded.

---

## 4. D2 — a numbered picker inside the TUI

### 4.1 The numbering

`manager.list_sessions()` returns the sessions of the user ordered by
`created_at` descending.  The classic startup menu already numbers them
in that order.  **The same order is used everywhere**, so the number the
operator sees in one list is the number in every other list.

### 4.2 `\chat-select` without an argument

The command opens the picker in the document pane — the same place
`\tools` puts its menu, and the same way it asks for the answer:

```
# 💬 Select a Chat Session

**Sessions:** 27  •  the active one is marked ★

| # | Session | Type | Created |
| ---: | :--- | :--- | :--- |
| 1 | objective-control-001 | custom | 2026-11-09 10:40 |
| 2 | ★ agent-torvald-project-002 | custom | 2026-11-08 12:15 |
| ... |

**How to select:**
- Type `\chat-select <number>` in the command bar and press Enter.
- `\chat-select <id>` also works — the id is in `\chat-sessions`.
```

The picker is **compact on purpose**: the table of `\chat-sessions`
carries the full UUID of every session, and its rows are 97 characters
long in a document pane that is 74 characters wide — the id is folded
in the middle and has to be copied by hand.  The picker leaves the UUID
out and fits.

### 4.3 `\chat-select <number>`

The reference is resolved to a session **before** the switch:

* a **number** → the session at that position in `list_sessions()`;
* anything else → the session id, exactly as today.

The resolution lives in the shared command layer
(`chat_manager/commands/cli.py`), so the classic REPL accepts a number
too — the parity the commit that introduced the gap was aiming at.

The id path is **not** touched: the reference is passed to
`switch_session()` unchanged, so an id that does not belong to the user
is still refused by the manager, and the message stays the same.

---

## 5. The changes, file by file

| Path | Change |
| :--- | :--- |
| `agent-torvalds-mw.py` | the `not use_tui` condition is dropped; the hint text of the classic REPL mentions the number |
| `chat_manager/commands/cli.py` | `cmd_chat_select` resolves a number; a new `resolve_session_reference` helper |
| `chat_manager/commands/handler.py` | a bare `\chat-select` prints the numbered list |
| `components/tui/chat_history_view.py` | a new `render_session_picker_markdown`; the `#` column in the session list; the bare `\chat-select` opens the picker |
| `components/tui/tui_app.py` | the notification that tells the operator to type the number |
| `components/command_registry.py` | the help text of `\chat-select` |
| `tests/test_tui_session_selection.py` | **new** — the proof of both halves |

---

## 6. The proof

| Check | Result |
| :--- | :--- |
| `tests/test_tui_session_selection.py` | the new tests |
| `chat_manager/tests/test_commands.py` | the existing tests of `\chat-select` still pass — the id path is unchanged |
| `tests/test_multi_window_parity.py` | the existing parity tests still pass |
| `investigate/tui-session-selection/probe_session_selection.py` | the end-to-end proof: the TUI offers the menu, the REPL offers it, both load the same session |

The probe is the proof that matters: it runs the **real**
`agent-torvalds-mw.py` on a pty and looks for the markers of the menu
in the byte stream the operator receives.

---

## 7. What is left alone

* **The classic REPL.**  It proposes the menu today, and it keeps it.
* **The 27 sessions in the database.**  They are the operator's history.
  The probe reads; it never writes.
* **`\chat-sessions`.**  It keeps the full UUID of every session — the
  operator needs it for `\chat-rename` and `\chat-delete`.  It gains the
  `#` column, so the numbering of the picker is visible there too.
* **The `--no-session-select` flag.**  It still skips the menu, in both
  modes.
