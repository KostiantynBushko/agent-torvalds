# Investigation Report: "No user query found in messages."

**Status:** root cause found, fix implemented, verified against the live model.
**Branch:** `investigate/no-user-query-error`
**Reported symptom:** `/home/kbush/torvald-log/exel.txt`

---

## 1. The symptom

```
Error: {"error":{"code":500,"message":"\n------------\nWhile executing CallExpression at
line 79, column 24 in source:\n...lti_step_tool %}↵    {{- raise_exception('No user query
found in messages.') }}↵...\n                                           ^\nError: Jinja Exception:
No user query found in messages.","type":"server_error"}} (status code: 500)
```

The request that triggered it (`user-request.txt`):

> in project folder: take a file A = OV_2026_10.xlsx file B = shtab.xlsx for person
> 'Митлушко Андрій Романович' merge entities from column 'D' in file A and column C in
> file B, the result must be in copy of file B in the project directory, the source of
> truth is file A. Original files must be untoched.

The traceback ends in `function_agent.py:122 take_step → _get_streaming_response`, i.e.
the failure happens while the agent assembles a prompt for the model.

## 2. What the error actually means

The message is **not** produced by the agent — it is raised by the **Jinja template of
the model** on the Ollama server. `ollama show --template
richardyoung/qwen3.6-27b-abliterated:Q4_K_M` contains:

```jinja
{%- set ns = namespace(multi_step_tool=true, last_query_index=messages|length - 1) %}
{%- for message in messages[::-1] %}
    {%- if ns.multi_step_tool and message.role == "user" %}
        {%- set content = render_content(message.content, false)|trim %}
        {%- if not(content.startswith('<tool_response>') and content.endswith('</tool_response>')) %}
            {%- set ns.multi_step_tool = false %}
            ...
{%- if ns.multi_step_tool %}
    {{- raise_exception('No user query found in messages.') }}
```

The template walks the messages **backwards** looking for a `user` message whose content
is *not* a `<tool_response>` wrapper. If it finds none, it refuses to render the
conversation.

`investigate/no-user-query-error/probe_trigger.py` confirms this against the running
server:

| message shape | result |
|---|---|
| plain user message | OK |
| user query + assistant tool call + tool result | OK |
| **only tool results (role `tool`)** | **500 — "No user query found in messages."** |
| **only tool results (`role=user` + `<tool_response>`)** | **500 — same error** |
| user query *after* a tool response | OK |
| assistant only | 500 — "No messages provided." |

So the error means exactly one thing: **the prompt the agent sent contained no user
request.**

## 3. Root cause

Two independent defects both lead to that state. Both are present in this codebase.

### 3.1 Primary cause — the prompt overflows the real context window

`llama_index.core.agent.workflow.FunctionAgent` never trims its scratchpad:

```python
# llama_index/core/agent/workflow/function_agent.py
scratchpad = await ctx.store.get(self.scratchpad_key, default=[])
current_llm_input = [*llm_input, *scratchpad]
```

Every tool result is appended to the scratchpad and stays there for the whole run. A
task like the one above reads a 784 KB spreadsheet, so the prompt grows quickly.

When the prompt is longer than the context window, the Ollama server **truncates it,
keeping the most recent tokens** (`--context-shift` is enabled on the server). The user
request sits at the **front** of the message list, so it is the first thing to be
discarded — and the template then raises the error.

`investigate/no-user-query-error/probe_truncation.py` reproduces this exactly: a
message list larger than the context window produces the **byte-for-byte identical**
error message from `exel.txt`.

### 3.2 The context window the agent believes in is 32× too large

This is what made the overflow so easy to hit. The model advertises a 262 144-token
context, but the server runs with **8 192**:

```
$ ollama ps
NAME                                           CONTEXT
richardyoung/qwen3.6-27b-abliterated:Q4_K_M    8192

$ ps aux | grep llama-server
... llama-server ... -c 8192 -np 1 --context-shift --keep 4
```

LlamaIndex reads the wrong number:

```python
# llama_index/llms/ollama/base.py
def get_context_window(self) -> int:
    if self.context_window == -1:
        info = self.client.show(self.model).modelinfo
        for key, value in info.items():
            if "context_length" in key:      # <- the model's MAXIMUM
                self.context_window = int(value)
```

