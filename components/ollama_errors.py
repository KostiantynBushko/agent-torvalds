"""What to say when the model server fails.

The agent talks to Ollama over HTTP.  When the server fails, what comes
back is a status code, a reference and a phrase - and nothing a person
can act on.  A traceback pasted into the chat is the worst answer to
that: it shows where the failure happened *inside the agent*, and it
hides the one thing that matters, which is that the **server** failed.

This module says what actually went wrong, in the words of the person
who has to fix it, and keeps the traceback for the log.

The errors it knows about, and where they come from:

- ``ollama.ResponseError`` - the server answered with a status.  The
  status is the useful part: 500 means the server died, 404 means the
  model is not pulled, 400 means the request was rejected.
- ``ollama.ResponseError`` with the status ``-1`` - the error came in
  the body of a response, so there is no HTTP status of its own.
- ``ConnectionError`` - Ollama turns a refused connection into this one,
  so it means the server could not be reached at all.
- a timeout - the request was sent and nothing came back.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

#: The identifier Ollama puts in the text of its errors.  The operator
#: can match the failure against the server log with it.
_REFERENCE = re.compile(r"\bref:\s*([0-9A-Za-z-]{4,})")

#: The status code Ollama repeats in the text of its own error.
_STATUS_IN_TEXT = re.compile(r"\s*\(status code:\s*-?\d+\)")


def status_code_of(exc: BaseException) -> Optional[int]:
    """The HTTP status code an exception carries, if it carries one.

    Ollama's ``ResponseError`` carries the status directly.  An error
    that came in the body of a response carries none - Ollama raises it
    with the status ``-1`` - and neither does a connection failure.

    Args:
        exc: The exception to look at.

    Returns:
        The status code, or ``None`` when there is none.
    """
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and status > 0:
        return status

    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if isinstance(status, int) and status > 0:
        return status

    return None


def reference_of(exc: BaseException) -> Optional[str]:
    """The reference an error carries, if it carries one.

    Args:
        exc: The exception to look at.

    Returns:
        The reference, or ``None`` when there is none.
    """
    match = _REFERENCE.search(str(exc))
    if match is None:
        return None
    return match.group(1)


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
    text = getattr(exc, "error", None)
    if not isinstance(text, str) or not text.strip():
        text = str(exc)

    text = _STATUS_IN_TEXT.sub("", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def describe(exc: BaseException) -> str:
    """The message to show the operator when a request fails.

    The message names what failed and what to do about it.  It never
    carries a traceback: the traceback belongs in the log, and the
    operator is not the one who has to read the frames.

    Args:
        exc: The exception that ended the request.

    Returns:
        The message to show.
    """
    status = status_code_of(exc)
    if status is not None:
        return _for_a_status(exc, status)

    if isinstance(exc, ConnectionError):
        return (
            f"The model server could not be reached at {_host()}. "
            "Is Ollama running? `ollama serve` starts it."
        )

    if _is_a_timeout(exc):
        return (
            "The model did not answer in time. The request may be too "
            "long for the context window, or the server may still be "
            "loading the model."
        )

    if _came_in_the_body(exc):
        return (
            "The model server reported an error while it was answering. "
            f"It said: {server_text(exc)}"
        )

    return f"Error: {server_text(exc)}"


def log_failure(exc: BaseException) -> None:
    """Write the traceback of a failure to the log.

    The traceback says where the failure happened *inside the agent*.
    That is what the log is for.  The chat gets the message from
    :func:`describe`, which says what actually went wrong.

    Args:
        exc: The exception that ended the request.
    """
    logger.error("The request failed: %s", exc, exc_info=exc)


def _for_a_status(exc: BaseException, status: int) -> str:
    """The message for an error the server answered with a status.

    Args:
        exc: The exception the server answered with.
        status: The HTTP status the server answered with.

    Returns:
        The message to show.
    """
    if status == 500:
        message = (
            "The model server failed (HTTP 500). The request reached "
            "Ollama, and the server could not answer it. The usual "
            "causes are a model that crashed and a model that ran out "
            "of memory - `ollama ps` shows whether a model is loaded, "
            "and the server log says why it died."
        )
    elif status == 404:
        message = (
            "The model was not found (HTTP 404). The server answered, "
            "but it does not have the model the agent asked for. Pull "
            "it with `ollama pull <model>`."
        )
    elif status == 400:
        message = (
            "The model server rejected the request (HTTP 400). The most "
            "common cause is a prompt longer than the context window - "
            "the agent sends the last turns that fit."
        )
    elif status in (401, 403):
        message = (
            f"The model server refused the request (HTTP {status}). It "
            "wants credentials the agent does not have."
        )
    else:
        message = (
            f"The model server answered with an error (HTTP {status}). "
            f"It said: {server_text(exc)}"
        )

    reference = reference_of(exc)
    if reference is not None:
        message = f"{message} Reference: {reference}."

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
    status = getattr(exc, "status_code", None)
    return isinstance(status, int) and status == -1


def _is_a_timeout(exc: BaseException) -> bool:
    """Whether the failure is a timeout.

    The check is on the name and not on the class: the HTTP client of
    the agent is not a declared dependency, and a timeout raised by any
    client is a timeout.

    Args:
        exc: The exception to look at.

    Returns:
        ``True`` when the failure is a timeout.
    """
    if isinstance(exc, TimeoutError):
        return True
    return "timeout" in type(exc).__name__.lower()


def _host() -> str:
    """The address of the model server, for the message.

    Returns:
        The address, or a phrase that fits any address when the
        configuration cannot be read.
    """
    try:
        from components.ollama_config import get_ollama_base_url

        return get_ollama_base_url()
    except Exception:  # noqa: BLE001 - the message must survive anything
        return "the configured endpoint"
