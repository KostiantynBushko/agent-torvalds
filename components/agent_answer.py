"""
The answer of a run — and what to show when there is none.

The agent prints its answer like this::

    ────────────── Agent Response ──────────────
    <the text of the model>

The text came from one line of code (``agent-torvalds.py``)::

    response_text = (
        result.get("output")
        if isinstance(result, dict)
        else str(result)
    )

``result`` is the ``AgentOutput`` the workflow produced, and
``AgentOutput.__str__`` is::

    def __str__(self) -> str:
        return self.response.content or ""

``ChatMessage.content`` is the text of the **TextBlocks** of the message —
the *thinking* of the model is not part of it.  So a run in which the model
reasoned but wrote no answer produced the **empty string**, and the section
under the rule was blank:

    ────────────── Agent Response ──────────────
    ─────────────────────────────────────────────

Nothing in the pipeline noticed.  The run reported no error, the statistics
were finalised as usual, and the operator was left with a rule and no
answer — while the tool result that *was* the answer sat in the output the
whole time.

This module gives the run one place to say what it has:

* :func:`extract_answer` returns the model's text when there is one;
* when there is none, it returns a readable notice **and the last tool
  result**, so the operator sees what the agent found instead of nothing.

Category: Infrastructure
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "NO_ANSWER_NOTICE",
    "extract_answer",
    "answer_is_missing",
]

#: What the operator is told when the model wrote nothing.
NO_ANSWER_NOTICE = (
    "⚠️ **The model returned no answer.**\n\n"
    "The run ended without a reply from the model — the answer is missing, "
    "not the rendering.  What the agent found is below."
)

#: How much of the model's thinking is shown when it wrote no answer.
THINKING_LIMIT = 2000

#: How much of a tool result is shown when the model wrote no answer.
TOOL_RESULT_LIMIT = 4000


def _safe_getattr(obj: Any, name: str, default: Any = None) -> Any:
    """Return the attribute *name* of *obj*, or *default*.

    A payload from the framework must not be able to break the answer:
    ``getattr`` only swallows the ``AttributeError`` of a missing
    attribute, so a property that *raises* would take the run down with it.
    """
    try:
        return getattr(obj, name, default)
    except Exception:  # noqa: BLE001 — a payload must not break the run
        return default


def _response_of(result: Any) -> Any:
    """Return the response message of *result*, or ``None``."""
    response = _safe_getattr(result, "response", None)
    if response is None:
        response = _safe_getattr(result, "output", None)
    return response


def _answer_text(result: Any) -> str:
    """Return the text the model wrote, or an empty string.

    The shapes that are read:

    * a **dict** — the legacy shape, ``{"output": "..."}``;
    * an **object with a response** — the ``AgentOutput`` the workflow
      produces.  Its ``__str__`` is the text of the message, and the text
      of the message is the text of its TextBlocks;
    * a **string** — the answer itself.
    """
    if result is None:
        return ""

    if isinstance(result, str):
        return result

    if isinstance(result, dict):
        for key in ("output", "response", "content", "text"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return ""

    response = _response_of(result)
    if response is None:
        return ""

    if isinstance(response, str):
        return response

    content = _safe_getattr(response, "content", None)
    if isinstance(content, str) and content.strip():
        return content

    return ""


def _thinking_of(result: Any) -> str:
    """Return what the model was thinking, or an empty string."""
    response = _response_of(result)
    if response is None:
        return ""

    parts: List[str] = []
    for block in _safe_getattr(response, "blocks", None) or []:
        if str(_safe_getattr(block, "block_type", "") or "") != "thinking":
            continue
        content = _safe_getattr(block, "content", None)
        if content:
            parts.append(str(content))

    return "\n".join(parts).strip()


def _tool_results_of(result: Any) -> List[tuple[str, str]]:
    """Return the ``(name, output)`` pairs of the tools the run called."""
    found: List[tuple[str, str]] = []

    for call in _safe_getattr(result, "tool_calls", None) or []:
        name = str(_safe_getattr(call, "tool_name", "") or "")
        output = _safe_getattr(call, "tool_output", None)

        content = _safe_getattr(output, "content", None)
        if content is None:
            content = _safe_getattr(output, "raw_output", None)
        if content is None:
            content = _safe_getattr(call, "content", None)
        if content is None:
            continue

        text = str(content).strip()
        if not text:
            continue
        found.append((name, text))

    return found


def _fallback(result: Any) -> str:
    """Return what is shown when the model wrote no answer.

    The notice comes first, then what the run *does* have: the last tool
    result — which is usually the thing the operator asked for — and the
    thinking of the model.
    """
    sections: List[str] = [NO_ANSWER_NOTICE]

    results = _tool_results_of(result)
    if results:
        name, text = results[-1]
        if len(text) > TOOL_RESULT_LIMIT:
            text = text[:TOOL_RESULT_LIMIT] + "\n… (truncated)"
        label = f"**{name}**" if name else "**the last tool**"
        sections.append(
            f"The last thing the agent did was:\n\n{label}\n\n```\n{text}\n```"
        )

    thinking = _thinking_of(result)
    if thinking:
        if len(thinking) > THINKING_LIMIT:
            thinking = thinking[:THINKING_LIMIT] + "\n… (truncated)"
        sections.append(
            "The model was thinking about this:\n\n> " + thinking.replace("\n", "\n> ")
        )

    return "\n\n".join(sections)


def answer_is_missing(result: Any) -> bool:
    """Return ``True`` when the model wrote no answer.

    A run without an answer is a run that has to say so; it is not a run
    that failed.  The difference matters for the statistics and for the
    log: an empty answer that is not reported looks like a broken
    renderer.
    """
    return not _answer_text(result).strip()


def extract_answer(result: Any) -> str:
    """Return the text of the agent's answer for *result*.

    Args:
        result: The result of a workflow run — normally an
            ``AgentOutput``, but a dict or a plain string are read too.

    Returns:
        The text of the answer.  When the model wrote nothing, a readable
        notice that carries the last tool result and the thinking of the
        model — never an empty string, so the answer section is never
        blank.
    """
    text = _answer_text(result)
    if text.strip():
        return text

    logger.warning(
        "The model returned no answer — the answer section is filled with "
        "what the run found instead of nothing."
    )
    return _fallback(result)
