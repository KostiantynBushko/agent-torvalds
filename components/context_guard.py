"""
Context guard — keeps the LLM prompt inside the model's context window while
always preserving the user query.

Why this module exists
----------------------
The model template used by the qwen3.5 family (e.g.
``richardyoung/qwen3.6-27b-abliterated``) contains this check::

    {%- set ns = namespace(multi_step_tool=true, ...) %}
    {%- for message in messages[::-1] %}
        {%- if ns.multi_step_tool and message.role == "user" %}
            {%- if not(content.startswith('<tool_response>') and content.endswith('</tool_response>')) %}
                {%- set ns.multi_step_tool = false %}
    {%- if ns.multi_step_tool %}
        {{- raise_exception('No user query found in messages.') }}

In other words the server refuses to render a conversation that has no
``user`` message which is not a ``<tool_response>`` wrapper.

Two independent defects can produce such a conversation:

1. **Prompt overflow.**  ``FunctionAgent`` never trims its scratchpad, so a
   long tool-using run (reading a big spreadsheet, for example) grows the
   prompt without bound.  Once it exceeds the model's context window the
   Ollama server truncates the prompt, keeping the *most recent* tokens.
   The user query sits at the *front* of the message list, so it is the
   first thing to be dropped — and the template then raises
   "No user query found in messages.".

2. **Memory trimming.**  ``ChatMemoryBuffer.get()`` trims the stored history
   from the front and, when the window collapses, returns only the last
   message, which may be an assistant or tool message.  The user query is
   then missing from the very first request of the next turn.

``select_context_window()`` fixes both: it never returns a conversation
without a user query, and it never returns a conversation larger than the
budget it is given.

Category: Infrastructure
"""

from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional, Sequence, Tuple

from llama_index.core.base.llms.types import ChatMessage, MessageRole

logger = logging.getLogger(__name__)

#: Fraction of the context window that is kept free for the model's answer.
DEFAULT_RESERVE_FRACTION = 0.20

#: Absolute minimum number of tokens reserved for the model's answer.
MIN_RESERVE_TOKENS = 1024

#: Absolute maximum number of tokens reserved for the model's answer.
MAX_RESERVE_TOKENS = 8192

#: Wrapper the model template uses for tool results.
TOOL_RESPONSE_OPEN = "<tool_response>"
TOOL_RESPONSE_CLOSE = "</tool_response>"


# ---------------------------------------------------------------------------
# Message classification
# ---------------------------------------------------------------------------


def message_text(message: ChatMessage) -> str:
    """Return the plain text of *message* (all text blocks joined)."""
    texts: List[str] = []
    for block in getattr(message, "blocks", None) or []:
        text = getattr(block, "text", None)
        if text:
            texts.append(text)
    if texts:
        return "\n".join(texts)
    content = getattr(message, "content", None)
    return content or ""


def is_tool_response(message: ChatMessage) -> bool:
    """True when *message* is a tool result rendered as a ``user`` turn.

    The model template treats such a message as "not a user query": it is
    skipped by the reverse scan that looks for the actual request.
    """
    if message.role != MessageRole.USER:
        return False
    content = message_text(message).strip()
    return content.startswith(TOOL_RESPONSE_OPEN) and content.endswith(
        TOOL_RESPONSE_CLOSE
    )


def is_user_query(message: ChatMessage) -> bool:
    """True when *message* is a real user request (not a tool result)."""
    return message.role == MessageRole.USER and not is_tool_response(message)


def has_user_query(messages: Sequence[ChatMessage]) -> bool:
    """True when *messages* contains at least one real user request."""
    return any(is_user_query(m) for m in messages)


def _has_tool_calls(message: ChatMessage) -> bool:
    """True when *message* is an assistant turn that requests tool calls."""
    if message.role != MessageRole.ASSISTANT:
        return False
    for block in getattr(message, "blocks", None) or []:
        if getattr(block, "block_type", None) == "tool_call":
            return True
    return bool(message.additional_kwargs.get("tool_calls"))