`modelinfo.context_length` is the model's *maximum* (262 144). The value the server
actually uses is `PARAMETER num_ctx 8192` in the model's Modelfile, which LlamaIndex
never looks at. The same wrong number is also sent back to the server on every request
(`_model_kwargs` → `num_ctx: 262144`).

So the agent happily built prompts up to 262 144 tokens for a server that only has
8 192 — 32× too much.

### 3.3 Secondary cause — the chat memory can drop the user request

`ChatMemoryBuffer.get()` trims the stored history from the front and, when the window
collapses, returns `chat_history[-1:]` — whatever the last message happens to be:

```python
# llama_index/core/memory/chat_memory_buffer.py
while token_count > self.token_limit and message_count > 1:
    message_count -= 1
    while message_count > 1 and chat_history[-message_count].role in (TOOL, ASSISTANT):
        message_count -= 1
    ...
if token_count > self.token_limit or message_count <= 0:
    return chat_history[-1:]          # <- may be an assistant/tool message
```

`investigate/no-user-query-error/probe_trimming.py` runs the real trimming over every
session that is really stored in PostgreSQL. **Two of the ten sessions lose their user
request this way** and would produce the same error on their next turn:

```
chat-custom-...-38d8d8d6   1474 messages -> trimmed to 1 (assistant) -> NO USER QUERY
chat-custom-...-399ec818   542 messages -> trimmed to 1 (assistant) -> NO USER QUERY
```

## 4. Evidence from the failing run

The failing session is still in the database. Session `iks_maino`
(`chat-custom-…-df510f96`) was created at 16:04:37, the request was stored at 16:06 and
the session was last touched at 16:20:41 — a **14-minute run** that never finalised:

```
chat_sessions:  iks_maino | created 2026-10-23 16:04:37 | updated 2026-10-23 16:20:41
chatstore:     2 messages — "CONTEXT: …" (user) and the request (user)
```

Only two messages were persisted because `finalize()` (which writes the scratchpad back
to the memory) never ran — the run died in the middle. The request itself was stored
correctly, which rules out the request path and points at the prompt assembly.

## 5. The fix

### 5.1 `components/context_guard.py` (new)

A pure, testable module that selects the conversation to send:

* keeps the leading system prompt,
* keeps **the request the user actually made** (restored from `user_msg_str` when the
  chat memory trimmed it away),
* keeps the most recent assistant/tool turns for as long as they fit,
* drops older turns first, always dropping an assistant tool call together with the
  tool results that answer it,
* **truncates** a single oversized tool result instead of dropping it, so the agent
  still sees the data it just fetched,
* never returns a conversation without a user request.

`select_context_window_split()` additionally preserves the boundary between the chat
memory and the run's scratchpad, because the agent has to put the trimmed messages
back into both.

### 5.2 `components/hitl_agent.py`

`HITLFunctionAgent.take_step()` now applies the guard before every model call. The
context window is read once and cached (reading the LLM metadata costs a round-trip to
the server), and the size of the tool schemas — which are sent with every request and
also occupy prompt space — is subtracted from the budget.

### 5.3 `components/ollama_config.py`

`resolve_context_window()` / `apply_context_window()` determine the context window the
server **really** uses, in this order:

1. `TORVALDS_CONTEXT_LENGTH` — explicit override,
2. `/api/ps` — the context length of the running model,
3. `PARAMETER num_ctx` in the model's Modelfile,
4. `llm.metadata.context_window` — the model's maximum (fallback).

The value is written back to the LLM, so `llm.metadata.context_window` reports the truth
and the `num_ctx` sent with every request matches the server instead of asking for an
impossible window.

`create_agent()` in `agent-torvalds.py` and `agent-torvalds-mw.py` calls it.

## 6. Verification

### 6.1 Against the live model (`verify_fix_live.py`)

The same oversized prompt that reproduces the failure, before and after the guard:

```
conversation : 16 messages, 1.50 MB
tokens       : ~924095 (real context window 8192, budget 6554)
user query   : True
[unguarded] HTTP 500  -> "No user query found in messages."   (reproduced)
[guarded]   HTTP 200  -> the model answered
RESULT: PASS — the failure reproduces without the guard and is gone with it.
```

### 6.2 The real agent, the real model, the real Excel task

`investigate/no-user-query-error/repro_live.py` runs the real `HITLFunctionAgent`
with the real model and the real Excel toolkit against a copy of the user's
workspace.  `repro_live_unpatched.py` does the same but bypasses the guard, which
is how the agent behaved before the fix.

