# Investigation: Agent Cache `request_stats` Always Zero

**Date**: 2026-10-20
**Status**: Investigation complete — root cause identified and empirically proven
**Location**: `self-development/investigate/agent-cache-zero-stats/`
**Affected file**: `~/.cache/torvalds/agent_cache.json` → `request_stats[]`
**Symptom**: `tool_call_count`, `completion_tokens`, `total_tokens` (and `llm_calls`, `prompt_tokens`, `tools_used`) are **always 0**, while `duration_ms` is correct.

---

## 1. Objective

Determine why the persisted per-request statistics written by
`agent_cache_system.save_request_stats()` always contain zeros for every
token/tool metric, and identify the correct fix in the callback wiring.

---

## 2. Symptom Confirmation

All 410 persisted entries in the live cache file have **zero** for every
metric except duration:

```
total entries: 410
entries with llm_calls>0        : 0
entries with total_tokens>0     : 0
entries with tool_call_count>0  : 0
entries with duration_ms>0      : 410
```

Representative entry (last 8 of the file, all identical in shape):

```json
{
  "timestamp": "2026-10-20T21:15:29.896003+00:00",
  "request_id": "cab12ce4",
  "duration_ms": 47881.25,
  "llm_calls": 0,
  "total_tokens": 0,
  "prompt_tokens": 0,
  "completion_tokens": 0,
  "tools_used": [],
  "tool_call_count": 0,
  "error_count": 0
}
```

**Key observation**: `duration_ms` is populated correctly. This is decisive —
duration is computed by `RequestStatsHandler.finalize()` from
`time.monotonic()` deltas, *not* from any callback event. Every other metric is
populated **exclusively** from callback events. Therefore the callback handler
is never receiving a single event, while the handler object itself is alive
and working.

---

## 3. Root Cause

### 3.1 Primary cause — the `callback_manager` passed to `agent.run()` is silently discarded

`agent-torvalds.py:731` builds a per-request callback manager and hands it to
the agent runner:

```python
# agent-torvalds.py:719-747
callback_handlers = []
if enable_stats:
    request_id = str(uuid.uuid4())[:8]
    stats_handler = RequestStatsHandler(request_id=request_id, user_query=cmd)
    callback_handlers.append(stats_handler)
callback_handlers.append(human_loop_handler)

callback_manager = CallbackManager(callback_handlers)
...
workflow_handler = agent.run(
    cmd,
    memory=chat_memory,
    max_iterations=MAX_ITERATIONS,
    callback_manager=callback_manager,   # <-- DISCARDED
)
```

`FunctionAgent` is a **Pydantic model** (`BaseWorkflowAgent(Workflow, BaseModel)`).
Its declared fields are:

```
['name', 'description', 'system_prompt', 'tools', 'tool_retriever',
 'can_handoff_to', 'llm', 'initial_state', 'state_prompt', 'output_cls',
 'structured_output_fn', 'streaming', 'early_stopping_method']
```

There is **no `callback_manager` field**. Pydantic's default `extra` behaviour
for this model is to **ignore** unknown keyword arguments — no error, no
warning. The object is accepted and the value vanishes.

Verified directly:

```python
>>> agent = FunctionAgent(tools=[], llm=MockLLM(), callback_manager=cm)
>>> hasattr(agent, 'callback_manager')
False
```

Furthermore, `BaseWorkflowAgent.run()` forwards unknown `**kwargs` into
`AgentWorkflowStartEvent`, and the workflow runtime never reads
`callback_manager` back out of it. A repo-wide grep of the installed
`llama_index/core/agent/` package confirms:

```
$ grep -rn "callback_manager" .venv/.../llama_index/core/agent/
(no results)
```

**Conclusion**: the `CallbackManager` containing `RequestStatsHandler` is
constructed, passed, accepted, and then dropped on the floor. The stats
handler is never subscribed to anything.

### 3.2 Secondary cause — the LLM has its own, separate `callback_manager`

