# Implementation report — the choice of the chat session is a background job

**Date**: 2026-11-13
**Branch**: `fix/tui-session-selection-background` (from `master`)
**Status**: implemented, verified — **not committed yet** (the commit needs
the approval of the operator)
**Companion to**: `investigation_tui_session_selection_background.md`,
`PROPOSAL_tui_session_selection_background.md`,
`probe_session_selection_background.py`

---

## 1. What was implemented

| | Defect | How it is closed |
|---|---|---|
| **D3** | the choice of the session was applied **in the loop that paints the layout** — the layout froze, and the digit the operator typed appeared only when the freeze was over | the answer is taken at once and shown in the pane; the work runs in a **background job**, and the database and the tokenizer are touched in a **thread** |
| **D4** | the count of the messages of the header was the **quadratic** trim of the memory buffer of LlamaIndex — forty seconds for a history of 6204 messages | the count is asked in **one pass** (`chat_manager.stats.count_messages_within_limit`), and the answer is the answer of the buffer |

## 2. The change, file by file

### `components/tui/tui_app.py`

| What | Where |
|---|---|
| the three background jobs of the TUI (`_session_task`, `_chat_command_task`, `_state_refresh_task`) | `__init__()` |
| the jobs are cancelled when the TUI goes down | `run()` |
| the choice of the session is scheduled, not done | `_handle_session_selection()` |
| the work of the answer, in a thread | `_apply_session_selection()` |
| the picker is rendered apart from being shown, so it can run in a thread | `_show_session_picker()` / `_render_session_picker()` |
| the state of the session is read apart from being applied | `_collect_chat_session_state()` / `_apply_chat_session_state()` |
| the refresh of the state, in a thread | `_refresh_chat_session_state_async()` |
| the chat commands (`\chat-select`, `\chat-info`, …) run in the background | `_run_chat_command()` |

The answer leaves the command bar the moment the operator presses Enter,
and the pane says what is being done:

```
# 💬 Select a Chat Session

**Answer:** `2`

⏳ Loading the session…
```

A second answer while the job runs is refused with a notification — the
picker belongs to the job that is running.

### `components/tui/chat_history_view.py`

`render_session_loading_markdown()` — the pane of the work in progress.

### `chat_manager/stats.py`

`count_messages_within_limit()` — the count of the messages that survive
the chat-token limit, in one pass.  `message_role()` — the role of a
message, as a plain string.

### `chat_manager/manager.py`

`ChatHistoryManager.count_buffered_messages()` — the count of the
messages the agent holds, asked in one pass.

### `chat_manager/startup.py`

`count_memory_messages()` — the count of the memory, with or without a
manager.

### `agent-torvalds-mw.py`

The count of the messages at the startup of the TUI is read in the
background as well: it reads the history of the session, and the
terminal must not stand still for it.

## 3. The measurements

`probe_session_selection_background.py`, on the heaviest session of the
operator (6204 messages, 15 MB of history):

| | Before | After |
|---|---|---|
| The Enter key cost the loop | 40 364 ms | **0.0 ms** |
| The digit is on the screen at once | no | **yes** |
| The command bar is empty after the answer | no | **yes** |
| The pane named the session after | 40.36 s | **0.06 s** |
| The count of the header arrived after | 40.26 s | **1.59 s** |
| The frames painted while it was loaded | 0 | **65** |

The count of the history on its own:

| | The buffer of LlamaIndex | The count of the project |
|---|---|---|
| 6204 messages (15 MB) | 40.379 s | **0.568 s** |

## 4. The tests

| Test | What it proves |
|---|---|
| `tests/test_tui_session_selection.py::TestTheChoiceOfTheSessionRunsInTheBackground` | the answer is on the screen at once; the loop is not blocked while the job works (a heartbeat keeps ticking); the session is switched when the job is done; a second answer is ignored; the chat commands run in the background |
| `chat_manager/tests/test_stats.py::TestCountMessagesWithinLimit` | the count is the answer of the memory buffer — for a dozen histories, including the assistant/tool roles and the message that is longer than the limit; the count asks the tokenizer for the tail only |
| `chat_manager/tests/test_manager.py::TestManagerMessages` | the manager counts the messages of the buffer, and the count agrees with the buffer |

The whole suite: **1851 passed**, the same **29 failures** as before the
change (they are pre-existing and unrelated — the async tests without
the plugin, the project scanner and the runtime toggle).

## 5. What was **not** changed

* **What the agent sends to the model.**  The memory buffer is the one
  of LlamaIndex, and the trimming of the history is the one of the
  library.  The fast count feeds the **number in the header** — a
  number for the operator, not a decision.
* **The rules of the picker.**  They live in
  `chat_manager/session_selector.py` and are shared with the classic
  console.  The change is *where* the work is done, not *what* it
  does.
* **The database.**  Nothing is written that was not written before.

## 6. A finding that is **not** fixed here

The quadratic trim of the memory buffer is paid by the **agent on every
turn**: the buffer is asked for its messages every time a request is
built.  The count of the header was only the place where it became
visible to the operator.

A session with thousands of messages therefore makes every turn of the
agent slow.  The remedy is the same one-pass trimming, applied to the
buffer itself — a subclass of `ChatMemoryBuffer` that overrides `get()`.
That changes **what the model is sent**, so it is a change of its own,
and it is not part of this fix.

## 7. The files of the change

```
agent-torvalds-mw.py                        |  35 +++++++---
chat_manager/manager.py                     |  32 ++++++++
chat_manager/startup.py                     |  28 ++++++++
chat_manager/stats.py                       | 104 +++++++++++++++++-
chat_manager/tests/test_manager.py          |  26 ++++++
chat_manager/tests/test_stats.py            |  96 +++++++++++++-
components/tui/chat_history_view.py         |  36 ++++++++
components/tui/tui_app.py                   | 265 +++++++++++++++++++++--
tests/test_tui_session_selection.py         | 198 +++++++++++++++++++-
investigate/tui-session-selection/probe_session_selection_background.py (new)
investigate/tui-session-selection/investigation_tui_session_selection_background.md (new)
investigate/tui-session-selection/PROPOSAL_tui_session_selection_background.md (new)
investigate/tui-session-selection/IMPLEMENTATION_REPORT_background.md (new)
```
