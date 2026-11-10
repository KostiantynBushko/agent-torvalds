#!/usr/bin/env python3
"""Probe: what the agent does with a 500 from the model server.

The probe is **read-only**.  It writes nothing into the repository, it
changes no configuration, and it talks to no server: the model server is
replaced by a fake client that fails the way the real one failed.

It answers three questions:

1. **What does the log hold after one failed request?**  How many records,
   at which levels, and how many of them carry the frames of the agent.
2. **Is the request worth sending again?**  The same request, sent to a
   server that has recovered, does it work?
3. **How many times is the request sent?**  Once, or until it works?

Usage::

    .venv/bin/python investigate/llm-server-500/probe_server_500.py

The probe works on the code as it is: it uses ``components.llm_retry`` when
the module is there, and the plain ``Ollama`` LLM when it is not.  Run it
again after the change, and the third answer changes.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from llama_index.core.llms import ChatMessage  # noqa: E402
from llama_index.llms.ollama.base import Ollama  # noqa: E402
from ollama import ResponseError  # noqa: E402
from rich.console import Console  # noqa: E402

from components.event_consumer import EventConsumer  # noqa: E402
from components.llm_errors import log_failure  # noqa: E402
from components.spinner_controller import SpinnerController  # noqa: E402
from components.state_handler import StateHandler  # noqa: E402

#: The failure of the report, exactly as Ollama raised it.
REPORTED = ResponseError(
    "Internal Server Error (ref: bc97453e-2f9e-4a09-a5c4-7ee1eb1e6e2a) "
    "(status code: 500)",
    500,
)

#: The context window of the fake model.  It is given, so the LLM does not
#: ask the real server about the model - the probe talks to no server.
CONTEXT_WINDOW = 8192


# ---------------------------------------------------------------------------
# The fake model server
# ---------------------------------------------------------------------------


class FakeAsyncClient:
    """The model server, failing the way the real one failed.

    The real failure is not raised when the request is sent - it is
    raised when the **stream** is read, because that is where the HTTP
    status is checked.  The fake keeps that shape: the failure comes out
    of the iteration, not out of the call.
    """

    def __init__(self, errors):
        self.errors = list(errors)
        self.calls = 0

    async def chat(self, **kwargs):
        self.calls += 1
        error = self.errors.pop(0) if self.errors else None

        async def stream():
            if error is not None:
                raise error
            yield {
                "model": "probe-model",
                "created_at": "2026-11-09T08:00:29Z",
                "message": {"role": "assistant", "content": "the model answered"},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 11,
                "eval_count": 4,
            }

        return stream()


class FailingHandler:
    """A workflow handler that fails the way the server made it fail."""

    def __init__(self, error):
        self.error = error

    async def stream_events(self):
        return
        yield  # pragma: no cover - makes this an async generator

    def __await__(self):
        async def _raise():
            raise self.error

        return _raise().__await__()


class _Capture(logging.Handler):
    """Every record the log receives, with the frames it carries."""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)


def _has_traceback(record: logging.LogRecord) -> bool:
    """Whether the record carries the frames of the agent."""
    return bool(record.exc_info)


def _print_records(records, title):
    print(f"\n--- {title} ---")
    if not records:
        print("  (no record)")
        return
    for record in records:
        frames = "with frames" if _has_traceback(record) else "no frames"
        print(
            f"  {record.levelname:<8} {record.name:<28} {frames:<12} "
            f"{record.getMessage()[:70]}"
        )


def _llm(client):
    """The LLM of the agent, talking to the fake server."""
    return Ollama(
        model="probe-model",
        base_url="http://localhost:11434",
        context_window=CONTEXT_WINDOW,
        async_client=client,
    )


# ---------------------------------------------------------------------------
# The three questions
# ---------------------------------------------------------------------------


async def question_one() -> None:
    """What does the log hold after one failed request?"""
    print("=" * 78)
    print("1. WHAT THE LOG HOLDS AFTER ONE FAILED REQUEST")
    print("=" * 78)

    capture = _Capture()
    root = logging.getLogger()
    root.addHandler(capture)
    old_level = root.level
    root.setLevel(logging.DEBUG)
    try:
        consumer = EventConsumer(
            spinner_controller=SpinnerController(console=Console(quiet=True)),
            state_handler=StateHandler(),
            console=Console(quiet=True),
        )
        try:
            await consumer.consume_events(FailingHandler(REPORTED), "hello")
        except ResponseError:
            pass

        # The second record: the orchestrator logs the same failure again.
        log_failure(REPORTED)
    finally:
        root.removeHandler(capture)
        root.setLevel(old_level)

    _print_records(capture.records, "every record the log received")

    with_frames = [r for r in capture.records if _has_traceback(r)]
    at_error = [r for r in with_frames if r.levelno >= logging.ERROR]
    print()
    print(f"  records in total              : {len(capture.records)}")
    print(f"  records carrying the frames   : {len(with_frames)}")
    print(f"  ... of them at ERROR or above : {len(at_error)}")


async def question_two() -> None:
    """Is the request worth sending again?"""
    print()
    print("=" * 78)
    print("2. IS THE REQUEST WORTH SENDING AGAIN?")
    print("=" * 78)

    client = FakeAsyncClient([REPORTED])
    llm = _llm(client)

    messages = [ChatMessage(role="user", content="hello")]

    # The first attempt fails, exactly as it failed for the operator.
    try:
        stream = await llm.astream_chat(messages)
        async for _ in stream:
            pass
        print("  the first attempt answered (unexpected)")
    except ResponseError as exc:
        print(f"  the first attempt failed     : {type(exc).__name__}: {exc}")

    # The second attempt is the same request, to a server that recovered.
    try:
        stream = await llm.astream_chat(messages)
        text = ""
        async for chunk in stream:
            text = chunk.message.content or text
        print(f"  the second attempt answered  : {text!r}")
    except ResponseError as exc:
        print(f"  the second attempt failed    : {exc}")

    print(f"  requests sent to the server  : {client.calls}")


async def question_three() -> None:
    """How many times is the request sent?"""
    print()
    print("=" * 78)
    print("3. HOW MANY TIMES IS THE REQUEST SENT?")
    print("=" * 78)

    llm_class = Ollama
    try:
        from components.llm_retry import RetryingOllama

        llm_class = RetryingOllama
        print("  the LLM of the agent         : RetryingOllama")
    except ImportError:
        print("  the LLM of the agent         : Ollama (no retry)")

    client = FakeAsyncClient([REPORTED])
    llm = llm_class(
        model="probe-model",
        base_url="http://localhost:11434",
        context_window=CONTEXT_WINDOW,
        async_client=client,
    )

    messages = [ChatMessage(role="user", content="hello")]
    answered = False
    try:
        stream = await llm.astream_chat(messages)
        async for _ in stream:
            answered = True
    except ResponseError as exc:
        print(f"  the request failed           : {exc}")

    print(f"  requests sent to the server  : {client.calls}")
    print(f"  the request answered          : {answered}")


async def main() -> int:
    await question_one()
    await question_two()
    await question_three()
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
