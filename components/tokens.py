"""
Tokens — the tokenizer of the agent, and the counting of tokens.

Why this module exists
----------------------
The tokenizer of the agent is **one** thing, and it was reached in four
places, each of them with its own way of getting it: one wrapped the call
in a ``try`` and returned ``None``, one remembered the failure, one loaded
it straight from LlamaIndex, and one fell back to an estimate.  The
estimate is **one** rule as well — four characters per token — and it was
written out in three modules.

This module holds both, as free functions:

* ``load_tokenizer()`` — the tokenizer of the agent; it raises when it
  cannot be loaded;
* ``get_tokenizer()`` — the same tokenizer, but ``None`` instead of an
  exception, for the callers that can live without one;
* ``estimate_tokens()`` — the estimate used when there is no tokenizer;
* ``count_tokens_of()`` — the count of a text, with the estimate as the
  fallback.

The tokenizer is the one the chat memory uses, so the accounting matches
the one the token limit is enforced with.

Nothing here imports LlamaIndex at import time.  The tokenizer is loaded
when it is asked for, so the modules that only need the *estimate* stay
cheap to import.

Category: Infrastructure
Retriever Keywords: tokens, tokenizer, count, estimate, chars per token
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

#: Characters per token in the estimate used when no tokenizer is available.
CHARS_PER_TOKEN = 4


__all__ = [
    "CHARS_PER_TOKEN",
    "count_tokens_of",
    "estimate_tokens",
    "get_tokenizer",
    "load_tokenizer",
]


# ---------------------------------------------------------------------------
# The tokenizer
# ---------------------------------------------------------------------------


def load_tokenizer() -> Callable[[str], Any]:
    """Return the tokenizer of the agent.

    The tokenizer is the one the chat memory uses, so the accounting
    matches the one the chat-token limit is enforced with.

    Returns:
        The tokenizer — a callable that turns a text into a list of
        tokens.

    Raises:
        Exception: Whatever the tokenizer library raises when it cannot
            be loaded.  A caller that cannot work without a tokenizer
            should let this happen; a caller that can work without one
            should use ``get_tokenizer()`` instead.
    """
    from llama_index.core.utils import get_tokenizer as _get_tokenizer

    return _get_tokenizer()


def get_tokenizer() -> Optional[Callable[[str], Any]]:
    """Return the tokenizer of the agent, or ``None`` when there is none.

    A tokenizer that cannot be loaded is not a reason to lose the feature
    that needs it: the caller measures with the estimate of the agent
    instead — four characters per token — and says that the number is an
    approximation.

    The failure is reported in the log.  It is **not** remembered here:
    a tokenizer that comes back later (a dependency installed while the
    agent runs) is picked up by the next call.  The callers that ask for
    it with every request remember the failure themselves, so the line
    is not repeated.

    Returns:
        The tokenizer, or ``None`` when it cannot be loaded.
    """
    try:
        return load_tokenizer()
    except Exception as exc:  # noqa: BLE001 - a tokenizer is never worth a run
        logger.warning(
            "The tokenizer of the agent is not available (%s) — the tokens "
            "are estimated.",
            exc,
        )
        return None


# ---------------------------------------------------------------------------
# The counting
# ---------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    """Return the estimated number of tokens of *text*.

    The estimate is four characters per token — the rule the agent has
    always used when no tokenizer can be loaded.  It is an approximation,
    and the caller that shows the number says so.

    Args:
        text: The text to estimate.

    Returns:
        The estimated number of tokens.
    """
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


def count_tokens_of(
    text: str,
    tokenizer: Optional[Callable[[str], Any]] = None,
) -> tuple[int, bool]:
    """Return the number of tokens of *text*, and whether it is estimated.

    The count is exact when there is a tokenizer.  Without one the
    estimate is used, and the second value says so — a caller that shows
    the number to the operator has to say that it is an approximation.

    Args:
        text: The text to count.
        tokenizer: The tokenizer to count with.  The tokenizer of the
            agent is loaded when it is not given.

    Returns:
        A tuple of the number of tokens and whether they were estimated.
    """
    if not text:
        return 0, False

    if tokenizer is None:
        tokenizer = get_tokenizer()
        if tokenizer is None:
            return estimate_tokens(text), True

    try:
        return len(tokenizer(text)), False
    except Exception as exc:  # noqa: BLE001 - the count degrades
        logger.warning(
            "The tokens could not be counted (%s) — they are estimated", exc
        )
        return estimate_tokens(text), True
