"""What the chat history of the active session holds.

The ``\\chat-info`` command tells the operator what a session contains: how
many messages, how large they are, and how many tokens they are worth.
The measurement lives here, so the classic console and the multi-window
console show the same numbers.

Two sizes are measured, and the difference between them matters:

* the **stored** messages — everything the session keeps, which grows with
  every turn and is never trimmed by the agent;
* the **buffered** messages — the tail of the history that survives the
  chat-token limit and is actually sent to the model.

The tokens are counted with the tokenizer the memory buffer itself uses, so
the numbers are the numbers the limit is enforced with.  That tokenizer
counts the tokens of one model family; for the local models the agent
usually talks to it is an estimate, and the output says so with ``≈``.

Category: Infrastructure
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from components.tokens import CHARS_PER_TOKEN, count_tokens_of

logger = logging.getLogger(__name__)

#: A kilobyte — the unit a size is shown in below one megabyte.
BYTES_PER_KB = 1024

#: A megabyte — the unit a size is shown in from one megabyte up.
BYTES_PER_MB = 1024 * 1024


@dataclass(frozen=True)
class HistoryStats:
    """What the chat history of the active session holds.

    Attributes:
        message_count: How many messages are stored for the session.
        total_bytes: The size of the text of those messages, in bytes.
        stored_tokens: The tokens of every stored message.
        buffer_tokens: The tokens of the messages that survive the
            chat-token limit — what the model is actually sent.
        token_limit: The chat-token limit in force for the session.
        estimated: True when the tokens were counted by an estimate
            instead of by the tokenizer of the agent.
    """

    message_count: int = 0
    total_bytes: int = 0
    stored_tokens: int = 0
    buffer_tokens: int = 0
    token_limit: int = 0
    estimated: bool = False


def _message_text(message: Any) -> str:
    """Return the text of a message.

    Args:
        message: A chat message, or a plain string.

    Returns:
        The text of the message.
    """
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    return str(content)


def count_tokens(messages: Sequence[Any]) -> tuple[int, bool]:
    """Count the tokens of the given messages.

    The messages are joined the way the memory buffer joins them, so the
    count is the count the chat-token limit is enforced with.

    Args:
        messages: The chat messages to count.

    Returns:
        A tuple of the number of tokens and whether they were estimated.
        The estimate is used when the tokenizer cannot be loaded — the
        count is then an approximation, and the caller says so.
    """
    text = " ".join(_message_text(message) for message in messages)
    if not text:
        return 0, False

    return count_tokens_of(text)


def measure(
    stored_messages: Sequence[Any],
    buffered_messages: Sequence[Any],
    token_limit: int,
) -> HistoryStats:
    """Measure a chat history.

    Args:
        stored_messages: Every message stored for the session.
        buffered_messages: The messages that survive the token limit.
        token_limit: The chat-token limit in force.

    Returns:
        The measurements of the history.
    """
    total_bytes = sum(
        len(_message_text(message).encode("utf-8")) for message in stored_messages
    )

    stored_tokens, stored_estimated = count_tokens(stored_messages)
    buffered_tokens, buffered_estimated = count_tokens(buffered_messages)

    return HistoryStats(
        message_count=len(stored_messages),
        total_bytes=total_bytes,
        stored_tokens=stored_tokens,
        buffer_tokens=buffered_tokens,
        token_limit=token_limit,
        estimated=stored_estimated or buffered_estimated,
    )


def format_size(total_bytes: int) -> str:
    """Render a number of bytes the way the operator reads a size.

    Args:
        total_bytes: The size in bytes.

    Returns:
        The size in bytes, kilobytes or megabytes.
    """
    if total_bytes < BYTES_PER_KB:
        return f"{total_bytes} B"
    if total_bytes < BYTES_PER_MB:
        return f"{total_bytes / BYTES_PER_KB:.1f} KB"
    return f"{total_bytes / BYTES_PER_MB:.2f} MB"


def format_tokens(stats: HistoryStats) -> str:
    """Render the token counts of a chat history.

    Args:
        stats: The measurements of the history.

    Returns:
        The stored tokens, the tokens in the buffer, and the limit.
    """
    text = (
        f"≈{stats.stored_tokens:,} stored, "
        f"≈{stats.buffer_tokens:,} in the buffer "
        f"(limit {stats.token_limit:,})"
    )
    if stats.estimated:
        text += " — estimated, the tokenizer is not available"
    return text


__all__ = [
    "BYTES_PER_KB",
    "BYTES_PER_MB",
    "CHARS_PER_TOKEN",
    "HistoryStats",
    "count_tokens",
    "format_size",
    "format_tokens",
    "measure",
]
