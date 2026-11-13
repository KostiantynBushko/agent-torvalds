"""The memory buffer of the agent — with a trimming that is not quadratic.

The memory buffer of LlamaIndex keeps the tail of the chat history that
fits in the chat-token limit.  It finds that tail with a loop that
counts the tokens of the **whole window again on every step**:

```python
# llama_index/core/memory/chat_memory_buffer.py
while token_count > self.token_limit and message_count > 1:
    message_count -= 1
    ...
    cur_messages = chat_history[-message_count:]
    token_count = self._token_count_for_messages(cur_messages)   # again
```

For a session with thousands of messages the work is quadratic.  The
agent pays it on **every turn**: the buffer is asked for its messages
every time a request is built, and a history of 6204 messages (15 MB)
takes **forty seconds** to trim.

The buffer of this module answers the same question in **one pass**:

* the messages are counted one by one, from the end, and the walk stops
  when they reach the limit — only the tail is ever counted, and the
  tail is bounded by the limit;
* the exact count of the window decides the boundary, because the
  joined text is not always the sum of the counts of the messages;
* the windows the library visits are the windows visited here, so the
  answer is the answer of the library — the same messages, the same
  order.

The tests compare the two, message by message, for a dozen histories
and for the history of the operator.

Category: Infrastructure
"""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence

from llama_index.core.base.llms.types import ChatMessage, MessageRole
from llama_index.core.memory import ChatMemoryBuffer

logger = logging.getLogger(__name__)


