"""
Timeout Manager for HITL (Human-in-the-Loop)

Provides centralized timeout management for HITL prompts.  Wraps async
prompt functions with configurable timeout handling, tracks timed-out
questions for review, and supplies fallback answers when users do not
respond in time.

Usage:
    from components.timeout_manager import TimeoutManager

    manager = TimeoutManager(default_timeout=30)

    # Wrap any async prompt function
    answer, timed_out = await manager.prompt_with_timeout(
        prompt_fn=some_async_prompt,
        timeout=45,
        default_answer="yes",
        question_id="install-pkg",
    )

    # Review timed-out questions
    log = manager.get_timeout_log()
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple


class TimeoutManager:
    """Centralized timeout management for HITL prompts.

    Responsibilities:
    - Wrap async prompt functions with timeout handling
    - Track timed-out questions for review
    - Provide fallback answers on timeout
    - Log timeout events for later inspection

    Attributes:
        default_timeout: Default timeout in seconds when none is specified
                         on individual prompts.
    """

    def __init__(self, default_timeout: int = 30) -> None:
        """Initialise the TimeoutManager.

        Args:
            default_timeout: Default timeout in seconds (default: 30).
        """
        if default_timeout < 0:
            raise ValueError("default_timeout must be non-negative")
        self.default_timeout = default_timeout
        self._timed_out_questions: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def prompt_with_timeout(
        self,
        prompt_fn: Callable[[], Coroutine[Any, Any, str]],
        timeout: Optional[int] = None,
        default_answer: str = "",
        question_id: Optional[str] = None,
    ) -> Tuple[str, bool]:
        """Prompt with timeout handling.

        Calls the provided async prompt function and waits up to *timeout*
        seconds for a response.  If the timeout expires the function is
        cancelled and *default_answer* is returned instead.

        Args:
            prompt_fn: Async callable that prompts the user and returns
                       a ``str`` answer.
            timeout: Seconds to wait.  Uses ``default_timeout`` when
                     ``None``.
            default_answer: Fallback value returned on timeout.
            question_id: Optional identifier for tracking and logging.

        Returns:
            A tuple ``(answer, was_timeout)`` where *was_timeout* is
            ``True`` if the timeout fired.
        """
        effective_timeout = timeout if timeout is not None else self.default_timeout

        try:
            answer = await asyncio.wait_for(
                prompt_fn(),
                timeout=effective_timeout,
            )
            return answer, False

        except asyncio.TimeoutError:
            # Log the timeout event
            self._timed_out_questions.append({
                "question_id": question_id,
                "timeout": effective_timeout,
                "default_answer": default_answer,
                "timestamp": datetime.now().isoformat(),
            })
            return default_answer, True

    async def prompt_with_retry(
        self,
        prompt_fn: Callable[[], Coroutine[Any, Any, str]],
        timeout: Optional[int] = None,
        default_answer: str = "",
        question_id: Optional[str] = None,
        max_retries: int = 1,
        retry_delay: float = 1.0,
    ) -> Tuple[str, bool, int]:
        """Prompt with timeout and optional retry logic.

        Similar to :meth:`prompt_with_timeout` but allows retrying the
        prompt up to *max_retries* times before falling back to the
        default answer.

        Args:
            prompt_fn: Async callable that prompts the user.
            timeout: Seconds per attempt.
            default_answer: Fallback value after all retries exhausted.
            question_id: Optional identifier for tracking.
            max_retries: Number of retry attempts (default: 1).
            retry_delay: Seconds to wait between retries (default: 1.0).

        Returns:
            A tuple ``(answer, was_timeout, attempts_made)``.
        """
        effective_timeout = timeout if timeout is not None else self.default_timeout
        total_attempts = 1 + max_retries

        for attempt in range(total_attempts):
            try:
                answer = await asyncio.wait_for(
                    prompt_fn(),
                    timeout=effective_timeout,
                )
                return answer, False, attempt + 1

            except asyncio.TimeoutError:
                if attempt == total_attempts - 1:
                    # Last attempt — log and return default
                    self._timed_out_questions.append({
                        "question_id": question_id,
                        "timeout": effective_timeout,
                        "default_answer": default_answer,
                        "timestamp": datetime.now().isoformat(),
                        "attempts": attempt + 1,
                    })
                    return default_answer, True, attempt + 1

                # Wait before retrying
                await asyncio.sleep(retry_delay)

        # Should never reach here, but satisfy type checker
        return default_answer, True, total_attempts

    def get_timeout_log(self) -> List[Dict[str, Any]]:
        """Return a copy of the timeout event log.

        Each entry is a dict with at least:
        - ``question_id``: The question identifier (may be ``None``).
        - ``timeout``: Timeout value that was used.
        - ``default_answer``: Fallback answer returned.
        - ``timestamp``: ISO-format timestamp of the timeout.
        """
        return self._timed_out_questions.copy()

    def reset(self) -> None:
        """Clear the timeout log."""
        self._timed_out_questions.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Return summary statistics about timeout events.

        Returns:
            Dictionary with keys:
            - ``total_timeouts``: Number of logged timeout events.
            - ``question_ids``: Set of unique question IDs that timed out.
            - ``first_timeout``: Timestamp of the first timeout (or ``None``).
            - ``last_timeout``: Timestamp of the most recent timeout (or ``None``).
        """
        log = self._timed_out_questions
        if not log:
            return {
                "total_timeouts": 0,
                "question_ids": set(),
                "first_timeout": None,
                "last_timeout": None,
            }

        question_ids = {
            entry["question_id"]
            for entry in log
            if entry.get("question_id") is not None
        }

        return {
            "total_timeouts": len(log),
            "question_ids": question_ids,
            "first_timeout": log[0]["timestamp"],
            "last_timeout": log[-1]["timestamp"],
        }

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"TimeoutManager(default_timeout={self.default_timeout}, "
            f"logged_timeouts={len(self._timed_out_questions)})"
        )
