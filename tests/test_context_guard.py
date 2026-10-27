"""
Tests for the context guard.

The bug this guards against: the model template of the qwen3.5 family
raises ``No user query found in messages.`` when the conversation it
receives has no ``user`` message that is not a ``<tool_response>``
wrapper.  That happens when the prompt exceeds the model's context window
(the Ollama server truncates it from the front, dropping the user query)
or when the chat memory trimmed the user query away.

Category: Infrastructure
"""

import pytest
from llama_index.core.base.llms.types import ChatMessage, MessageRole
from llama_index.core.base.llms.types import ToolCallBlock

from components.context_guard import (
    context_budget,
    count_tokens,
    group_messages,
    has_user_query,
    is_tool_response,
    is_user_query,
    select_context_window,
    select_context_window_split,
    truncate_message,
)


TOKENIZER = lambda text: text.split()  # noqa: E731 - cheap, deterministic stand-in


def user(text: str) -> ChatMessage:
    return ChatMessage(role=MessageRole.USER, content=text)


def assistant(text: str = "") -> ChatMessage:
    return ChatMessage(role=MessageRole.ASSISTANT, content=text)


def tool(text: str) -> ChatMessage:
    return ChatMessage(role=MessageRole.TOOL, content=text)


def assistant_tool_call(name: str = "read_xlsx_file") -> ChatMessage:
    return ChatMessage(
        role=MessageRole.ASSISTANT,
        blocks=[
            ToolCallBlock(tool_name=name, tool_kwargs={"path": "a.xlsx"})
        ],
    )


def build_conversation(query: str, turns: int, payload_words: int) -> list:
    """A conversation shaped like a long agent run."""
    messages = [ChatMessage(role=MessageRole.SYSTEM, content="You are Torvalds.")]
    messages.append(user(query))
    for _ in range(turns):
        messages.append(assistant_tool_call())
        messages.append(tool(" ".join(["payload"] * payload_words)))
        messages.append(assistant("thinking"))
    return messages


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def test_tool_response_user_message_is_not_a_user_query():
    message = user("<tool_response>\nrow 1\n</tool_response>")
    assert is_tool_response(message)
    assert not is_user_query(message)
    assert not has_user_query([message])


def test_plain_user_message_is_a_user_query():
    message = user("merge the excel files")
    assert is_user_query(message)
    assert has_user_query([message])


def test_has_user_query_ignores_assistant_and_tool_messages():
    assert not has_user_query([assistant("hi"), tool("result")])


# ---------------------------------------------------------------------------
# Token accounting
# ---------------------------------------------------------------------------


def test_count_tokens_counts_words():
    assert count_tokens([user("one two three")], TOKENIZER) == 3


def test_count_tokens_of_empty_list_is_zero():
    assert count_tokens([], TOKENIZER) == 0


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------


def test_tool_result_groups_with_its_assistant_turn():
    messages = [
        assistant_tool_call(),
        tool("a"),
        tool("b"),
        assistant("done"),
    ]
    groups = group_messages(messages)
    assert len(groups) == 2
    assert len(groups[0]) == 3
    assert len(groups[1]) == 1


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------


def test_truncate_message_shortens_text():
    message = user(" ".join(["word"] * 100))
    truncated = truncate_message(message, 10, TOKENIZER)
    # 10 words of payload plus the "... [truncated ...]" marker.
    assert len(truncated.content.split()) <= 10 + 8
    assert "truncated" in truncated.content
    # The original is untouched.
    assert len(message.content.split()) == 100


def test_truncate_message_keeps_short_messages_unchanged():
    message = user("short")
    assert truncate_message(message, 100, TOKENIZER) is message


# ---------------------------------------------------------------------------
# Budget
# ---------------------------------------------------------------------------


def test_context_budget_reserves_room_for_the_answer():
    budget = context_budget(100000)
    assert budget < 100000
    # 20% would be 20000 tokens, but the reserve is capped at 8192.
    assert budget == 100000 - 8192


def test_context_budget_reserves_at_least_the_minimum():
    budget = context_budget(10000)
    # 20% of 10000 is 2000, which is above the 1024 minimum.
    assert budget == 10000 - 2000


