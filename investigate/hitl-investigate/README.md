# HITL Investigation

Investigation into why the Human-in-the-Loop (HITL) feature never prompts the
user — **and the fix that makes it work**.

**Full report: [`INVESTIGATION_REPORT.md`](INVESTIGATION_REPORT.md)**

## TL;DR

HITL was completely inert. There were **four independent blocking defects**,
plus two secondary ones:

| # | Defect | Impact |
|---|---|---|
| 1 | `_extract_text()` can't read a `ChatResponse` — the text is in `response.message.content` | Questions are never detected |
| 2 | `CBEventType.AGENT_STEP` is never emitted by llama-index | The `on_event_start` branch is dead code |
| 3 | `AgentQuestionEvent` is sent with `ctx.send_event()` (step dispatch), but external code can't use `write_event_to_stream()` | The event is silently dropped |
| 4 | No workflow step accepts `AgentAnswerEvent` | The answer can never reach the agent |
| 5 | The callback path *and* the stream path both prompt | Double prompt (latent, masked by #1/#2) |
| 6 | `--hitl-default-answer` never reaches `HumanLoopHandler` | Timeout fallback ignores the CLI flag |

The callback wiring **was** part of the cause — but that part was already
fixed as a side effect of PR #19 (`bind_callback_manager`). Fixing the wiring
alone is **not** sufficient: with it repaired, the user is prompted but the
answer is discarded, and the prompt is duplicated.

## The fix

| Defect | Fix | Where |
|---|---|---|
| #1 | The extractor reads `response.message.content`, the text blocks, and both `raw` shapes (`{"content": …}` and `{"message": {"content": …}}`) | `components/human_loop_handler.py`, `components/hitl_agent.py` |
| #2 | The dead `AGENT_STEP` branch was removed; the handler observes the `LLM` event instead | `components/human_loop_handler.py` |
| #3 | The question is raised as an `InputRequiredEvent` **returned from a step**, so the framework publishes it to the event stream | `components/hitl_agent.py` |
| #4 | A step **waits** for the answer with `ctx.wait_for_event(AgentAnswerEvent, …)` and the answer is fed back into the scratchpad | `components/hitl_agent.py` |
| #5 | Exactly one prompt path: the `EventConsumer` prompts, the handler only observes | `components/event_consumer.py`, `components/human_loop_handler.py` |
| #6 | `--hitl-default-answer` is applied to the handler *and* the agent | `agent-torvalds.py`, `agent-torvalds-mw.py` |

The key change is architectural: `components/hitl_agent.HITLFunctionAgent`
overrides `parse_agent_output` and, when the LLM output looks like a
question, waits for the human:

```python
@step
async def parse_agent_output(self, ctx, ev):
    if not self._is_question(text):
        return await super().parse_agent_output(ctx, ev)

    answer_event = await ctx.wait_for_event(
        AgentAnswerEvent,
        waiter_event=AgentQuestionEvent(...),   # -> published to the stream
        waiter_id=f"hitl_{question_id}",
        requirements={"question_id": question_id},
        timeout=timeout + 5,
    )
    # ... feed the answer back into the scratchpad and continue
```

`AgentQuestionEvent` now subclasses `InputRequiredEvent` and
`AgentAnswerEvent` subclasses `HumanResponseEvent`, so the existing class
names and the `EventConsumer` routing are preserved while conforming to the
framework contract.

## Running the diagnostics

All scripts run from the repository root (`self-development/`) and need no
network access except `diag_live_hitl.py`.

```bash
cd self-development

# Acceptance script — asserts every defect is gone (13/13)
../.venv/bin/python investigate/hitl-investigate/verify_hitl.py

# End-to-end round-trip through the real consumer + agent (8/8)
../.venv/bin/python investigate/hitl-investigate/verify_hitl_roundtrip.py

# Root-cause diagnostics — contrast the broken and the fixed mechanism
../.venv/bin/python investigate/hitl-investigate/diag_callback_events.py
../.venv/bin/python investigate/hitl-investigate/diag_answer_path.py
../.venv/bin/python investigate/hitl-investigate/diag_event_routing.py
../.venv/bin/python investigate/hitl-investigate/diag_workflows_mechanism.py

# Live proof against a running Ollama (optional)
../.venv/bin/python investigate/hitl-investigate/diag_live_hitl.py
```

Override the model for the live script:

```bash
HITL_DIAG_MODEL=qwen3-coder:latest ../.venv/bin/python \
    investigate/hitl-investigate/diag_live_hitl.py
```

## A note on the mock

`_hitl_test_doubles.py` provides a mock LLM that mirrors the **real Ollama**
payload shape (`raw={"message": {"content": ...}}`) and the decorated streaming
path (`astream_chat`).

This matters: `MockFunctionCallingLLM.chat()` produces
`raw={"content": ...}`, a shape that the broken `_extract_text()` *would*
have handled. A test written against that mock passes while production
fails. The mock here deliberately reproduces the production shape so the
diagnostics cannot pass by accident.

## Tests

```bash
../.venv/bin/python -m pytest tests/test_hitl_roundtrip.py \
                     tests/test_hitl_integration.py -v
```

`tests/test_hitl_roundtrip.py` covers the whole round-trip through the real
event stream — the coverage the original test suite lacked, which is why four
independent blocking defects could ship together.

## Status

**Fixed** — all six defects are addressed and verified by the scripts above
and by `tests/test_hitl_roundtrip.py`.
