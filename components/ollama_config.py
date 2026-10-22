"""
Ollama endpoint configuration for the Torvalds agent.

The agent talks to a local [Ollama](https://ollama.com) server for both the
chat model and the embedding model.  Ollama listens on
``http://localhost:11434`` by default, and that is where the agent looks
unless an override is configured.

Two environment variables are honoured, in this order:

``TORVALDS_OLLAMA_HOST``
    The agent-specific override.  Use this one.
``OLLAMA_HOST``
    The standard Ollama variable.  It is usually set for the *server* to
    decide which interface to bind to (e.g. ``0.0.0.0:11434``), so it is
    only used as a fallback and the scheme is normalised for the client.

Both the LlamaIndex ``Ollama`` LLM and the ``OllamaEmbedding`` class expect a
full URL including the scheme, so a bare ``host:port`` is rewritten to
``http://host:port``.

Example:
    TORVALDS_OLLAMA_HOST=http://192.168.1.10:11434 python agent-torvalds.py
"""
import os

#: Endpoint used when nothing is configured.
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"

#: Environment variables, in order of precedence.
OLLAMA_HOST_ENV_VARS = ("TORVALDS_OLLAMA_HOST", "OLLAMA_HOST")


def _normalize_base_url(url: str) -> str:
    """Add the default scheme when the URL does not carry one.

    The Ollama *server* accepts a bare ``host:port`` (that is how
    ``OLLAMA_HOST=0.0.0.0:11434`` is normally written), but the HTTP client
    used by LlamaIndex needs a complete URL.

    Args:
        url: The raw value of the environment variable.

    Returns:
        str: A URL with a scheme.
    """
    if "://" not in url:
        return f"http://{url}"
    return url


def get_ollama_base_url() -> str:
    """Return the Ollama endpoint the agent should connect to.

    Returns:
        str: The base URL of the Ollama server, e.g.
        ``http://localhost:11434``.
    """
    for var in OLLAMA_HOST_ENV_VARS:
        raw = os.environ.get(var)
        if raw and raw.strip():
            return _normalize_base_url(raw.strip())
    return DEFAULT_OLLAMA_BASE_URL
