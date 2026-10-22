"""
HITL Timeout Semantics — single source of truth.

The Human-in-the-Loop path spans a lot of components: the orchestrators
(``agent-torvalds.py`` / ``agent-torvalds-mw.py``), the timeout manager,
the console / whiptail input modules, the HITL event classes, the agent
step and the multi-window TUI.  Every one of them needs to agree on what
a timeout *means*, otherwise a value that is meant to be "wait forever"
silently turns into "give up after a few seconds" somewhere in the chain.

The convention
--------------
``-1`` means **no timeout**.  The agent waits for the user's answer
constantly — for as long as the human needs — instead of falling back to
the default answer on a timer.

======================  ====================================================
Value                   Meaning
======================  ====================================================
``-1`` (or any negative) No timeout — wait for the human indefinitely.
``0``                   Expire immediately (useful for scripted runs).
``n > 0``               Wait at most *n* seconds, then fall back.
======================  ====================================================

``None`` is treated as "no timeout" as well, because that is what
``asyncio.wait_for`` and ``Context.wait_for_event`` expect.

Usage::

    from components.hitl_timeout import NO_TIMEOUT, normalize_timeout

    normalize_timeout(NO_TIMEOUT)  # -> None  (wait forever)
    normalize_timeout(30)          # -> 30.0

Category: HITL / Timeouts
Retriever Keywords: hitl, timeout, no timeout, indefinite, wait forever
"""

from __future__ import annotations

from typing import Optional, Union

#: Sentinel timeout value meaning "wait for the human indefinitely".
NO_TIMEOUT: int = -1

#: Smallest accepted timeout value.  Anything below this is a typo.
MIN_TIMEOUT: int = NO_TIMEOUT

TimeoutLike = Optional[Union[int, float]]


def is_no_timeout(timeout: TimeoutLike) -> bool:
    """Return ``True`` when *timeout* means "wait forever".

    Args:
        timeout: The timeout value to inspect.  ``None`` and every
            negative value mean "no timeout".
    """
    return timeout is None or timeout < 0


def normalize_timeout(timeout: TimeoutLike) -> Optional[float]:
    """Translate a timeout value into the form the async runtime expects.

    Args:
        timeout: The timeout value to translate.

    Returns:
        ``None`` for "no timeout" — the value ``asyncio.wait_for`` and
        ``Context.wait_for_event`` interpret as "wait indefinitely" — and
        the number of seconds otherwise.
    """
    if is_no_timeout(timeout):
        return None
    return float(timeout)


def validate_timeout(timeout: int) -> int:
    """Validate a timeout value.

    Args:
        timeout: The timeout value to validate.

    Returns:
        The validated timeout, unchanged.

    Raises:
        ValueError: If the value is below ``MIN_TIMEOUT`` (``-1``).  A
            value of ``-1`` is valid and means "no timeout".
    """
    if timeout < MIN_TIMEOUT:
        raise ValueError(
            f"timeout must be >= {MIN_TIMEOUT} "
            f"({MIN_TIMEOUT} means 'no timeout'), got {timeout}"
        )
    return timeout


def describe_timeout(timeout: TimeoutLike) -> str:
    """Render a timeout value for display.

    Args:
        timeout: The timeout value to describe.

    Returns:
        ``"none"`` for "no timeout", otherwise ``"<n>s"``.
    """
    if is_no_timeout(timeout):
        return "none"
    return f"{int(timeout)}s"