In LlamaIndex 0.14.x, `llm_chat_callback()` (the decorator on
`Ollama.chat`/`Ollama.achat`) resolves the callback manager from the **LLM
instance**, not from the agent:

```python
# llama_index/core/llms/callbacks.py:42-47
@contextmanager
def wrapper_logic(_self: Any) -> Generator[CallbackManager, None, None]:
    callback_manager = getattr(_self, "callback_manager", None)
    if not isinstance(callback_manager, CallbackManager):
        _self.callback_manager = CallbackManager()
    yield _self.callback_manager
```

`BaseLLM.callback_manager` defaults to `CallbackManager([])` — **empty**.

So there are two independent callback managers in play:

| Holder | Contains `RequestStatsHandler`? | Receives LLM events? |
|---|---|---|
| `agent.run(callback_manager=...)` | no (discarded by pydantic) | n/a |
| `llm.callback_manager` | no (empty by default) | **yes — this is the live one** |

The stats handler is attached to the *dead* manager; the *live* manager has no
handlers. Result: zero events, zero metrics.

This is compounded by the fact that **both** entrypoints call `create_agent()`
*without* a callback manager:

```python
# agent-torvalds.py:1053-1058
agent = create_agent(
    use_retriever=not args.full and not args.select,
    top_k=args.top_k,
    system_prompt=system_prompt,
    tools=selected_tools,
)   # <-- no callback_manager= argument

# agent-torvalds-mw.py:848-853 and 1222-1228 — same
```

So `create_agent()`'s `callback_manager` parameter defaults to `None`, and the
`Ollama(...)` instance it builds ends up with `CallbackManager([])`:

```python
>>> llm = MockLLM(callback_manager=None)
>>> llm.callback_manager.handlers
[]
```

Even the *intent* expressed in `create_agent()`'s docstring — *"callback
manager passed to the LLM at creation time so that LLM-level events ... propagate
through stats and HITL handlers"* — is never realised, because the manager is
never supplied at creation time.

### 3.3 Tertiary cause — `CBEventType.FUNCTION_CALL` is never emitted

`RequestStatsHandler` counts tool calls by listening for
`CBEventType.FUNCTION_CALL`:

```python
# components/stats_handler.py:114-118
EVENTS_OF_INTEREST: list[CBEventType] = [
    CBEventType.LLM,
    CBEventType.FUNCTION_CALL,
    CBEventType.EXCEPTION,
]
```

But `CBEventType.FUNCTION_CALL` is **never emitted anywhere** in the installed
packages:

```
$ grep -rn "CBEventType.FUNCTION_CALL" .venv/.../site-packages/ --include=*.py
(no results)
```

The `FunctionAgent` workflow emits **no** callback events of its own. Tool
execution is reported through the *workflow event stream* (`ToolCall` /
`ToolCallResult` events written via `ctx.write_event_to_stream(...)`), which is
a completely different mechanism from the callback manager.

Verified:

```python
$ grep -n "on_event_start|on_event_end|CBEventType" \
    .venv/.../llama_index/core/agent/workflow/base_agent.py
(no results)
```

Consequence: even with the callback wiring fixed, `tool_call_count` and
`tools_used` would **still** be 0, because there is no event source for them.

### 3.4 What *does* work

`components/event_consumer.py` already receives `ToolCall` and
`ToolCallResult` events from the workflow stream and tracks them in
`StateHandler` (`state.get('tool_calls')` increments correctly — see
`components/event_consumer.py:392-440` and `components/state_handler.py:167`).

So the tool-call truth already exists — it just never reaches
`RequestStatsHandler`.

---

## 4. Empirical Proof

### 4.1 Reproduction of the exact production symptom

Using the same wiring as `agent-torvalds.py` (mock LLM, no network):

```
RESULT via agent.run(callback_manager=...) :
{'llm_call_count': 0, 'total_prompt_tokens': 0, 'total_completion_tokens': 0,
 'total_tokens': 0, 'tools_used': [], 'tool_call_count': 0, 'error_count': 0}

agent.callback_manager exists?: False
llm.callback_manager handlers: []
```

Identical to the cache file entries.

