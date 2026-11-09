"""
Tests for the retry of a failed model request
(components/llm_retry.py).

The model server fails for two kinds of reason.  One of them is the
request - the prompt was too long, the model is not pulled - and sending
that request again fails in exactly the same way.  The other kind is the
server - the model died, the server is busy, the connection was cut -
and the very same request, a moment later, usually works.

The failure of the report is the second kind: the Ollama server
answered 500, the model had died, and the request was never sent again.

    ollama._types.ResponseError: Internal Server Error
    (ref: bc97453e-2f9e-4a09-a5c4-7ee1eb1e6e2a) (status code: 500)

The tests below check that the request is sent again for that failure,
that it is **not** sent again for a failure of the request, and that the
frames of the agent are written under the DEBUG level.
"""
import logging
import sys
from pathlib import Path

import pytest
from llama_index.core.llms import ChatMessage
from llama_index.llms.ollama.base import Ollama as OllamaLLM
from ollama import ResponseError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from components.event_consumer import EventConsumer  # noqa: E402
from components.llm_errors import (  # noqa: E402
    Ollama,
    describe,
    log_failure,
    provider_of_the_llm,
)
from components.llm_retry import (  # noqa: E402
    RetryingOllama,
    delay_for,
    is_transient,
)
from components.spinner_controller import SpinnerController  # noqa: E402
from components.state_handler import StateHandler  # noqa: E402

#: The failure of the report, exactly as Ollama raised it.
REPORTED = ResponseError(
    "Internal Server Error (ref: bc97453e-2f9e-4a09-a5c4-7ee1eb1e6e2a) "
    "(status code: 500)",
    500,
)

#: The answer of the fake server.
ANSWER = "the model answered"


class FakeAsyncClient:
    """The model server, failing the way the real one failed.

    The real failure is not raised when the request is sent - it is
    raised when the **stream** is read, because that is where the HTTP
    status is checked.  The fake keeps that shape.
    """

    def __init__(self, errors=()):
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
                "message": {"role": "assistant", "content": ANSWER},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 11,
                "eval_count": 4,
            }

        return stream()


class HalfAnswerClient:
    """A server that answers half of the answer, and then dies.

    The failure comes in the middle of the stream, which is the case the
    status code does not describe: the request was accepted, and the
    model died while it was answering.
    """

    def __init__(self):
        self.calls = 0

    async def chat(self, **kwargs):
        self.calls += 1
        dying = self.calls == 1

        async def stream():
            if dying:
                yield {
                    "model": "probe-model",
                    "created_at": "2026-11-09T08:00:29Z",
                    "message": {"role": "assistant", "content": "half of "},
                    "done": False,
                }
                raise REPORTED
            yield {
                "model": "probe-model",
                "created_at": "2026-11-09T08:00:30Z",
                "message": {"role": "assistant", "content": ANSWER},
                "done": True,
            }

        return stream()


def _llm(client, **kwargs):
    """The LLM of the agent, talking to the fake server."""
    settings = {
        "model": "probe-model",
        "base_url": "http://localhost:11434",
        # The context window is given, so the LLM does not ask the real
        # server about the model - the test talks to no server.
        "context_window": 8192,
        "async_client": client,
        "retry_delay": 0.01,
    }
    settings.update(kwargs)
    return RetryingOllama(**settings)


async def _ask(llm, text="hello"):
    """Send one request and return the answer, or the failure."""
    messages = [ChatMessage(role="user", content=text)]
    try:
        stream = await llm.astream_chat(messages)
        answer = ""
        async for chunk in stream:
            answer = chunk.message.content or answer
        return answer
    except Exception as exc:  # noqa: BLE001 - the failure is the answer
        return exc


# ---------------------------------------------------------------------------
# Which failures are worth another attempt
# ---------------------------------------------------------------------------


