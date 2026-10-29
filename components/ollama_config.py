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
        logger.debug("Adding default http scheme to URL: %s -> http://%s", url, url)
        return f"http://{url}"
    logger.debug("URL already has scheme: %s", url)
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
            normalized = _normalize_base_url(raw.strip())
            logger.info(
                "Ollama base URL from environment variable %s: %s",
                var,
                normalized,
            )
            return normalized
    logger.info(
        "No Ollama host environment variable set, using default: %s",
        DEFAULT_OLLAMA_BASE_URL,
    )
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
    logger.debug("Probing context length from Modelfile for model: %s", llm.model)
    try:
        info = llm.client.show(llm.model)
    except Exception as e:
        logger.debug(
            "Failed to retrieve model info from server for Modelfile probe: %s", e
        )
        return None

    modelfile = getattr(info, "modelfile", None) or ""
    if not modelfile:
        logger.debug("No Modelfile content available for model: %s", llm.model)
        return None

    for line in modelfile.splitlines():
        line = line.strip()
        if not line.upper().startswith("PARAMETER NUM_CTX"):
            continue
        value = line.split("num_ctx")[-1].strip()
        try:
            length = int(value)
            logger.info(
                "Context length from Modelfile for model %s: %d tokens",
                llm.model,
                length,
            )
            return length
        except ValueError:
            logger.warning(
                "Invalid num_ctx value in Modelfile for model %s: %s",
                llm.model,
                value,
            )
            return None
    logger.debug(
        "No PARAMETER num_ctx found in Modelfile for model: %s", llm.model
    )
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

    logger.debug(
        "Probing context length from running model via /api/ps for: %s",
        llm.model,
    )

    base_url = str(getattr(llm, "base_url", "") or "").rstrip("/")
    if not base_url:
        logger.debug("No base_url available on LLM instance, skipping /api/ps probe")
        return None

    try:
        with urllib.request.urlopen(f"{base_url}/api/ps", timeout=10) as resp:
            payload = json.loads(resp.read().decode())
    except Exception as e:
        logger.debug(
            "Failed to query /api/ps for running model context length: %s", e
        )
        return None

    models = payload.get("models") or []
    if not models:
        logger.debug("No running models found in /api/ps response")
        return None

    for entry in models:
        name = entry.get("model") or entry.get("name") or ""
        if llm.model in name or name in llm.model:
            length = entry.get("context_length")
            if length:
                logger.info(
                    "Context length from running model %s: %d tokens",
                    name,
                    length,
                )
                return int(length)
            logger.debug(
                "Running model %s found but has no context_length field", name
            )
    logger.debug(
        "No matching running model found for %s in /api/ps", llm.model
    )
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
    logger.debug(
        "Resolving context window for model: %s, default: %s",
        getattr(llm, "model", "unknown"),
        default,
    )

    # 1. Check explicit environment override
    override = os.environ.get(CONTEXT_LENGTH_ENV_VAR)
    if override and override.strip().isdigit():
        length = int(override.strip())
        logger.info(
            "Context window resolved from %s: %d tokens",
            SOURCE_ENVIRONMENT,
            length,
        )
        return length, SOURCE_ENVIRONMENT
    elif override:
        logger.warning(
            "Invalid value for %s: %s (expected integer)",
            CONTEXT_LENGTH_ENV_VAR,
            override,
        )

    # 2 & 3. Probe running model and Modelfile
    for probe, source in (
        (_context_length_from_running_model, SOURCE_RUNNING_MODEL),
        (_context_length_from_modelfile, SOURCE_MODELFILE),
    ):
        logger.debug("Attempting to resolve context window from: %s", source)
        length = probe(llm)
        if length and length > 0:
            logger.info(
                "Context window resolved from %s: %d tokens",
                source,
                length,
            )
            return int(length), source
        logger.debug("Could not resolve context window from: %s", source)

    # 4. Fall back to model's advertised maximum
    try:
        length = int(llm.metadata.context_window)
        if length > 0:
            logger.info(
                "Context window resolved from %s: %d tokens",
                SOURCE_MODEL_MAXIMUM,
                length,
            )
            return length, SOURCE_MODEL_MAXIMUM
    except Exception as e:
        logger.debug(
            "Could not read context_window from llm.metadata: %s", e
        )

    # 5. Use default if provided
    if default is not None:
        logger.info(
            "Context window resolved from %s: %s tokens",
            SOURCE_DEFAULT,
            default,
        )
        return default, SOURCE_DEFAULT

    # 6. Nothing could be determined
    logger.warning(
        "Could not determine context window for model %s from any source",
        getattr(llm, "model", "unknown"),
    )
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
    length, source = resolve_context_window_with_source(llm, default)
    if length is not None:
        logger.debug(
            "Resolved context window: %d tokens (source: %s)", length, source
        )
    else:
        logger.debug("Could not resolve context window from any source")
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
    logger.debug(
        "Applying context window for model: %s, default: %s",
        getattr(llm, "model", "unknown"),
        default,
    )

    length, source = resolve_context_window_with_source(llm, default=default)
    if not length or length <= 0:
        logger.info(
            "Context window: unknown — the server did not report one, so "
            "the context guard cannot size the prompt."
        )
        return None

    try:
        llm.context_window = int(length)
    except Exception as e:
        logger.info(
            "Context window: %d tokens — %s (the LLM did not accept it: %s)",
            length,
            source,
            e,
        )
        return None

    logger.info("Context window: %d tokens — %s", length, source)
    return length