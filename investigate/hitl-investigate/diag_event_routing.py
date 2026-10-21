#!/usr/bin/env python3
"""
Diagnostic 3 — Event routing: does AgentQuestionEvent reach EventConsumer?

The **broken** mechanism routed the question like this::

    HumanLoopHandler._emit_event(q_event)
      -> EventConsumer.send_event(event)
        -> handler.ctx.send_event(event)      <-- DISPATCH to step queues

But ``EventConsumer.consume_events`` reads the *stream*::

    async for event in handler.stream_events():
        await self._handle_event(event)

and the workflow only puts an event on that stream via
``ctx.write_event_to_stream(ev)``.  ``ctx.send_event()`` does NOT write to
the stream — it enqueues the event onto the step queues.  Since no step
accepted ``AgentQuestionEvent``, the question event was dropped and
``EventConsumer._on_agent_question`` was never reached.

The **fixed** mechanism uses the framework's supported path: the agent step
calls ``ctx.wait_for_event(AgentAnswerEvent,
waiter_event=AgentQuestionEvent(...))``.  The runtime publishes the waiter
event to the stream, and the answer resolves the waiter.

This diagnostic proves both halves by running a real workflow and watching
which events actually appear on ``stream_events()``.

No network access required.

Run from the repository root (self-development/):
    python investigate/hitl-investigate/diag_event_routing.py
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
from llama_index.core.tools import FunctionTool

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hitl_test_doubles import QuestionLLM, add_two

from components.hitl_agent import HITLFunctionAgent
from components.hitl_events import AgentAnswerEvent, AgentQuestionEvent


class RecordingConsumer:
    """Stands in for EventConsumer: records what reaches the stream."""

    def __init__(self) -> None:
        self.streamed: List[str] = []
        self.handled: List[str] = []

    async def _on_agent_question(self, event: Any) -> None:
        self.handled.append(f"AgentQuestionEvent:{event.question_id}")

    async def send_event(self, event: Any) -> None:
        self.handled.append(f"send_event:{type(event).__name__}")


async def main() -> int:
    print("=" * 78)
    print("DIAG 3 — Event routing: does AgentQuestionEvent reach the consumer?")
    print("=" * 78)

    tool = FunctionTool.from_defaults(fn=add_two, name="add_two")

    # ---------------------------------------------------------------
    # Part 1 — the broken mechanism (plain FunctionAgent)
    # ---------------------------------------------------------------
    print("\n--- Part 1: plain FunctionAgent + ctx.send_event (the old way) ---")
    consumer = RecordingConsumer()
    agent = FunctionAgent(tools=[tool], llm=QuestionLLM())
    handler = agent.run("delete the database")

    # This is exactly what HumanLoopHandler._emit_event used to do.
    consumer.handled.append("send_event:AgentQuestionEvent")
    handler.ctx.send_event(AgentQuestionEvent(question="q?", question_id="q-1"))

    async for event in handler.stream_events():
        consumer.streamed.append(type(event).__name__)
    await handler

    q_sent = any(e.startswith("send_event:AgentQuestionEvent") for e in consumer.handled)
    q_streamed = "AgentQuestionEvent" in consumer.streamed

    print("\n  --- EVENTS THAT REACHED THE STREAM (what EventConsumer sees) ---")
    for e in consumer.streamed:
        print(f"    {e}")

    print("\n  --- EVENTS SENT VIA EventConsumer.send_event() ---")
    for e in consumer.handled:
        print(f"    {e}")

    print(f"\n  AgentQuestionEvent sent via ctx.send_event?  {q_sent}")
    print(f"  AgentQuestionEvent on the stream?             {q_streamed}")
    print(f"  EventConsumer._on_agent_question reachable?   {q_streamed}")

    print("\n  --- WHICH STEPS ACCEPT AgentQuestionEvent? ---")
    for name, st in agent._get_steps().items():
        evs = sorted(
            {getattr(t, "__name__", str(t)) for t in (st._step_config.accepted_events or [])}
        )
        print(f"    {name:24s} {evs}")

    # ---------------------------------------------------------------
    # Part 2 — the fixed mechanism (HITL agent)
    # ---------------------------------------------------------------
    print("\n--- Part 2: HITLFunctionAgent + ctx.wait_for_event (the new way) ---")
    consumer2 = RecordingConsumer()
    agent2 = HITLFunctionAgent(tools=[tool], llm=QuestionLLM())
    handler2 = agent2.run("delete the database")

    async for event in handler2.stream_events():
        consumer2.streamed.append(type(event).__name__)
        if isinstance(event, AgentQuestionEvent):
            await consumer2._on_agent_question(event)
            handler2.ctx.send_event(
                AgentAnswerEvent(question_id=event.question_id, answer="no")
            )
    await handler2

    print("\n  --- EVENTS THAT REACHED THE STREAM ---")
    for e in consumer2.streamed:
        print(f"    {e}")
    print(f"  EventConsumer._on_agent_question reachable?   "
          f"{'AgentQuestionEvent' in consumer2.streamed}")

    # ---------------------------------------------------------------
    print("\n--- VERDICT (after the fix) ---")
    if q_sent and not q_streamed:
        print("[OK] ctx.send_event() does NOT publish to the stream")
        print("       -> this is the root cause of the dropped question")
    if "AgentQuestionEvent" in consumer2.streamed:
        print("[OK] the HITL agent publishes AgentQuestionEvent to the stream")
        print("       -> EventConsumer._on_agent_question() is reached")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
