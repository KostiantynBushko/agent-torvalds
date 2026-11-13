# Proposal: the choice of the chat session is a background job

**Date**: 2026-11-13
**Status**: **Implemented** — see `IMPLEMENTATION_REPORT_background.md`
**Companion to**: `investigation_tui_session_selection_background.md`,
`probe_session_selection_background.py`
**Branch**: `fix/tui-session-selection-background`
**Scope**: `components/tui/tui_app.py`, `components/tui/chat_history_view.py`,
`chat_manager/stats.py`, `chat_manager/manager.py`,
`chat_manager/startup.py`, `agent-torvalds-mw.py`,
`tests/test_tui_session_selection.py`, `chat_manager/tests/test_stats.py`,
`chat_manager/tests/test_manager.py`

---

## 1. What the operator asked for

> *the agent hangs for this time can we run it in background as background job*

The request has two parts, and both are answered:

1. **the work runs in the background** — the loop that paints the
   layout is never held up by the choice of the session;
2. **the session is loaded fast** — the seconds of the operator are
   gone, not only hidden behind a spinner.

## 2. The shape of the fix

### 2.1 The answer is taken at once

The answer leaves the command bar the moment the operator presses
Enter, and it is shown in the document pane:

```
╭─ 📄 Markdown Document Viewer ─────────────────────────────╮
│                    💬 Select a Chat Session                │
│                                                             │
│  **Answer:** `2`                                            │
│                                                             │
│  ⏳ Loading the session…                                    │
│                                                             │
│  The work runs in the background: the layout keeps painting │
│  while the database and the tokenizer do their part.        │
╰─────────────────────────────────────────────────────────────╯
```

The digit is on the screen in the next frame — **not** after the
session is loaded.

### 2.2 The work is a job

```
        the loop that paints the layout
        ┌──────────────────────────────────────┐
        │  Enter ──► the answer is taken       │
        │           the pane says "Loading…"   │
        │           a job is started            │
        │                                      │
        │           the frames keep coming ───┼──► 15 fps
        └──────────────────────────────────────┘
                          │
                          ▼
        the job (a thread)
        ┌──────────────────────────────────────┐
        │  apply_session_answer()   16 ms      │
        │  the count of the header  1.5 s      │
        └──────────────────────────────────────┘
```

The database and the tokenizer are touched in a **thread**
(`asyncio.to_thread`), so the event loop keeps painting while they
work.  The rules of the answer are **not** touched: the number, the
`new <name>` and the empty answer mean what they meant before — see
`chat_manager/session_selector.py`, which both front-ends share.

### 2.3 The count of the header is counted in one pass

The count is the number of messages the agent holds — the tail of the
history that survives the chat-token limit.  The memory buffer of
LlamaIndex answers that question with a loop that counts the tokens of
the whole window again on every step, and the work is quadratic.

`chat_manager.stats.count_messages_within_limit()` answers the same
question by walking the history **once**, from the end, and stopping at
the limit.  The answer is the answer of the buffer — the tests compare
the two, message by message, for a dozen histories.

| | The buffer of LlamaIndex | The count of the project |
|---|---|---|
| 6204 messages (15 MB) | **40.379 s** | **0.568 s** |

### 2.4 The buffer of the agent trims in one pass

The count was slow because the memory buffer of LlamaIndex trims the
history with a loop that counts the tokens of the **whole window again
on every step**.  The work is quadratic, and the agent pays it on
**every turn** — the buffer is asked for its messages every time a
request is built.

`chat_manager.memory.TrimmingChatMemoryBuffer` answers the same
question in one pass: the messages are counted one by one, from the
end, and the walk stops when they reach the limit.  The windows the
library visits are the windows visited here, so **the answer is the
answer of the library** — the same messages, in the same order.

| | the buffer of LlamaIndex | the buffer of the project |
|---|---|---|
| 6204 messages (15 MB) | **39.467 s** | **0.009 s** |

The tests compare the two, message by message, for a dozen histories,
for the roles, and for a hundred random ones.

## 3. What is *not* changed

* **What the agent sends to the model.**  The messages are the same
  ones, in the same order: the trimming of the project answers the
  question of the library.  Only the work it takes to find them is
  different.
* **The rules of the picker.**  They live in
  `chat_manager/session_selector.py` and are shared with the classic
  console.  The change is *where* the work is done, not *what* it
  does.
* **The database.**  Nothing is written that was not written before:
  the session is activated, and that is all.

## 4. The result

| | Before | After |
|---|---|---|
| The Enter key cost the loop | 40 364 ms | **0.0 ms** |
| The digit is on the screen at once | no | **yes** |
| The pane named the session after | 40.36 s | **0.06 s** |
| The count of the header arrived after | 40.26 s | **1.59 s** |
| The frames painted while it was loaded | 0 | **65** |
| One turn of the agent | ~40 s | **1.70 s** |

The numbers are from the probe, on the heaviest session of the
operator (6204 messages).  What is left of a turn is the reading of
the history from the database — 15 MB — and not the trimming.