def test_context_budget_for_a_small_ollama_window():
    """Ollama servers commonly run with 8k — the guard has to work there."""
    budget = context_budget(8192)
    assert 0 < budget < 8192
    assert budget == 8192 - 1638


def test_context_budget_of_zero_is_zero():
    assert context_budget(0) == 0


# ---------------------------------------------------------------------------
# The guard
# ---------------------------------------------------------------------------


def test_short_conversation_is_returned_unchanged():
    messages = build_conversation("merge the files", turns=2, payload_words=5)
    window = select_context_window(messages, budget_tokens=100000, tokenizer=TOKENIZER)
    assert window == messages


def test_oversized_conversation_is_trimmed_to_the_budget():
    messages = build_conversation("merge the files", turns=50, payload_words=200)
    budget = 500
    window = select_context_window(messages, budget_tokens=budget, tokenizer=TOKENIZER)

    assert len(window) < len(messages)
    assert count_tokens(window, TOKENIZER) <= budget


def test_trimmed_conversation_always_keeps_the_user_query():
    messages = build_conversation("merge the files", turns=50, payload_words=200)
    window = select_context_window(
        messages, budget_tokens=500, tokenizer=TOKENIZER,
        original_request="merge the files",
    )
    assert has_user_query(window)
    assert any(
        m.role == MessageRole.USER and "merge the files" in (m.content or "")
        for m in window
    )


def test_request_is_restored_when_the_memory_trimmed_it_away():
    """The chat memory can drop the user query; the guard puts it back."""
    messages = [
        ChatMessage(role=MessageRole.SYSTEM, content="You are Torvalds."),
        assistant("The merge landed green."),
    ]
    window = select_context_window(
        messages,
        budget_tokens=100000,
        tokenizer=TOKENIZER,
        original_request="merge the excel files",
    )
    assert has_user_query(window)
    assert any(
        "merge the excel files" in (m.content or "") for m in window
    )


def test_oversized_tool_result_is_truncated_not_dropped():
    messages = [
        ChatMessage(role=MessageRole.SYSTEM, content="sys"),
        user("do the thing"),
        assistant_tool_call(),
        tool(" ".join(["huge"] * 5000)),
    ]
    window = select_context_window(messages, budget_tokens=200, tokenizer=TOKENIZER)
    assert has_user_query(window)
    assert count_tokens(window, TOKENIZER) <= 200
    # The tool result is still there, just shortened.
    assert any(m.role == MessageRole.TOOL for m in window)


def test_window_fits_the_model_context_window():
    """The trimmed prompt must be small enough for the server not to cut it."""
    messages = build_conversation("merge the files", turns=400, payload_words=500)
    context_window = 262144
    budget = context_budget(context_window)
    window = select_context_window(
        messages,
        budget_tokens=budget,
        tokenizer=TOKENIZER,
        original_request="merge the files",
    )
    assert count_tokens(window, TOKENIZER) <= budget
    assert has_user_query(window)


def test_empty_conversation_is_handled():
    assert select_context_window([], budget_tokens=100, tokenizer=TOKENIZER) == []


# ---------------------------------------------------------------------------
# The split variant used by the agent
# ---------------------------------------------------------------------------


def test_split_keeps_the_memory_boundary():
    memory_part = [
        ChatMessage(role=MessageRole.SYSTEM, content="sys"),
        user("merge the files"),
    ]
    scratchpad_part = []
    for _ in range(40):
        scratchpad_part.append(assistant_tool_call())
        scratchpad_part.append(tool(" ".join(["payload"] * 100)))

    combined = [*memory_part, *scratchpad_part]
    head, tail = select_context_window_split(
        combined,
        split_at=len(memory_part),
        budget_tokens=300,
        tokenizer=TOKENIZER,
        original_request="merge the files",
    )

    assert len(head) + len(tail) < len(combined)
    assert has_user_query([*head, *tail])
    # Everything that came from the memory stays in the head.
    assert all(m in head for m in memory_part[:1])
    # The request survives.
    assert any("merge the files" in (m.content or "") for m in head + tail)


def test_split_of_a_short_conversation_is_lossless():
    memory_part = [ChatMessage(role=MessageRole.SYSTEM, content="sys"), user("hi")]
    scratchpad_part = [assistant("ok")]
    combined = [*memory_part, *scratchpad_part]
    head, tail = select_context_window_split(
        combined, split_at=len(memory_part), budget_tokens=100000, tokenizer=TOKENIZER
    )
    assert head == memory_part
    assert tail == scratchpad_part


