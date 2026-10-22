"""
Tests for the Ollama endpoint resolution (components/ollama_config.py).

The agent must be able to reach a local Ollama server without any
configuration, must prefer the agent-specific variable over the generic
Ollama one, and must turn a bare ``host:port`` into a URL the HTTP client
accepts.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from components.ollama_config import (  # noqa: E402
    DEFAULT_OLLAMA_BASE_URL,
    get_ollama_base_url,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Remove every endpoint variable so each test starts from a clean slate."""
    monkeypatch.delenv("TORVALDS_OLLAMA_HOST", raising=False)
    monkeypatch.delenv("OLLAMA_HOST", raising=False)


class TestDefault:
    """With nothing configured the agent talks to the standard Ollama port."""

    def test_default_is_localhost_11434(self):
        assert get_ollama_base_url() == DEFAULT_OLLAMA_BASE_URL
        assert get_ollama_base_url() == "http://localhost:11434"


class TestTorvaldsHost:
    """TORVALDS_OLLAMA_HOST is the agent-specific override."""

    def test_full_url_is_used_as_is(self, monkeypatch):
        monkeypatch.setenv("TORVALDS_OLLAMA_HOST", "http://gpu-box:11434")
        assert get_ollama_base_url() == "http://gpu-box:11434"

    def test_https_is_preserved(self, monkeypatch):
        monkeypatch.setenv("TORVALDS_OLLAMA_HOST", "https://ollama.example.com")
        assert get_ollama_base_url() == "https://ollama.example.com"

    def test_bare_host_port_gets_the_http_scheme(self, monkeypatch):
        monkeypatch.setenv("TORVALDS_OLLAMA_HOST", "192.168.1.10:11434")
        assert get_ollama_base_url() == "http://192.168.1.10:11434"

    def test_surrounding_whitespace_is_stripped(self, monkeypatch):
        monkeypatch.setenv("TORVALDS_OLLAMA_HOST", "  http://gpu-box:11434  ")
        assert get_ollama_base_url() == "http://gpu-box:11434"

    def test_empty_value_falls_back_to_the_default(self, monkeypatch):
        monkeypatch.setenv("TORVALDS_OLLAMA_HOST", "")
        assert get_ollama_base_url() == DEFAULT_OLLAMA_BASE_URL

    def test_whitespace_only_value_falls_back_to_the_default(self, monkeypatch):
        monkeypatch.setenv("TORVALDS_OLLAMA_HOST", "   ")
        assert get_ollama_base_url() == DEFAULT_OLLAMA_BASE_URL


class TestOllamaHostFallback:
    """OLLAMA_HOST is honoured, but only when the agent-specific one is unset."""

    def test_ollama_host_is_used_as_a_fallback(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_HOST", "http://fallback:11434")
        assert get_ollama_base_url() == "http://fallback:11434"

    def test_torvalds_host_wins_over_ollama_host(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_HOST", "http://fallback:11434")
        monkeypatch.setenv("TORVALDS_OLLAMA_HOST", "http://primary:11434")
        assert get_ollama_base_url() == "http://primary:11434"

    def test_bare_ollama_host_gets_the_http_scheme(self, monkeypatch):
        # This is the form the Ollama *server* uses to bind all interfaces.
        monkeypatch.setenv("OLLAMA_HOST", "0.0.0.0:11434")
        assert get_ollama_base_url() == "http://0.0.0.0:11434"


class TestIntegration:
    """The orchestrators and the retriever must use the resolved endpoint."""

    def test_retriever_embedding_uses_the_resolved_endpoint(self, monkeypatch):
        monkeypatch.setenv("TORVALDS_OLLAMA_HOST", "http://gpu-box:11434")

        import agent_tool_retriever as retriever

        assert retriever.Settings.embed_model.base_url == "http://gpu-box:11434"

    def test_orchestrators_expose_the_resolved_endpoint(self, monkeypatch):
        monkeypatch.setenv("TORVALDS_OLLAMA_HOST", "http://gpu-box:11434")

        import importlib.util

        for name, path in (
            ("agent_torvalds", "agent-torvalds.py"),
            ("agent_torvalds_mw", "agent-torvalds-mw.py"),
        ):
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            try:
                spec.loader.exec_module(module)
            finally:
                sys.modules.pop(name, None)

            assert module.OLLAMA_BASE_URL == "http://gpu-box:11434", name