**Without the guard** — the original failure, reproduced end to end:

```
call 0:    132 tokens,  3 msgs
call 1:    397 tokens,  6 msgs
call 2:    580 tokens, 11 msgs
call 3: 378830 tokens, 14 msgs   <== OVER THE CONTEXT WINDOW

agent raised ResponseError: {"error":{"code":500,"message":"...raise_exception(
'No user query found in messages.') }}...","type":"server_error"}} (status code: 500)
```

**With the guard** — the prompt stays small and the run continues:

```
call 0:    132 tokens,  3 msgs
call 1:    397 tokens,  6 msgs
call 2:    580 tokens, 11 msgs
call 3:    675 tokens, 14 msgs
call 4:    658 tokens, 13 msgs
call 5:    770 tokens, 17 msgs
...
call 15:   753 tokens, 16 msgs
```

The token count plateaus instead of growing without bound, and every prompt keeps
the user request.

> Note: the live reproduction pins the model to the one from the bug report
> (`NUQ_TEST_MODEL`, default `richardyoung/qwen3.6-27b-abliterated:Q4_K_M`).
> The environment may point `TORVALDS_MODEL` at a cloud model with a 1M-token
> window, which does not reproduce the failure.

### 6.3 Tests

* `tests/test_context_guard.py` — 21 unit tests for the guard.
* `tests/test_context_guard_agent.py` — 3 integration tests that drive the real
  `HITLFunctionAgent` workflow and assert that every prompt stays inside the context
  window and keeps the user request.

```
24 passed
```

The integration test caught a real bug during development (a `NameError` on
`context_budget` that would have broken every run).

### 6.4 No regressions

The full suite was run on the branch and on a clean worktree at the base commit:

| | failed | passed |
|---|---|---|
| base (`2684e26`) | 76 | 1275 |
| branch | 76 | 1299 |

The 76 failures are pre-existing and unrelated (git toolkit, HITL runtime toggle, math
toolkit, project manager, whiptail). The branch adds 24 passing tests and breaks
nothing.

## 7. Notes and follow-ups

* The user's `TORVALDS_TOKEN_LIMIT` (the *chat memory* budget) and the *context window*
  are two different things. The previous session's report blamed the former; it is
  unrelated to this failure. `TOKEN_LIMITS` in `agent-torvalds.py:173` is dead code —
  it is never referenced.
* The scratchpad still grows without bound in `ctx.store`; only what is **sent** is
  bounded. The full transcript is still persisted by `finalize()`, which is what makes
  the chat history long-term useful.
* Raising the server's context window (`OLLAMA_CONTEXT_LENGTH=32768 ollama serve`)
  gives the agent more room, but the guard is still required: the model template will
  reject any prompt that lost its user request, whatever the window size.
* `read_xlsx_file` returning an entire workbook as a tool result is the practical
  trigger. A dedicated "read a sheet/column range" tool would keep the prompts small,
  but that is a separate change.

## 8. Files

| file | purpose |
|---|---|
| `components/context_guard.py` | the guard (new) |
| `components/hitl_agent.py` | applies the guard in `take_step` |
| `components/ollama_config.py` | resolves the real context window |
| `agent-torvalds.py`, `agent-torvalds-mw.py` | call `apply_context_window` |
| `tests/test_context_guard.py` | unit tests (new) |
| `tests/test_context_guard_agent.py` | integration tests (new) |
| `investigate/no-user-query-error/probe_trigger.py` | which message shapes the template rejects |
| `investigate/no-user-query-error/probe_trimming.py` | real sessions that lose the user query |
| `investigate/no-user-query-error/probe_truncation.py` | the server-side truncation |
| `investigate/no-user-query-error/verify_fix_live.py` | before/after against the live model |
| `investigate/no-user-query-error/harness_agent_flow.py` | records the agent's message lists |
| `investigate/no-user-query-error/harness_hitl.py` | the HITL round-trip |
| `investigate/no-user-query-error/repro_live.py` | live run of the real agent |
| `investigate/no-user-query-error/repro_live_unpatched.py` | the same run without the guard — reproduces the original failure |
| `tests/test_ollama_context_window.py` | tests for the context-window resolution |
| `investigate/no-user-query-error/repro_end_to_end.py` | end-to-end chain on real stored data |
