# The TUI loads the last chat session and never asks which one

## What the operator reported

> *by running TUI agent I cannot chose chat from DB the agent does not
> propose select one it just loads the last one*

Two claims in one sentence, and they are two different defects:

1. **the agent does not propose to select one** — the startup menu of the
   chat sessions never appears in the TUI;
2. **it just loads the last one** — the session that was used last is
   restored and the agent starts working in it.

And, underneath both, the reason the operator says *cannot choose chat
from DB*: the only way to change the session **inside** the TUI is to
copy a 36-character UUID out of a table and type it back.

Both are confirmed.  The proof is a probe that runs both entry points on
a pty of their own:

```
.venv/bin/python investigate/tui-session-selection/probe_session_selection.py
```

```
[TUI  (agent-torvalds-mw.py)]
  menu proposed        : NO
  markers found        : -
  a session was loaded : YES
  type of that session : custom

[REPL (agent-torvalds.py)]
  menu proposed        : YES
  markers found        : ['Session selection:', 'Available sessions:', 'Select a session [1-']
  a session was loaded : YES
  type of that session : custom

  both modes loaded the same session: YES

========================================================================
CONFIRMED: the TUI loads a session without proposing the choice, while
the classic REPL proposes it.
========================================================================
```

Both modes load **the same session** — the one that was active at the
end of the last run.  The difference is the **proposal**: the classic
REPL asks, the TUI does not.

The database the agent talks to holds **27 sessions** for the operator
and exactly **one** of them is active.  That one is restored on every
start, so the TUI always opens the last conversation and never offers
the other 26.

> The probe reports the *type* of the session and whether both modes
> loaded the same one.  It never prints the name or the id: they belong
> to the operator's own database, and this repository is public.

---

## D1 — the TUI skips the startup session menu

The proposal exists, it is tested, and the classic orchestrator runs it.
The TUI does not, because of one condition:

```python
# agent-torvalds-mw.py:1656
if not args.no_session_select and not use_tui:
    console.print("[cyan]Session selection:[/cyan]")
    select_startup_session(
        input_func=lambda prompt="": console.input(prompt),
        output_func=lambda text: console.print(text),
    )
```

`not use_tui` switches the whole block off.  The classic orchestrator has
no such condition — it asks in every mode:

```python
# agent-torvalds.py:1505
if not args.no_session_select:
    console.print("[cyan]Session selection:[/cyan]")
    select_startup_session(...)
```

### The condition is not a technical necessity

The obvious reason to skip a blocking console prompt in TUI mode is
that the TUI owns the terminal.  **That reason does not apply here**,
because the menu runs *before* the TUI takes the screen:

| line | what happens |
| :--- | :--- |
| 1656 | the session menu would run here |
| 1669 | `if not use_tui:` → the classic REPL |
| 1802 | `await app.run()` → the Live display takes the alternate screen |

At line 1656 the terminal is still an ordinary console.  The TUI has
not started: the `Live` display, the alternate screen and the
non-blocking input reader all come later, at line 1802.

**The same file already does this.**  The startup tool picker
(`--select`) blocks on `input()` in front of the TUI, in *both* modes,
with no `not use_tui` guard at all:

```python
# agent-torvalds-mw.py - the --select block, no use_tui condition
if args.select:
    from agent_tool_selection import select_tools_interactively
    selected_tools = select_tools_interactively()
```

and it uses the plain builtin `input()`:

```python
# agent_tool_selection.py:641
raw = input(f"Select categories [example: 1,2,5 or 1-3] (1-{total_categories}): ")
```

So a blocking picker before the TUI is an established pattern of this
orchestrator.  The session menu is the one that was left out.

### How it got that way

The guard arrived with `3346557` — *"feat: align multi-window agent with
the classic orchestrator (#18)"*.  The commit was about **parity**, and
it says so:

> *Chat History Manager: initialized at startup with the `\chat-*` runtime
> commands available in both the TUI and the classic REPL.*

The runtime commands (`\chat-sessions`, `\chat-select`) were given to
both modes.  The **startup** selection was not — and the commit message
does not record that as a decision.  It reads like an omission inside a
parity commit, not a deliberate exclusion.

No test pins the current behaviour: `tests/test_multi_window_parity.py`
only checks that the `--no-session-select` flag *exists*.

---

## D2 — inside the TUI, choosing a session means typing a UUID

The TUI has the chat commands, and they work.  `\chat-sessions` renders
the list, `\chat-select <id>` switches.  But the *id* is the only thing
they accept:

```python
# chat_manager/commands/cli.py:81
def cmd_chat_select(manager, session_id):
    session = manager.switch_session(session_id)
```

```python
# chat_manager/manager.py:429
def switch_session(self, session_id):
    if self.get_session(session_id) is None:
        return None          # ← a number is not a session id
```

`get_session` looks the id up in the `chat_sessions` table by
`session_id`.  A number is not an id, so the number of the menu is
rejected:

```
$ \chat-select 1
Session '1' not found.
```

The classic startup menu numbers its sessions and accepts the number
(`chat_manager/session_selector.py` → `sessions[index - 1]`).  That
numbering never reaches the TUI, because the TUI never calls the
selector.

And the id the operator is expected to type is not easy to come by.
`\chat-sessions` renders the list as a Markdown table with the **full
UUID** in every row:

```
| Active | ID | Name | Type | Created |
| :---: | :--- | :--- | :--- | :--- |
|  | `<session-uuid>` | <session-name> | custom | 2026-11-09 10:40 |
```

The document pane of the TUI is 74 characters wide at a 120-column
terminal (`markdown_view.py`: `max(40, int(console.width * 0.62))`),
and the row above is **97** characters long.  The row is folded in the
middle of the UUID, and the operator is expected to read a UUID off a
folded table and type it back into the command bar.

So the TUI has *no* usable way to pick a chat out of the 27 in the
database: no proposal at startup, and no numbered menu afterwards.

---

## What is not the cause

* **The database is not degraded.**  The connector reaches the primary
  database; the 27 sessions are read from it.  The fallback is not in
  play.
* **The selector does not work.**  `chat_manager/session_selector.py`
  is fine — the classic REPL uses it and the probe shows the menu with
  all three markers.
* **The TUI is not hiding the menu behind a rendering problem.**  The
  block at line 1656 is never entered in TUI mode; the capture contains
  no trace of it.

---

## What was left alone

* **The session name in the telemetry pane.**  The active session *is*
  visible (`telemetry_view.py`: `state.chat_session_name`), so the
  operator can see which session they are in — after the fact.  The
  header does not carry it.
* **The classic REPL.**  It proposes the menu and it works.  Nothing in
  this investigation asks for a change there.
* **The 27 sessions in the database.**  They are the operator's history.
  Nothing was written to the database during this investigation — the
  only command that was run against it was a read.

---

## The decision that is open

Two defects, and they can be closed in two different ways.  The
operator decides which:

| | D1 — the startup proposal | D2 — choosing inside the TUI |
| :--- | :--- | :--- |
| **A** | run the existing menu before the TUI starts (drop `not use_tui`) | leave as is — `\chat-select <uuid>` still works |
| **B** | leave as is | a numbered picker in the document pane, like `\tools` |
| **C** | run the existing menu before the TUI starts | a numbered picker in the document pane, like `\tools` |

Option **C** is the one that matches the parity the commit that
introduced the gap was aiming at: the operator gets the choice at
startup *and* a usable way to change the session while the TUI is up.

Nothing has been changed.  This document and the probe are the only
artefacts of the investigation.