class TrimmingChatMemoryBuffer(ChatMemoryBuffer):
    """The memory buffer of LlamaIndex, with the trimming in one pass.

    The buffer of the library trims the history with a loop that counts
    the tokens of the whole window again on every step.  This one walks
    the tail of the history once and stops at the limit.

    The answer is the answer of the library: the same messages, in the
    same order.  The only difference is the work it takes to find them.
    """

    #: The roles whose message may not open the history.  The model is
    #: given the pair, and a tool message without the assistant message
    #: that called it is a history it cannot read — so the buffer of the
    #: library drops those messages too.
    _SKIPPED_ROLES = (MessageRole.TOOL, MessageRole.ASSISTANT)

    def get(
        self,
        input: Optional[str] = None,
        initial_token_count: int = 0,
        **kwargs,
    ) -> List[ChatMessage]:
        """The messages of the history that fit in the token limit.

        Args:
            input: Not used — the buffer of the library ignores it too.
            initial_token_count: The tokens the caller adds to the
                count of the history.
            **kwargs: Not used.

        Returns:
            The tail of the history that fits in the token limit.
        """
        chat_history = self.get_all()

        if initial_token_count > self.token_limit:
            raise ValueError("Initial token count exceeds token limit")

        total = len(chat_history)
        if total == 0:
            return []

        # The limit the history itself has to fit in.
        limit = self.token_limit - initial_token_count

        # The tail: the messages are counted one by one, from the end,
        # and the walk stops when they reach the limit.  Only the tail is
        # counted — the rest of the history is never looked at.
        candidate = 0
        running = 0
        for message in reversed(chat_history):
            tokens = self._token_count_for_messages([message])
            if running + tokens > limit:
                break
            running += tokens
            candidate += 1

        if candidate >= total:
            # The history may fit as a whole.  It is counted exactly —
            # and a history that fits is small by construction, because
            # the limit bounds it.
            if self._token_count_for_messages(chat_history) <= limit:
                return list(chat_history)

        # The exact count of the window decides the boundary: the joined
        # text is not always the sum of the counts of the messages.
        candidate = self._correct(chat_history, total, limit, candidate)

        if candidate < 1:
            # A message that is longer than the limit is kept on its
            # own: the model is told that the message is too long,
            # rather than the history being silently shortened to
            # nothing.  This is what the buffer of the library does.
            return list(chat_history[-1:])

        return list(chat_history[-candidate:])

    # ------------------------------------------------------------------
    # The boundary
    # ------------------------------------------------------------------

    def _correct(
        self,
        chat_history: Sequence[ChatMessage],
        total: int,
        limit: int,
        candidate: int,
    ) -> int:
        """The exact boundary: the largest window that fits.

        The walk of the tail gives a candidate — the window whose
        messages reach the limit when they are counted one by one.  The
        count of the joined text is not always the sum of the counts of
        the messages, so the boundary is walked exactly: down while the
        window is too big, up while it fits.

        Args:
            chat_history: The messages of the session, oldest first.
            total: How many messages the history holds.
            limit: The tokens the history may take.
            candidate: The size of the window the walk of the tail found.

        Returns:
            The size of the window that fits.
        """
        # The window of the walk of the tail is not always a window the
        # library would look at: a window that opens with an assistant
        # or a tool message is skipped.  The walk starts at the largest
        # window at or below the candidate that may open the history.
        k = self._visited_at_or_below(chat_history, total, candidate)

        # The window of the candidate is too big: walk down to the
        # first window that fits.
        while k > 1 and self._count_window(chat_history, k) > limit:
            k = self._visited_below(chat_history, total, k)

        # The window fits: walk up to the largest window that fits as
        # well.
        while k < total:
            above = self._visited_above(chat_history, total, k)
            if above is None or above <= k:
                break
            if self._count_window(chat_history, above) > limit:
                break
            k = above

        return k

    def _count_window(
        self,
        chat_history: Sequence[ChatMessage],
        size: int,
    ) -> int:
        """The exact number of the tokens of the last *size* messages.

        Args:
            chat_history: The messages of the session, oldest first.
            size: How many messages of the end of the history.

        Returns:
            The number of the tokens of the window.
        """
        if size <= 0:
            return 0
        return self._token_count_for_messages(chat_history[-size:])

    def _may_open(
        self,
        chat_history: Sequence[ChatMessage],
        total: int,
        size: int,
    ) -> bool:
        """Whether a window of *size* messages may open the history.

        Args:
            chat_history: The messages of the session, oldest first.
            total: How many messages the history holds.
            size: How many messages of the end of the history.

        Returns:
            True when the window may open the history.
        """
        if size <= 1:
            return True
        return chat_history[total - size].role not in self._SKIPPED_ROLES

    def _visited_at_or_below(
        self,
        chat_history: Sequence[ChatMessage],
        total: int,
        size: int,
    ) -> int:
        """The largest window at or below *size* that may open the history.

        The whole history is a window of its own, and the library tries
        it first — without the rule of the roles.  When it does not
        fit, the walk starts one message below it.

        Args:
            chat_history: The messages of the session, oldest first.
            total: How many messages the history holds.
            size: The window the walk is at.

        Returns:
            The size of the window the walk starts at.
        """
        for candidate in range(min(size, total - 1), 1, -1):
            if self._may_open(chat_history, total, candidate):
                return candidate
        return 1

    def _visited_below(
        self,
        chat_history: Sequence[ChatMessage],
        total: int,
        size: int,
    ) -> int:
        """The largest window below *size* that may open the history.

        Args:
            chat_history: The messages of the session, oldest first.
            total: How many messages the history holds.
            size: The window the walk is at.

        Returns:
            The size of the window below it.
        """
        for candidate in range(size - 1, 1, -1):
            if self._may_open(chat_history, total, candidate):
                return candidate
        return 1

    def _visited_above(
        self,
        chat_history: Sequence[ChatMessage],
        total: int,
        size: int,
    ) -> Optional[int]:
        """The smallest window above *size* that may open the history.

        The whole history is a window of its own, and the library tries
        it first.

        Args:
            chat_history: The messages of the session, oldest first.
            total: How many messages the history holds.
            size: The window the walk is at.

        Returns:
            The size of the window above it.
        """
        for candidate in range(size + 1, total):
            if self._may_open(chat_history, total, candidate):
                return candidate
        return total


__all__ = ["TrimmingChatMemoryBuffer"]