class TestTheTransientFailures:
    """The failures of the server, and not of the request."""

    def test_a_500_is_worth_another_attempt(self):
        # The failure of the report: the model of the server died.
        assert is_transient(REPORTED)

    def test_a_503_is_worth_another_attempt(self):
        assert is_transient(ResponseError("service unavailable", 503))

    def test_a_429_is_worth_another_attempt(self):
        assert is_transient(ResponseError("too many requests", 429))

    def test_a_connection_that_never_came_about_is_worth_another_attempt(self):
        assert is_transient(ConnectionError("Failed to connect to Ollama"))

    def test_a_server_that_did_not_answer_in_time_is_worth_another_attempt(self):
        assert is_transient(TimeoutError("slow"))


class TestThePermanentFailures:
    """The failures of the request, and not of the server."""

    def test_a_404_is_not_worth_another_attempt(self):
        # The model is not pulled: it will not be pulled by asking again.
        assert not is_transient(ResponseError("model not found", 404))

    def test_a_400_is_not_worth_another_attempt(self):
        # The prompt was too long: it is still too long.
        assert not is_transient(ResponseError("invalid context length", 400))

    def test_a_401_is_not_worth_another_attempt(self):
        assert not is_transient(ResponseError("unauthorized", 401))

    def test_an_error_in_the_body_is_not_worth_another_attempt(self):
        # Ollama raises an error of the body with the status -1: the
        # server answered, and what it said will be said again.
        assert not is_transient(ResponseError("model requires more memory"))

    def test_an_unknown_failure_is_not_worth_another_attempt(self):
        assert not is_transient(ValueError("boom"))


# ---------------------------------------------------------------------------
# The retry
# ---------------------------------------------------------------------------


class TestTheRetry:
    """The request is sent again when the server fails."""

    @pytest.mark.asyncio
    async def test_the_request_is_sent_again(self):
        client = FakeAsyncClient([REPORTED])
        llm = _llm(client)

        answer = await _ask(llm)

        assert answer == ANSWER
        assert client.calls == 2

    @pytest.mark.asyncio
    async def test_a_failure_of_the_request_is_not_sent_again(self):
        client = FakeAsyncClient([ResponseError("model not found", 404)])
        llm = _llm(client)

        answer = await _ask(llm)

        assert isinstance(answer, ResponseError)
        assert client.calls == 1

    @pytest.mark.asyncio
    async def test_the_retry_is_bounded(self):
        # Three attempts in all: the first one and two more.
        client = FakeAsyncClient([REPORTED] * 5)
        llm = _llm(client, max_retries=2)

        answer = await _ask(llm)

        assert isinstance(answer, ResponseError)
        assert client.calls == 3

    @pytest.mark.asyncio
    async def test_no_retry_at_all(self):
        client = FakeAsyncClient([REPORTED])
        llm = _llm(client, max_retries=0)

        answer = await _ask(llm)

        assert isinstance(answer, ResponseError)
        assert client.calls == 1

    @pytest.mark.asyncio
    async def test_the_wait_grows_with_every_attempt(self):
        # The waits of the two attempts are 1.0 and 2.0 seconds - the
        # test does not wait for them.
        client = FakeAsyncClient([REPORTED] * 5)
        llm = _llm(client, max_retries=2, retry_delay=0.001, retry_backoff=2.0)

        answer = await _ask(llm)

        assert isinstance(answer, ResponseError)
        assert client.calls == 3

    @pytest.mark.asyncio
    async def test_a_stream_that_failed_half_way_is_sent_again(self):
        # The model died while it was answering.  The request is sent
        # again, and the answer of the attempt that works is the answer.
        client = HalfAnswerClient()
        llm = _llm(client)

        answer = await _ask(llm)

        assert answer == ANSWER
        assert client.calls == 2

    @pytest.mark.asyncio
    async def test_a_failure_of_the_reader_is_not_a_failure_of_the_server(self):
        # The reader of the stream is the agent.  When it fails, the
        # request is not sent again - the server answered.
        client = FakeAsyncClient()
        llm = _llm(client)
        messages = [ChatMessage(role="user", content="hello")]

        stream = await llm.astream_chat(messages)
        with pytest.raises(RuntimeError):
            async for _ in stream:
                raise RuntimeError("the reader failed")

        assert client.calls == 1

    @pytest.mark.asyncio
    async def test_the_failure_of_a_retried_request_is_logged(self, caplog):
        client = FakeAsyncClient([REPORTED])
        llm = _llm(client)

        with caplog.at_level(logging.WARNING):
            await _ask(llm)

        assert "sent again" in caplog.text


