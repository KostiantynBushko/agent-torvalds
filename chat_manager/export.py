"""The content of a session, rendered for the operator.

The ``\\chat-export`` command prints the content of the active session, or
writes it to a file.  This module is what the export *looks like* — the
header that says which session it is, and the transcript of its messages.

Two things are called "the session", and they are not the same size:

* the **stored** messages — everything the session keeps, which grows with
  every turn and is never trimmed by the agent;
* the **buffered** messages — the tail of the history that survives the
  chat-token limit, and is what the model is actually sent.

An export can carry either one, and the header says which — an export
that does not say where it came from is a mystery file.

And it can be written in two formats:

* the **text** — the rendering the log already uses
  (:func:`components.chat_message.to_string`), so the text of a session
  reads the same everywhere it is shown;
* the **JSON** — the same messages, structured, for a program that has to
  read them.  It is not the text with brackets around it: the role, the
  content, the thinking and the tool calls are fields, and a consumer
  does not have to parse a line to learn what a message is.

Category: Infrastructure
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from chat_manager.stats import count_tokens, format_size, message_text
from components.chat_message import to_string

logger = logging.getLogger(__name__)

#: The format of an export — the text a person reads.
FORMAT_TEXT = "text"

#: The format of an export — the JSON a program reads.
FORMAT_JSON = "json"

#: The source of an export — everything the session keeps.
SOURCE_STORED = "stored"

#: The source of an export — the tail of the history that reaches the model.
SOURCE_BUFFER = "buffer"

#: How the sources are named in the words of the command.
SOURCE_NOUN = {
    SOURCE_STORED: "stored messages",
    SOURCE_BUFFER: "buffered messages",
}

__all__ = [
    "FORMAT_JSON",
    "FORMAT_TEXT",
    "SOURCE_BUFFER",
    "SOURCE_NOUN",
    "SOURCE_STORED",
    "message_to_dict",
    "render_transcript",
    "render_header",
    "render_json",
    "render_session",
    "render_text",
    "resolve_path",
    "write_export",
]


# ---------------------------------------------------------------------------
# The rendering
# ---------------------------------------------------------------------------


def render_transcript(messages: Sequence[Any]) -> str:
    """Render the messages of a session as a readable transcript.

    One message per line, in the order the session kept them.  A message
    that carries nothing reads as ``"assistant: (empty)"`` — the renderer
    of the project says so, and the export says the same.

    Args:
        messages: The messages of the session.

    Returns:
        The transcript of the session.
    """
    return "\n".join(to_string(message) for message in messages)


def _session_fields(session: Any) -> Dict[str, Any]:
    """Return what is known about the session.

    The same fields serve the text header and the JSON document: a
    consumer of the JSON must learn the same things about the session
    that a reader of the text learns.

    Args:
        session: The session of the export.

    Returns:
        The id, the name, the type and the timestamps of the session.
    """
    name = getattr(session, "session_name", "unknown")
    session_id = getattr(session, "session_id", "unknown")
    session_type = getattr(session, "session_type", None)
    type_name = getattr(session_type, "value", session_type)

    def _timestamp(value: Any) -> Optional[str]:
        isoformat = getattr(value, "isoformat", None)
        if callable(isoformat):
            try:
                return str(isoformat())
            except Exception:  # noqa: BLE001 — a timestamp must not break the export
                return None
        return str(value) if value is not None else None

    return {
        "id": str(session_id),
        "name": str(name),
        "type": str(type_name),
        "created_at": _timestamp(getattr(session, "created_at", None)),
        "updated_at": _timestamp(getattr(session, "updated_at", None)),
    }


def _size_of(messages: Sequence[Any]) -> int:
    """Return the size of the text of the given messages, in bytes."""
    return sum(len(message_text(message).encode("utf-8")) for message in messages)


def _tokens_of(messages: Sequence[Any]) -> str:
    """Return the tokens of the given messages, as they are shown."""
    if not messages:
        return "0"

    tokens, estimated = count_tokens(messages)
    text = f"≈{tokens:,}"
    if estimated:
        text += " — estimated, the tokenizer is not available"
    return text


def render_header(
    session: Any,
    messages: Sequence[Any],
    source: str = SOURCE_STORED,
) -> str:
    """Render the header of an export.

    The header says which session the export came from, **which part of
    it** was exported, and how big that part is.  An export that does not
    say where it came from is a mystery file, and one that does not say
    whether it carries the whole session or only what the model sees is
    half a mystery file.

    The size and the tokens are the ones of the **exported** messages, so
    they describe what was exported and not the session behind it.

    Args:
        session: The session the export is of.
        messages: The messages the export carries.
        source: Where the messages came from — ``SOURCE_STORED`` or
            ``SOURCE_BUFFER``.

    Returns:
        The header of the export.
    """
    fields = _session_fields(session)

    return "\n".join([
        f"Session: {fields['name']} ({fields['id']})",
        f"Type: {fields['type']}",
        (
            f"Source: {source} | Messages: {len(messages)} | "
            f"Size: {format_size(_size_of(messages))} | "
            f"Tokens: {_tokens_of(messages)}"
        ),
    ])


def render_text(
    session: Any,
    messages: Sequence[Any],
    source: str = SOURCE_STORED,
) -> str:
    """Render the whole export of a session as text.

    Args:
        session: The session the export is of.
        messages: The messages of the export.
        source: Where the messages came from — ``SOURCE_STORED`` or
            ``SOURCE_BUFFER``.

    Returns:
        The header of the export, a blank line, and the transcript.
    """
    header = render_header(session, messages, source)

    if not messages:
        return f"{header}\n\nThe session holds no messages."

    return f"{header}\n\n{render_transcript(messages)}"


def render_session(
    session: Any,
    messages: Sequence[Any],
    source: str = SOURCE_STORED,
    output_format: str = FORMAT_TEXT,
) -> str:
    """Render the whole export of a session, in the format asked for.

    Args:
        session: The session the export is of.
        messages: The messages of the export.
        source: Where the messages came from — ``SOURCE_STORED`` or
            ``SOURCE_BUFFER``.
        output_format: The format of the export — ``FORMAT_TEXT`` or
            ``FORMAT_JSON``.

    Returns:
        The export.
    """
    if output_format == FORMAT_JSON:
        return render_json(session, messages, source)

    return render_text(session, messages, source)


# ---------------------------------------------------------------------------
# The JSON
# ---------------------------------------------------------------------------


def _safe_getattr(obj: Any, name: str, default: Any = None) -> Any:
    """Return the attribute *name* of *obj*, or *default*.

    The export must not be able to break a run: a payload whose property
    raises would take the agent down, and the payload is not ours.
    """
    try:
        return getattr(obj, name, default)
    except Exception:  # noqa: BLE001 — a payload must not break the export
        return default


def _role_of(message: Any) -> str:
    """Return the role of a message as a short lower-case name."""
    role = _safe_getattr(message, "role", None)
    if role is None:
        return "?"
    return str(_safe_getattr(role, "value", role)).lower()


def _text_of(message: Any) -> str:
    """Return the text a message carries.

    The text blocks are the truth of a message; the plain ``content`` is
    the older shape, and it is read when there are no blocks.
    """
    parts: List[str] = []

    for block in _safe_getattr(message, "blocks", None) or []:
        if str(_safe_getattr(block, "block_type", "") or "") != "text":
            continue
        text = _safe_getattr(block, "text", "")
        if text:
            parts.append(str(text))

    if parts:
        return "\n".join(parts)

    content = _safe_getattr(message, "content", None)
    return str(content) if content else ""


def _thinking_of(message: Any) -> Optional[str]:
    """Return the thinking of a message, or ``None`` when it has none."""
    parts: List[str] = []

    for block in _safe_getattr(message, "blocks", None) or []:
        if str(_safe_getattr(block, "block_type", "") or "") != "thinking":
            continue
        content = _safe_getattr(block, "content", "")
        if content:
            parts.append(str(content))

    return "\n".join(parts) if parts else None


def _tool_calls_of(message: Any) -> List[Dict[str, Any]]:
    """Return the tool calls a message carries.

    A call can be carried in two places: as a ``ToolCallBlock`` in
    ``message.blocks`` (the current shape) and in the OpenAI-shaped
    ``additional_kwargs["tool_calls"]`` (the shape the Ollama adapter
    still writes).  Both are read, and a call that is in both is
    returned once.
    """
    calls: List[Dict[str, Any]] = []
    seen: List[str] = []

    for block in _safe_getattr(message, "blocks", None) or []:
        if str(_safe_getattr(block, "block_type", "") or "") != "tool_call":
            continue

        name = str(_safe_getattr(block, "tool_name", "") or "")
        arguments = _safe_getattr(block, "tool_kwargs", None)
        calls.append({"name": name, "arguments": arguments})
        seen.append(f"{name}({arguments!r})")

    kwargs = _safe_getattr(message, "additional_kwargs", None) or {}
    try:
        legacy = kwargs.get("tool_calls") or []
    except AttributeError:
        legacy = []

    for call in legacy:
        if isinstance(call, dict):
            function = call.get("function")
            if isinstance(function, dict):
                name = str(function.get("name", "") or "")
                arguments = function.get("arguments")
            else:
                name = str(call.get("name", "") or "")
                arguments = call.get("arguments")
        else:
            name = str(_safe_getattr(call, "name", "") or "")
            arguments = _safe_getattr(call, "arguments", None)

        marker = f"{name}({arguments!r})"
        if name or arguments:
            if marker in seen:
                continue
            seen.append(marker)
            calls.append({"name": name, "arguments": arguments})

    return calls


def message_to_dict(message: Any) -> Dict[str, Any]:
    """Return one message as a dictionary.

    The fields are the ones the renderer reads — the role, the text, the
    thinking and the tool calls — and the metadata of the message, when
    it carries any.  Nothing is lost that a consumer would want.

    Args:
        message: The message.

    Returns:
        The message, as a dictionary.
    """
    metadata = _safe_getattr(message, "metadata", None)

    return {
        "role": _role_of(message),
        "content": _text_of(message),
        "thinking": _thinking_of(message),
        "tool_calls": _tool_calls_of(message),
        "metadata": metadata if isinstance(metadata, dict) else {},
    }


def render_json(
    session: Any,
    messages: Sequence[Any],
    source: str = SOURCE_STORED,
) -> str:
    """Render the export of a session as JSON.

    The document carries the session, the source of the messages, the
    measurements, and the messages themselves — the same things the text
    export carries, in a shape a program can read without parsing a line.

    Args:
        session: The session the export is of.
        messages: The messages of the export.
        source: Where the messages came from — ``SOURCE_STORED`` or
            ``SOURCE_BUFFER``.

    Returns:
        The export, as JSON.
    """
    tokens, estimated = count_tokens(list(messages))

    document = {
        "session": _session_fields(session),
        "source": source,
        "message_count": len(messages),
        "size_bytes": _size_of(messages),
        "tokens": tokens,
        "tokens_estimated": estimated,
        "messages": [message_to_dict(message) for message in messages],
    }

    return json.dumps(document, indent=2, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# The file
# ---------------------------------------------------------------------------


def resolve_path(path: str) -> Path:
    """Return the path an export is written to.

    The path is the operator's: ``~`` is expanded, and a relative path is
    taken from the working directory of the agent.  Nothing is written
    down here — the path comes from the operator, every time.

    Args:
        path: The path the operator gave.

    Returns:
        The path to write to.
    """
    return Path(path).expanduser()


def write_export(path: Path, text: str) -> int:
    """Write an export to a file.

    The file is written as UTF-8 and **overwritten**: an export is a copy
    of the session, not a log to append to.  A directory that does not
    exist is **not** created — the operator decides what the disk carries.

    Args:
        path: The file to write.
        text: The content of the export.

    Returns:
        The number of bytes written.

    Raises:
        OSError: The file could not be written.
    """
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return len(text.encode("utf-8"))
