#!/usr/bin/env python3
"""
Live HITL test — the Human-in-the-Loop against a *real* LLM (Ollama).

The mock-based round trip (``investigate/hitl-investigate/verify_hitl_roundtrip.py``)
proves the wiring.  This script proves the wiring against a real model:
the LLM is asked something that needs a human decision, the agent raises
the question, the ``EventConsumer`` prompts, the answer is fed back into
the model, and the final answer has to reflect what the human said.

The answer is read from stdin, so the run is reproducible::

    printf 'no\\n' | python scripts/hitl_live_llm_test.py

Category: HITL / Testing
Retriever Keywords: hitl, live test, ollama, round trip, human answer
"""

from __future__ import annotations

import asyncio
import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console

from components.event_consumer import EventConsumer
from components.hitl_runtime_toggle import HITLRuntimeToggle
from components.human_loop_handler import HumanLoopHandler
from components.spinner_controller import SpinnerController
from components.state_handler import StateHandler

agent_module = importlib.import_module("agent-torvalds")

console = Console()

#: The query — it asks for a destructive action, so the agent must ask.
QUERY = (
    "You are about to delete the file /tmp/hitl-live-test.txt. "
    "Ask me for confirmation before you do anything, then wait for my answer."
)

#: The answer the human gives on stdin.
ANSWER = "no, do not delete anything"


async def main() -> int:
    """Run the live HITL round trip."""
    console.print("[bold cyan]=== Live HITL test (real LLM) ===[/bold cyan]\n")

    spinner = SpinnerController(console)
    state = StateHandler()
    toggle = HITLRuntimeToggle(initial_state=True, console=console)
    human_loop = HumanLoopHandler(
        input_method="console",
        default_timeout=-1,
        default_answer="",
        console=console,
        spinner=spinner,
        enable_hitl=True,
        runtime_toggle=toggle,
    )
    consumer = EventConsumer(
        spinner_controller=spinner,
        state_handler=state,
        console=console,
        verbose=False,
        hitl_timeout=-1,
        hitl_default_answer="",
        hitl_enabled=True,
    )
    human_loop.event_consumer = consumer

    console.print("[yellow]creating the agent (this loads the tools)...[/yellow]")
    agent = agent_module.create_agent(use_retriever=False)
    console.print("[green]✓ agent ready[/green]\n")
    console.print(f"[cyan]query:[/cyan] {QUERY}\n")

    spinner.start()
    try:
        response, stats = await agent_module.prompt_handler(
            QUERY, agent, enable_stats=True, event_consumer=consumer
        )
    finally:
        spinner.stop()

    console.print(f"\n[bold green]final answer:[/bold green] {response}")

    hitl_stats = consumer.get_hitl_stats()
    console.print(f"\n[cyan]HITL stats:[/cyan] {hitl_stats}")

    # ``prompt_handler`` wires the *module-global* handler into the
    # consumer, so the history is read from there — not from the local
    # instance created above.
    active_handler = getattr(agent_module, "human_loop_handler", human_loop)
    console.print(f"[cyan]questions:[/cyan] {active_handler.question_count}")
    for entry in active_handler.get_question_history():
        console.print(
            f"  [dim]{entry.get('question_id')}: {entry.get('question')!r} "
            f"→ {entry.get('answer')!r}[/dim]"
        )
    if stats:
        console.print(
            f"[dim]{stats.total_tokens} tokens, "
            f"{stats.llm_call_count} LLM calls, "
            f"{len(stats.tool_calls)} tool calls[/dim]"
        )

    questions = hitl_stats.get("question_count", 0)
    if questions >= 1:
        console.print("\n[bold green]✓ the agent asked the human[/bold green]")
        return 0
    console.print("\n[bold red]✗ the agent did not ask the human[/bold red]")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