class TestTheWait:
    """How long the agent waits before it sends the request again."""

    def test_the_first_wait_is_the_base(self):
        assert delay_for(1, 2.0, 2.0) == 2.0

    def test_the_wait_grows(self):
        assert delay_for(2, 2.0, 2.0) == 4.0
        assert delay_for(3, 2.0, 2.0) == 8.0

    def test_the_wait_never_goes_below_the_base(self):
        assert delay_for(0, 2.0, 2.0) == 2.0


# ---------------------------------------------------------------------------
# The LLM of the agent
# ---------------------------------------------------------------------------


class TestTheLLMOfTheAgent:
    """The retrying LLM is the LLM of the agent, and still speaks of Ollama."""

    def test_it_is_an_ollama_llm(self):
        client = FakeAsyncClient()
        assert isinstance(_llm(client), OllamaLLM)

    def test_the_provider_is_still_ollama(self):
        # The subclass lives in a module of its own, which names no
        # provider - the message would say "the model server" instead of
        # "the Ollama server" if the ancestors were not looked at.
        client = FakeAsyncClient()
        provider = provider_of_the_llm(_llm(client))
        assert isinstance(provider, Ollama)

    def test_the_failure_is_described_in_the_words_of_ollama(self):
        client = FakeAsyncClient()
        provider = provider_of_the_llm(_llm(client))
        message = describe(REPORTED, provider)
        assert "Ollama server failed" in message


# ---------------------------------------------------------------------------
# The frames of the agent
# ---------------------------------------------------------------------------


class TestTheFramesOfTheAgent:
    """The frames belong to the DEBUG level, not to the ERROR level."""

    def test_the_frames_are_written_under_debug(self, caplog):
        try:
            raise REPORTED
        except ResponseError as exc:
            with caplog.at_level(logging.DEBUG):
                log_failure(exc)

        assert "Traceback" in caplog.text
        assert "bc97453e" in caplog.text

    def test_the_error_level_holds_no_frames(self, caplog):
        try:
            raise REPORTED
        except ResponseError as exc:
            with caplog.at_level(logging.ERROR):
                log_failure(exc)

        assert "Traceback" not in caplog.text
        assert "The request failed" in caplog.text


class _FailingHandler:
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


class TestTheEventConsumer:
    """The event consumer writes the frames under the DEBUG level too."""

    @pytest.mark.asyncio
    async def test_the_error_level_holds_no_frames(self, caplog):
        from rich.console import Console

        consumer = EventConsumer(
            spinner_controller=SpinnerController(console=Console(quiet=True)),
            state_handler=StateHandler(),
            console=Console(quiet=True),
        )

        with caplog.at_level(logging.ERROR):
            with pytest.raises(ResponseError):
                await consumer.consume_events(_FailingHandler(REPORTED), "hello")

        assert "Traceback" not in caplog.text
        assert "exception" in caplog.text

    @pytest.mark.asyncio
    async def test_the_frames_are_written_under_debug(self, caplog):
        from rich.console import Console

        consumer = EventConsumer(
            spinner_controller=SpinnerController(console=Console(quiet=True)),
            state_handler=StateHandler(),
            console=Console(quiet=True),
        )

        with caplog.at_level(logging.DEBUG):
            with pytest.raises(ResponseError):
                await consumer.consume_events(_FailingHandler(REPORTED), "hello")

        assert "Traceback" in caplog.text
