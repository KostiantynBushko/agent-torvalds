"""
Tests for the handling of the model server's errors
(components/ollama_errors.py).

The agent must explain a failure of the model server in the words of the
person who has to fix it, and it must not paste a traceback into the
chat: the traceback shows the frames of the agent and hides the failure
of the server.

The error of the report is reproduced exactly, because it is the error
the operator actually met:

    ollama._types.ResponseError: Internal Server Error
    (ref: 5da53c14-e0ba-41ea-9ae5-3fec8c43ef64) (status code: 500)
"""
import importlib.util
import logging
import sys
from pathlib import Path

import pytest
from ollama import ResponseError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from components.ollama_errors import (  # noqa: E402
    describe,
    log_failure,
    reference_of,
    server_text,
    status_code_of,
)

#: The error of the report, exactly as Ollama raised it.
REPORTED = ResponseError(
    "Internal Server Error (ref: 5da53c14-e0ba-41ea-9ae5-3fec8c43ef64) "
    "(status code: 500)",
    500,
)


# ---------------------------------------------------------------------------
# The error of the report
# ---------------------------------------------------------------------------


class TestTheReportedError:
    """The 500 the operator met."""

    def test_the_message_names_the_server(self):
        assert "model server failed" in describe(REPORTED)

    def test_the_message_carries_the_reference(self):
        assert "5da53c14-e0ba-41ea-9ae5-3fec8c43ef64" in describe(REPORTED)

    def test_the_message_says_what_to_do(self):
        message = describe(REPORTED)
        assert "ollama ps" in message
        assert "server log" in message

    def test_the_message_has_no_traceback(self):
        assert "Traceback" not in describe(REPORTED)

    def test_the_message_does_not_repeat_the_status_code(self):
        # Ollama writes the status into the text of its own error, and
        # its __str__ writes it again.  The message says it once.
        assert describe(REPORTED).count("(status code:") == 0

    def test_the_message_does_not_show_the_frames(self):
        message = describe(REPORTED)
        assert "File \"" not in message
        assert "site-packages" not in message


# ---------------------------------------------------------------------------
# The status codes
# ---------------------------------------------------------------------------


class TestTheStatusCodes:
    """Every status the server can answer with."""

    def test_404_means_the_model_is_not_pulled(self):
        message = describe(ResponseError("model not found", 404))
        assert "not found" in message
        assert "ollama pull" in message

    def test_400_means_the_request_was_rejected(self):
        message = describe(ResponseError("invalid context length", 400))
        assert "rejected" in message
        assert "context window" in message

    def test_401_means_the_server_wants_credentials(self):
        assert "credentials" in describe(ResponseError("unauthorized", 401))

    def test_403_means_the_server_wants_credentials(self):
        assert "credentials" in describe(ResponseError("forbidden", 403))

    def test_an_unusual_status_is_still_reported(self):
        message = describe(ResponseError("bad gateway", 502))
        assert "HTTP 502" in message
        assert "bad gateway" in message


# ---------------------------------------------------------------------------
# The failures that are not a status
# ---------------------------------------------------------------------------


class TestTheConnectionFailure:
    """The server could not be reached at all."""

    def test_the_message_says_the_server_is_not_reached(self):
        message = describe(ConnectionError("Failed to connect to Ollama"))
        assert "could not be reached" in message

    def test_the_message_names_the_endpoint(self):
        message = describe(ConnectionError("Failed to connect to Ollama"))
        assert "http://localhost:11434" in message

    def test_the_message_says_how_to_start_it(self):
        assert "ollama serve" in describe(ConnectionError("no"))


class TestTheTimeout:
    """The request was sent and nothing came back."""

    def test_a_builtin_timeout_is_a_timeout(self):
        assert "did not answer in time" in describe(TimeoutError("slow"))

    def test_a_client_timeout_is_a_timeout(self):
        class TimeoutException(Exception):
            pass

        assert "did not answer in time" in describe(TimeoutException("slow"))


