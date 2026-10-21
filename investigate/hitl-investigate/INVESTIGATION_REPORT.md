# Investigation: Human-in-the-Loop (HITL) Does Not Work

**Date**: 2026-10-21
**Status**: Investigation complete — 4 independent blocking defects found and empirically proven
**Location**: `self-development/investigate/hitl-investigate/`
**Affected components**: `components/human_loop_handler.py`, `components/event_consumer.py`, `components/hitl_events.py`
**Entry points**: `agent-torvalds.py`, `agent-torvalds-mw.py`
**Environment**: llama-index-core 0.14.25, llama-index-llms-ollama 0.11.x, `workflows` (bundled), Python 3.12
**Base commit**: `4d992b6` (master)

---

## 1. Objective

Determine why the HITL feature never prompts the user, and identify what is
required to make it work.

**Hypothesis carried in from the previous investigation** (the "zero stats"
fix, PR #19): the same dead-`CallbackManager` bug that zeroed the cache
statistics should also affect HITL, because `HumanLoopHandler` was attached to
the *same* discarded callback manager.

**Result**: the hypothesis is **correct but incomplete**. The callback wiring
*was* one of the causes — but it is only one of four, and it is the one that
was already fixed as a side effect. Even with the wiring repaired, HITL
remains completely non-functional for three further, independent reasons.

---

## 2. Summary of Findings

| # | Defect | Severity | Status |
|---|---|---|---|
| **1** | `_extract_text()` cannot read a `ChatResponse` — the text lives in `response.message.content`, which is never inspected | **Blocker** | Open |
| **2** | `CBEventType.AGENT_STEP` is never emitted by llama-index — the `on_event_start` branch is dead code | **Blocker** | Open |
| **3** | `AgentQuestionEvent` is sent with `ctx.send_event()` (step dispatch), but external code cannot use `write_event_to_stream()` — the event is silently dropped | **Blocker** | Open |
| **4** | No workflow step accepts `AgentAnswerEvent` — the human's answer can never reach the agent | **Blocker** | Open |
| **5** | Double prompt: the callback handler *and* the event consumer both prompt for the same question | High (latent) | Open |
| **6** | `--hitl-default-answer` is applied to the `EventConsumer` but never to `HumanLoopHandler` | Medium | Open |

**Net effect**: HITL is inert in every sense — the user is never prompted,
and even if they were, the answer would not influence the agent.

---

## 3. Root Cause Analysis

### 3.1 Defect #1 — `_extract_text()` cannot read a `ChatResponse`

`HumanLoopHandler` detects questions by pulling text out of the LLM payload
and matching it against regex patterns:

```python
# components/human_loop_handler.py:283-296
@staticmethod
def _extract_text(obj: Any) -> str:
    if isinstance(obj, str):
        return obj
    text = getattr(obj, "text", None)       # (a)
    if text:
        return str(text)
    raw = getattr(obj, "raw", None)
    if isinstance(raw, dict):
        return str(raw.get("text", raw.get("content", "")))   # (b)
    return str(obj)                        # (c)
```

The payload actually delivered to the handler is a `ChatResponse`:

```python
# llama_index/core/base/llms/types.py:1282
class ChatResponse(BaseModel):
    message: ChatMessage      # <-- the text is HERE
    raw: Optional[Any] = None
    delta: Optional[str] = None
    ...
```

Every branch of `_extract_text` misses it:

* **(a)** `ChatResponse` has **no** `.text` attribute → `None`.
* **(b)** The Ollama `raw` dict has keys
  `['created_at', 'done', 'done_reason', 'eval_count', 'eval_duration', 'load_duration', 'logprobs', 'message', 'model', 'prompt_eval_count', 'prompt_eval_duration', 'total_duration', 'usage']`.
  It has **no** `'text'` and **no** `'content'` key — the content is nested
  one level deeper at `raw["message"]["content"]` → `""`.
* **(c)** The fallback `str(obj)` returns the pydantic repr
  (`'assistant: Before I delete the database, ...'`), which is *not* the
  answer text and would not match reliably.

The result is that `_extract_text()` returns `""`, `_is_question("")` is
`False`, and the question is never detected.

**Live proof** (`diag_live_ollama.py`, real Ollama + `qwen2.5-coder:7b-instruct-q4_K_M`):

```
response text : 'Sure, I can do that! What would you like me to confirm?'
RESPONSE type : ChatResponse
has .text?    : False
.raw keys     : [... 'message' ... 'usage']
.raw['message']: Message(role='assistant', content='Sure, I can do that! What would you like me to confirm?', ...)
.raw.get('content'): None
.raw.get('text')   : None
>>> _extract_text() -> ''
>>> _is_question()  -> False

--- with the FIXED extractor ---
fixed extraction -> 'Sure, I can do that! What would you like me to confirm?'
_is_question()   -> True
```

The model *did* ask a question. The agent *did* receive it. HITL threw it
away.

> **Note on the mock trap**: `MockFunctionCallingLLM.chat()` builds
> `raw={"content": content}` — a shape that `_extract_text()` *would* have
> handled. A test written against that mock would pass while production
> fails. This is why the diagnostics in this folder use a mock that mirrors
> the real Ollama `raw` shape (`_hitl_test_doubles.py`).

### 3.2 Defect #2 — `CBEventType.AGENT_STEP` is never emitted

The handler listens for two event types:

```python
# components/human_loop_handler.py:196-232
def on_event_start(self, event_type, payload=None, event_id="", parent_id="", **kwargs):
    if event_type == CBEventType.AGENT_STEP and payload:   # <-- never happens
        ...
def on_event_end(self, event_type, payload=None, event_id="", **kwargs):
    if event_type in (CBEventType.LLM, CBEventType.AGENT_STEP) and payload:
        ...
```

`AGENT_STEP` is **defined in the enum but never emitted anywhere**:

```
$ grep -rn "AGENT_STEP" .venv/lib/python3.12/site-packages/ --include=*.py
.venv/.../llama_index/core/callbacks/schema.py:46:    AGENT_STEP = "agent_step"
```

That single line is the entire result — the enum member, and nothing else.
The `FunctionAgent` workflow emits **no** callback events of its own; agent
progress is reported through the *workflow event stream* (`AgentOutput`,
`ToolCall`, …), which is an entirely different mechanism.

Consequently the `on_event_start` branch is **dead code**. The only live
event source is `CBEventType.LLM` in `on_event_end` — and that path is
broken by Defect #1.

**Proof** (`diag_callback_events.py`):

```
All event types seen : ['llm']
AGENT_STEP emitted?  : False
```

### 3.3 Defect #3 — the question event is silently dropped

This is the subtlest defect and the direct analogue of the "zero stats" bug.

`HumanLoopHandler._handle_question()` emits the question to the consumer:

```python
# components/human_loop_handler.py:325-330
q_event = AgentQuestionEvent(question=..., question_id=..., ...)
await self._emit_event(q_event)
```

which lands in `EventConsumer.send_event()`:

```python
# components/event_consumer.py:742-743
if hasattr(self, '_current_handler') and self._current_handler:
    self._current_handler.ctx.send_event(event)
```

`ctx.send_event()` **dispatches the event to the step queues** — it does
**not** put it on the event stream:

```python
# workflows/context/external_context.py:117-129
def send_event(self, message: Event, step: str | None = None) -> None:
    """Send an event into the workflow."""
    if step is not None:
        self._workflow._validate_valid_step_message(step, message)
    self._execute_task(self._external_adapter.send_event(TickAddEvent(...)))
```

Meanwhile `EventConsumer` reads the **stream**:

```python
# components/event_consumer.py:270
async for event in handler.stream_events():
    await self._handle_event(event)
```

Only `ctx.write_event_to_stream()` populates that stream — and it is
**unavailable to external code**:

```python
# workflows/context/context.py:606, 621
def write_event_to_stream(self, ev: Event | None) -> None:
    self._require_internal(fn="write_event_to_stream").write_event_to_stream(ev)

# workflows/context/context.py:216-224
def _require_internal(self, fn: str) -> InternalContext[MODEL_T]:
    ...
    raise ContextStateError(f"{fn} is only available from within step functions.")
```

And no workflow step accepts `AgentQuestionEvent`:

```
  step aggregate_tool_results   accepts ['ToolCallResult']
  step call_tool                accepts ['ToolCall']
  step init_run                 accepts ['AgentWorkflowStartEvent']
  step parse_agent_output       accepts ['AgentOutput']
  step run_agent_step            accepts ['AgentSetup']
  step setup_agent              accepts ['AgentInput']
```

So the event is enqueued for steps that will never take it, and is
**silently discarded**. `EventConsumer._on_agent_question()` is unreachable.

**Proof** (`diag_event_routing.py`):

```
--- EVENTS THAT REACHED THE STREAM (what EventConsumer sees) ---
    AgentInput / AgentStream / AgentOutput / ToolCall / ToolCallResult / ...

--- EVENTS SENT VIA EventConsumer.send_event() ---
    send_event:AgentQuestionEvent
    send_event:AgentAnswerEvent

  AgentQuestionEvent sent via ctx.send_event?  True
  AgentQuestionEvent on the stream?             False
  EventConsumer._on_agent_question reachable?   False
```

Note the deceptive part: `ctx.send_event()` **does not raise**. The failure
is completely silent — which is exactly why the feature "does not work and
does not complain".

### 3.4 Defect #4 — the human's answer can never reach the agent

Even if Defects #1–#3 were fixed and the user answered the question, the
answer would be discarded. `AgentAnswerEvent` is sent the same way
(`ctx.send_event()`), and again no step accepts it:

```
  Any step accepts AgentAnswerEvent? False
  'wait_for_event' in function_agent.py? False
```

The `FunctionAgent` workflow has no `wait_for_event` call anywhere, and no
step that would re-inject the answer into the conversation. The agent
therefore continues as if the human had never spoken.

**This makes HITL decorative even in the best case**: the user gets asked,
the user answers, and the answer goes nowhere.

**Proof** (`diag_workflows_mechanism.py`, Part 3) — a step *can* consume
`AgentAnswerEvent` if one is added:

```
  final result: 'got answer: yes, go ahead'
  [OK] a step CAN consume AgentAnswerEvent: True
```

### 3.5 Defect #5 — double prompt (latent)

Two independent code paths prompt the user for the same question:

| Path | Location |
|---|---|
| Callback path | `HumanLoopHandler._handle_question()` → `_prompt_user()` |
| Stream path | `EventConsumer._on_agent_question()` → `console_input.prompt()` |

`HumanLoopHandler._handle_question()` both prompts the user **and** emits
`AgentQuestionEvent`; the consumer then prompts *again* for the same event.

This is currently masked because the callback path never fires (Defects #1–2).
The moment the callback path is repaired, the double prompt appears.

**Proof** (`verify_hitl.py`, section E — with the fixes applied):

```
      prompts: 2  streamed: ['AgentInput', 'AgentStream', 'AgentOutput', 'HumanInputEvent', 'StopEvent']
        prompt 1 from: HumanLoopHandler (callback path)
        prompt 2 from: EventConsumer (workflow-stream path)
```

The `investigate/agent-cache-zero-stats/diag_hitl_double_prompt.py` script
from the previous investigation also reports a single prompt — but only
because the callback path is dead, so the "real flow" it exercises never
reaches the second prompt.

### 3.6 Defect #6 — `--hitl-default-answer` never reaches the handler

The CLI value is applied to the `EventConsumer` but not to the
`HumanLoopHandler`:

```python
# agent-torvalds.py:878-882
hitl_toggle._enabled = hitl_enabled
human_loop_handler.enable_hitl = hitl_enabled
human_loop_handler.input_method = hitl_method
human_loop_handler.default_timeout = hitl_timeout
#  <-- human_loop_handler.default_answer is NEVER set
```

```python
# agent-torvalds.py:1084-1092
event_consumer = EventConsumer(
    ...,
    hitl_default_answer=hitl_default_answer,   # <-- only here
    hitl_enabled=hitl_enabled,
)
```

`HumanLoopHandler.default_answer` keeps the value it was constructed with
(the `TORVALDS_HITL_DEFAULT_ANSWER` env var, default `""`). The same gap
exists in `agent-torvalds-mw.py:1013-1016`.

### 3.7 What *is* working

For completeness, these parts are correct and should be preserved:

* The **callback wiring** — fixed in PR #19 via
  `components.stats_handler.bind_callback_manager()`. The `HumanLoopHandler`
  now genuinely receives `CBEventType.LLM` events. This was the *only* thing
  the "zero stats" fix changed for HITL, and by itself it is not enough.
* The **question-detection regexes** — `_QUESTION_PATTERNS` behaves well:

  ```
  True   'Shall I proceed?'
  True   'Do you want to continue?'
  True   'Please confirm.'
  False  'Here is the result of the build.'
  False  'The command completed successfully.'
  False  'The tests passed.'
  ```

  No false positives on ordinary assistant prose.
* The **input-type heuristics** — `_detect_input_type()` correctly maps
  password / yes-no / free-text.
* The **console & whiptail input modules** — timeout handling and default
  fallbacks are correct.
* The **runtime toggle** (`\toggle-hitl`, `\hitl-status`, …) — correctly
  wired into both the handler and the consumer.

---

## 4. Relationship to the "zero stats" investigation

The earlier investigation (PR #19) identified the dead-`CallbackManager`
bug and fixed it. Its §9.3 noted:

> "Side effect — HITL detection is revived too … The reason the normal path
> is inert is that `_extract_text()` does not handle `ChatResponse` … This is
> pre-existing behaviour, left unchanged here because fixing it would newly
> enable HITL prompting in production — a behaviour change that needs its own
> decision."

That decision is now required. The current investigation confirms the
observation and extends it: reviving HITL requires **three** further changes
beyond the text extraction (defects #2, #3, #4), otherwise the user will be
prompted for an answer that is then discarded.

---

## 5. The Correct Mechanism

The `workflows` library already has a first-class HITL mechanism, and it is
*not* the one currently used:

| | Current implementation | Supported mechanism |
|---|---|---|
| Question event | `AgentQuestionEvent` (custom) | `InputRequiredEvent` (framework) |
| Emitted by | external code via `ctx.send_event()` | **returned from a step** → auto-written to the stream |
| Answer event | `AgentAnswerEvent` (custom) | `HumanResponseEvent` (framework) |
| Delivered by | external code via `ctx.send_event()` | external code via `ctx.send_event()` → **consumed by a step** |
| Consumed by | *nothing* | a step that accepts it |
| Agent waits? | never | yes — the step is the wait |

The framework contract (`workflows/events.py:504`):

> *"Automatically written to the event stream if returned from a step. If
> returned from a step, it does not need to be consumed by other steps and
> will pass validation. It's expected that the caller will respond to this
> event and send back a `HumanResponseEvent`."*

**Proof that the supported mechanism works** (`diag_workflows_mechanism.py`,
Part 1) — a real round-trip:

```
  stream: HumanInputEvent -> 'Shall I delete the database?'
  events on stream: ['AgentInput', 'AgentStream', 'AgentOutput', 'HumanInputEvent', 'StopEvent']
  final result    : 'answer received: yes, go ahead'

  [OK] question reached the stream : True
  [OK] answer consumed by the agent: True
```

versus the current implementation (Part 2):

```
  ctx.send_event(AgentQuestionEvent) -> accepted (no error)
  ctx.write_event_to_stream(...)      -> raised ContextStateError:
                                         write_event_to_stream is only available
                                         from within step functions.
  events on stream: ['AgentInput', 'AgentStream', 'AgentOutput', 'StopEvent']
  AgentQuestionEvent on stream? False
```

---

## 6. Proposed Fix

### Fix A — teach `_extract_text()` about `ChatResponse` (defect #1)

```python
# components/human_loop_handler.py
@staticmethod
def _extract_text(obj: Any) -> str:
    """Best-effort text extraction from LlamaIndex response objects."""
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj

    # ChatResponse -> response.message.content
    message = getattr(obj, "message", None)
    if message is not None:
        content = getattr(message, "content", None)
        if content:
            return str(content)
        blocks = getattr(message, "blocks", None)
        if blocks:
            parts = [getattr(b, "text", "") for b in blocks if getattr(b, "text", None)]
            if parts:
                return "".join(parts)

    # CompletionResponse -> .text
    text = getattr(obj, "text", None)
    if text:
        return str(text)

    # raw dict shapes (Mock: {"content": ...}, Ollama: {"message": {"content": ...}})
    raw = getattr(obj, "raw", None)
    if isinstance(raw, dict):
        for key in ("text", "content"):
            if raw.get(key):
                return str(raw[key])
        msg = raw.get("message")
        if isinstance(msg, dict) and msg.get("content"):
            return str(msg["content"])
        # Ollama's raw["message"] is a pydantic Message, not a dict
        if msg is not None:
            content = getattr(msg, "content", None)
            if content:
                return str(content)

    return ""
```

**Effect**: questions are detected. *Verified* — `_is_question()` returns
`True` for the real Ollama payload.

### Fix B — remove the dead `AGENT_STEP` branch (defect #2)

`CBEventType.AGENT_STEP` is never emitted. Either delete the branch, or —
better — subscribe to the *workflow* event stream instead, where agent
output actually appears (`AgentOutput` / `AgentStream` events). The latter
is the more robust design because it also covers multi-iteration runs.

**Effect**: removes a misleading code path that can never fire.

### Fix C — route the question through the supported mechanism (defects #3, #4)

Make the question an `InputRequiredEvent` **returned from a step**, and make
the answer a `HumanResponseEvent` **consumed by a step**.

Concretely, a `HITLFunctionAgent(FunctionAgent)` that adds two steps:

```python
class HITLFunctionAgent(FunctionAgent):
    """FunctionAgent with a genuine HITL round-trip."""

    @step
    async def ask_human(self, ctx: Context, ev: AgentOutput) -> InputRequiredEvent:
        """Return the question — the framework writes it to the event stream."""
        text = extract_text(ev.response)
        if not is_question(text):
            return None            # not a question -> continue normally
        return AgentQuestionEvent(
            prefix="Agent asks: ",
            question=text,
            question_id=...,
        )

    @step
    async def resume(self, ctx: Context, ev: HumanResponseEvent) -> StopEvent:
        """Consume the human's answer and feed it back to the model."""
        ...
```

and on the consumer side:

```python
async for event in handler.stream_events():
    if isinstance(event, AgentQuestionEvent):
        answer = await prompt_user(event.question, timeout=event.timeout)
        handler.ctx.send_event(HumanResponseEvent(response=answer))
```

**Effect**: the question reaches the consumer, the answer reaches the agent,
and the agent actually waits. *Verified* in `diag_workflows_mechanism.py` and
`verify_hitl.py` section E.

> **Design note**: `AgentQuestionEvent` should subclass `InputRequiredEvent`
> (which already has the `prefix` field) and `AgentAnswerEvent` should
> subclass `HumanResponseEvent`. That keeps the existing class names and the
> `EventConsumer` routing while conforming to the framework contract.

### Fix D — pick exactly one prompt path (defect #5)

With Fix C in place, the callback path and the stream path would both
prompt. Pick one:

* **Recommended** — the **stream path** wins. It is the one that is
  guaranteed to be in sync with the agent's actual output (including the
  final answer), it can pause the spinner correctly, and it supports the
  TUI. The `HumanLoopHandler` should then be reduced to *detection only*:
  it detects the question and raises it as an event, but does not prompt.
* Alternatively, keep the callback path and make the consumer ignore
  `AgentQuestionEvent` — but then the agent still cannot wait for the
  answer, so Fix C is required regardless.

**Effect**: exactly one prompt per question. *Verified* — 2 prompts before
the fix, 1 after.

### Fix E — propagate `--hitl-default-answer` to the handler (defect #6)

```python
# agent-torvalds.py:882  and  agent-torvalds-mw.py:1016
human_loop_handler.default_timeout = hitl_timeout
human_loop_handler.default_answer = hitl_default_answer   # <-- add
```

**Effect**: the CLI flag and the `TORVALDS_HITL_DEFAULT_ANSWER` env var
behave consistently.

### Recommended implementation order

1. **Fix A** (text extraction) — smallest change, unblocks detection.
2. **Fix C** (supported mechanism) — the architectural core.
3. **Fix D** (single prompt path) — must land with C.
4. **Fix B** (remove dead branch) — cleanup, can land with C.
5. **Fix E** (default answer) — trivial.

---

## 7. Verification Plan

1. **Unit** — `_extract_text()` returns the assistant text for
   `ChatResponse` (both the Mock `raw={"content": …}` and the Ollama
   `raw={"message": {"content": …}}` shapes).
2. **Unit** — a question in the LLM output produces exactly **one**
   `AgentQuestionEvent`.
3. **Integration** — run one request whose prompt elicits a question;
   assert the user is prompted once and the answer appears in the agent's
   next LLM call.
4. **Integration** — assert the `AgentQuestionEvent` appears on
   `handler.stream_events()`.
5. **Integration** — assert the agent's final answer reflects the human's
   input (e.g. "no" aborts the deletion, "yes" proceeds).
6. **Regression** — a request with **no** question produces **zero** prompts
   and the normal output path is unaffected.
7. **Regression** — HITL disabled (`--no-hitl`, `\hitl-off`) produces zero
   prompts.
8. **Regression** — timeout path: no answer within the timeout → the default
   answer is used and the agent continues.
9. **Live** — repeat with a real Ollama model that asks a question.

---

## 8. Implementation Status

**RESOLVED** — the investigation was implemented on branch
`fix/hitl-roundtrip` (based on `master` @ `4d992b6`).

All six defects are fixed and verified:

| # | Defect | Fix | Where |
|---|---|---|---|
| 1 | `_extract_text()` cannot read a `ChatResponse` | Read `response.message.content`, the text blocks, and both `raw` shapes | `components/human_loop_handler.py`, `components/hitl_agent.py` |
| 2 | Dead `AGENT_STEP` branch | Branch removed; the handler observes the `LLM` event | `components/human_loop_handler.py` |
| 3 | The question event is dropped | The question is raised as an `InputRequiredEvent` **returned from a step** — the framework publishes it to the event stream | `components/hitl_agent.py` |
| 4 | The answer never reaches the agent | A step **waits** with `ctx.wait_for_event(AgentAnswerEvent, …)`; the answer is fed back into the scratchpad | `components/hitl_agent.py` |
| 5 | Double prompt | One prompt path: the `EventConsumer` prompts, the handler only observes | `components/event_consumer.py`, `components/human_loop_handler.py` |
| 6 | `--hitl-default-answer` never reaches the handler | Applied to the handler *and* the agent | `agent-torvalds.py`, `agent-torvalds-mw.py` |

### 8.1 What was added

* `components/hitl_agent.py` — `HITLFunctionAgent`, a `FunctionAgent` that
  raises the question on the workflow event stream and waits for the answer.
  This is the architectural core of the fix.
* `components/hitl_events.py` — `AgentQuestionEvent` now extends
  `InputRequiredEvent` and `AgentAnswerEvent` extends `HumanResponseEvent`,
  so the existing class names and the `EventConsumer` routing are preserved
  while conforming to the framework contract.
* `tests/test_hitl_roundtrip.py` — the round-trip coverage the original test
  suite lacked.

### 8.2 A side effect worth knowing

The destructive-operation question pattern had to be tightened.  The old
pattern matched the bare verbs (`delete`, `drop`, `remove`, …) anywhere in
the text, so the agent's own reply — *"Understood, I will not delete it."* —
was itself detected as a question.  With detection working, the agent would
have asked the human the same question over and over.  The pattern now
requires the verb to start a sentence, and the agent never asks the same
question twice in one run.

### 8.3 Verification

```bash
cd self-development
../.venv/bin/python investigate/hitl-investigate/verify_hitl.py          # 13/13
../.venv/bin/python investigate/hitl-investigate/verify_hitl_roundtrip.py # 8/8
../.venv/bin/python -m pytest tests/test_hitl_roundtrip.py -v           # 22 passed
```

Live proof against a real Ollama model
(`investigate/hitl-investigate/diag_live_hitl.py`):

```
🤖 Agent asks: Shall I proceed?
✅ Response sent to agent
  prompts issued : 1
  HITL stats     : {'enabled': True, 'question_count': 1, 'timeout_count': 0, ...}
  final response : Understood. No action will be taken.
  [OK] the user was prompted exactly once
  [OK] the question reached the consumer
  [OK] the answer was recorded: 'no'
```

The original text of this section is kept below for reference.

---

**Investigation only — no production code was modified.**

All findings are proven by executable diagnostics in this folder. The
acceptance script `verify_hitl.py` currently reports **12/13** checks
passing; the single failing check (E1, "exactly one prompt") is the
*expected* failure that documents Defect #5.

```
  [PASS] A1 current extractor returns empty
  [PASS] A2 _is_question() is False today
  [PASS] A3 proposed extractor recovers the text
  [PASS] A4 proposed _is_question() is True
  [PASS] B1 'agent_step' never emitted
  [PASS] B2 'llm' IS emitted (so LLM events are the only source)
  [PASS] C1 AgentQuestionEvent absent from the stream
  [PASS] C2 the send was silently accepted (no error)
  [PASS] D1 no step accepts AgentAnswerEvent
  [PASS] D2 'wait_for_event' absent from the agent module
  [FAIL] E1 exactly one prompt for one question — got 2
  [PASS] E2 question reached the stream
  [PASS] E3 answer consumed by the agent
```

---

## 9. Files Involved

| File | Role |
|---|---|
| `components/human_loop_handler.py:283-296` | `_extract_text()` — cannot read `ChatResponse` (Defect #1) |
| `components/human_loop_handler.py:196-232` | `on_event_start` / `on_event_end` — `AGENT_STEP` branch is dead code (Defect #2) |
| `components/human_loop_handler.py:325-330` | `_handle_question()` — emits the question event (Defects #3, #5) |
| `components/event_consumer.py:742-743` | `send_event()` — uses `ctx.send_event()` instead of the stream (Defect #3) |
| `components/event_consumer.py:270` | `consume_events()` — reads the stream (the mismatch) |
| `components/event_consumer.py:628-716` | `_on_agent_question()` — unreachable; also a second prompt source (Defect #5) |
| `components/hitl_events.py:45-170` | `AgentQuestionEvent` / `AgentAnswerEvent` — do not subclass the framework HITL events (Defects #3, #4) |
| `agent-torvalds.py:726-747` | Builds the callback manager and binds it to the LLM (already fixed by PR #19) |
| `agent-torvalds.py:878-882` | CLI config applied to the handler — `default_answer` missing (Defect #6) |
| `agent-torvalds-mw.py:1013-1016` | Same gap in the multi-window entry point (Defect #6) |
| `components/tui/state_bridge.py:325-420` | TUI input module — working, but unreachable today |
| `components/hitl_runtime_toggle.py` | Runtime toggle — working |

---

## 10. Reproduction Scripts

All scripts live in `investigate/hitl-investigate/` and run from the
repository root (`self-development/`).

| Script | Purpose | Needs Ollama |
|---|---|---|
| `verify_hitl.py` | **Acceptance script** — asserts every finding (12/13) | no |
| `diag_callback_events.py` | Which callback events reach the handler; `AGENT_STEP` absence; the `_extract_text` failure | no |
| `diag_answer_path.py` | Which steps accept which events; proves `AgentAnswerEvent` has no consumer | no |
| `diag_event_routing.py` | Proves `AgentQuestionEvent` never reaches the stream | no |
| `diag_workflows_mechanism.py` | Proves the supported `InputRequiredEvent`/`HumanResponseEvent` mechanism works | no |
| `diag_fix_verification.py` | Exercises the proposed fixes (FIX-1/2/3/4) | no |
| `diag_live_ollama.py` | Live proof against a real Ollama model | **yes** |

```bash
cd self-development
../.venv/bin/python investigate/hitl-investigate/verify_hitl.py
../.venv/bin/python investigate/hitl-investigate/diag_callback_events.py
../.venv/bin/python investigate/hitl-investigate/diag_answer_path.py
../.venv/bin/python investigate/hitl-investigate/diag_event_routing.py
../.venv/bin/python investigate/hitl-investigate/diag_workflows_mechanism.py
../.venv/bin/python investigate/hitl-investigate/diag_live_ollama.py   # needs Ollama
```

`_hitl_test_doubles.py` provides a mock LLM that mirrors the **real Ollama**
`raw` payload shape and the decorated streaming path, so the diagnostics
cannot pass by accident against a mock that does not match production.

### Existing tests

The pre-existing HITL tests pass because they exercise the components in
isolation and never run the real event path:

```bash
../.venv/bin/python -m pytest tests/test_hitl_events.py tests/test_hitl_integration.py -v
```

That is itself an important finding: **the current test suite gives no
coverage of the HITL round-trip**, which is why four independent blocking
defects could ship together.
