"""Tests for the memory buffer of the project.

The buffer of LlamaIndex trims the history of the session with a loop
that counts the tokens of the whole window again on every step, and the
work is quadratic: a history of a few thousand messages takes a minute
to trim, and the agent pays it on every turn.

The buffer of the project answers the same question in one pass.  The
tests here prove two things:

* the answer is **the answer of the library** — the same messages, in
  the same order, for a dozen histories and for random ones;
* the work is **one pass** — the tokenizer is asked for the tail only,
  and not for the whole history once per message.

Run with:
    pytest chat_manager/tests/test_memory.py -v
"""
import random
import string
import unittest

from llama_index.core.base.llms.types import ChatMessage, MessageRole
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.storage.chat_store.simple_chat_store import SimpleChatStore

from chat_manager.memory import TrimmingChatMemoryBuffer


def _messages(count: int, size: int = 100, role=MessageRole.USER) -> list:
    """Build a history of *count* messages."""
    return [
        ChatMessage(role=role, content="x" * size + str(index))
        for index in range(count)
    ]


def _library(messages, token_limit: int, initial_token_count: int = 0) -> list:
    """The answer of the memory buffer of LlamaIndex."""
    store = SimpleChatStore()
    store.set_messages("key", list(messages))
    buffer = ChatMemoryBuffer.from_defaults(
        token_limit=token_limit,
        chat_store=store,
        chat_store_key="key",
    )
    return buffer.get(initial_token_count=initial_token_count)


def _project(messages, token_limit: int, initial_token_count: int = 0) -> list:
    """The answer of the memory buffer of the project."""
    store = SimpleChatStore()
    store.set_messages("key", list(messages))
    buffer = TrimmingChatMemoryBuffer.from_defaults(
        token_limit=token_limit,
        chat_store=store,
        chat_store_key="key",
    )
    return buffer.get(initial_token_count=initial_token_count)


def _content(messages) -> list:
    """The messages as plain pairs, so they can be compared."""
    return [(message.role, message.content) for message in messages]


class TestTheAnswerIsTheAnswerOfTheLibrary(unittest.TestCase):
    """The two buffers have to agree, message by message."""

    def test_they_agree_on_a_dozen_histories(self):
        """The same messages, in the same order, for every shape."""
        cases = (
            (1, 10, 10000),
            (3, 10, 10000),
            (50, 100, 10000),
            (200, 500, 10000),
            (200, 500, 1000),
            (200, 500, 100),
            (10, 5000, 10000),
            (30, 100, 500),
            (100, 20, 1),
            (1, 100000, 10),
        )

        for count, size, limit in cases:
            messages = _messages(count, size)
            self.assertEqual(
                _content(_library(messages, limit)),
                _content(_project(messages, limit)),
                f"the buffers differ for {count} messages "
                f"and a limit of {limit}",
            )

    def test_they_agree_on_the_roles(self):
        """A history may not open with an assistant or a tool message."""
        roles = (
            MessageRole.USER,
            MessageRole.ASSISTANT,
            MessageRole.TOOL,
        )

        for count in (5, 40, 120):
            for limit in (50, 500, 5000):
                messages = [
                    ChatMessage(role=roles[index % 3], content="x" * 80 + str(index))
                    for index in range(count)
                ]
                self.assertEqual(
                    _content(_library(messages, limit)),
                    _content(_project(messages, limit)),
                    f"the buffers differ for {count} messages, "
                    f"a limit of {limit} and the roles {roles}",
                )

    def test_they_agree_on_random_histories(self):
        """Random text, random roles, random limits."""
        rnd = random.Random(7)
        words = [
            "".join(rnd.choices(string.ascii_lowercase, k=rnd.randint(1, 12)))
            for _ in range(500)
        ]
        roles = (MessageRole.USER, MessageRole.ASSISTANT, MessageRole.TOOL)

        for _ in range(120):
            count = rnd.choice([1, 2, 3, 7, 13, 40, 120])
            messages = [
                ChatMessage(
                    role=rnd.choice(roles),
                    content=" ".join(rnd.choices(words, k=rnd.randint(0, 60))),
                )
                for _ in range(count)
            ]
            limit = rnd.choice([20, 200, 2000, 20000])

            self.assertEqual(
                _content(_library(messages, limit)),
                _content(_project(messages, limit)),
                "the buffers differ",
            )

    def test_they_agree_when_the_caller_adds_tokens(self):
        """The tokens of the caller count towards the limit."""
        messages = _messages(40, 200)

        for initial in (0, 10, 500):
            self.assertEqual(
                _content(_library(messages, 1000, initial)),
                _content(_project(messages, 1000, initial)),
                f"the buffers differ with {initial} tokens of the caller",
            )

    def test_they_agree_on_an_empty_history(self):
        """An empty history holds nothing."""
        self.assertEqual(_library([], 1000), _project([], 1000))

    def test_the_token_limit_of_the_caller_is_refused(self):
        """More tokens than the limit is an error — in both buffers."""
        with self.assertRaises(ValueError):
            _project(_messages(3, 10), 10, initial_token_count=20)


