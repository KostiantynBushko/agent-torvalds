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
    SOURCE_ENVIRONMENT,
    SOURCE_MODELFILE,
    SOURCE_MODEL_MAXIMUM,
    SOURCE_RUNNING_MODEL,
    apply_context_window,
    resolve_context_window,
    resolve_context_window_with_source,
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
