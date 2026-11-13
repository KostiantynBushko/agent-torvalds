"""Tests for the measurement of the chat history."""

import unittest
from unittest.mock import patch

from chat_manager.stats import (
    BYTES_PER_KB,
    BYTES_PER_MB,
    HistoryStats,
    count_messages_within_limit,
    count_tokens,
    format_size,
    format_tokens,
    measure,
)


class _Message:
    """A stand-in for a chat message."""

    def __init__(self, content: str, role: str = "user") -> None:
        self.content = content
        self.role = role


class TestFormatSize(unittest.TestCase):
    """Tests for the rendering of a size."""

    def test_bytes_below_a_kilobyte(self):
        """A small size is shown in bytes."""
        self.assertEqual(format_size(0), "0 B")
        self.assertEqual(format_size(512), "512 B")

    def test_kilobytes(self):
        """A size above a kilobyte is shown in kilobytes."""
        self.assertEqual(format_size(BYTES_PER_KB), "1.0 KB")
        self.assertEqual(format_size(BYTES_PER_KB + BYTES_PER_KB // 2), "1.5 KB")

    def test_megabytes(self):
        """A size above a megabyte is shown in megabytes."""
        self.assertEqual(format_size(BYTES_PER_MB), "1.00 MB")
        self.assertEqual(format_size(BYTES_PER_MB * 2 + BYTES_PER_MB // 2), "2.50 MB")


class TestCountTokens(unittest.TestCase):
    """Tests for the counting of tokens."""

    def test_no_messages(self):
        """An empty history holds no tokens."""
        tokens, estimated = count_tokens([])
        self.assertEqual(tokens, 0)
        self.assertFalse(estimated)

    def test_the_tokenizer_counts(self):
        """The tokenizer of the agent counts the tokens."""
        tokens, estimated = count_tokens(
            [_Message("the chat history holds the messages of the session")]
        )
        self.assertGreater(tokens, 0)
        self.assertFalse(estimated)

    def test_an_unavailable_tokenizer_is_estimated(self):
        """Without a tokenizer the tokens are estimated, and it is said."""
        with patch(
            "components.tokens.load_tokenizer",
            side_effect=ImportError("no tokenizer here"),
        ):
            tokens, estimated = count_tokens([_Message("x" * 400)])

        self.assertGreater(tokens, 0)
        self.assertTrue(estimated)


class TestCountMessagesWithinLimit(unittest.TestCase):
    """The count of the messages that survive the chat-token limit.

    The count is the answer of the memory buffer of LlamaIndex — the
    number of the messages the agent holds — and it has to be that
    answer without the quadratic work of the buffer.
    """

    def _library_count(self, messages, token_limit) -> int:
        """The answer of the memory buffer of LlamaIndex."""
        from llama_index.core.memory import ChatMemoryBuffer
        from llama_index.core.storage.chat_store.simple_chat_store import (
            SimpleChatStore,
        )

        store = SimpleChatStore()
        store.set_messages("key", list(messages))
        buffer = ChatMemoryBuffer.from_defaults(
            token_limit=token_limit,
            chat_store=store,
            chat_store_key="key",
        )
        return len(buffer.get())

    def _messages(self, count: int, size: int = 100, role: str = "user"):
        """A history of *count* messages."""
        return [_Message("x" * size + str(index), role) for index in range(count)]

    def test_no_messages(self):
        """An empty history holds no messages."""
        self.assertEqual(count_messages_within_limit([], 1000), 0)

    def test_a_history_that_fits_is_counted_whole(self):
        messages = self._messages(10)
        self.assertEqual(count_messages_within_limit(messages, 10000), 10)

    def test_the_tail_that_fits_is_counted(self):
        """Only the messages that survive the limit are counted."""
        messages = self._messages(200, size=500)
        count = count_messages_within_limit(messages, 1000)
        self.assertGreater(count, 0)
        self.assertLess(count, len(messages))

    def test_the_answer_is_the_answer_of_the_buffer(self):
        """The count and the buffer have to agree."""
        for messages, limit in (
            (self._messages(3, 10), 10000),
            (self._messages(50, 100), 10000),
            (self._messages(200, 500), 10000),
            (self._messages(200, 500), 1000),
            (self._messages(200, 500), 100),
            (self._messages(10, 5000), 10000),
            (self._messages(30, 100), 500),
            (self._messages(100, 20, role="assistant"), 1000),
            (self._messages(100, 20, role="tool"), 1000),
        ):
            self.assertEqual(
                count_messages_within_limit(messages, limit),
                self._library_count(messages, limit),
                f"the count differs for {len(messages)} messages "
                f"and a limit of {limit}",
            )

    def test_a_message_that_is_longer_than_the_limit_is_kept(self):
        """A message that is too long is kept on its own."""
        messages = [_Message("x" * 100000)]
        self.assertEqual(count_messages_within_limit(messages, 10), 1)

    def test_the_count_is_one_pass_over_the_tail(self):
        """The count must not walk the whole history again and again.

        The buffer of LlamaIndex counts the tokens of the whole window
        on every step of its trimming loop, and the work is quadratic:
        a history of a few thousand messages takes a minute.  The count
        here walks the tail once, and the tokenizer is asked for the
        tail only.
        """
        messages = self._messages(2000, size=200)
        asked = []

        def _tokenizer(text: str):
            asked.append(text)
            return list(range(len(text) // 4))

        count = count_messages_within_limit(messages, 400, tokenizer=_tokenizer)

        self.assertGreater(count, 0)
        # The tokenizer was asked for a handful of texts, not for the
        # whole history once per message.
        self.assertLess(len(asked), 100)


class TestMeasure(unittest.TestCase):
    """Tests for the measurement of a history."""

    def test_the_history_is_measured(self):
        """The messages, the bytes and the tokens are counted."""
        stored = [_Message("first message"), _Message("second message")]
        buffered = [stored[-1]]

        stats = measure(stored, buffered, token_limit=5000)

        self.assertIsInstance(stats, HistoryStats)
        self.assertEqual(stats.message_count, 2)
        self.assertEqual(stats.total_bytes, len("first message") + len("second message"))
        self.assertGreater(stats.stored_tokens, 0)
        self.assertLessEqual(stats.buffer_tokens, stats.stored_tokens)
        self.assertEqual(stats.token_limit, 5000)
        self.assertFalse(stats.estimated)

    def test_an_empty_history_measures_as_empty(self):
        """A history without messages measures as empty."""
        stats = measure([], [], token_limit=5000)

        self.assertEqual(stats.message_count, 0)
        self.assertEqual(stats.total_bytes, 0)
        self.assertEqual(stats.stored_tokens, 0)
        self.assertEqual(stats.buffer_tokens, 0)


class TestFormatTokens(unittest.TestCase):
    """Tests for the rendering of the token counts."""

    def test_the_counts_and_the_limit_are_shown(self):
        """The stored tokens, the buffered tokens and the limit are shown."""
        stats = HistoryStats(
            message_count=10,
            total_bytes=2048,
            stored_tokens=5020,
            buffer_tokens=251,
            token_limit=256,
        )

        text = format_tokens(stats)

        self.assertIn("5,020", text)
        self.assertIn("251", text)
        self.assertIn("256", text)
        self.assertIn("stored", text)
        self.assertIn("buffer", text)

    def test_an_estimate_says_so(self):
        """An estimated count is marked as one."""
        stats = HistoryStats(stored_tokens=100, buffer_tokens=100, token_limit=5000, estimated=True)

        self.assertIn("estimated", format_tokens(stats))


if __name__ == "__main__":
    unittest.main()
