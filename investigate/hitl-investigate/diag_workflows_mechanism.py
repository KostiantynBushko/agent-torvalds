#!/usr/bin/env python3
"""
Diagnostic 5 — The correct HITL mechanism in `workflows`.

This diagnostic establishes the *architecturally correct* way to implement
HITL against a `workflows`-based agent, and contrasts it with what the
current implementation does.

Supported mechanism (`workflows`):

    class MyAgent(FunctionAgent):
        @step
        async def ask_human(self, ctx, ev: AgentOutput) -> InputRequiredEvent:
            return InputRequiredEvent(prefix="...")      # auto-written to the STREAM

        @step
        async def resume(self, ctx, ev: HumanResponseEvent) -> StopEvent:
            return StopEvent(result=ev.response)         # CONSUMES the answer

    # caller side
    async for ev in handler.stream_events():
        if isinstance(ev, InputRequiredEvent):
            handler.ctx.send_event(HumanResponseEvent(response=...))

Key properties:

  * ``InputRequiredEvent`` returned from a step is *automatically* written to
    the event stream (no ``write_event_to_stream`` needed).
  * ``HumanResponseEvent`` sent from outside via ``ctx.send_event`` IS
    dispatched to a step that accepts it — so the answer really does reach
    the agent.

Contrast with the current implementation:

  * ``AgentQuestionEvent`` is sent from *outside* with ``ctx.send_event``,
    which only dispatches to step queues; no step accepts it, and external
    code cannot call ``write_event_to_stream`` at all.  It is dropped.
  * ``AgentAnswerEvent`` is likewise sent from outside and no step accepts
    it, so the answer never reaches the agent.

This diagnostic proves both halves.

No network access required.

Run from the repository root (self-development/):
    python investigate/hitl-investigate/diag_workflows_mechanism.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, List

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.callbacks import CallbackManager
from llama_index.core.tools import FunctionTool
from llama_index.core.agent.workflow import AgentOutput
from workflows import Context, step
from workflows.events import Event, HumanResponseEvent, InputRequiredEvent, StopEvent

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _hitl_test_doubles import QuestionLLM, add_two

from components.hitl_events import AgentAnswerEvent, AgentQuestionEvent


class HumanInputEvent(InputRequiredEvent):
    """A question for the human, expressed as the supported terminal event."""

    question: str = ""
    question_id: str = ""


class HITLAgent(FunctionAgent):
    """Agent with a genuine HITL round-trip."""

    @step
    async def ask_human(self, ctx: Context, ev: AgentOutput) -> InputRequiredEvent:
        """Return an InputRequiredEvent -> automatically written to the stream."""
        return HumanInputEvent(
            prefix="Agent needs input: ",
            question="Shall I delete the database?",
            question_id="q-1",
        )

    @step
    async def resume(self, ctx: Context, ev: HumanResponseEvent) -> StopEvent:
        """Consume the human's answer and finish."""
        return StopEvent(result=f"answer received: {ev.response}")


async def main() -> int:
    print("=" * 78)
    print("DIAG 5 — The correct HITL mechanism in `workflows`")
    print("=" * 78)

    # ---------------------------------------------------------------
    # Part 1 — the supported mechanism round-trip
    # ---------------------------------------------------------------
    print("\n--- Part 1: InputRequiredEvent / HumanResponseEvent round-trip ---")

    llm = QuestionLLM()
    tool = FunctionTool.from_defaults(fn=add_two, name="add_two")
    agent = HITLAgent(tools=[tool], llm=llm)

    streamed: List[str] = []
    answers_seen: List[str] = []

    handler = agent.run("delete the database")
    async for event in handler.stream_events():
        streamed.append(type(event).__name__)
        if isinstance(event, HumanInputEvent):
            print(f"  stream: {type(event).__name__} -> {event.question!r}")
            # This is what the caller does: send the answer back.
            handler.ctx.send_event(
                HumanResponseEvent(response="yes, go ahead")
            )

    result = await handler
    answers_seen.append(str(getattr(result, "result", result)))
    print(f"\n  events on stream: {streamed}")
    print(f"  final result    : {answers_seen[0]!r}")

    ok1 = "HumanInputEvent" in streamed
    ok2 = "yes, go ahead" in answers_seen[0]
    print(f"\n  [OK] question reached the stream : {ok1}")
    print(f"  [OK] answer consumed by the agent: {ok2}")

    # ---------------------------------------------------------------
    # Part 2 — what the current implementation does
    # ---------------------------------------------------------------
    print("\n--- Part 2: current implementation (AgentQuestionEvent) ---")

    llm2 = QuestionLLM()
    agent2 = FunctionAgent(tools=[tool], llm=llm2)
    handler2 = agent2.run("delete the database")

    dropped: List[str] = []
    try:
        handler2.ctx.send_event(
            AgentQuestionEvent(question="q?", question_id="q-1")
        )
    except Exception as exc:
        dropped.append(f"raised {type(exc).__name__}: {exc}")
    print(f"  ctx.send_event(AgentQuestionEvent) -> {dropped or 'accepted (no error)'}")

    try:
        handler2.ctx.write_event_to_stream(AgentQuestionEvent(question="q?", question_id="q-1"))
    except Exception as exc:
        dropped.append(f"write_event_to_stream raised {type(exc).__name__}: {exc}")
    print(f"  ctx.write_event_to_stream(...)      -> {dropped[-1] if dropped else 'accepted'}")

    streamed2: List[str] = []
    async for event in handler2.stream_events():
        streamed2.append(type(event).__name__)
    await handler2

    print(f"\n  events on stream: {streamed2}")
    print(f"  AgentQuestionEvent on stream? {'AgentQuestionEvent' in streamed2}")

    # ---------------------------------------------------------------
    # Part 3 — can a step consume AgentAnswerEvent if we add one?
    # ---------------------------------------------------------------
    print("\n--- Part 3: a step CAN consume AgentAnswerEvent ---")

    class AnswerAwareAgent(FunctionAgent):
        """A step that consumes AgentAnswerEvent.

        The workflow validator requires the consumed event to also be
        *produced* somewhere, so the agent re-emits it from the output step
        (exactly the pattern a real fix would use).
        """

        @step
        async def produce_answer(self, ctx: Context, ev: AgentOutput) -> AgentAnswerEvent:
            return AgentAnswerEvent(
                question_id="q-1", answer="yes, go ahead", was_timeout=False
            )

        @step
        async def wait_for_answer(self, ctx: Context, ev: AgentAnswerEvent) -> StopEvent:
            return StopEvent(result=f"got answer: {ev.answer}")

    agent3 = AnswerAwareAgent(tools=[tool], llm=QuestionLLM())
    handler3 = agent3.run("delete the database")
    res3 = await handler3
    got = str(getattr(res3, "result", res3))
    print(f"  final result: {got!r}")
    ok3 = "yes, go ahead" in got
    print(f"  [OK] a step CAN consume AgentAnswerEvent: {ok3}")

    print("\n--- SUMMARY (after the fix) ---")
    print(f"  InputRequiredEvent reaches the stream      : {'OK' if ok1 else 'FAIL'}")
    print(f"  HumanResponseEvent consumed by a step      : {'OK' if ok2 else 'FAIL'}")
    print(f"  AgentQuestionEvent reaches the stream      : "
          f"{'OK (via ctx.wait_for_event)' if 'AgentQuestionEvent' in streamed2 else 'FAIL (ctx.send_event is dropped)'}")
    print(f"  AgentAnswerEvent consumable by a step      : {'OK' if ok3 else 'FAIL'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
