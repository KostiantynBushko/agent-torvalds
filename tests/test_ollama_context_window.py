"""
Tests for the Ollama context-window resolution.

The model advertises its *maximum* context length, but the server usually
runs with a much smaller window (``PARAMETER num_ctx`` in the Modelfile, or
``--ctx-size`` on the command line).  A prompt that exceeds the real window
is truncated from the front by the server, which drops the user request and
makes the model template fail with "No user query found in messages.".

Category: Infrastructure
"""

import logging
import os
from unittest.mock import patch

import pytest

from components.ollama_config import (
    CONTEXT_LENGTH_ENV_VAR,
    MIN_CONTEXT_WINDOW,
    SOURCE_DEFAULT,
    SOURCE_ENVIRONMENT,
    SOURCE_MODELFILE,
    SOURCE_MODEL_MAXIMUM,
    SOURCE_RUNNING_MODEL,
    UNKNOWN_CONTEXT_WINDOW,
    apply_context_window,
    fit_context_window,
    resolve_context_window,
    resolve_context_window_with_source,
    window_for_prompt,
)


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        import json

        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeModelInfo:
    def __init__(self, modelfile: str):
        self.modelfile = modelfile
        self.modelinfo = {"qwen35.context_length": 262144}


class FakeClient:
    def __init__(self, modelfile: str):
        self._modelfile = modelfile

    def show(self, model):
        return FakeModelInfo(self._modelfile)


class FakeOllama:
    """Just enough of an Ollama LLM for the resolution helpers."""

    def __init__(self, modelfile: str = "", base_url: str = "http://localhost:11434"):
        self.model = "some/model:Q4_K_M"
        self.base_url = base_url
        self.client = FakeClient(modelfile)
        self.context_window = -1
        self.request_timeout = 10

    @property
    def metadata(self):
        class _Meta:
            context_window = 262144

        return _Meta()


MODELFILE_8K = "FROM /path/to/blob\nTEMPLATE {{ .Prompt }}\nPARAMETER num_ctx 8192\n"
MODELFILE_NO_PARAM = "FROM /path/to/blob\nTEMPLATE {{ .Prompt }}\n"


def test_modelfile_num_ctx_wins_over_the_model_maximum():
    llm = FakeOllama(modelfile=MODELFILE_8K)
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        assert resolve_context_window(llm) == 8192


def test_falls_back_to_the_model_maximum():
    llm = FakeOllama(modelfile=MODELFILE_NO_PARAM)
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        assert resolve_context_window(llm) == 262144


def test_running_model_wins_over_the_modelfile():
    llm = FakeOllama(modelfile=MODELFILE_8K)
    payload = {
        "models": [
            {"model": "some/model:Q4_K_M", "context_length": 4096},
        ]
    }
    with patch("urllib.request.urlopen", return_value=FakeResponse(payload)):
        assert resolve_context_window(llm) == 4096


def test_environment_override_wins():
    llm = FakeOllama(modelfile=MODELFILE_8K)
    with patch.dict(os.environ, {CONTEXT_LENGTH_ENV_VAR: "12345"}):
        assert resolve_context_window(llm) == 12345


def test_apply_context_window_sets_the_llm():
    llm = FakeOllama(modelfile=MODELFILE_8K)
    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        assert apply_context_window(llm) == 8192
    assert llm.context_window == 8192


def test_apply_context_window_of_an_unknown_model_is_harmless():
    class NoContext:
        model = "x"
        base_url = ""

    assert apply_context_window(NoContext()) is None


# ---------------------------------------------------------------------------
# The source of the window
# ---------------------------------------------------------------------------


class TestSources:
    """Where the number came from — a number alone says nothing."""

    def test_the_running_model_is_named_as_the_source(self):
        llm = FakeOllama(modelfile=MODELFILE_8K)
        payload = {
            "models": [
                {"model": "some/model:Q4_K_M", "context_length": 4096},
            ]
        }
        with patch("urllib.request.urlopen", return_value=FakeResponse(payload)):
            length, source = resolve_context_window_with_source(llm)
        assert length == 4096
        assert source == SOURCE_RUNNING_MODEL

    def test_the_modelfile_is_named_as_the_source(self):
        llm = FakeOllama(modelfile=MODELFILE_8K)
        with patch("urllib.request.urlopen", side_effect=OSError("offline")):
            length, source = resolve_context_window_with_source(llm)
        assert length == 8192
        assert source == SOURCE_MODELFILE

    def test_the_advertised_maximum_is_named_as_the_source(self):
        llm = FakeOllama(modelfile=MODELFILE_NO_PARAM)
        with patch("urllib.request.urlopen", side_effect=OSError("offline")):
            length, source = resolve_context_window_with_source(llm)
        assert length == 262144
        assert source == SOURCE_MODEL_MAXIMUM

    def test_the_override_is_named_as_the_source(self):
        llm = FakeOllama(modelfile=MODELFILE_8K)
        with patch.dict(os.environ, {CONTEXT_LENGTH_ENV_VAR: "12345"}):
            length, source = resolve_context_window_with_source(llm)
        assert length == 12345
        assert source == SOURCE_ENVIRONMENT

    def test_the_resolution_still_returns_the_length(self):
        llm = FakeOllama(modelfile=MODELFILE_8K)
        with patch("urllib.request.urlopen", side_effect=OSError("offline")):
            assert resolve_context_window(llm) == 8192


