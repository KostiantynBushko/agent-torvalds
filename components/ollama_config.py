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
``TORVALDS_CONTEXT_LENGTH``
    Override the context window the agent assumes.  Use this when the
    server runs with a context length that cannot be detected.

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


#: Environment variable that overrides the detected context window.
CONTEXT_LENGTH_ENV_VAR = "TORVALDS_CONTEXT_LENGTH"


def _context_length_from_modelfile(llm) -> int | None:
    """Read ``PARAMETER num_ctx`` from the model's Modelfile.

    Ollama stores the context length a model was created with in its
    Modelfile.  That value — and not the model's advertised maximum — is
    what the server uses unless it is overridden on the command line.
    """
    try:
        info = llm.client.show(llm.model)
    except Exception:  # noqa: BLE001 - the server may be unreachable
        return None

    modelfile = getattr(info, "modelfile", None) or ""
    for line in modelfile.splitlines():
        line = line.strip()
        if not line.upper().startswith("PARAMETER NUM_CTX"):
            continue
        value = line.split("num_ctx")[-1].strip()
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _context_length_from_running_model(llm) -> int | None:
    """Read the context length of the model that is currently loaded.

    ``/api/ps`` reports the context length the server actually allocated,
    which is the authoritative value while the model is loaded.  The
    request is made directly so that it does not depend on the internals
    of the Ollama client.
    """
    import json
    import urllib.request

    base_url = str(getattr(llm, "base_url", "") or "").rstrip("/")
    if not base_url:
        return None

    try:
        with urllib.request.urlopen(f"{base_url}/api/ps", timeout=10) as resp:
            payload = json.loads(resp.read().decode())
    except Exception:  # noqa: BLE001 - the endpoint may be unavailable
        return None

    for entry in payload.get("models") or []:
        name = entry.get("model") or entry.get("name") or ""
        if llm.model in name or name in llm.model:
            length = entry.get("context_length")
            if length:
                return int(length)
    return None


def resolve_context_window(llm, default: int | None = None) -> int | None:
    """Return the context window the Ollama server really uses.

    ``llm.metadata.context_window`` reports the *model's maximum*
    context length.  The server usually runs with a much smaller window
    (``PARAMETER num_ctx`` in the Modelfile, or ``--ctx-size`` on the
    command line), and a prompt that exceeds it is silently truncated from
    the front — which drops the user request and makes the model template
    fail with "No user query found in messages.".

    The sources are tried in order of decreasing accuracy:

    1. ``TORVALDS_CONTEXT_LENGTH`` — explicit override.
    2. ``/api/ps`` — the context length of the running model.
    3. ``PARAMETER num_ctx`` in the model's Modelfile.
    4. ``llm.metadata.context_window`` — the model's maximum.

    Args:
        llm: The Ollama LLM instance.
        default: Returned when nothing could be determined.

    Returns:
        The context window in tokens, or *default*.
    """
    override = os.environ.get(CONTEXT_LENGTH_ENV_VAR)
    if override and override.strip().isdigit():
        return int(override.strip())

    for probe in (
        _context_length_from_running_model,
        _context_length_from_modelfile,
    ):
        length = probe(llm)
        if length and length > 0:
            return length

    try:
        length = int(llm.metadata.context_window)
        if length > 0:
            return length
    except Exception:  # noqa: BLE001 - metadata may be unavailable
        pass

    return default


def apply_context_window(llm, default: int | None = None) -> int | None:
    """Set the LLM's context window to the one the server really uses.

    Setting it on the LLM has two effects: ``llm.metadata.context_window``
    reports the truth, and the ``num_ctx`` option sent with every request
    matches the server instead of asking for an impossible window.
    """
    length = resolve_context_window(llm, default=default)
    if not length or length <= 0:
        return None
    try:
        llm.context_window = int(length)
    except Exception:  # noqa: BLE001 - the LLM may not be an Ollama instance
        return None
    return length
