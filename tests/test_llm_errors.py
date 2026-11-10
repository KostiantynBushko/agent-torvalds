"""
Tests for the handling of the model server's errors
(components/llm_errors.py).

The agent must explain a failure of the model server in the words of the
person who has to fix it, and it must not paste a traceback into the
chat: the traceback shows the frames of the agent and hides the failure
of the server.

The **wording** belongs to the provider: a 500 from a local Ollama
server means the model crashed, and a 500 from the Anthropic API means
the API had a fault of its own.  A message that names the wrong provider
is worse than no message, so the tests below check that each provider
speaks only about itself.

The error of the report is reproduced exactly, because it is the error
the operator actually met:

    ollama._types.ResponseError: Internal Server Error
    (ref: 5da53c14-e0ba-41ea-9ae5-3fec8c43ef64) (status code: 500)
"""
import contextlib
import importlib.util
import logging
import sys
from pathlib import Path

import pytest
from ollama import ResponseError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from components.llm_errors import (  # noqa: E402
    Anthropic,
    Ollama,
    OpenAI,
    describe,
    log_failure,
    provider_of_the_llm,
    server_text,
    status_code_of,
)

#: The error of the report, exactly as Ollama raised it.
REPORTED = ResponseError(
    "Internal Server Error (ref: 5da53c14-e0ba-41ea-9ae5-3fec8c43ef64) "
    "(status code: 500)",
    500,
)


