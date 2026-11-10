"""What to say when the model server fails.

The agent talks to a model server over HTTP.  When the server fails, what
comes back is a status code, a reference and a phrase - and nothing a
person can act on.  A traceback pasted into the chat is the worst answer
to that: it shows where the failure happened *inside the agent*, and it
hides the one thing that matters, which is that the **server** failed.

This module says what actually went wrong, in the words of the person who
has to fix it, and keeps the traceback for the log - under the DEBUG
level, where the frames of the agent belong.

**The wording belongs to the provider.**  A 500 from a local Ollama server
means the model crashed; a 500 from the Anthropic API means the API had a
fault of its own.  A message that names the wrong provider is worse than
no message at all, so the provider is found twice - from the failure
itself, which is the better witness, and from the LLM the agent holds,
which is the fallback for the failures that say nothing.  Ollama turns a
refused connection into a plain ``ConnectionError``, and that failure
names nobody.

The module depends on no provider package at all - not even on the one
that raised the error.  It reads the failure the way every HTTP client
reports it: a status code, a text and a class name.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

#: The identifiers the backends put in their errors.  Ollama writes
#: ``ref:``, and the cloud APIs write ``request-id:``.
_REFERENCE = re.compile(r"\b(?:ref|request-id)\s*:\s*([0-9A-Za-z_-]{4,})")

#: The status code Ollama repeats in the text of its own error.
_STATUS_IN_TEXT = re.compile(r"\s*\(status code:\s*-?\d+\)")

#: The names the HTTP clients give their connection failures.  The module
#: depends on no provider package - not even on the one that raised the
#: error - so the failure is recognised by the name it was given:
#: ``httpx.ConnectError``, ``anthropic.APIConnectionError`` and
#: ``openai.APIConnectionError`` all say the same thing.
_CONNECTION_NAMES = ("connectionerror", "connecterror")

#: The names the HTTP clients give their timeouts: ``httpx.TimeoutException``,
#: ``anthropic.APITimeoutError`` and ``openai.APITimeoutError``.
_TIMEOUT_NAMES = ("timeout",)


# ---------------------------------------------------------------------------
# The providers
# ---------------------------------------------------------------------------


class Provider:
    """What the operator needs to know about one model backend.

    Attributes:
        subject: How the backend is called in a sentence - "The Ollama
            server", "The Anthropic API".  The message starts with it,
            so a failure is named after the backend that failed, and
            after nothing at all when the backend is unknown.
        packages: The packages whose errors belong to this backend.
        llm_paths: The parts of a module path that belong to this
            backend, for the LLM instances the agent holds.
        endpoint: The address of the backend, when nothing is configured.
        endpoint_env: The environment variables that hold the address of
            the backend.  A cloud API keeps its own address and its SDK
            reads it from the environment; a server on the machine takes
            the ``llm.host`` setting instead, and leaves this empty.
        advice: What to do about each status the backend answers with.  A
            status that is not listed gets the generic advice.
        unreachable: What to do when the backend cannot be reached at all.
    """

    subject = "The model server"
    packages: tuple = ()
    llm_paths: tuple = ()
    endpoint = ""
    endpoint_env: tuple = ()
    advice: dict = {}
    unreachable = "Is it running?"


class Ollama(Provider):
    """The model server on the machine."""

    subject = "The Ollama server"
    packages = ("ollama",)
    llm_paths = ("llama_index.llms.ollama",)
    endpoint = "http://localhost:11434"
    unreachable = "Is it running? `ollama serve` starts it."
    advice = {
        400: (
            "The most common cause is a prompt that is longer than the "
            "context window - the agent sends the last turns that fit."
        ),
        404: (
            "The model was not found: the server does not have the model "
            "the agent asked for. Pull it with `ollama pull <model>`."
        ),
        500: (
            "The usual causes are a model that crashed and a model that "
            "ran out of memory - `ollama ps` shows whether a model is "
            "loaded, and the server log says why it died."
        ),
    }


class Anthropic(Provider):
    """The Anthropic API."""

    subject = "The Anthropic API"
    packages = ("anthropic",)
    llm_paths = ("llama_index.llms.anthropic",)
    endpoint = "https://api.anthropic.com"
    endpoint_env = ("ANTHROPIC_BASE_URL",)
    # A key that is wrong is answered with 401, and that advice names
    # the key.  A refused connection is the network, not the key.
    unreachable = "Check that the address is reachable, and that no proxy is in the way."
    advice = {
        400: (
            "Anthropic rejects a prompt that is longer than the context "
            "window, and a `max_tokens` larger than the model's."
        ),
        401: (
            "Anthropic wants an API key: set `ANTHROPIC_API_KEY`, and "
            "check that it belongs to the account that may use the model."
        ),
        404: (
            "Anthropic answers 404 for a model id that does not exist - "
            "check the model id in `llm.model` (the ids look like "
            "`claude-sonnet-4-5`)."
        ),
        429: (
            "This is a usage limit: the account sent too many requests, "
            "or too many tokens. Wait a moment and try again."
        ),
        500: (
            "It is a fault of the API and not of the request: the request "
            "sent again is likely to succeed."
        ),
        529: (
            "Anthropic answers 529 when the model is overloaded. Wait a "
            "moment and try again."
        ),
    }


class OpenAI(Provider):
    """The OpenAI API."""

    subject = "The OpenAI API"
    packages = ("openai",)
    llm_paths = ("llama_index.llms.openai",)
    endpoint = "https://api.openai.com"
    endpoint_env = ("OPENAI_BASE_URL",)
    # A key that is wrong is answered with 401, and that advice names
    # the key.  A refused connection is the network, not the key.
    unreachable = "Check that the address is reachable, and that no proxy is in the way."
    advice = {
        401: (
            "OpenAI wants an API key: set `OPENAI_API_KEY`, and check "
            "that it belongs to the account that may use the model."
        ),
        404: (
            "OpenAI answers 404 for a model id that does not exist - "
            "check the model id in `llm.model`."
        ),
        429: (
            "This is a usage limit: the account sent too many requests, "
            "or too many tokens. Wait a moment and try again."
        ),
        500: (
            "It is an error on OpenAI's side and not of the request: the "
            "request sent again is likely to succeed."
        ),
    }


#: The backends the agent can talk to, in the order they are looked for.
_PROVIDERS = (Ollama, Anthropic, OpenAI)

#: The advice that holds for any model server.
_GENERIC_ADVICE = {
    400: "The most common cause is a prompt that is longer than the context window.",
    401: "It wants credentials the agent does not have.",
    403: "The credentials the agent has may not be allowed to use this model.",
    404: "Check the model id, and check that the account may use it.",
    429: "The request was too many, or too fast. Wait a moment and try again.",
    500: "The request reached the server, and the server could not answer it.",
    529: "It answered that it is too busy. Wait a moment and try again.",
}

#: The lead of the message, for each status a model server answers with.
#: The subject of the backend is put in front of it: "The Ollama server
#: failed (HTTP 500)."
_LEAD = {
    400: "rejected the request (HTTP 400).",
    401: "refused the request (HTTP 401).",
    403: "refused the request (HTTP 403).",
    429: "is rate-limiting the agent (HTTP 429).",
    500: "failed (HTTP 500).",
    529: "is overloaded (HTTP 529).",
}


# ---------------------------------------------------------------------------
# Reading the failure
# ---------------------------------------------------------------------------


def _chain(exc: BaseException) -> Iterator[BaseException]:
    """The exception and the ones it was raised from.

    A client library often wraps the failure of the server, so the
    status code and the name of the failure are on the exception
    underneath.

    Args:
        exc: The exception to walk.

    Yields:
        Every exception of the chain, the first one first.
    """
    seen: set[int] = set()
    current: Optional[BaseException] = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def provider_of(exc: BaseException) -> Optional[Provider]:
    """The backend the failure came from.

    The failure is the better witness: it names the backend that failed,
    while the LLM only names the backend the agent *asked*.

    Args:
        exc: The exception to look at.

    Returns:
        The backend, or ``None`` when the failure names none.
    """
    package = type(exc).__module__.split(".")[0]
    for provider in _PROVIDERS:
        if package in provider.packages:
            return provider()
    return None


def provider_of_the_llm(llm: object) -> Optional[Provider]:
    """The backend the LLM talks to.

    The LLM is the fallback witness.  The failures that say nothing about
    who failed - Ollama turns a refused connection into a plain
    ``ConnectionError`` - are still described in the words of the backend
    the agent was talking to.

    The whole **line of ancestors** of the LLM is looked at, not only the
    class itself: the LLM of the agent is a subclass of the LLM of the
    provider - ``RetryingOllama`` is an ``Ollama`` - and the subclass
    lives in a module of its own, which names no provider at all.

    Args:
        llm: The LLM the agent holds, or ``None``.

    Returns:
        The backend, or ``None`` when the LLM names none.
    """
    if llm is None:
        return None

    for klass in type(llm).__mro__:
        module = klass.__module__
        for provider in _PROVIDERS:
            if any(path in module for path in provider.llm_paths):
                return provider()
    return None


def status_code_of(exc: BaseException) -> Optional[int]:
    """The HTTP status code an exception carries, if it carries one.

    Ollama's ``ResponseError`` carries the status directly, and so does
    the ``APIStatusError`` of the cloud SDKs.  An error that came in the
    body of a response carries none - Ollama raises it with the status
    ``-1`` - and neither does a connection failure.

    Args:
        exc: The exception to look at.

    Returns:
        The status code, or ``None`` when there is none.
    """
    for error in _chain(exc):
        status = getattr(error, "status_code", None)
        if isinstance(status, int) and status > 0:
            return status

        response = getattr(error, "response", None)
        status = getattr(response, "status_code", None)
        if isinstance(status, int) and status > 0:
            return status

    return None


def reference_of(exc: BaseException) -> Optional[str]:
    """The reference an error carries, if it carries one.

    The cloud SDKs put the id of the request on the exception; Ollama
    puts it in the text of the error.

    Args:
        exc: The exception to look at.

    Returns:
        The reference, or ``None`` when there is none.
    """
    for error in _chain(exc):
        request_id = getattr(error, "request_id", None)
        if isinstance(request_id, str) and request_id.strip():
            return request_id.strip()

        match = _REFERENCE.search(str(error))
        if match is not None:
            return match.group(1)

    return None


def server_text(exc: BaseException) -> str:
    """The text of an error, as the server wrote it.

    Ollama repeats the status code in the text of its own error, so the
    text is cleaned before it is shown: "Internal Server Error (status
    code: 500) (status code: 500)" says the same thing twice.

    Args:
        exc: The exception to read.

    Returns:
        The text of the error.
    """
    for error in _chain(exc):
        text = getattr(error, "error", None)
        if not isinstance(text, str) or not text.strip():
            text = getattr(error, "message", None)
        if not isinstance(text, str) or not text.strip():
            text = str(error)

        text = _STATUS_IN_TEXT.sub("", text)
        text = re.sub(r"\s{2,}", " ", text).strip()
        if text:
            return text

    return str(exc)


def endpoint_for(provider: Optional[Provider]) -> str:
    """The address of the backend, for the message about a dead server.

    A server on the machine takes the ``llm.host`` setting - it points at
    whatever serves the model.  A cloud API keeps its own address, and
    its SDK reads it from the environment; the ``llm.host`` setting says
    nothing about it, and using it would name the wrong address.

    Args:
        provider: The backend in question.

    Returns:
        The address, or an empty string when there is none.
    """
    if provider is None or not provider.endpoint:
        return ""

    if provider.endpoint_env:
        for var in provider.endpoint_env:
            raw = os.environ.get(var)
            if raw and raw.strip():
                return raw.strip()
        return provider.endpoint

    from components.ollama_config import get_configured_base_url

    return get_configured_base_url(provider.endpoint)


def _subject_of(provider: Optional[Provider]) -> str:
    """How the backend is called in the message.

    Args:
        provider: The backend in question, or ``None``.

    Returns:
        The subject of the backend, or the neutral one when the backend
        is unknown.
    """
    if provider is None:
        return "The model server"
    return provider.subject


# ---------------------------------------------------------------------------
# The message
# ---------------------------------------------------------------------------


def describe(exc: BaseException, provider: Optional[Provider] = None) -> str:
    """The message to show the operator when a request fails.

    The message names what failed and what to do about it.  It never
    carries a traceback: the traceback belongs in the log, and the
    operator is not the one who has to read the frames.

    Args:
        exc: The exception that ended the request.
        provider: The backend the agent was talking to, for the failures
            that do not name one themselves.

    Returns:
        The message to show.
    """
    resolved = provider_of(exc) or provider
    status = status_code_of(exc)

    if status is not None:
        return _for_a_status(exc, resolved, status)

    if is_a_connection_failure(exc):
        return _the_server_cannot_be_reached(resolved)

    if is_a_timeout(exc):
        return (
            f"{_subject_of(resolved)} did not answer in time. The request "
            "may be too long for the context window, or the server may "
            "still be loading the model."
        )

    if _came_in_the_body(exc):
        return (
            f"{_subject_of(resolved)} reported an error while it was "
            f"answering. It said: {server_text(exc)}"
        )

    return f"Error: {server_text(exc)}"


def log_failure(exc: BaseException) -> None:
    """Write a failure to the log.

    Two records are written, and they answer two different questions.

    The **ERROR** record says *what* failed: "The request failed: Internal
    Server Error (ref: ...) (status code: 500)".  That is the line the
    operator reads when the agent says that the server failed.

    The **DEBUG** record carries the frames of the agent.  They say where
    the failure happened *inside the agent*, and they are of no use to
    anybody who did not write the agent - so they are written under the
    DEBUG level, where they are found when they are looked for and stay
    out of the way when they are not.

    The chat gets the message from :func:`describe`, which says what
    actually went wrong.

    Args:
        exc: The exception that ended the request.
    """
    logger.error("The request failed: %s", exc)
    logger.debug("The request failed — the frames of the agent:", exc_info=exc)


def _for_a_status(
    exc: BaseException, provider: Optional[Provider], status: int
) -> str:
    """The message for a failure the server answered with a status.

    Args:
        exc: The exception the server answered with.
        provider: The backend the failure came from.
        status: The HTTP status the server answered with.

    Returns:
        The message to show.
    """
    lead = _LEAD.get(status)
    if lead is None:
        lead = f"answered with an error (HTTP {status})."

    parts = [f"{_subject_of(provider)} {lead} "]

    endpoint = endpoint_for(provider)
    if endpoint:
        parts.append(f"The request went to {endpoint}. ")

    advice = None
    if provider is not None:
        advice = provider.advice.get(status)
    if advice is None:
        advice = _GENERIC_ADVICE.get(status)
    if advice is None:
        advice = f"It said: {server_text(exc)}"
    parts.append(advice)

    message = "".join(parts)

    reference = reference_of(exc)
    if reference is not None:
        message = f"{message} Reference: {reference}."

    return message


def _the_server_cannot_be_reached(provider: Optional[Provider]) -> str:
    """The message for a server that did not answer at all.

    Args:
        provider: The backend the agent tried to reach.

    Returns:
        The message to show.
    """
    subject = _subject_of(provider)
    endpoint = endpoint_for(provider)

    if endpoint:
        message = f"{subject} could not be reached at {endpoint}."
    else:
        message = f"{subject} could not be reached."

    if provider is not None and provider.unreachable:
        message = f"{message} {provider.unreachable}"

    return message


def _came_in_the_body(exc: BaseException) -> bool:
    """Whether the error came in the body of a response.

    Ollama raises such an error with the status ``-1``: the response
    was fine, and the body carried the failure.

    Args:
        exc: The exception to look at.

    Returns:
        ``True`` when the error came in the body.
    """
    for error in _chain(exc):
        status = getattr(error, "status_code", None)
        if isinstance(status, int) and status == -1:
            return True
    return False


def is_a_connection_failure(exc: BaseException) -> bool:
    """Whether the failure is a connection that never came about.

    Args:
        exc: The exception to look at.

    Returns:
        ``True`` when the server could not be reached.
    """
    for error in _chain(exc):
        if isinstance(error, ConnectionError):
            return True
        if _named(error, _CONNECTION_NAMES):
            return True
    return False


def is_a_timeout(exc: BaseException) -> bool:
    """Whether the failure is a timeout.

    Args:
        exc: The exception to look at.

    Returns:
        ``True`` when the failure is a timeout.
    """
    for error in _chain(exc):
        if isinstance(error, TimeoutError):
            return True
        if _named(error, _TIMEOUT_NAMES):
            return True
    return False


def _named(exc: BaseException, names: tuple[str, ...]) -> bool:
    """Whether the name of an exception carries one of the given names.

    Args:
        exc: The exception to look at.
        names: The names to look for, in lower case.

    Returns:
        ``True`` when the name carries one of them.
    """
    name = type(exc).__name__.lower()
    return any(candidate in name for candidate in names)
