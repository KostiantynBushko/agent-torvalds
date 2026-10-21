#!/usr/bin/env python3
"""Diagnostic: does the revived HITL path double-prompt the user?

The HumanLoopHandler and the EventConsumer BOTH prompt the user when a
question is detected:

* HumanLoopHandler._handle_question  -> awaits self._prompt_user()
* EventConsumer._on_agent_question   -> awaits self.console_input.prompt()

Before the fix neither ran (the callback manager was dead). After the fix
both can run for the same question -> two prompts for one question.

This drives the callback handler directly with a question-shaped payload to
count how many times the user is actually prompted.
"""
import asyncio
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from llama_index.core.callbacks.schema import CBEventType, EventPayload
from rich.console import Console

from components.human_loop_handler import HumanLoopHandler
from components.event_consumer import EventConsumer
from components.state_handler import StateHandler


class _NullSpinner:
    def start(self): pass
    def stop(self): pass
    def pause(self): pass
    def resume(self): pass
    @property
    def is_paused(self): return False


class _FakeResponse:
    """Mimics an LLM response whose text ends with a question mark."""
    text = "Would you like me to continue with the deployment?"


async def main() -> None:
    console = Console()
    consumer = EventConsumer(
        spinner_controller=_NullSpinner(),
        state_handler=StateHandler(),
        console=console,
    )

    hitl = HumanLoopHandler(
        input_method="console",
        default_timeout=3,
        default_answer="",
        console=console,
        spinner=_NullSpinner(),
        enable_hitl=True,
        event_consumer=consumer,
    )

    # Count the prompts issued by the HANDLER.
    handler_prompts = []
    orig_prompt_user = hitl._prompt_user

    async def spy_prompt_user(question, input_type, timeout, default_answer):
        handler_prompts.append(question)
        # Do NOT actually block on stdin.
        return "yes", False

    hitl._prompt_user = spy_prompt_user

    # Count the prompts issued by the EVENT CONSUMER.
    consumer_prompts = []
    orig_consumer_prompt = consumer.console_input.prompt

    async def spy_consumer_prompt(message, default="", timeout=30):
        consumer_prompts.append(message)
        return "yes"

    consumer.console_input.prompt = spy_consumer_prompt

    # Fire the LLM event end with a question-shaped response.
    hitl.on_event_end(
        event_type=CBEventType.LLM,
        payload={EventPayload.RESPONSE: _FakeResponse()},
        event_id="evt-1",
    )

    # Let the ensure_future task run.
    await asyncio.sleep(0.5)

    print()
    print("=== prompt counts for ONE question ===")
    print(f"  HumanLoopHandler._prompt_user calls : {len(handler_prompts)}")
    print(f"  EventConsumer console_input.prompt  : {len(consumer_prompts)}")
    total = len(handler_prompts) + len(consumer_prompts)
    print(f"  TOTAL user prompts for one question : {total}")
    if total > 1:
        print("  >>> DOUBLE PROMPT DETECTED <<<")
    else:
        print("  >>> single prompt (ok) <<<")


if __name__ == "__main__":
    asyncio.run(main())
