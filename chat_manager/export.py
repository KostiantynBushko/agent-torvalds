"""The content of a session, rendered for the operator.

The ``\\chat-export`` command prints the content of the active session, or
writes it to a file.  This module is what the export *looks like* — the
header that says which session it is, and the transcript of its messages.

Two things are called "the session", and they are not the same size:

* the **stored** messages — everything the session keeps, which grows with
  every turn and is never trimmed by the agent;
* the **buffered** messages — the tail of the history that survives the
  chat-token limit, and is what the model is actually sent.

The export takes the **stored** messages.  An export that silently dropped
the older half of a conversation would be a trap, and the header carries
both sizes, so the operator sees what the model sees and what the session
keeps.

The messages themselves are rendered by :func:`components.chat_message.to_string`
— the renderer the log already uses — so the text of a session reads the
same everywhere it is shown.

Category: Infrastructure
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional, Sequence

from chat_manager.stats import HistoryStats, format_size, format_tokens
from components.chat_message import to_string

logger = logging.getLogger(__name__)

__all__ = [
    "render_transcript",
    "render_header",
    "render_session",
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


def render_header(
    session: Any,
    message_count: int,
    stats: Optional[HistoryStats] = None,
) -> str:
    """Render the header of an export.

    The header says which session the export came from and how big it is.
    An export that does not say where it came from is a mystery file.

    Args:
        session: The session the export is of.
        message_count: How many messages the export carries.
        stats: The measurements of the session, when they could be taken.

    Returns:
        The header of the export.
    """
    name = getattr(session, "session_name", "unknown")
    session_id = getattr(session, "session_id", "unknown")
    session_type = getattr(session, "session_type", None)
    type_name = getattr(session_type, "value", session_type)

    lines = [
        f"Session: {name} ({session_id})",
        f"Type: {type_name}",
    ]

    if stats is None:
        lines.append(f"Messages: {message_count}")
    else:
        lines.append(
            f"Messages: {stats.message_count} | "
            f"Size: {format_size(stats.total_bytes)} | "
            f"Tokens: {format_tokens(stats)}"
        )

    return "\n".join(lines)


def render_session(
    session: Any,
    messages: Sequence[Any],
    stats: Optional[HistoryStats] = None,
) -> str:
    """Render the whole export of a session.

    Args:
        session: The session the export is of.
        messages: The stored messages of the session.
        stats: The measurements of the session, when they could be taken.

    Returns:
        The header of the export, a blank line, and the transcript.
    """
    header = render_header(session, len(messages), stats)

    if not messages:
        return f"{header}\n\nThe session holds no messages."

    return f"{header}\n\n{render_transcript(messages)}"


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
