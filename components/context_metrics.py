"""
Context metrics — the size of the prompt that goes to the model.

Why this module exists
----------------------
The operator asked on 2026-11-04:

    *"I need to see in the log the context size in tokens and size of
    bytes.  So when request is made to LLM I want to see current context
    size"*

What "the context" is
---------------------
The prompt the agent sends to the model is **chat messages** — and only
chat messages, plus the tool schemas, which travel with every request but
are not messages:

    [*llm_input, *scratchpad]

* ``llm_input`` — what the chat memory holds: the system prompt, the
  history of the session and the request of the user;
* ``scratchpad`` — the turns of the current run: the assistant turns that
  asked for a tool, and the tool results that answered them.

That is exactly how the base class assembles the prompt
(``llama_index/core/agent/workflow/function_agent.py``), so what is
measured here is what goes on the wire.

What is measured
----------------
* **tokens** — counted with the tokenizer the chat memory itself uses, so
  the number is the number the token limit is enforced with;
* **bytes** — the size of the text of the prompt, in UTF-8.

The tool schemas are counted **separately**.  They are sent with every
request, they take up room in the context window, and they are not chat
messages — folding them into the message count would hide where the
prompt actually goes.

What is **not** counted: the markers the chat template of the model puts
around the messages (``<|im_start|>`` and friends).  They are a handful
of tokens per message, and they belong to the template of the model, not
to the agent.

What degrades and what does not
--------------------------------
A tokenizer that cannot be loaded is **not** a reason to lose the
measurement: the tokens are then *estimated* (four characters per token),
and the log line says that they are estimated.  The bytes are always
exact — counting them needs no tokenizer at all.

Category: Infrastructure
Retriever Keywords: context, prompt, tokens, bytes, size, llm request, log,
                    context window, budget
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

from components.tokens import (
    CHARS_PER_TOKEN,
    count_tokens_of,
    estimate_tokens,
)

logger = logging.getLogger(__name__)


__all__ = [
    "CHARS_PER_TOKEN",
    "ContextSize",
    "count_tokens_of",
    "describe_context",
    "estimate_tokens",
    "measure_context",
    "prompt_text",
    "tool_schema_text",
]


# ---------------------------------------------------------------------------
# The measurements
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContextSize:
    """The size of the prompt that goes to the model.

    Attributes:
        messages: How many chat messages the prompt holds.
        tokens: The tokens of the text of those messages.
        bytes: The size of the text of those messages, in UTF-8 bytes.
        tool_schema_tokens: The tokens of the tool schemas that travel
            with every request.
        tool_schema_bytes: The size of the tool schemas, in UTF-8 bytes.
        estimated: True when the tokens were estimated instead of
            counted with the tokenizer of the agent.
    """

    messages: int = 0
    tokens: int = 0
    bytes: int = 0
    tool_schema_tokens: int = 0
    tool_schema_bytes: int = 0
    estimated: bool = False

    @property
    def total_tokens(self) -> int:
        """The tokens of the whole request — the messages and the schemas."""
        return self.tokens + self.tool_schema_tokens

    @property
    def total_bytes(self) -> int:
        """The bytes of the whole request — the messages and the schemas."""
        return self.bytes + self.tool_schema_bytes


# ---------------------------------------------------------------------------
# The text that goes on the wire
# ---------------------------------------------------------------------------


def prompt_text(messages: Sequence[Any]) -> str:
    """Return the text of the prompt — everything that costs tokens.

    The tool calls are part of it: an assistant turn that asks for a tool
    carries the name of the tool and its arguments, and they take up
    prompt space just like plain text does.

    Args:
        messages: The chat messages of the prompt.

    Returns:
        The text of the prompt.
    """
    from components.context_guard import token_text

    return " ".join(token_text(message) for message in messages)


def tool_schema_text(tools: Any) -> str:
    """Return the JSON of the tool schemas that travel with every request.

    The schemas are not chat messages, but they are sent with the prompt
    and they take up room in the context window.

    Args:
        tools: The tools of the agent.

    Returns:
        The JSON of the schemas, or an empty string when there are none
        or when they cannot be read.
    """
    if not tools:
        return ""

    import json

    try:
        specs = [
            tool.metadata.to_openai_tool(skip_length_check=True)
            for tool in tools
        ]
        return json.dumps(specs)
    except Exception as exc:  # noqa: BLE001 - a size is never worth a run
        logger.debug("Could not read the tool schemas: %s", exc)
        return ""


# ---------------------------------------------------------------------------
# The tokens
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# The measurement
# ---------------------------------------------------------------------------


def measure_context(
    messages: Sequence[Any],
    tools: Any = None,
    tokenizer: Optional[Callable[[str], Any]] = None,
) -> ContextSize:
    """Measure the prompt that goes to the model.

    Args:
        messages: The chat messages of the prompt.
        tools: The tools of the agent — their schemas travel with every
            request and are measured separately.
        tokenizer: The tokenizer to count with.  The tokenizer of the
            agent is loaded when it is not given.

    Returns:
        The measurements of the prompt.
    """
    text = prompt_text(messages)
    schema = tool_schema_text(tools)

    tokens, estimated = count_tokens_of(text, tokenizer)
    schema_tokens, schema_estimated = count_tokens_of(schema, tokenizer)

    return ContextSize(
        messages=len(messages),
        tokens=tokens,
        bytes=len(text.encode("utf-8")),
        tool_schema_tokens=schema_tokens,
        tool_schema_bytes=len(schema.encode("utf-8")),
        estimated=estimated or schema_estimated,
    )


def _format_size(total_bytes: int) -> str:
    """Render a number of bytes the way the operator reads a size.

    The helper of the chat history is used, so that the size of the
    prompt and the size of a session are written the same way.  A helper
    that cannot be imported is not a reason to lose the line: the plain
    number of bytes is used instead.
    """
    try:
        from chat_manager.stats import format_size
    except Exception:  # noqa: BLE001 - the line is still worth writing
        return f"{total_bytes} B"
    return format_size(total_bytes)


def describe_context(
    size: ContextSize,
    window: Optional[int] = None,
    budget: Optional[int] = None,
) -> str:
    """Render the measurements of a prompt the way the operator reads them.

    Args:
        size: The measurements of the prompt.
        window: The context window of the model, in tokens.  The share of
            the window the prompt takes is reported when it is known.
        budget: The number of tokens the prompt may use, when a budget is
            in force.

    Returns:
        The description of the prompt — one line, no newlines.
    """
    messages = f"{size.messages} message" + ("" if size.messages == 1 else "s")
    parts = [
        messages,
        f"{size.total_tokens:,} tokens",
        _format_size(size.total_bytes),
    ]

    if window:
        share = 100.0 * size.total_tokens / window
        parts.append(f"{share:.1f}% of the {window:,}-token window")
    if budget:
        parts.append(f"budget {budget:,} tokens")
    if size.estimated:
        parts.append("the tokens are estimated")

    return ", ".join(parts)