class TestTheTrimmingIsOnePass(unittest.TestCase):
    """The work has to be one pass over the tail, not a loop over the
    whole history."""

    def test_the_tokenizer_is_asked_for_the_tail_only(self):
        """The whole history is not counted once per message."""
        asked = []

        def _tokenizer(text: str) -> list:
            asked.append(text)
            return list(range(len(text) // 4))

        messages = _messages(2000, size=200)

        store = SimpleChatStore()
        store.set_messages("key", list(messages))
        buffer = TrimmingChatMemoryBuffer.from_defaults(
            token_limit=400,
            chat_store=store,
            chat_store_key="key",
            tokenizer_fn=_tokenizer,
        )
        kept = buffer.get()

        self.assertGreater(len(kept), 0)
        self.assertLess(len(kept), len(messages))
        # A handful of texts, not one per message of the history.
        self.assertLess(len(asked), 100)

    def test_a_history_that_fits_is_returned_whole(self):
        """Nothing is trimmed when everything fits."""
        messages = _messages(10, size=10)

        self.assertEqual(len(_project(messages, 10000)), len(messages))

    def test_a_message_that_is_longer_than_the_limit_is_kept(self):
        """A message too long for the limit is kept on its own."""
        messages = [ChatMessage(role=MessageRole.USER, content="x" * 100000)]

        self.assertEqual(len(_project(messages, 10)), 1)

    def test_a_trimmed_window_may_not_open_with_an_assistant_message(self):
        """The window opens with a message the model can read.

        A tool message without the assistant message that called it is a
        history the model cannot read, so the window is moved past it.
        """
        messages = [
            ChatMessage(role=MessageRole.ASSISTANT, content="x" * 80),
            ChatMessage(role=MessageRole.USER, content="y" * 80),
            ChatMessage(role=MessageRole.USER, content="z" * 80),
        ]

        # A limit that leaves room for the last messages only.
        kept = _project(messages, 25)

        self.assertLess(len(kept), len(messages), "the history was not trimmed")
        self.assertNotIn(kept[0].role, (MessageRole.ASSISTANT, MessageRole.TOOL))
        # The library agrees.
        self.assertEqual(
            _content(_library(messages, 25)),
            _content(kept),
        )

    def test_a_history_that_fits_is_kept_whole(self):
        """The rule of the roles applies to a trimmed history only.

        The library tries the whole history first, and returns it when
        it fits — the rule of the roles comes into play when something
        has to be dropped.
        """
        messages = [
            ChatMessage(role=MessageRole.ASSISTANT, content="x" * 80),
            ChatMessage(role=MessageRole.USER, content="y" * 80),
            ChatMessage(role=MessageRole.USER, content="z" * 80),
        ]

        kept = _project(messages, 10000)

        self.assertEqual(len(kept), len(messages))
        self.assertEqual(kept[0].role, MessageRole.ASSISTANT)


if __name__ == "__main__":
    unittest.main()