# ---------------------------------------------------------------------------
# The log
# ---------------------------------------------------------------------------


class TestInfoLog:
    """The window is written to the log at the INFO level."""

    def test_the_log_carries_the_size_and_the_source(self, caplog):
        llm = FakeOllama(modelfile=MODELFILE_8K)
        with patch("urllib.request.urlopen", side_effect=OSError("offline")):
            with caplog.at_level(
                logging.INFO, logger="components.ollama_config"
            ):
                apply_context_window(llm)

        text = "\n".join(record.getMessage() for record in caplog.records)
        assert "Context window: 8192 tokens" in text
        assert SOURCE_MODELFILE in text

    def test_nothing_is_logged_below_the_info_level(self, caplog):
        llm = FakeOllama(modelfile=MODELFILE_8K)
        with patch("urllib.request.urlopen", side_effect=OSError("offline")):
            with caplog.at_level(
                logging.WARNING, logger="components.ollama_config"
            ):
                apply_context_window(llm)

        text = "\n".join(record.getMessage() for record in caplog.records)
        assert "Context window" not in text

    def test_an_unknown_window_is_reported_as_unknown(self, caplog):
        class NoContext:
            model = "x"
            base_url = ""

        with caplog.at_level(logging.INFO, logger="components.ollama_config"):
            assert apply_context_window(NoContext()) is None

        text = "\n".join(record.getMessage() for record in caplog.records)
        assert "Context window: unknown" in text


# ---------------------------------------------------------------------------
# The advertised maximum is not the window of the server
# ---------------------------------------------------------------------------


class TestTheAdvertisedMaximum:
    """A model that advertises a million tokens must not be sent one.

    The advertised maximum is the **capacity** of the model, not the
    window the server runs with.  Asking for it is not free: the server
    gives the model a context of that size, the machine cannot hold it,
    and the model is pushed off the GPU — measured in the report of
    ``investigate/agent-empty-answer/``: 3.09 GB of VRAM instead of
    6.64 GB, and 173 seconds for a request that should have taken
    seconds.
    """

    def test_the_advertised_maximum_is_not_applied_to_the_llm(self):
        """The window of the LLM is not the advertised maximum."""
        llm = FakeOllama(modelfile=MODELFILE_NO_PARAM)
        with patch("urllib.request.urlopen", side_effect=OSError("offline")):
            assert apply_context_window(llm) is None
        assert llm.context_window != 262144, (
            "the advertised maximum of the model was sent to the server"
        )

    def test_the_window_is_unknown_when_the_server_says_nothing(self):
        """The window is unknown, not invented."""
        llm = FakeOllama(modelfile=MODELFILE_NO_PARAM)
        with patch("urllib.request.urlopen", side_effect=OSError("offline")):
            apply_context_window(llm)
        assert llm.context_window == UNKNOWN_CONTEXT_WINDOW

    def test_the_configured_default_is_used_instead(self):
        """A window the operator configured is a real window."""
        llm = FakeOllama(modelfile=MODELFILE_NO_PARAM)
        with patch("urllib.request.urlopen", side_effect=OSError("offline")):
            assert apply_context_window(llm, default=8192) == 8192
        assert llm.context_window == 8192

    def test_the_log_says_that_the_maximum_was_refused(self, caplog):
        """The operator sees why the number was not used."""
        llm = FakeOllama(modelfile=MODELFILE_NO_PARAM)
        with patch("urllib.request.urlopen", side_effect=OSError("offline")):
            with caplog.at_level(
                logging.INFO, logger="components.ollama_config"
            ):
                apply_context_window(llm)

        text = "\n".join(record.getMessage() for record in caplog.records)
        assert "advertised maximum" in text
        assert "262144" in text


# ---------------------------------------------------------------------------
# The window is sized to the prompt
# ---------------------------------------------------------------------------


class TestWindowForPrompt:
    """The window is raised to hold the prompt, and never lowered."""

    def test_the_window_leaves_room_above_the_prompt(self):
        """The count of the agent is low, so the window is higher."""
        needed = window_for_prompt(15000)

        assert needed > 15000, "the window does not hold the prompt"
        assert needed < 15000 * 2, "the window is far bigger than needed"

    def test_the_window_has_a_floor(self):
        """A tiny prompt still gets a usable window."""
        assert window_for_prompt(10) >= MIN_CONTEXT_WINDOW

    def test_the_window_is_raised_to_the_prompt(self):
        """The window of the LLM is raised to hold the prompt."""
        llm = FakeOllama(modelfile=MODELFILE_8K)
        llm.context_window = 8192

        fit_context_window(llm, 15000)

        assert llm.context_window >= 15000

    def test_the_window_is_never_lowered(self):
        """A window that changes in both directions costs the cache."""
        llm = FakeOllama(modelfile=MODELFILE_8K)
        llm.context_window = 65536

        fit_context_window(llm, 1000)

        assert llm.context_window == 65536, (
            "the window was lowered — the server gives the cache back and "
            "takes it again with every request"
        )

    def test_an_llm_that_does_not_take_the_window_is_survivable(self):
        """A window is never worth a run."""
        class Stubborn:
            model = "x"
            base_url = ""

            @property
            def context_window(self):
                return 8192

            @context_window.setter
            def context_window(self, value):
                raise RuntimeError("no")

        assert fit_context_window(Stubborn(), 15000) == 8192