class TestTheErrorInTheBody:
    """The response was fine, and the body carried the failure."""

    def test_the_message_says_the_server_reported_it(self):
        message = describe(ResponseError("model requires more system memory"))
        assert "reported an error" in message
        assert "more system memory" in message


class TestTheUnknownError:
    """An error the module knows nothing about."""

    def test_the_message_is_the_error(self):
        assert describe(ValueError("boom")) == "Error: boom"

    def test_the_message_has_no_traceback(self):
        assert "Traceback" not in describe(ValueError("boom"))


# ---------------------------------------------------------------------------
# The helpers
# ---------------------------------------------------------------------------


class TestTheHelpers:
    """The pieces the message is built from."""

    def test_the_status_is_read_from_the_exception(self):
        assert status_code_of(REPORTED) == 500

    def test_a_connection_failure_has_no_status(self):
        assert status_code_of(ConnectionError("no")) is None

    def test_the_reference_is_read_from_the_text(self):
        assert reference_of(REPORTED) == "5da53c14-e0ba-41ea-9ae5-3fec8c43ef64"

    def test_an_error_without_a_reference_has_none(self):
        assert reference_of(ValueError("boom")) is None

    def test_the_text_does_not_repeat_the_status(self):
        text = server_text(REPORTED)
        assert text.count("(status code:") == 0
        assert "Internal Server Error" in text

    def test_the_traceback_goes_to_the_log(self, caplog):
        # The exception is raised first: an exception that was never
        # raised carries no frames, and the frames are the point.
        try:
            raise REPORTED
        except ResponseError as exc:
            with caplog.at_level(logging.ERROR):
                log_failure(exc)

        assert "Traceback" in caplog.text
        assert "5da53c14" in caplog.text


# ---------------------------------------------------------------------------
# The chat path
# ---------------------------------------------------------------------------


class _FailingAgent:
    """An agent whose workflow starts and returns a handler."""

    def run(self, *args, **kwargs):
        return object()


class _FailingConsumer:
    """An event consumer that fails the way the model server made it fail."""

    def __init__(self, error):
        self.error = error

    def set_stats_handler(self, handler):
        self.stats_handler = handler

    def set_human_loop_handler(self, handler):
        self.human_loop_handler = handler

    async def consume_events(self, handler, user_msg):
        raise self.error


def _load_orchestrator(monkeypatch):
    """Load ``agent-torvalds.py``."""
    monkeypatch.setattr(sys, "argv", ["agent-torvalds.py"])
    spec = importlib.util.spec_from_file_location(
        "agent_torvalds_errors", ROOT / "agent-torvalds.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_the_chat_gets_a_message_and_not_a_traceback(monkeypatch):
    """The agent explains the failure of the server instead of dumping frames."""
    module = _load_orchestrator(monkeypatch)
    consumer = _FailingConsumer(REPORTED)

    response, _stats = await module.prompt_handler(
        "hello", _FailingAgent(), enable_stats=False, event_consumer=consumer
    )

    assert "Traceback" not in response
    assert "model server failed" in response
    assert "5da53c14-e0ba-41ea-9ae5-3fec8c43ef64" in response


@pytest.mark.asyncio
async def test_the_chat_never_shows_a_traceback(monkeypatch):
    """No failure reaches the chat as a stack trace."""
    module = _load_orchestrator(monkeypatch)
    consumer = _FailingConsumer(ValueError("something else went wrong"))

    response, _stats = await module.prompt_handler(
        "hello", _FailingAgent(), enable_stats=False, event_consumer=consumer
    )

    assert "Traceback" not in response
    assert response == "Error: something else went wrong"


def test_the_chat_path_of_the_tui_holds_no_traceback():
    """The TUI panel holds the message, not the frames."""
    source = (ROOT / "components" / "tui" / "tui_app.py").read_text(
        encoding="utf-8"
    )

    assert "traceback.format_exc()" not in source
    assert "describe(e)" in source
