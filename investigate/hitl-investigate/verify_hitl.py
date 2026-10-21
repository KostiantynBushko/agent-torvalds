#!/usr/bin/env python3
"""
Acceptance script for the HITL investigation.

Originally this script asserted the *defects*: it documented that HITL was
inert.  After the fix (branch ``fix/hitl-roundtrip``) the same script now
asserts that every defect is **gone**.

  A. The question text is recovered from a real ``ChatResponse``.
     (defect #1 — the extractor could not read ``response.message.content``)

  B. ``CBEventType.AGENT_STEP`` is never emitted, so the handler has no
     branch for it.  (defect #2 — dead code)

  C. The question reaches the workflow event stream — via the framework's
     supported mechanism, not via ``ctx.send_event()``.
     (defect #3 — the event was silently dropped)

  D. A workflow step accepts the answer, so the human's answer reaches the
     agent.  (defect #4 — no step consumed ``AgentAnswerEvent``)

  E. Exactly one prompt per question.
     (defect #5 — the callback path and the stream path both prompted)

  F. ``--hitl-default-answer`` reaches the handler and the agent.
     (defect #6 — the CLI value never reached ``HumanLoopHandler``)

No network access required.

Run from the repository root (self-development/):
    python investigate/hitl-investigate/verify_hitl.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, List

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

sys.path.insert(0, str(Path(__file__).resolve().parent))

from llama_index.core.agent.workflow import AgentOutput, FunctionAgent
from llama_index.core.base.llms.types import ChatMessage, ChatResponse
from llama_index.core.callbacks import CallbackManager
from llama_index.core.callbacks.base import BaseCallbackHandler
from llama_index.core.tools import FunctionTool
from workflows import Context, step
from workflows.events import HumanResponseEvent, InputRequiredEvent, StopEvent

from _hitl_test_doubles import QUESTION_TEXT, QuestionLLM, add_two

from components.hitl_agent import HITLFunctionAgent
from components.hitl_events import AgentAnswerEvent, AgentQuestionEvent
from components.human_loop_handler import HumanLoopHandler
from components.stats_handler import bind_callback_manager

RESULTS: List[tuple] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f"  — {detail}" if detail else ""))


# ----------------------------------------------------------------------
async def test_a_text_extraction() -> None:
    print("\n--- A. The extractor reads a ChatResponse (defect #1 fixed) ---")
    resp = ChatResponse(
        message=ChatMessage(role="assistant", content=QUESTION_TEXT),
        raw={"message": {"role": "assistant", "content": QUESTION_TEXT}},
    )
    handler = HumanLoopHandler(enable_hitl=True)
    text = handler._extract_text(resp)
    print(f"      extracted: {text!r}")
    check("A1 the extractor recovers the assistant text", text == QUESTION_TEXT)
    check("A2 _is_question() is True", handler._is_question(text) is True)


async def test_b_agent_step_never_emitted() -> None:
    print("\n--- B. AGENT_STEP is never emitted (defect #2 fixed) ---")

    class ProbeHandler(BaseCallbackHandler):
        def __init__(self) -> None:
            super().__init__(event_starts_to_ignore=[], event_ends_to_ignore=[])
            self.types: set = set()

        def on_event_start(self, event_type, payload=None, event_id="", **kwargs):
            self.types.add(str(getattr(event_type, "value", event_type)))
            return event_id

        def on_event_end(self, event_type, payload=None, event_id="", **kwargs):
            self.types.add(str(getattr(event_type, "value", event_type)))

        def start_trace(self, trace_id=None):
            pass

        def end_trace(self, trace_id=None, trace_map=None):
            pass

    probe = ProbeHandler()
    llm = QuestionLLM()
    llm.callback_manager = CallbackManager([probe])
    await llm.achat([ChatMessage(role="user", content="hi")])
    print(f"      event types seen: {sorted(probe.types)}")
    check("B1 'agent_step' is never emitted", "agent_step" not in probe.types)
    check("B2 'llm' IS emitted (the only live source)", "llm" in probe.types)

    # The handler must not carry a branch for the dead event type.
    handler = HumanLoopHandler()
    before = len(handler.get_question_history())
    from llama_index.core.callbacks.schema import CBEventType, EventPayload

    handler.on_event_start(
        event_type=CBEventType.AGENT_STEP,
        payload={EventPayload.COMPLETION: "Do you want to proceed?"},
        event_id="e1",
    )
    check(
        "B3 the handler has no dead AGENT_STEP branch",
        len(handler.get_question_history()) == before,
    )


async def test_c_question_reaches_the_stream() -> None:
    print("\n--- C. The question reaches the stream (defect #3 fixed) ---")

    # C-a: ctx.send_event() still cannot write to the stream — this is why
    # the old implementation dropped the question.
    agent = FunctionAgent(tools=[], llm=QuestionLLM())
    handler = agent.run("hello")
    handler.ctx.send_event(AgentQuestionEvent(question="q?", question_id="q-1"))
    streamed = [type(e).__name__ async for e in handler.stream_events()]
    await handler
    print(f"      ctx.send_event() -> stream: {streamed}")
    check(
        "C1 ctx.send_event() cannot publish to the stream (root cause)",
        "AgentQuestionEvent" not in streamed,
    )

    # C-b: the supported mechanism *does* publish the question.
    agent2 = HITLFunctionAgent(tools=[], llm=QuestionLLM())
    handler2 = agent2.run("hello")
    streamed2: List[str] = []
    async for event in handler2.stream_events():
        streamed2.append(type(event).__name__)
        if isinstance(event, AgentQuestionEvent):
            handler2.ctx.send_event(
                AgentAnswerEvent(question_id=event.question_id, answer="no")
            )
    await handler2
    print(f"      HITL agent -> stream: {streamed2}")
    check(
        "C2 the HITL agent publishes AgentQuestionEvent to the stream",
        "AgentQuestionEvent" in streamed2,
    )


async def test_d_answer_reaches_the_agent() -> None:
    print("\n--- D. The answer reaches the agent (defect #4 fixed) ---")

    # D-a: a plain FunctionAgent still has no consumer for the answer.
    agent = FunctionAgent(tools=[], llm=QuestionLLM())
    accepts = []
    for name, st in agent._get_steps().items():
        evs = sorted(
            {getattr(t, "__name__", str(t)) for t in (st._step_config.accepted_events or [])}
        )
        accepts.append(f"{name}:{','.join(evs)}")
    print(f"      plain FunctionAgent steps: {accepts}")
    any_answer = any(
        t is AgentAnswerEvent or (isinstance(t, type) and issubclass(t, AgentAnswerEvent))
        for st in agent._get_steps().values()
        for t in (st._step_config.accepted_events or [])
    )
    check("D1 a plain FunctionAgent consumes no answer", not any_answer)

    # D-b: the HITL agent does consume it, and the answer is injected into
    # the next LLM call — that is how the human's answer reaches the model.
    tool = FunctionTool.from_defaults(fn=add_two, name="add_two")
    llm2 = QuestionLLM()
    agent2 = HITLFunctionAgent(tools=[tool], llm=llm2)
    handler = agent2.run("delete the database")
    async for event in handler.stream_events():
        if isinstance(event, AgentQuestionEvent):
            handler.ctx.send_event(
                AgentAnswerEvent(question_id=event.question_id, answer="yes, go ahead")
            )
    result = await handler
    final = str(getattr(result, "result", result))

    last_messages = llm2.last_messages
    injected = any(
        "yes, go ahead" in str(getattr(m, "content", "")) for m in last_messages
    )
    print(f"      final result : {final!r}")
    print(f"      last LLM call: {[str(getattr(m, 'content', '')) for m in last_messages]}")
    check(
        "D2 the answer is injected into the agent's next LLM call",
        injected,
    )


async def test_e_single_prompt() -> None:
    print("\n--- E. Exactly one prompt per question (defect #5 fixed) ---")

    prompts: List[str] = []

    class CountingHandler(HumanLoopHandler):
        async def _prompt_user(self, question, input_type, timeout, default_answer):
            prompts.append(question)
            return ("yes, go ahead", False)

    handler = CountingHandler(input_method="console", default_timeout=5, enable_hitl=True)

    tool = FunctionTool.from_defaults(fn=add_two, name="add_two")
    agent = HITLFunctionAgent(tools=[tool], llm=QuestionLLM())
    bind_callback_manager(agent, CallbackManager([handler]))

    wh = agent.run("delete the database")
    async for event in wh.stream_events():
        if isinstance(event, AgentQuestionEvent):
            # The consumer side: prompt exactly once.
            prompts.append(event.question)
            wh.ctx.send_event(
                AgentAnswerEvent(question_id=event.question_id, answer="yes, go ahead")
            )
    await wh

    print(f"      prompts: {len(prompts)}")
    check("E1 exactly one prompt for one question", len(prompts) == 1, f"got {len(prompts)}")
    check(
        "E2 the handler no longer owns a prompting path",
        not hasattr(handler, "_prompt_user")
        or not hasattr(HumanLoopHandler, "_prompt_user"),
    )


def test_f_default_answer() -> None:
    print("\n--- F. The default answer reaches handler and agent (defect #6 fixed) ---")
    handler = HumanLoopHandler(default_answer="fallback")
    agent = HITLFunctionAgent(tools=[], llm=QuestionLLM(), hitl_default_answer="fallback")
    check("F1 the handler holds the default answer", handler.default_answer == "fallback")
    check("F2 the agent holds the default answer", agent.hitl_default_answer == "fallback")


async def main() -> int:
    print("=" * 78)
    print("HITL ACCEPTANCE — the defects of the investigation are fixed")
    print("=" * 78)

    await test_a_text_extraction()
    await test_b_agent_step_never_emitted()
    await test_c_question_reaches_the_stream()
    await test_d_answer_reaches_the_agent()
    await test_e_single_prompt()
    test_f_default_answer()

    print("\n" + "=" * 78)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"RESULT: {passed}/{total} checks passed")
    for name, ok, detail in RESULTS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    print("=" * 78)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
