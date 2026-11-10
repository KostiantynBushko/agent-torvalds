"""Ask the model server again when it fails for a reason that passes.

The model server fails for two kinds of reason.  One of them is **the
request**: the prompt was too long, the model is not pulled, the key is
wrong.  Sending that request again fails in exactly the same way, and
the only thing the operator gets out of it is a slower failure.

The other kind of reason is **the server**: it ran out of memory, it
crashed while loading the model, it was busy, the connection was cut.
That request is worth sending again — the very same request, to the very
same server, a moment later, usually works.

This module tells the two apart, and sends the second kind of request
again.  The failure of the report is the case in point: the Ollama
server answered **500**, the model had died, and the request was never
sent again — the operator was told what happened and nothing more.

The retry happens **around the request**, not around the whole run.  The
tools that already ran are not run again, the conversation is not lost,
and the answer of the model that finally answers is the answer of the
run.  The retry is the *same request* — the same prompt, the same
tools — because the request was never the problem.

The module knows nothing about the model server it talks to: the failure
is read the way every HTTP client reports it — a status code, a class
name — so the same rule holds for Ollama, for the Anthropic API and for
the OpenAI API.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Sequence

from llama_index.core.llms import (
    ChatMessage,
    ChatResponse,
    ChatResponseAsyncGen,
)
from llama_index.llms.ollama.base import Ollama

from components.llm_errors import (
    is_a_connection_failure,
    is_a_timeout,
    status_code_of,
)

logger = logging.getLogger(__name__)


#: The statuses that are worth another attempt.
#:
#: ``500`` is the one the operator met: the model of the server died, or
#: it ran out of memory.  The server may well serve the next request.
TRANSIENT_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})

#: The statuses that will fail the same way every time.  A prompt that
#: was too long is still too long, a model that is not pulled is still
#: not pulled, and a key that is wrong is still wrong.
PERMANENT_STATUSES = frozenset({400, 401, 403, 404, 405, 413, 415, 422})


def is_transient(exc: BaseException) -> bool:
    """Whether the failure is worth sending the request again.

    A status decides it: the statuses of :data:`TRANSIENT_STATUSES` pass,
    the statuses of :data:`PERMANENT_STATUSES` do not.  A status that is
    in neither list is not retried either — an answer the agent does not
    understand is not a failure it may repeat.

    A failure that carries no status at all is a connection that never
    came about or a server that did not answer in time — both of them
    pass.

    A failure that came in the **body** of a response (Ollama raises it
    with the status ``-1``) carries no status, and it does not pass: the
    server answered, and what it said — "model requires more system
    memory" — will be said again.

    Args:
        exc: The exception that ended the request.

    Returns:
        ``True`` when the request is worth sending again.
    """
    status = status_code_of(exc)
    if status is not None:
        if status in PERMANENT_STATUSES:
            return False
        return status in TRANSIENT_STATUSES

    if is_a_connection_failure(exc):
        return True

    if is_a_timeout(exc):
        return True

    return False


def delay_for(attempt: int, base: float, backoff: float) -> float:
    """How long to wait before the next attempt.

    The wait grows with every attempt: a server that has just died needs
    a moment, and a server that is busy needs a longer one.

    Args:
        attempt: The number of the attempt that is about to be made —
            1 for the first one.
        base: The wait of the first attempt, in seconds.
        backoff: The factor the wait grows by.

    Returns:
        The wait, in seconds.
    """
    if attempt < 1:
        attempt = 1
    return float(base) * (float(backoff) ** (attempt - 1))


class RetryingOllama(Ollama):
    """The Ollama LLM that asks again when the server fails transiently.

    It is the LLM of the agent, with one difference: a request that
    failed for a reason that passes is sent again, and the answer of the
    attempt that works is the answer of the request.

    The retry is bounded by three settings:

    ``max_retries``
        How many times the request is sent **again** after it failed.
        Zero means no retry at all.
    ``retry_delay``
        How long to wait before the first attempt again, in seconds.
    ``retry_backoff``
        The factor the wait grows by, from one attempt to the next.

    The wait happens **between** the attempts, and the failure of an
    attempt that is followed by a successful one is written to the log
    as a warning — the operator sees that the server stumbled and that
    the agent carried on.
    """

    #: How many times a failed request is sent again.
    max_retries: int = 2

    #: How long to wait before the request is sent again, in seconds.
    retry_delay: float = 2.0

    #: The factor the wait grows by, from one attempt to the next.
    retry_backoff: float = 2.0

    # -- the helpers ----------------------------------------------------

    def _wait_before(self, attempt: int, exc: BaseException) -> float:
        """How long to wait before the attempt that is about to be made.

        Args:
            attempt: The number of the attempt that is about to be made.
            exc: The failure of the attempt before it.

        Returns:
            The wait, in seconds.
        """
        wait = delay_for(attempt, self.retry_delay, self.retry_backoff)
        logger.warning(
            "The model server failed (%s: %s) — the request is sent again "
            "in %.1f seconds (attempt %d of %d).",
            type(exc).__name__,
            exc,
            wait,
            attempt + 1,
            self.max_retries + 1,
        )
        return wait

    def _should_retry(self, exc: BaseException, attempt: int) -> bool:
        """Whether the request is sent again.

        Args:
            exc: The failure of the attempt that just failed.
            attempt: How many attempts have been made already.

        Returns:
            ``True`` when the request is sent again.
        """
        if attempt >= self.max_retries:
            return False
        return is_transient(exc)

    async def _wait_before_the_next_attempt(
        self, exc: BaseException, attempt: int
    ) -> int:
        """Wait before the next attempt, or let the failure through.

        Args:
            exc: The failure of the attempt that just failed.
            attempt: How many attempts have been made already.

        Returns:
            The number of the attempt that is about to be made.

        Raises:
            The failure itself, when it is not worth another attempt.
        """
        if not self._should_retry(exc, attempt):
            raise exc
        attempt += 1
        await asyncio.sleep(self._wait_before(attempt, exc))
        return attempt

    # -- the requests ---------------------------------------------------

    async def astream_chat(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> ChatResponseAsyncGen:
        """Stream the answer of the model, asking again when it fails.

        The stream is the path the agent uses: the model answers while
        the answer is being written.  A failure in the middle of the
        stream is a failure of the server, and the whole request is sent
        again — the text that was streamed before the failure is streamed
        again with it.

        Args:
            messages: The conversation to send.
            **kwargs: The rest of the request.

        Returns:
            The stream of the answer.
        """
        parent = super(RetryingOllama, self)

        async def gen() -> ChatResponseAsyncGen:
            attempt = 0
            while True:
                try:
                    stream = await parent.astream_chat(messages, **kwargs)
                except Exception as exc:
                    # The request never reached the stream.
                    attempt = await self._wait_before_the_next_attempt(
                        exc, attempt
                    )
                    continue

                iterator = stream.__aiter__()
                while True:
                    try:
                        chunk = await iterator.__anext__()
                    except StopAsyncIteration:
                        # The answer is complete.
                        return
                    except Exception as exc:
                        # The stream failed in the middle of the answer.
                        attempt = await self._wait_before_the_next_attempt(
                            exc, attempt
                        )
                        break
                    # The chunk is yielded **outside** the try: a failure
                    # of the reader of the stream is not a failure of the
                    # server, and it must not send the request again.
                    yield chunk
                # The stream failed: the request is sent again, and the
                # answer is streamed from the beginning.

        return gen()

    async def achat(
        self, messages: Sequence[ChatMessage], **kwargs: Any
    ) -> ChatResponse:
        """Ask the model for an answer, asking again when it fails.

        Args:
            messages: The conversation to send.
            **kwargs: The rest of the request.

        Returns:
            The answer of the model.
        """
        parent = super(RetryingOllama, self)

        attempt = 0
        while True:
            try:
                return await parent.achat(messages, **kwargs)
            except Exception as exc:
                attempt = await self._wait_before_the_next_attempt(
                    exc, attempt
                )