class _AnthropicError(Exception):
    """An error shaped like the ones the Anthropic SDK raises.

    The SDK is not a dependency of the agent yet, so the shape is
    reproduced here: the module says who raised it, the status is on
    the exception, and the request id is beside it.
    """

    __module__ = "anthropic._exceptions"

    def __init__(self, message, status_code, request_id=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.request_id = request_id


class _OpenAIError(Exception):
    """An error shaped like the ones the OpenAI SDK raises."""

    __module__ = "openai._exceptions"

    def __init__(self, message, status_code, request_id=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.request_id = request_id


class _OllamaLLM:
    """An LLM shaped like the one llama-index builds for Ollama."""

    __module__ = "llama_index.llms.ollama.base"


class _AnthropicLLM:
    """An LLM shaped like the one llama-index builds for Anthropic."""

    __module__ = "llama_index.llms.anthropic.base"


# ---------------------------------------------------------------------------
# The error of the report
# ---------------------------------------------------------------------------


class TestTheReportedError:
    """The 500 the operator met."""

    def test_the_message_names_the_server(self):
        # The failure is an Ollama one, so the Ollama server is named.
        # The generic "the model server" is for a failure that names no
        # provider - see TestAnUnknownFailure.
        assert "Ollama server failed" in describe(REPORTED)

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
        message = describe(
            ConnectionError("Failed to connect to Ollama"), Ollama()
        )
        assert "http://localhost:11434" in message

    def test_the_message_says_how_to_start_it(self):
        assert "Is it running?" in describe(
            ConnectionError("no"), Ollama()
        )


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

    def test_the_message_names_no_provider(self):
        # The failure names no provider, and none was given.
        assert "ollama" not in describe(ValueError("boom")).lower()
        assert "anthropic" not in describe(ValueError("boom")).lower()


# ---------------------------------------------------------------------------
# The providers
# ---------------------------------------------------------------------------


class TestTheAnthropicProvider:
    """What the Anthropic API says when it fails."""

    def test_a_500_is_a_fault_of_the_api(self):
        message = describe(_AnthropicError("Internal server error", 500))
        assert "fault of the API" in message
        assert "sent again" in message

    def test_a_529_is_an_overloaded_api(self):
        message = describe(_AnthropicError("Overloaded", 529))
        assert "overloaded" in message

    def test_a_429_is_a_usage_limit(self):
        message = describe(_AnthropicError("Rate limit exceeded", 429))
        assert "usage limit" in message

    def test_a_404_names_the_model(self):
        message = describe(_AnthropicError("model not found", 404))
        assert "claude-" in message

    def test_a_401_names_the_key(self):
        message = describe(_AnthropicError("invalid x-api-key", 401))
        assert "ANTHROPIC_API_KEY" in message

    def test_the_message_carries_the_request_id(self):
        message = describe(_AnthropicError("Overloaded", 529, "req_01ABC"))
        assert "req_01ABC" in message

    def test_the_endpoint_is_the_api(self):
        message = describe(
            _AnthropicError("Overloaded", 529), Anthropic()
        )
        assert "https://api.anthropic.com" in message


class TestTheOpenAIProvider:
    """What the OpenAI API says when it fails."""

    def test_a_429_is_a_usage_limit(self):
        message = describe(_OpenAIError("Rate limit reached", 429))
        assert "usage limit" in message

    def test_a_401_names_the_key(self):
        message = describe(_OpenAIError("invalid api key", 401))
        assert "OPENAI_API_KEY" in message

    def test_the_message_carries_the_request_id(self):
        message = describe(_OpenAIError("Rate limit reached", 429, "req_01XYZ"))
        assert "req_01XYZ" in message


class TestTheProviderNeverSpeaksForAnother:
    """A message that names the wrong provider is worse than no message."""

    def test_an_anthropic_failure_never_says_ollama(self):
        message = describe(_AnthropicError("Overloaded", 529)).lower()
        assert "ollama" not in message

    def test_an_ollama_failure_never_says_anthropic(self):
        message = describe(REPORTED).lower()
        assert "anthropic" not in message

    def test_an_openai_failure_never_says_ollama(self):
        message = describe(_OpenAIError("Rate limit reached", 429)).lower()
        assert "ollama" not in message


class TestTheProviderDetection:
    """How the provider is found."""

    def test_the_failure_names_its_provider(self):
        message = describe(_AnthropicError("Overloaded", 529))
        assert "overloaded" in message

    def test_the_llm_names_its_provider(self):
        provider = provider_of_the_llm(_AnthropicLLM())
        assert isinstance(provider, Anthropic)

    def test_an_ollama_llm_is_ollama(self):
        provider = provider_of_the_llm(_OllamaLLM())
        assert isinstance(provider, Ollama)

    def test_an_unknown_llm_names_no_provider(self):
        assert provider_of_the_llm(object()) is None

    def test_no_llm_names_no_provider(self):
        assert provider_of_the_llm(None) is None

    def test_the_failure_wins_over_the_llm(self):
        # The failure says Anthropic, so the failure is described in the
        # words of Anthropic.
        message = describe(_AnthropicError("Overloaded", 529), Ollama())
        assert "overloaded" in message
        assert "ollama ps" not in message

    def test_the_llm_is_used_when_the_failure_names_nothing(self):
        # Ollama turns a refused connection into a plain ConnectionError,
        # which says nothing about who was refused.
        message = describe(ConnectionError("refused"), provider_of_the_llm(_OllamaLLM()))
        assert "http://localhost:11434" in message


# ---------------------------------------------------------------------------
# The helpers
# ---------------------------------------------------------------------------


class TestTheHelpers:
    """The pieces the message is built from."""

    def test_the_status_is_read_from_the_exception(self):
        assert status_code_of(REPORTED) == 500

    def test_the_status_is_read_from_an_api_error(self):
        assert status_code_of(_AnthropicError("x", 529)) == 529

    def test_a_connection_failure_has_no_status(self):
        assert status_code_of(ConnectionError("no")) is None

    def test_the_text_does_not_repeat_the_status(self):
        text = server_text(REPORTED)
        assert text.count("(status code:") == 0
        assert "Internal Server Error" in text

    def test_the_text_of_an_api_error_is_its_message(self):
        assert server_text(_AnthropicError("Overloaded", 529)) == "Overloaded"

    def test_the_traceback_goes_to_the_log(self, caplog):
        # The exception is raised first: an exception that was never
        # raised carries no frames, and the frames are the point.
        try:
            raise REPORTED
        except ResponseError as exc:
            with caplog.at_level(logging.DEBUG):
                log_failure(exc)

        assert "Traceback" in caplog.text
        assert "5da53c14" in caplog.text

    def test_the_frames_are_not_at_the_error_level(self, caplog):
        # The frames of the agent are of no use to anybody who did not
        # write the agent, so they are written under the DEBUG level.
        # The ERROR record says what failed, and nothing else.
        try:
            raise REPORTED
        except ResponseError as exc:
            with caplog.at_level(logging.ERROR):
                log_failure(exc)

        assert "Traceback" not in caplog.text
        assert "The request failed" in caplog.text
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


def _no_cache_writes(monkeypatch):
    """The test writes nothing into the cache of the operator.

    The orchestrators count the commands of the session in that cache,
    and the cache is written atomically through a temp file whose name
    is the same for every writer.  Two writers at once - the suite and
    another agent - make each other lose the file, and the test then
    fails for a reason that has nothing to do with the wording.
    """
    monkeypatch.setattr(
        "agent_cache_system.increment_session_commands", lambda: None
    )
    monkeypatch.setattr("agent_cache_system.log_error", lambda message: "")


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
    _no_cache_writes(monkeypatch)
    module = _load_orchestrator(monkeypatch)
    consumer = _FailingConsumer(REPORTED)

    response, _stats = await module.prompt_handler(
        "hello", _FailingAgent(), enable_stats=False, event_consumer=consumer
    )

    assert "Traceback" not in response
    assert "Ollama server failed" in response
    assert "5da53c14-e0ba-41ea-9ae5-3fec8c43ef64" in response


@pytest.mark.asyncio
async def test_the_chat_never_shows_a_traceback(monkeypatch):
    """No failure reaches the chat as a stack trace."""
    _no_cache_writes(monkeypatch)
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
    assert "describe(e, provider)" in source


# ---------------------------------------------------------------------------
# The other entry points
#
# There is more than one way to run the agent, and every one of them
# answers a failed request.  A wording that reaches one of them and not
# the others is a wording that is there by accident.
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _logging_handlers_kept():
    """The logging of the root logger, put back afterwards.

    Loading an orchestrator reconfigures the logging - ``configure_logging``
    calls ``basicConfig(force=True)``, which removes the handlers of the
    root logger, and the handlers pytest put there with them.  They are
    put back, so the rest of the suite keeps its capture.
    """
    root = logging.getLogger()
    handlers = root.handlers[:]
    level = root.level
    try:
        yield
    finally:
        root.handlers[:] = handlers
        root.setLevel(level)


def _load_multi_window_orchestrator():
    """Load ``agent-torvalds-mw.py``."""
    with _logging_handlers_kept():
        spec = importlib.util.spec_from_file_location(
            "agent_torvalds_mw_errors", ROOT / "agent-torvalds-mw.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_the_multi_window_chat_gets_a_message_and_not_a_traceback(monkeypatch):
    """The multi-window agent explains the failure instead of dumping frames."""
    _no_cache_writes(monkeypatch)
    module = _load_multi_window_orchestrator()
    consumer = _FailingConsumer(REPORTED)

    response, _stats = await module.prompt_handler(
        "hello", _FailingAgent(), enable_stats=False, event_consumer=consumer
    )

    assert "Traceback" not in response
    assert "Ollama server failed" in response
    assert "5da53c14-e0ba-41ea-9ae5-3fec8c43ef64" in response


def test_the_chat_path_of_the_multi_window_holds_no_traceback():
    """The multi-window chat holds the message, not the frames."""
    source = (ROOT / "agent-torvalds-mw.py").read_text(encoding="utf-8")

    assert "traceback.format_exc()" not in source
    assert "describe(e, provider_of_the_llm" in source


def test_the_chat_path_of_the_cpp_agent_holds_no_traceback():
    """The llama.cpp chat holds the message, not the frames."""
    source = (ROOT / "agent-torvalds-cpp.py").read_text(encoding="utf-8")

    assert "traceback.format_exc()" not in source
    assert "describe(e, provider_of_the_llm" in source