### 4.2 Live proof with real Ollama

Ollama `0.33.2` running locally, model `qwen2.5-coder:7b-instruct-q4_K_M`:

| Wiring | llm_calls | prompt | completion | total | tools |
|---|---|---|---|---|---|
| **BROKEN** — `agent.run(callback_manager=cm)` only | **0** | 0 | 0 | **0** | 0 |
| **FIXED** — `llm.callback_manager = cm` | **1** | 35 | 11 | **46** | 0 |

The token extraction logic in `RequestStatsHandler._on_llm_end()` is **correct**
— it reads `payload[EventPayload.RESPONSE].raw["usage"]`, and
`Ollama._get_response_token_counts()` populates `raw["usage"]` with
`prompt_tokens` / `completion_tokens` / `total_tokens`. The extraction simply
never gets a chance to run.

### 4.3 Per-request callback manager swap works and is repeatable

Because the agent is created once at startup but stats are per-request, the
LLM's callback manager must be re-pointed on each request:

```
initial llm.cm handlers: []
req0: llm_calls=1 tokens=42
req1: llm_calls=1 tokens=42
```

---

## 5. Root Cause Summary

| # | Cause | Location | Effect |
|---|---|---|---|
| 1 | `FunctionAgent(callback_manager=...)` silently dropped by pydantic (`extra='ignore'`, no such field) | `agent-torvalds.py:530`, `agent-torvalds-mw.py:529`, `agent_tool_retriever.py:163` | Stats handler subscribes to a dead manager → **all** metrics 0 |
| 2 | LLM has its own independent `callback_manager` (default `CallbackManager([])`) | `llama_index/core/base/llms/base.py:31-36` | The *live* manager has no handlers |
| 3 | `CBEventType.FUNCTION_CALL` is never emitted by llama-index 0.14.25 | `components/stats_handler.py:116` | `tool_call_count` / `tools_used` have **no event source** even after fixing 1 & 2 |

**The one-line summary**: the stats handler is attached to a `CallbackManager`
that LlamaIndex throws away, while the `CallbackManager` that actually receives
events (the one on `llm`) is empty — and tool calls aren't published as
callback events at all.

---

## 6. Proposed Fix

### Fix A — point the LLM's callback manager at the per-request stats handler

The LLM's own `callback_manager` must carry the `RequestStatsHandler`. Because
the agent is created once but requests are many, the manager has to be swapped
per request (in `prompt_handler`, right before `agent.run(...)`):

```python
# agent-torvalds.py — in prompt_handler(), before agent.run()
if stats_handler:
    # The LLM's callback_manager is the one llama-index actually uses
    # (llm_chat_callback resolves it from the LLM instance).
    # FunctionAgent(callback_manager=...) is silently ignored by pydantic.
    agent.llm.callback_manager = callback_manager
```

Alternatively, attach the handler to the LLM once at creation time
(`Ollama(..., callback_manager=...)`) and let the handler instance be
per-request — but the current design creates a fresh `RequestStatsHandler` per
request, so the swap is the minimal, safest change.

**Effect**: `llm_calls`, `total_prompt_tokens`, `total_completion_tokens`,
`total_tokens` become populated.

### Fix B — source tool calls from the workflow event stream

`CBEventType.FUNCTION_CALL` does not exist in this llama-index version, so the
stats handler must receive tool calls another way. Two viable options:

* **B1 (recommended)** — have `EventConsumer` (which already receives
  `ToolCall` events) forward them into the stats handler. `EventConsumer._on_tool_call`
  is the natural hook; it can call a new
  `RequestStatsHandler.record_tool_call(tool_name, duration_ms)` method.
* **B2** — wrap each tool with a `FunctionTool` callback
  (`FunctionTool.from_defaults(..., callback=...)`) that reports into the stats
  handler. The `callback` fires on every tool invocation and gives the
  tool name plus the result.

**Effect**: `tool_call_count` and `tools_used` become populated.

### Fix C — defensive normalisation in `save_request_stats`