# ---------------------------------------------------------------------------
# The order of the window
#
# These tests guard the defect that made the agent loop: the guard kept
# the *oldest* turns instead of the newest ones, and emitted the tail in
# reverse chronological order.  The window then stopped changing, and a
# greedy model (temperature 0) answered it the same way on every
# iteration.  See ``investigate/agent-loop-context-guard/``.
# ---------------------------------------------------------------------------


def test_window_keeps_the_newest_turn():
    """The turn the model has just produced must survive the trim."""
    messages = build_conversation("merge the files", turns=20, payload_words=200)
    window = select_context_window(
        messages, budget_tokens=500, tokenizer=TOKENIZER,
        original_request="merge the files",
    )
    # The last group of the conversation is the newest one.
    assert window[-1].role == MessageRole.ASSISTANT
    assert window[-1].content == "thinking"
    assert window[-2].role == MessageRole.TOOL


def test_window_drops_the_oldest_turns_first():
    """When the budget is tight, the oldest turns are the ones that go."""
    messages = build_conversation("merge the files", turns=20, payload_words=200)
    window = select_context_window(
        messages, budget_tokens=500, tokenizer=TOKENIZER,
        original_request="merge the files",
    )
    texts = [m.content or "" for m in window]
    # The conversation is chronological: the first turn is gone, the last
    # one is there.
    assert len(window) < len(messages)
    assert texts[-1] == "thinking"


def test_window_is_in_chronological_order():
    """The tail must not be reversed."""
    messages = build_conversation("merge the files", turns=6, payload_words=200)
    window = select_context_window(
        messages, budget_tokens=500, tokenizer=TOKENIZER,
        original_request="merge the files",
    )
    # Every tool result comes right after the assistant turn that asked
    # for it, and the assistant turns come in the order they were made.
    seen_thinking = 0
    for message in window:
        if message.role == MessageRole.ASSISTANT and message.content == "thinking":
            seen_thinking += 1
    assert seen_thinking >= 1
    # The tool results of the kept turns are in order.
    tool_positions = [
        index for index, m in enumerate(window) if m.role == MessageRole.TOOL
    ]
    assert tool_positions == sorted(tool_positions)


def test_window_keeps_the_chat_history_before_the_request():
    """The history that precedes the request must not be thrown away."""
    messages = [
        ChatMessage(role=MessageRole.SYSTEM, content="sys"),
        ChatMessage(role=MessageRole.USER, content="earlier question"),
        ChatMessage(role=MessageRole.ASSISTANT, content="earlier answer"),
        ChatMessage(role=MessageRole.USER, content="merge the files"),
    ]
    window = select_context_window(
        messages,
        budget_tokens=1000,
        tokenizer=TOKENIZER,
        original_request="merge the files",
    )
    texts = [m.content or "" for m in window]
    assert "earlier question" in texts
    assert "earlier answer" in texts
    # The request still comes after the history.
    assert texts.index("earlier answer") < texts.index("merge the files")


def test_truncate_message_keeps_a_tool_call():
    """Shortening a tool call must not turn it into a piece of text."""
    message = assistant_tool_call()
    truncated = truncate_message(message, 1, TOKENIZER)
    assert truncated.blocks[0].block_type == "tool_call"
    assert truncated.blocks[0].tool_name == "read_xlsx_file"


def test_oversized_tool_result_is_truncated_and_keeps_its_call():
    """A huge tool result is shortened, its call stays."""
    messages = [
        ChatMessage(role=MessageRole.SYSTEM, content="sys"),
        user("do the thing"),
        assistant_tool_call(),
        tool(" ".join(["huge"] * 5000)),
    ]
    window = select_context_window(
        messages, budget_tokens=200, tokenizer=TOKENIZER,
        original_request="do the thing",
    )
    calls = [
        block
        for message in window
        for block in (getattr(message, "blocks", None) or [])
        if getattr(block, "block_type", None) == "tool_call"
    ]
    assert calls, "the tool call was lost"
    assert any(m.role == MessageRole.TOOL for m in window)