# ---------------------------------------------------------------------------
# Token accounting
# ---------------------------------------------------------------------------


def get_tokenizer() -> Callable[[str], List[Any]]:
    """Return the tokenizer used to size the prompt.

    Mirrors ``llama_index.core.utils.get_tokenizer`` so the accounting
    matches the one ``ChatMemoryBuffer`` uses.
    """
    from llama_index.core.utils import get_tokenizer as _get_tokenizer

    return _get_tokenizer()


def token_text(message: ChatMessage) -> str:
    """Return everything of *message* that costs tokens.

    That is the text blocks plus the tool calls: an assistant turn that
    requests a tool call carries the call name and its arguments, which
    take up prompt space just like plain text does.
    """
    parts: List[str] = []
    for block in getattr(message, "blocks", None) or []:
        block_type = getattr(block, "block_type", None)
        if block_type == "tool_call":
            parts.append(str(getattr(block, "tool_name", "")))
            parts.append(str(getattr(block, "tool_kwargs", "")))
        else:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
    if not parts:
        content = getattr(message, "content", None)
        if content:
            parts.append(content)
    return " ".join(parts)


def count_tokens(
    messages: Sequence[ChatMessage],
    tokenizer: Optional[Callable[[str], List[Any]]] = None,
) -> int:
    """Approximate the number of tokens *messages* occupy.

    Uses the same "join the contents and tokenize" approach as
    ``ChatMemoryBuffer._token_count_for_messages`` so the numbers line up,
    and additionally counts the tool call arguments.
    """
    if not messages:
        return 0
    if tokenizer is None:
        tokenizer = get_tokenizer()
    joined = " ".join(str(token_text(m)) for m in messages)
    return len(tokenizer(joined))


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------


def group_messages(messages: Sequence[ChatMessage]) -> List[List[ChatMessage]]:
    """Split *messages* into droppable groups.

    An assistant turn that requests tool calls and the tool results that
    answer it form a single group: dropping one without the other would
    leave a dangling tool response in the conversation.
    """
    return [
        [message for _, message in group]
        for group in _group_items(list(enumerate(messages)))
    ]


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------


def truncate_message(
    message: ChatMessage,
    max_tokens: int,
    tokenizer: Optional[Callable[[str], List[Any]]] = None,
) -> ChatMessage:
    """Return a copy of *message* whose text fits into *max_tokens*.

    Only the text of the message is shortened; the role and the block
    structure are preserved.  A single oversized tool result is common
    (a whole spreadsheet dumped as JSON), and dropping it entirely would
    throw away the result the agent just asked for.
    """
    if tokenizer is None:
        tokenizer = get_tokenizer()
    if max_tokens <= 0:
        return message

    text = message_text(message)
    if not text:
        return message
    if len(tokenizer(text)) <= max_tokens:
        return message

    # The marker is appended to the shortened text, so it has to fit too.
    marker = "\n... [truncated by the Torvalds context guard]"
    room = max(max_tokens - len(tokenizer(marker)), 1)

    # Binary-search the longest prefix that fits.
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if len(tokenizer(text[:mid])) <= room:
            low = mid
        else:
            high = mid - 1

    shortened = text[:low] + marker

    truncated = message.model_copy(deep=True)
    for block in getattr(truncated, "blocks", None) or []:
        if getattr(block, "block_type", None) == "text":
            block.text = shortened
            break
    else:
        # No text block: fall back to rebuilding the message from content.
        truncated = ChatMessage(role=message.role, content=shortened)
    return truncated


# ---------------------------------------------------------------------------
# The guard itself
# ---------------------------------------------------------------------------


