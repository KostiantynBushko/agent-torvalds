"""
Chat messages, rendered the way a person reads them.

The event consumer used to log the prompt as a Python ``repr``::

    EventConsumer._on_agent_input: input=[ChatMessage(role=<MessageRole.SYSTEM:
    'system'>, additional_kwargs={}, blocks=[TextBlock(block_type='text',
    text='You are Torvalds, a technical AI assistant that ...')]),
    ChatMessage(role=<MessageRole.USER: 'user'>, ...), ...]

One enormous record: the system prompt, the whole chat history and the
run's scratchpad, escaped and wrapped in object syntax, spread over
dozens of lines.  Nothing in it is readable at a glance.

This module renders the same messages the way they are meant to be read::

    system: You are Torvalds, a technical AI assistant that interacts with the operating system.
    user: I want to improve debug message for context window
    assistant: thinking: The user asks for a better debug message. | tool call: pwd(path=/)
    tool: output: /home/kbush

Why a function and not a method
-------------------------------
``ChatMessage`` is a class of the LlamaIndex framework, not of this
project, so a ``to_string`` method cannot be added to it.  Adding one
would mean patching the framework's class at import time - a monkey
patch, invisible to anybody who reads the framework.  A function in this
project's own namespace does the same job and can be found.

What is rendered
----------------
Everything the message carries:

* the **text** of its text blocks;
* its **thinking**, marked as such - the model reasons out loud, and
  the reason is part of what the model is shown;
* its **tool calls**, with the name and the arguments - a tool call is
  the one part of an assistant turn that is *not* text, and a report
  that showed the text and none of the tools would be misleading.

A tool call can be carried in two places: as a ``ToolCallBlock`` in
``message.blocks`` (the current shape) and in the OpenAI-shaped
``additional_kwargs["tool_calls"]`` (the shape the Ollama adapter still
writes for chat histories that predate the blocks).  Both are rendered,
and a call that is present in both is rendered once.

Category: Infrastructure
"""

from __future__ import annotations

from typing import Any, List

__all__ = ["to_string", "to_strings"]


def _tidy(text: str) -> str:
    """Return *text* without the empty lines that carry nothing.

    A system prompt usually ends with a few newlines, and a document
    separates its paragraphs with a run of blank lines.  In the log
    that becomes a wall of empty records that the reader has to skip
    over — the reader is looking for the *text*, not for the paper it
    was printed on.

    One empty line is kept: it is a paragraph break and it carries
    meaning.  A run of them is reduced to one, and the leading and
    trailing ones are dropped.

    Args:
        text: The text of a message.

    Returns:
        The text without its leading and trailing empty lines and
        without runs of empty lines.
    """
    lines = [line.rstrip() for line in text.splitlines()]

    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()

    tidied: List[str] = []
    for line in lines:
        if not line and tidied and not tidied[-1]:
            # An empty line right after another one: one is enough.
            continue
        tidied.append(line)

    return "\n".join(tidied)


def _role(message: Any) -> str:
    """Return the role of *message* as a short lower-case name."""
    role = getattr(message, "role", None)
    if role is None:
        return "?"
    return str(getattr(role, "value", role)).lower()


def _arguments(arguments: Any) -> str:
    """Return the arguments of a tool call as ``name=value`` pairs."""
    if arguments is None:
        return ""
    if isinstance(arguments, str):
        return arguments.strip()
    try:
        items = list(dict(arguments).items())
    except (TypeError, ValueError):
        return str(arguments)
    return ", ".join(f"{key}={value}" for key, value in items)


def _tool_call(name: str, arguments: Any) -> str:
    """Return a tool call as ``tool call: name(key=value)``."""
    rendered = _arguments(arguments)
    if rendered:
        return f"tool call: {name}({rendered})"
    return f"tool call: {name}"


def _block(block: Any) -> str:
    """Return what a single content block carries, as text."""
    block_type = str(getattr(block, "block_type", "") or "")

    if block_type == "text":
        return _tidy(str(getattr(block, "text", "") or ""))

    if block_type == "thinking":
        content = _tidy(str(getattr(block, "content", "") or ""))
        return f"thinking: {content}" if content else "thinking"

    if block_type == "tool_call":
        name = str(getattr(block, "tool_name", "") or "")
        return _tool_call(name, getattr(block, "tool_kwargs", None))

    if block_type:
        # An image, an audio clip, a document - nothing to read, but the
        # operator should know it is there.
        return f"[{block_type}]"

    return ""


def _legacy_tool_calls(message: Any) -> List[str]:
    """Return the tool calls *message* carries in ``additional_kwargs``.

    The OpenAI shape is ``{"name": ..., "arguments": ...}``; the shape
    the Ollama adapter writes nests the two under a ``function`` key.
    Both are read.

    Returns:
        One rendered tool call per call.  Empty when the message carries
        none.
    """
    kwargs = getattr(message, "additional_kwargs", None) or {}
    try:
        calls = kwargs.get("tool_calls") or []
    except AttributeError:
        return []

    found: List[str] = []
    for call in calls:
        if isinstance(call, dict):
            function = call.get("function")
            if isinstance(function, dict):
                name = str(function.get("name", "") or "")
                arguments = function.get("arguments")
            else:
                name = str(call.get("name", "") or "")
                arguments = call.get("arguments")
        else:
            name = str(getattr(call, "name", "") or "")
            arguments = getattr(call, "arguments", None)

        if name or arguments:
            found.append(_tool_call(name, arguments))

    return found


def to_string(message: Any) -> str:
    """Return *message* as a human-readable string.

    The result reads as the role, a colon, and what the message
    carries::

        user: I want to improve debug message for context window
        assistant: thinking: The user asks for a better debug message. | tool call: pwd(path=/)

    Args:
        message: The chat message.  Anything that carries a ``role``
            works; a message that carries nothing at all reads as
            ``"assistant: (empty)"``.

    Returns:
        The readable rendering of the message.  Never raises: a
        debugging aid must not be able to break a run.
    """
    role = _role(message)
    parts: List[str] = []
    block_calls: List[str] = []

    for block in getattr(message, "blocks", None) or []:
        rendered = _block(block)
        if not rendered:
            continue
        parts.append(rendered)
        if str(getattr(block, "block_type", "") or "") == "tool_call":
            block_calls.append(rendered)

    # The tool calls the message carries in the OpenAI shape.  A call
    # that is already shown as a block is not shown twice: the Ollama
    # adapter keeps both in step, and the reader has to see the same
    # tools the model is shown.
    for rendered in _legacy_tool_calls(message):
        if rendered not in block_calls:
            parts.append(rendered)

    if not parts:
        # No blocks (or none of them carries anything): the content is
        # the message.
        content = getattr(message, "content", None)
        if content:
            content = _tidy(str(content))
        if content:
            parts.append(content)

    if not parts:
        return f"{role}: (empty)"

    return f"{role}: " + " | ".join(parts)


def to_strings(messages: Any) -> List[str]:
    """Return one readable string per message of *messages*.

    Args:
        messages: The prompt - normally a list of chat messages.

    Returns:
        One string per message, in the order the messages are sent.  An
        empty list when *messages* is not a list of messages, so the
        caller can tell a prompt from another payload.
    """
    if not isinstance(messages, (list, tuple)):
        return []
    return [to_string(message) for message in messages]
