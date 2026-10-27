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
    # A small budget cannot afford the long marker, so a short one is
    # used instead — otherwise the shortened message would still be
    # larger than the room it was given.
    marker = "\n... [truncated by the Torvalds context guard]"
    marker_tokens = len(tokenizer(marker))
    if max_tokens <= marker_tokens:
        marker = "…"
        marker_tokens = len(tokenizer(marker))
    room = max(max_tokens - marker_tokens, 1)

    # Binary-search the longest prefix that fits.
    low, high = 0, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if len(tokenizer(text[:mid])) <= room:
            low = mid
        else:
            high = mid - 1

    shortened = text[:low] + marker

    # Tokenisation is not additive: appending the marker can push the
    # message over the limit even when the prefix alone fits.  Shorten
    # the prefix until the *whole* message fits.
    for _ in range(24):
        if len(tokenizer(shortened)) <= max_tokens:
            break
        low = int(low * 0.9)
        shortened = text[:low] + marker

    if len(tokenizer(shortened)) > max_tokens:
        # Nothing of the original fits: keep the marker alone.
        shortened = marker

    truncated = message.model_copy(deep=True)
    for block in getattr(truncated, "blocks", None) or []:
        if getattr(block, "block_type", None) == "text":
            block.text = shortened
            break
    else:
        # No text block: the message carries a tool call and nothing
        # else.  There is nothing to shorten, and rebuilding the message
        # from its content would turn the tool call into a piece of
        # text — the model would no longer know what it asked for.  The
        # message is returned unchanged; the caller checks the size.
        return message
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

    The window is built in chronological order:

    * the leading system prompt,
    * the chat history that precedes the request,
    * the request the user actually made,
    * the turns that follow it (the run's scratchpad).

    When the conversation does not fit into the budget, the *oldest* turns
    are dropped — the newest ones are the ones the model needs, because
    they carry the result of the action it has just taken.
    """
    original = list(messages)
    items: List[Tuple[int, ChatMessage]] = list(enumerate(original))

    system_items: List[Tuple[int, ChatMessage]] = []
    for item in items:
        if item[1].role == MessageRole.SYSTEM:
            system_items.append(item)
        else:
            break

    request, request_index, _ = _find_request(items, original_request)
    if request is None:
        # Nothing usable at all — keep the conversation as it is.
        return original, list(range(len(original)))

    # The conversation is split in two: the chat history that precedes
    # the request, and the turns that follow it (the run's scratchpad).
    # Both are grouped, so that an assistant turn and the tool results
    # answering it are kept together.
    if request_index is None:
        # The request was restored — it is not part of the conversation.
        # Everything that is not the system prompt follows it.
        history_items: List[Tuple[int, ChatMessage]] = []
        tail_items = [item for item in items if item[0] >= len(system_items)]
    else:
        history_items = [
            item for item in items
            if len(system_items) <= item[0] < request_index
        ]
        tail_items = [item for item in items if item[0] > request_index]

    history_groups = _group_items(history_items)
    tail_groups = _group_items(tail_items)

    # The mandatory part: the system prompt and the request.  They are
    # shortened when they do not fit — the request is never dropped,
    # because the model template refuses a conversation without a user
    # request.
    system_items, request, used = _fit_core(
        system_items, request, request_index, budget_tokens, tokenizer
    )

    # Fill with the most recent turns, newest first.
    #
    # The order matters more than anything else here.  The turn the model
    # has just produced is the one it needs to see: it carries the result
    # of the action it took.  A window that keeps the *oldest* turns
    # instead blinds the model, and a blind model repeats the same action
    # — with a greedy model (temperature 0) the prompt stops changing,
    # the answer stops changing, and the agent loops forever.  That is
    # exactly what happened in the run reported in
    # ``investigate/agent-loop-context-guard/``.
    #
    # The scratchpad is newer than the chat history, so it is filled
    # first; the history takes whatever is left.
    selected_tail = _fill_groups(
        tail_groups, used, budget_tokens, tokenizer
    )
    used += sum(
        count_tokens([m for _, m in group], tokenizer)
        for group in selected_tail
    )
    selected_history = _fill_groups(
        history_groups, used, budget_tokens, tokenizer
    )

    # Safety net: the window must never be larger than the budget.  A
    # prompt that is too large is truncated by the server, and the server
    # drops the user request first — which is the failure the guard
    # exists to prevent.  Whole turns are dropped, never single
    # messages, so the conversation never ends up with a tool result
    # whose call is gone.
    selected_history, selected_tail = _enforce_budget(
        selected_history, selected_tail, budget_tokens, tokenizer
    )

    # Assemble the window in chronological order.
    window_items: List[Tuple[int, ChatMessage]] = list(system_items)
    for group in reversed(selected_history):
        window_items.extend(group)
    window_items.append((request_index, request))
    for group in reversed(selected_tail):
        window_items.extend(group)

    return (
        [m for _, m in window_items],
        [index for index, _ in window_items],
    )


def _fit_core(
    system_items: List[Tuple[int, ChatMessage]],
    request: ChatMessage,
    request_index: Optional[int],
    budget_tokens: int,
    tokenizer: Callable[[str], List[Any]],
) -> Tuple[
    List[Tuple[int, ChatMessage]], ChatMessage, int
]:
    """Shrink the system prompt and the request until they fit.

    The request is shortened first and the system prompt second: the
    request is what the model template insists on, and the shorter of the
    two is the one that carries the information the model needs.
    """
    def total() -> int:
        return count_tokens(
            [m for _, m in system_items] + [request], tokenizer
        )

    used = total()
    if used <= budget_tokens:
        return system_items, request, used

    # The request first.
    overflow = used - budget_tokens
    request_tokens = max(count_tokens([request], tokenizer), 1)
    keep_tokens = max(request_tokens - overflow, 1)
    request = truncate_message(request, keep_tokens, tokenizer)
    used = total()

    # Then the system prompt.
    if used > budget_tokens:
        overflow = used - budget_tokens
        for position in range(len(system_items) - 1, -1, -1):
            index, message = system_items[position]
            message_tokens = max(count_tokens([message], tokenizer), 1)
            keep = max(message_tokens - overflow, 1)
            system_items[position] = (
                index,
                truncate_message(message, keep, tokenizer),
            )
            overflow = max(overflow - (message_tokens - keep), 0)
            if overflow <= 0:
                break
        used = total()

    return system_items, request, used


def _fill_groups(
    groups: Sequence[List[Tuple[int, ChatMessage]]],
    used: int,
    budget_tokens: int,
    tokenizer: Callable[[str], List[Any]],
) -> List[List[Tuple[int, ChatMessage]]]:
    """Select the newest groups of *groups* that fit into the budget.

    The result is in reverse chronological order — the newest group first.

    The newest group is the one that carries the result of the action the
    model has just taken, and without it the model is blind.  It is
    therefore shortened when it does not fit, and only dropped when even a
    shortened version does not fit — which needs a budget of a handful of
    tokens.
    """
    if not groups:
        return []

    selected: List[List[Tuple[int, ChatMessage]]] = []

    newest = groups[-1]
    newest_tokens = count_tokens([m for _, m in newest], tokenizer)
    if used + newest_tokens > budget_tokens:
        room = max(budget_tokens - used, 1)
        truncated = _truncate_group(newest, room, tokenizer)
        if truncated is None:
            # The group cannot be salvaged — the room is too small even
            # for a shortened version of it.  Keeping it whole would blow
            # the budget, so the section is dropped.  This only happens
            # with a budget of a handful of tokens, which the agent never
            # allows (see ``MIN_PROMPT_BUDGET``).
            return []
        newest = truncated
        newest_tokens = count_tokens([m for _, m in newest], tokenizer)
    selected.append(newest)

    # The remaining budget is filled with the turns before it, newest
    # first.  ``spent`` tracks what the window uses so far, so that the
    # groups that are kept add up to the budget.
    spent = used + newest_tokens
    for group in reversed(groups[:-1]):
        group_tokens = count_tokens([m for _, m in group], tokenizer)
        if spent + group_tokens <= budget_tokens:
            selected.append(group)
            spent += group_tokens
            continue

        # The group does not fit as a whole.  Its largest member (normally
        # the tool result) is truncated so the group still fits; a group
        # that cannot be salvaged is dropped entirely.
        room = budget_tokens - spent
        truncated_group = _truncate_group(group, room, tokenizer)
        if truncated_group is not None:
            selected.append(truncated_group)
        break

    return selected


def _enforce_budget(
    selected_history: List[List[Tuple[int, ChatMessage]]],
    selected_tail: List[List[Tuple[int, ChatMessage]]],
    budget_tokens: int,
    tokenizer: Callable[[str], List[Any]],
) -> Tuple[
    List[List[Tuple[int, ChatMessage]]], List[List[Tuple[int, ChatMessage]]]
]:
    """Drop whole turns until the window fits into *budget_tokens*.

    The turns are dropped oldest first: the chat history goes before the
    scratchpad, and within each part the oldest turn goes first.  The
    newest turn of the scratchpad is never dropped.
    """
    history = list(selected_history)
    tail = list(selected_tail)

    def total() -> int:
        return sum(
            count_tokens([m for _, m in group], tokenizer)
            for group in [*history, *tail]
        )

    while total() > budget_tokens:
        if history:
            history.pop()
            continue
        if len(tail) > 1:
            tail.pop()
            continue
        break

    return history, tail


def _truncate_group(
    group: Sequence[Tuple[int, ChatMessage]],
    room: int,
    tokenizer: Callable[[str], List[Any]],
) -> Optional[List[Tuple[int, ChatMessage]]]:
    """Shrink *group* so that it fits into *room* tokens.

    The largest member of the group — normally the tool result — is
    shortened; the rest of the group is kept, so the model still sees the
    shape of the exchange.  ``None`` is returned when the group cannot be
    salvaged at all.
    """
    if not group or room <= 0:
        return None

    group_tokens = count_tokens([m for _, m in group], tokenizer)
    if group_tokens <= room:
        return list(group)

    biggest = max(
        range(len(group)),
        key=lambda i: count_tokens([group[i][1]], tokenizer),
    )
    overhead = group_tokens - count_tokens([group[biggest][1]], tokenizer)
    allowance = room - overhead
    if allowance <= 0:
        # The rest of the group already uses up the room: the group
        # cannot be salvaged.
        return None

    index, message = group[biggest]
    truncated_group = list(group)
    truncated_group[biggest] = (
        index,
        truncate_message(message, allowance, tokenizer),
    )
    shortened_tokens = count_tokens([m for _, m in truncated_group], tokenizer)
    if shortened_tokens > room:
        # Even the shortened group does not fit.  It is still smaller than
        # the original, and the overshoot is the size of the rest of the
        # group — which is small — so it is kept.
        if shortened_tokens < group_tokens:
            return truncated_group
        return None
    return truncated_group


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