def _find_request(
    items: Sequence[Tuple[int, ChatMessage]],
    original_request: Optional[str],
) -> Tuple[Optional[ChatMessage], Optional[int], int]:
    """Locate the user request.

    Returns the request message, the index it was taken from (``None``
    when it had to be restored) and the index in *items* right after it.
    The original request wins when it is available, because it is the one
    the user actually typed — the memory may have dropped it, and the
    scratchpad may only contain later user turns (a Human-in-the-Loop
    answer, for instance).
    """
    if original_request:
        wanted = original_request.strip()
        for index, message in items:
            if is_user_query(message) and message_text(message).strip() == wanted:
                return message, index, index + 1
        # Not in the conversation: restore it.
        return ChatMessage(role=MessageRole.USER, content=original_request), None, 0

    for index, message in reversed(list(items)):
        if is_user_query(message):
            return message, index, index + 1

    return None, None, 0


def _select_window(
    messages: Sequence[ChatMessage],
    budget_tokens: int,
    tokenizer: Callable[[str], List[Any]],
    original_request: Optional[str],
) -> Tuple[List[ChatMessage], List[Optional[int]]]:
    """Build the window and report where each message came from.

    The second return value holds, for every message of the window, the
    index it was taken from in *messages* (``None`` for a message that was
    restored rather than taken from the conversation).
    """
    original = list(messages)
    items: List[Tuple[int, ChatMessage]] = list(enumerate(original))

    system_items: List[Tuple[int, ChatMessage]] = []
    for item in items:
        if item[1].role == MessageRole.SYSTEM:
            system_items.append(item)
        else:
            break

    request, request_index, tail_start = _find_request(
        items, original_request
    )
    if request is None:
        # Nothing usable at all — keep the conversation as it is.
        return original, list(range(len(original)))

    core_items: List[Tuple[int, ChatMessage]] = [
        *system_items,
        (request_index, request),
    ]

    used = count_tokens([m for _, m in core_items], tokenizer)
    if used > budget_tokens:
        # Even the mandatory core does not fit: shrink the request text.
        overflow = used - budget_tokens
        request_tokens = max(count_tokens([request], tokenizer), 1)
        keep_tokens = max(request_tokens - overflow, 1)
        request = truncate_message(request, keep_tokens, tokenizer)
        core_items = [*system_items, (request_index, request)]
        used = count_tokens([m for _, m in core_items], tokenizer)

    # The conversation that follows the request, grouped so that an
    # assistant turn and the tool results answering it stay together.
    tail_start = max(tail_start, len(system_items))
    tail_items = [item for item in items if item[0] >= tail_start]
    groups = _group_items(tail_items)

    # Fill with the most recent turns, newest first.
    selected: List[List[Tuple[int, ChatMessage]]] = []
    for group in groups:
        group_tokens = count_tokens([m for _, m in group], tokenizer)
        if used + group_tokens <= budget_tokens:
            selected.append(group)
            used += group_tokens
            continue

        # The group does not fit as a whole.  Its largest member (normally
        # the tool result) is truncated so the group still fits; a group
        # that cannot be salvaged is dropped entirely.
        room = budget_tokens - used
        if room > 64 and group:
            biggest = max(
                range(len(group)),
                key=lambda i: count_tokens([group[i][1]], tokenizer),
            )
            overhead = group_tokens - count_tokens([group[biggest][1]], tokenizer)
            index, message = group[biggest]
            truncated_group = list(group)
            truncated_group[biggest] = (
                index,
                truncate_message(message, room - overhead, tokenizer),
            )
            if count_tokens([m for _, m in truncated_group], tokenizer) <= room:
                selected.append(truncated_group)
                used += count_tokens(
                    [m for _, m in truncated_group], tokenizer
                )
        break

    window_items: List[Tuple[int, ChatMessage]] = list(core_items)
    for group in reversed(selected):
        window_items.extend(group)

    return (
        [m for _, m in window_items],
        [index for index, _ in window_items],
    )


def _group_items(
    items: Sequence[Tuple[int, ChatMessage]],
) -> List[List[Tuple[int, ChatMessage]]]:
    """Group ``(index, message)`` pairs into droppable units.

    An assistant turn that requests tool calls and the tool results that
    answer it form a single group: dropping one without the other would
    leave a dangling tool response in the conversation.
    """
    groups: List[List[Tuple[int, ChatMessage]]] = []
    pending: List[Tuple[int, ChatMessage]] = []

    for item in items:
        message = item[1]
        if _has_tool_calls(message):
            if pending:
                groups.append(pending)
                pending = []
            pending = [item]
        elif message.role == MessageRole.TOOL and pending:
            pending.append(item)
        else:
            if pending:
                groups.append(pending)
                pending = []
            groups.append([item])

    if pending:
        groups.append(pending)
    return groups


