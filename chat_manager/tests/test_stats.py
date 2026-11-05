"""Tests for the measurement of the chat history."""

import unittest
from unittest.mock import patch

from chat_manager.stats import (
    BYTES_PER_KB,
    BYTES_PER_MB,
    HistoryStats,
    count_tokens,
    format_size,
    format_tokens,
    measure,
)


class _Message:
    """A stand-in for a chat message."""

    def __init__(self, content: str) -> None:
        self.content = content


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
