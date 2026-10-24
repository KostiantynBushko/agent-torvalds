"""
Tests for the Ollama context-window resolution.

The model advertises its *maximum* context length, but the server usually
runs with a much smaller window (``PARAMETER num_ctx`` in the Modelfile, or
``--ctx-size`` on the command line).  A prompt that exceeds the real window
is truncated from the front by the server, which drops the user request and
makes the model template fail with "No user query found in messages.".

Category: Infrastructure
"""

import os
from unittest.mock import patch

import pytest

from components.ollama_config import (
    CONTEXT_LENGTH_ENV_VAR,
    apply_context_window,
    resolve_context_window,
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
