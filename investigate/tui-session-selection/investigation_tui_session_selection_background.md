# Investigation: the choice of the chat session freezes the TUI

**Date**: 2026-11-13
**Status**: investigated — the defect is closed by
`PROPOSAL_tui_session_selection_background.md` and reported in
`IMPLEMENTATION_REPORT_background.md`
**Companion to**: `investigation_tui_session_selection.md` (the picker
itself), `PROPOSAL_tui_session_selection.md`,
`IMPLEMENTATION_REPORT.md`, `probe_session_selection_background.py`
**Branch**: `fix/tui-session-selection-background`

---

## 1. What the operator reported

> *ok here is issue with chat session selection, by typing numeber and press
> enter the agent hangs about a aouple of second and the digit after session
> is loaded*

> *we have an issue with chat session selection, first of all it takes a couple
> of seonds to load session, the agent hangs for this time can we run it in
> background as background job*

Two symptoms, one cause:

| | Symptom | What it says |
|---|---|---|
| **S1** | the agent hangs for a couple of seconds after the number | the work is done **in the loop that paints the layout** |
| **S2** | the digit appears **after** the session is loaded | the layout paints **no frame** while the work is done |

S2 is the proof of S1.  The terminal is in cbreak mode — the echo of the
terminal is off and the TUI draws what the operator types
(`components/tui/input_reader.py`).  A character that is typed is put
into the buffer of the state and painted by the **next frame**.  If the
work of the answer is done in the loop, there is no next frame until the
work is done: the digit the operator typed shows up together with the
confirmation, and it looks as if the answer had arrived *after* the
session was loaded.

## 2. The measurement

`probe_session_selection_background.py` drives the production
`TuiApp` against the database of the operator and measures the three
moments of the choice.  It picks the session with the **longest**
history — the heaviest one — and restores the session that was active
before it ran.

**Before the fix** (the work in the loop):

```
The Enter key cost the loop: 40364.4 ms
The digit is on the screen at once: False
The command bar is empty: False
The pane named the session after 40.36 s
The frames painted while it was loaded: 0
```

Zero frames.  The layout was frozen for forty seconds.

## 3. Where the seconds come from

The work of the answer is three things, and only one of them is slow:

| Step | Cost | What it is |
|---|---|---|
| `apply_session_answer()` | **16 ms** | the switch of the session in the database |
| `manager.get_messages()` | **40 s** | the count of the messages of the header |
| the render of the frame | 15 ms | the layout |

The switch itself is fast.  The slow part is the **count of the
messages** that the header shows, and it is slow because of the way the
memory buffer of LlamaIndex trims the history:

```python
# llama_index/core/memory/chat_memory_buffer.py
while token_count > self.token_limit and message_count > 1:
    message_count -= 1
    ...
    cur_messages = chat_history[-message_count:]
    token_count = self._token_count_for_messages(cur_messages)   # again
```

Every step of the loop counts the tokens of the **whole window again**.
For a session with thousands of messages the work is quadratic.  The
history of the heaviest session of the operator is 15 MB — 6204
messages — and the trimming of it takes:

```
count of the whole history: 40.379 s
```

The same trim is paid by the **agent on every turn**, because the
memory buffer is asked for its messages every time a request is built.
The session picker is only where it became visible.

## 4. The defect

| | Defect | Where |
|---|---|---|
| **D3** | the choice of the session is applied **in the loop that paints the layout** | `components/tui/tui_app.py`, `_handle_session_selection()` |
| **D4** | the count of the messages of the header is the quadratic trim of the memory buffer | `chat_manager/manager.py`, `get_messages()` |
| **D5** | the **agent** pays the same quadratic trim on every turn | `llama_index/core/memory/chat_memory_buffer.py`, `get()` |

D3 is what the operator sees: the freeze, and the digit that arrives
too late.  D4 is what makes the freeze long — and D5 is what the
operator pays on every turn of the agent, whether he notices it or not.

## 5. What is *not* the cause

* **The database is not slow.**  The switch of the session takes 16 ms,
  and the list of the sessions 1 ms.  The same database answers the
  cheap count of the messages in 27 ms.
* **The tokenizer is not slow.**  The tokenizer of the agent is loaded
  once per process and cached by LlamaIndex.  Counting the tokens of
  the whole 15 MB history once takes a second — not forty.
* **The answer of the operator is not the problem.**  The rules of the
  picker (`chat_manager/session_selector.py`) are the same for the
  classic console and for the TUI, and the classic console — which
  asks in the terminal — does not freeze: it does not count the
  messages at all.

## 6. The probe

```bash
.venv/bin/python investigate/tui-session-selection/probe_session_selection_background.py
```

It reports the cost of the Enter key, the moment the pane names the
session, the moment the count reaches the header, and the number of the
frames painted while the work is done.  It restores the session of the
operator when it is done.