def select_context_window(
    messages: Sequence[ChatMessage],
    budget_tokens: int,
    tokenizer: Optional[Callable[[str], List[Any]]] = None,
    original_request: Optional[str] = None,
) -> List[ChatMessage]:
    """Return a conversation that fits into *budget_tokens*.

    The result always contains the user request.  When the whole
    conversation already fits, it is returned unchanged, so normal
    conversations are not affected in any way.

    When it does not fit, the following are kept, in order:

    * the leading system prompt,
    * the request the user actually made,
    * the most recent assistant/tool turns, newest first, for as long as
      they fit.

    Older turns are dropped first; an assistant turn and the tool results
    that answer it are dropped together.  A single turn that is too large
    on its own (a huge tool result) is truncated instead of dropped.
    """
    if tokenizer is None:
        tokenizer = get_tokenizer()

    original = list(messages)
    if not original:
        return original

    if count_tokens(original, tokenizer) <= budget_tokens and has_user_query(original):
        return original

    window, _ = _select_window(original, budget_tokens, tokenizer, original_request)

    logger.info(
        "Context guard: trimmed the prompt from %d to %d messages "
        "(~%d tokens, budget %d)",
        len(original),
        len(window),
        count_tokens(window, tokenizer),
        budget_tokens,
    )
    return window


def select_context_window_split(
    messages: Sequence[ChatMessage],
    split_at: int,
    budget_tokens: int,
    tokenizer: Optional[Callable[[str], List[Any]]] = None,
    original_request: Optional[str] = None,
) -> Tuple[List[ChatMessage], List[ChatMessage]]:
    """Trim *messages* and split the result at *split_at*.

    The agent keeps two separate lists: the messages coming from the chat
    memory and the messages coming from the run's scratchpad.  The caller
    has to put the trimmed messages back into both, so the split point has
    to be preserved.  The returned tuple is ``(head, tail)`` where *head*
    holds the messages that came from ``messages[:split_at]``.
    """
    if tokenizer is None:
        tokenizer = get_tokenizer()

    original = list(messages)
    if not original:
        return [], []

    if count_tokens(original, tokenizer) <= budget_tokens and has_user_query(original):
        return original[:split_at], original[split_at:]

    window, indices = _select_window(
        original, budget_tokens, tokenizer, original_request
    )

    head: List[ChatMessage] = []
    tail: List[ChatMessage] = []
    in_tail = False
    for message, index in zip(window, indices):
        if not in_tail and index is not None and index >= split_at:
            in_tail = True
        if in_tail:
            tail.append(message)
        else:
            head.append(message)

    logger.info(
        "Context guard: trimmed the prompt from %d to %d messages "
        "(head %d / tail %d, ~%d tokens, budget %d)",
        len(original),
        len(window),
        len(head),
        len(tail),
        count_tokens(window, tokenizer),
        budget_tokens,
    )
    return head, tail


def context_budget(
    context_window: int,
    reserve_fraction: float = DEFAULT_RESERVE_FRACTION,
    min_reserve: int = MIN_RESERVE_TOKENS,
    max_reserve: int = MAX_RESERVE_TOKENS,
) -> int:
    """Return the number of tokens that may be used for the prompt.

    Part of the context window is kept free for the model's own answer.
    The reserve is proportional but bounded, so that it also makes sense
    for the small windows (8k) that Ollama servers usually run with.
    """
    if context_window <= 0:
        return 0
    reserve = int(context_window * reserve_fraction)
    reserve = max(reserve, min_reserve)
    reserve = min(reserve, max_reserve)
    budget = context_window - reserve
    return max(budget, 1)