Independently of A and B, `agent_cache_system.save_request_stats()` should not
write `None` where a number is expected, and should tolerate a missing key:

```python
"total_tokens": stats_dict.get("total_tokens") or 0,
"prompt_tokens": stats_dict.get("total_prompt_tokens") or 0,
"completion_tokens": stats_dict.get("total_completion_tokens") or 0,
```

Currently `.get("total_tokens")` returns `None` (not `0`) when the key is
absent, which makes `get_stats_summary()`'s `sum(s.get("total_tokens", 0))`
raise `TypeError` on `None` — swallowed by the bare `except Exception` and
surfacing as `{"error": ...}` instead of a summary.

Verified:

```python
>>> sum([{'total_tokens': None}].__iter__() and
...     (s.get('total_tokens', 0) for s in [{'total_tokens': None}]))
TypeError: unsupported operand type(s) for +: 'int' and 'NoneType'
```

Note: with the current `to_dict()` shape this is latent rather than active —
`to_dict()` always emits the key — but it becomes reachable as soon as any
caller passes a partial dict, and it is a trap worth closing while the area is
being touched.

---

## 7. Files Involved

| File | Role |
|---|---|
| `agent_cache_system.py:335-370` | `save_request_stats()` — writes the zeroed entries |
| `agent_cache_system.py:378-410` | `get_stats_summary()` — aggregates them |
| `components/stats_handler.py:126-300` | `RequestStatsHandler` — the handler that never fires |
| `components/stats_handler.py:114-118` | `EVENTS_OF_INTEREST` — includes the never-emitted `FUNCTION_CALL` |
| `agent-torvalds.py:719-747` | Builds `CallbackManager` + calls `agent.run(callback_manager=...)` |
| `agent-torvalds.py:491-530` | `create_agent()` — passes `callback_manager` to `Ollama`/`FunctionAgent` |
| `agent-torvalds-mw.py:729-744` | Same pattern in the multi-window entrypoint |
| `agent_tool_retriever.py:163` | Same pattern in the retriever agent factory |
| `components/event_consumer.py:392-440` | Already receives `ToolCall` events (source for Fix B) |
| `components/tui/tui_app.py:403-404` | TUI persists the same zeroed stats |

---

## 8. Verification Plan

1. Run one request through the agent with a tool-using prompt.
2. Assert `llm_call_count > 0` and `total_tokens > 0` in the rendered stats panel.
3. Assert `tool_call_count > 0` and `tools_used` non-empty.
4. Check `~/.cache/torvalds/agent_cache.json` → newest `request_stats` entry has
   non-zero `total_tokens` and `tool_call_count`.
5. Run `get_stats_summary()` and confirm it returns a summary (not `{"error": ...}`).
6. Regression: run 3 consecutive requests to confirm the per-request callback
   manager swap does not leak state between requests (each entry must reflect
   only its own request).

---

## 9. Implementation Status

All three fixes are **implemented and verified**.

| Fix | Where | Status |
|---|---|---|
| **A** | `components/stats_handler.py` → `bind_callback_manager()`; called from `agent-torvalds.py`, `agent-torvalds-mw.py`, `agent_tool_retriever.py` | Done |
| **B** | `components/stats_handler.py` → `begin_tool_call()` / `end_tool_call()` / `record_tool_call()`; fed by `components/event_consumer.py` → `set_stats_handler()` | Done |
| **C** | `agent_cache_system.py` → `_as_number()` used by `save_request_stats()` and `get_stats_summary()` | Done |

### 9.1 Verification results (live, Ollama 0.33.2)

`verify_end_to_end.py` drives the production wiring (per-request
`CallbackManager` → `bind_callback_manager` → `EventConsumer` → stats
handler → `save_request_stats`):

```
llm_call_count             = 2
total_prompt_tokens        = 711
total_completion_tokens    = 50
total_tokens               = 761
tool_call_count            = 1
tools_used                 = ['add_two']
error_count                = 0
```

Persisted cache entry (newest `request_stats` in
`~/.cache/torvalds/agent_cache.json`):

