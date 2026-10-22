"""
End-to-end verification of the "no timeout" HITL convention.

Traces the timeout value through the *real* components — orchestrator ->
agent -> event -> consumer -> input module -> asyncio — and proves that
the agent waits for the human instead of expiring.

Run from the repository root::

    .venv/bin/python investigate/hitl-investigate/verify_hitl_no_timeout.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
))))

from components.console_input_module import ConsoleInputModule
from components.event_consumer import EventConsumer
from components.hitl_events import AgentQuestionEvent
from components.hitl_timeout import describe_timeout, normalize_timeout
from components.human_loop_handler import HumanLoopHandler
from components.timeout_manager import TimeoutManager

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    print(f"[{PASS if condition else FAIL}] {name}" + (f" — {detail}" if detail else ""))


async def main() -> int:
    print("=" * 72)
    print("HITL no-timeout verification")
    print("=" *  72)

    # ------------------------------------------------------------------
    # 1. The orchestrator default
    # ------------------------------------------------------------------
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "torvalds_classic",
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))),
            "agent-torvalds.py",
        ),
    )
    orchestrator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(orchestrator)

    check(
        "orchestrator default timeout is -1 (no timeout)",
        orchestrator.HITL_TIMEOUT == -1,
        f"HITL_TIMEOUT={orchestrator.HITL_TIMEOUT}",
    )

    # ------------------------------------------------------------------
    # 2. The event the agent raises
    # ------------------------------------------------------------------
    event = AgentQuestionEvent(
        question="Shall I delete the database?",
        question_id="verify-1",
    )
    check(
        "AgentQuestionEvent.timeout is -1",
        event.timeout == -1,
        f"timeout={event.timeout} ({describe_timeout(event.timeout)})",
    )
    try:
        event.validate()
        check("AgentQuestionEvent.validate() accepts -1", True)
    except Exception as exc:  # noqa: BLE001
        check("AgentQuestionEvent.validate() accepts -1", False, str(exc))

    # ------------------------------------------------------------------
    # 3. The consumer forwards the value
    # ------------------------------------------------------------------
    consumer = EventConsumer(
        spinner_controller=None,
        state_handler=None,
        console=None,
    )
    check(
        "EventConsumer.hitl_timeout is -1",
        consumer.hitl_timeout == -1,
        f"hitl_timeout={consumer.hitl_timeout}",
    )

    seen: dict[str, object] = {}

    class SpyInput(ConsoleInputModule):
        async def prompt_with_status(self, message="", default="", timeout=-1):
            seen["timeout"] = timeout
            # The human takes their time.
            await asyncio.sleep(1.5)
            return "yes", False

    consumer.console_input = SpyInput()
    answer, was_timeout = await consumer._collect_answer(event)
    check(
        "the consumer hands -1 to the input module",
        seen.get("timeout") == -1,
        f"input module received timeout={seen.get('timeout')}",
    )
    check(
        "the answer is delivered, not a timeout fallback",
        answer == "yes" and not was_timeout,
        f"answer={answer!r} was_timeout={was_timeout}",
    )

    # ------------------------------------------------------------------
    # 4. asyncio really waits forever for -1
    # ------------------------------------------------------------------
    check(
        "asyncio receives None (wait forever) for -1",
        normalize_timeout(-1) is None,
        f"normalize_timeout(-1)={normalize_timeout(-1)!r}",
    )

    started = time.monotonic()

    async def slow_human():
        await asyncio.sleep(2.0)
        return "answered"

    try:
        value = await asyncio.wait_for(slow_human(), timeout=normalize_timeout(-1))
        elapsed = time.monotonic() - started
        check(
            "a 2s answer survives a 'no timeout' wait",
            value == "answered" and elapsed >= 2.0,
            f"elapsed={elapsed:.2f}s",
        )
    except asyncio.TimeoutError:
        check("a 2s answer survives a 'no timeout' wait", False, "timed out")

    # ------------------------------------------------------------------
    # 5. The timeout manager
    # ------------------------------------------------------------------
    manager = TimeoutManager()
    check(
        "TimeoutManager default is -1",
        manager.default_timeout == -1,
        f"default_timeout={manager.default_timeout}",
    )

    started = time.monotonic()
    value, timed_out = await manager.prompt_with_timeout(slow_human)
    elapsed = time.monotonic() - started
    check(
        "the timeout manager waits for the slow answer",
        value == "answered" and not timed_out and elapsed >= 2.0,
        f"elapsed={elapsed:.2f}s timed_out={timed_out}",
    )

    # ------------------------------------------------------------------
    # 6. A finite timeout still expires
    # ------------------------------------------------------------------
    value, timed_out = await manager.prompt_with_timeout(
        slow_human, timeout=1
    )
    check(
        "a finite timeout still expires",
        timed_out and value == "",
        f"timed_out={timed_out} value={value!r}",
    )

    # ------------------------------------------------------------------
    # 7. The handler
    # ------------------------------------------------------------------
    handler = HumanLoopHandler()
    check(
        "HumanLoopHandler default is -1",
        handler.default_timeout == -1,
        f"default_timeout={handler.default_timeout}",
    )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("=" * 72)
    failed = [r for r in results if not r[1]]
    passed = len(results) - len(failed)
    print(f"{passed}/{len(results)} checks passed")
    if failed:
        print("FAILED:")
        for name, _, detail in failed:
            print(f"  - {name} {detail}")
    print("=" * 72)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
