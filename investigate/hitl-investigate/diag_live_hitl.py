#!/usr/bin/env python3
"""
Live end-to-end proof of the HITL round-trip against a real Ollama model.

This is the production path:

  1. A real ``Ollama`` LLM is used (so the ``raw`` payload has the real
     shape ``{"message": {"role": ..., "content": ...}}`` and the streaming
     path is exercised).
  2. The real ``HITLFunctionAgent`` raises the question.
  3. The real ``EventConsumer`` prompts the user (the answer is injected
     automatically so the script can run unattended).
  4. The answer is delivered back to the agent and the agent continues.

Requires a running Ollama server.  Override the model with::

    HITL_DIAG_MODEL=<model> python investigate/hitl-investigate/diag_live_hitl.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, List

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from llama_index.core.agent.workflow import AgentOutput
from llama_index.core.tools import FunctionTool
from llama_index.llms.ollama import Ollama
from rich.console import Console

from components.event_consumer import EventConsumer
from components.hitl_agent import HITLFunctionAgent
from components.hitl_events import AgentQuestionEvent
from components.human_loop_handler import HumanLoopHandler
from components.spinner_controller import SpinnerController
from components.state_handler import StateHandler

MODEL = os.environ.get("HITL_DIAG_MODEL", "qwen2.5-coder:7b-instruct-q4_K_M")

USER_PROMPT = (
    "I want to delete the production database. "
    "Before you do anything, ask me one short confirmation question "
    "that ends with a question mark (for example: 'Shall I proceed?'). "
    "Do not answer it yourself."
)

SYSTEM_PROMPT = (
    "You are Torvalds, a technical AI assistant that interacts with the "
    "operating system.\n"
    "Operating Principles:\n"
    "Use available system interfaces and tools when performing actions.\n"
    "Request explicit confirmation before destructive or irreversible "
    "operations.\n"
    "When you need confirmation, reply with a single short question that "
    "ends with a question mark and wait for the user's answer.\n"
    "Do not call a tool to confirm; ask the user directly."
)

ANSWER = "no, do not delete anything"


def add_two(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


class AutoInput:
    """Answers the HITL prompt automatically so the script can run unattended."""

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.prompts: List[str] = []

    async def prompt(self, message: str = "", default: str = "", timeout: int = 30) -> str:
        self.prompts.append(message)
        return self.answer

    async def confirm(self, message: str = "", default_yes: bool = True, timeout: int = 30) -> bool:
        self.prompts.append(message)
        return self.answer.strip().lower() in ("y", "yes")


async def main() -> int:
    print("=" * 78)
    print(f"LIVE HITL ROUND-TRIP — model: {MODEL}")
    print("=" * 78)

    llm = Ollama(model=MODEL, request_timeout=120, temperature=0.0)

    console = Console()
    handler = HumanLoopHandler(enable_hitl=True, console=console)
    consumer = EventConsumer(
        spinner_controller=SpinnerController(console=console),
        state_handler=StateHandler(),
        console=console,
        hitl_timeout=60,
        hitl_default_answer="no",
        hitl_enabled=True,
        human_loop_handler=handler,
    )
    auto = AutoInput(ANSWER)
    consumer.console_input = auto

    agent = HITLFunctionAgent(
        tools=[FunctionTool.from_defaults(fn=add_two)],
        llm=llm,
        system_prompt=SYSTEM_PROMPT,
        hitl_enabled=True,
        hitl_default_timeout=60,
        hitl_default_answer="no",
    )

    workflow_handler = agent.run(USER_PROMPT)
    result = await consumer.consume_events(workflow_handler, USER_PROMPT)

    print("\n--- RESULT ---")
    print(f"  prompts issued : {len(auto.prompts)}")
    print(f"  HITL stats     : {consumer.get_hitl_stats()}")
    print(f"  final response : {str(result)[:400]}")

    ok = True
    if len(auto.prompts) != 1:
        print("  [FAIL] expected exactly one prompt")
        ok = False
    else:
        print("  [OK] the user was prompted exactly once")

    if consumer.get_hitl_stats()["question_count"] != 1:
        print("  [FAIL] the consumer did not see exactly one question")
        ok = False
    else:
        print("  [OK] the question reached the consumer")

    history = handler.get_question_history()
    if not history or not history[0].get("answer"):
        print("  [FAIL] the answer was not recorded in the history")
        ok = False
    else:
        print(f"  [OK] the answer was recorded: {history[0]['answer']!r}")

    print("=" * 78)
    print("RESULT:", "PASS" if ok else "FAIL")
    print("=" * 78)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
