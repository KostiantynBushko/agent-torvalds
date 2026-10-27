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
import logging
import os

logger = logging.getLogger(__name__)

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

#: Where a context window was found.  The name is written into the log,
#: because a number on its own says nothing about whether it is the
#: number the server really uses.
SOURCE_ENVIRONMENT = "the TORVALDS_CONTEXT_LENGTH override"
SOURCE_RUNNING_MODEL = "the running model (/api/ps)"
SOURCE_MODELFILE = "the model's Modelfile (PARAMETER num_ctx)"
SOURCE_MODEL_MAXIMUM = "the model's advertised maximum"
SOURCE_DEFAULT = "the configured default"
SOURCE_UNKNOWN = "unknown"


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


def resolve_context_window_with_source(
    llm, default: int | None = None
) -> tuple[int | None, str]:
    """Return the context window the Ollama server really uses, and where
    it was found.

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
        A tuple of the context window in tokens (or *default*) and the
        name of the source it came from.
    """
    override = os.environ.get(CONTEXT_LENGTH_ENV_VAR)
    if override and override.strip().isdigit():
        return int(override.strip()), SOURCE_ENVIRONMENT

    for probe, source in (
        (_context_length_from_running_model, SOURCE_RUNNING_MODEL),
        (_context_length_from_modelfile, SOURCE_MODELFILE),
    ):
        length = probe(llm)
        if length and length > 0:
            return int(length), source

    try:
        length = int(llm.metadata.context_window)
        if length > 0:
            return length, SOURCE_MODEL_MAXIMUM
    except Exception:  # noqa: BLE001 - metadata may be unavailable
        pass

    if default is not None:
        return default, SOURCE_DEFAULT

    return None, SOURCE_UNKNOWN


def resolve_context_window(llm, default: int | None = None) -> int | None:
    """Return the context window the Ollama server really uses.

    See :func:`resolve_context_window_with_source` for the order the
    sources are tried in.

    Args:
        llm: The Ollama LLM instance.
        default: Returned when nothing could be determined.

    Returns:
        The context window in tokens, or *default*.
    """
    length, _ = resolve_context_window_with_source(llm, default)
    return length


def apply_context_window(llm, default: int | None = None) -> int | None:
    """Set the LLM's context window to the one the server really uses.

    Setting it on the LLM has two effects: ``llm.metadata.context_window``
    reports the truth, and the ``num_ctx`` option sent with every request
    matches the server instead of asking for an impossible window.

    The window is written to the log at the ``INFO`` level, together with
    the source it came from.  The number alone does not say whether it is
    the window the server really uses or merely the maximum the model
    advertises — and the difference between the two is the difference
    between a prompt that fits and one the server truncates from the
    front.

    Args:
        llm: The Ollama LLM instance.
        default: Used when the window cannot be determined.

    Returns:
        The context window in tokens, or ``None`` when it could not be
        determined or the LLM did not accept it.
    """
    length, source = resolve_context_window_with_source(llm, default=default)
    if not length or length <= 0:
        logger.info(
            "Context window: unknown — the server did not report one, so "
            "the context guard cannot size the prompt."
        )
        return None
    try:
        llm.context_window = int(length)
    except Exception:  # noqa: BLE001 - the LLM may not be an Ollama instance
        logger.info(
            "Context window: %d tokens — %s (the LLM did not accept it)",
            length,
            source,
        )
        return None
    logger.info("Context window: %d tokens — %s", length, source)
    return length