```json
{
  "duration_ms": 3342.03,
  "llm_calls": 2,
  "total_tokens": 761,
  "prompt_tokens": 711,
  "completion_tokens": 50,
  "tools_used": ["add_two"],
  "tool_call_count": 1,
  "error_count": 0
}
```

`get_stats_summary()` returns a real summary (not `{"error": ...}`) even
though the cache still holds legacy entries written with `None` values.

### 9.2 Important caveat — the model must support native function calling

`tool_call_count` stays 0 for models that emit the tool call as **plain
text** instead of a native function call. This is a property of the model,
not of the stats wiring.

Measured on the same wiring:

| Model | ToolCall events | `tool_call_count` |
|---|---|---|
| `qwen3-coder:latest` (native tools) | `ToolCall` + `ToolCallResult` | **1** |
| `qwen2.5-coder:7b-instruct-q4_K_M` (text only) | none — output was the literal string `{"name": "add_two", ...}` | **0** |

When the model answers with the raw JSON text, the agent never enters the
tool-calling branch, so no `ToolCall` event is produced and there is nothing
for the stats handler to count. `llm_call_count` and the token counters are
populated correctly in both cases.

### 9.3 Side effect — HITL detection is revived too

`HumanLoopHandler` was attached to the *same* (previously dead) callback
manager, so it never received an event either. Binding the manager to the
LLM therefore also revives HITL question detection.

This was checked for a double-prompt regression (the handler prompts the
user *and* emits `AgentQuestionEvent`, which the `EventConsumer` also
consumes and can prompt for):

* real flow, forced text extraction → **1** prompt (no double prompt)
* real flow, normal extraction → 0 prompts

The reason the normal path is inert is that `_extract_text()` does not
handle `ChatResponse` — the text lives in `response.message.content`, while
`_extract_text()` only looks at `.text` (absent), `.raw` (a dict without
`content`) and the object itself. It therefore returns `""` and
`_is_question("")` is `False`. This is pre-existing behaviour, left
unchanged here because fixing it would newly enable HITL prompting in
production — a behaviour change that needs its own decision.

### 9.4 Concurrency correction

The workflow runs one `call_tool` step per tool call **concurrently**, so
several calls to the same tool can be in flight simultaneously. Keying the
pending tool starts by tool name alone collapsed them into a single entry
and mis-paired the timings. The pending starts are now keyed by `tool_id`
with a FIFO queue per key, and `EventConsumer` passes `event.tool_id`
through. Verified with two concurrent calls to the same tool:

```
tool_call_count  = 2
per-call durations (ms): [401, 402]
pending starts left     : {}
```

---

## 10. Reproduction Scripts

The scripts used to produce the evidence in section 4 are included in this
folder (`investigate/agent-cache-zero-stats/`):

* `repro_zero_stats.py` — reproduces the zeroed stats (no network required)
* `repro_fixed_stats.py` — demonstrates the fix with a mock LLM
* `repro_live_ollama.py` — live proof against a running Ollama instance
* `verify_end_to_end.py` — **full production-wiring verification** (needs Ollama)
* `diag_tool_events.py` — shows which workflow events actually arrive
* `diag_native_fc.py` — compares a native-function-calling model against a text-only one
* `diag_concurrent_tools.py` — proves concurrent same-tool calls are counted correctly
* `diag_hitl_double_prompt.py` / `diag_hitl_real_forced.py` — double-prompt regression checks
* `diag_payload_shape.py` — dumps the LLM event-end payload shape

Run them from the repository root (`self-development/`):

```bash
python investigate/agent-cache-zero-stats/repro_zero_stats.py
python investigate/agent-cache-zero-stats/repro_fixed_stats.py
python investigate/agent-cache-zero-stats/repro_live_ollama.py   # needs Ollama
python investigate/agent-cache-zero-stats/verify_end_to_end.py    # needs Ollama
```

### Automated tests

`tests/test_stats_wiring.py` covers all three fixes without needing a
network connection (uses `MockFunctionCallingLLM`):

```bash
python -m pytest tests/test_stats_wiring.py -v
```
