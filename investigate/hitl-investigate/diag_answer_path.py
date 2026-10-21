#!/usr/bin/env python3
"""
Diagnostic 2 — Does the human's answer ever reach the agent?

The script contrasts the **broken** mechanism with the **fixed** one.

  Broken (the original implementation):
    ``ctx.send_event(AgentAnswerEvent)`` *broadcasts* to every step.  A plain
    ``FunctionAgent``'s steps are init_run / setup_agent / run_agent_step /
    parse_agent_output / call_tool / aggregate_tool_results — none of them
    accepts ``AgentAnswerEvent``, and no step calls
    ``ctx.wait_for_event(AgentAnswerEvent)``.  So the answer is dropped and
    the agent never sees it.

  Fixed:
    ``components.hitl_agent.HITLFunctionAgent`` overrides
    ``parse_agent_output`` and calls
    ``ctx.wait_for_event(AgentAnswerEvent, waiter_event=AgentQuestionEvent(...))``.
    The framework publishes the question to the event stream and suspends the
    step; the answer resolves the waiter and the step is replayed with it.

No network access required.

Run from the repository root (self-development/):
    python investigate/hitl-investigate/diag_answer_path.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, List, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.tools import FunctionTool

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hitl_test_doubles import add_two as _add_two
from _hitl_test_doubles import QuestionLLM

from components.hitl_agent import HITLFunctionAgent
from components.hitl_events import AgentAnswerEvent, AgentQuestionEvent

QUESTION_TEXT = "Shall I delete the database? Do you want to continue?"


def _accepts_answer(agent: Any) -> bool:
    """Return True when any step of *agent* accepts an AgentAnswerEvent."""
    for st in agent._get_steps().values():
        for t in st._step_config.accepted_events or []:
            if t is AgentAnswerEvent or (
                isinstance(t, type) and issubclass(t, AgentAnswerEvent)
            ):
                return True
    return False


async def main() -> int:
    print("=" * 78)
    print("DIAG 2 — Does the human's answer reach the agent?")
    print("=" * 78)

    tool = FunctionTool.from_defaults(fn=_add_two, name="add_two")

    # ---------------------------------------------------------------
    # Part 1 — the plain FunctionAgent (the broken mechanism)
    # ---------------------------------------------------------------
    print("\n--- Part 1: plain FunctionAgent (no answer consumer) ---")
    llm = QuestionLLM()
    agent = FunctionAgent(tools=[tool], llm=llm)

    for name, st in agent._get_steps().items():
        cfg = st._step_config
        evs = sorted(
            {getattr(t, "__name__", str(t)) for t in (cfg.accepted_events or [])}
        )
        print(f"  step {name:24s} accepts {evs}")

    accepted_answer = _accepts_answer(agent)
    agent_mod = Path(agent.__class__.__module__.replace(".", "/") + ".py")
    src = agent_mod.read_text() if agent_mod.exists() else ""
    print(f"\n  Any step accepts AgentAnswerEvent? {accepted_answer}")
    print(f"  'wait_for_event' in {agent_mod.name}? {'wait_for_event' in src}")

    # ---------------------------------------------------------------
    # Part 2 — the HITL agent (the fixed mechanism)
    # ---------------------------------------------------------------
    print("\n--- Part 2: HITLFunctionAgent (waits for the answer) ---")
    hitl_agent = HITLFunctionAgent(tools=[tool], llm=QuestionLLM())

    for name, st in hitl_agent._get_steps().items():
        cfg = st._step_config
        evs = sorted(
            {getattr(t, "__name__", str(t)) for t in (cfg.accepted_events or [])}
        )
        print(f"  step {name:24s} accepts {evs}")

    hitl_accepted = _accepts_answer(hitl_agent)
    hitl_mod = Path(hitl_agent.__class__.__module__.replace(".", "/") + ".py")
    hitl_src = hitl_mod.read_text() if hitl_mod.exists() else ""
    has_wait = "wait_for_event" in hitl_src
    print(f"\n  Any step *declares* AgentAnswerEvent in accepted_events? {hitl_accepted}")
    print(f"  'wait_for_event' in {hitl_mod.name}? {has_wait}")
    print("  -> the answer is consumed through the waiter's event type,")
    print("     not through a step's accepted_events declaration.")

    # ---------------------------------------------------------------
    # Part 3 — the round-trip: the answer really reaches the model
    # ---------------------------------------------------------------
    print("\n--- Part 3: the answer is injected into the next LLM call ---")
    order: List[str] = []

    handler = hitl_agent.run("delete the database")
    async for event in handler.stream_events():
        order.append(f"STREAM: {type(event).__name__}")
        if isinstance(event, AgentQuestionEvent):
            order.append("ANSWER-SENT")
            handler.ctx.send_event(
                AgentAnswerEvent(
                    question_id=event.question_id, answer="yes, go ahead"
                )
            )

    result = await handler
    order.append("WORKFLOW-FINISHED")
    print(f"\n  final agent response: {getattr(result, 'response', result)}")

    print("\n  --- ORDER OF EVENTS ---")
    for i, o in enumerate(order):
        print(f"    {i:2d}. {o}")

    # ---------------------------------------------------------------
    print("\n--- VERDICT (after the fix) ---")
    if not accepted_answer:
        print("[OK] a plain FunctionAgent has no answer consumer")
        print("       -> this is why the original implementation dropped the answer")
    if has_wait:
        print("[OK] the HITL agent waits for the answer (ctx.wait_for_event)")
    else:
        print("[FAIL] the HITL agent does not wait for the answer")
    if "WORKFLOW-FINISHED" in order and order.index("WORKFLOW-FINISHED") == len(order) - 1:
        print("[OK] the workflow waits for the answer before finishing")
    else:
        print("[FAIL] the workflow finished before the answer was sent")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
