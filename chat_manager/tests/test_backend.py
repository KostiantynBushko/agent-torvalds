"""Tests for the chat store backends.

Verifies that the backends satisfy the LlamaIndex ``BaseChatStore`` contract
and that the PostgreSQL backend correctly reports connection failures so the
manager can fall back to the in-memory backend.
"""

import unittest

from llama_index.core.base.llms.types import ChatMessage
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.storage.chat_store.base import BaseChatStore

from chat_manager.backend.base import BackendConfig, ChatStoreBackend
from chat_manager.backend.postgres import PostgresChatStoreBackend
from chat_manager.backend.simple import SimpleChatStoreBackend


class TestBackendContract(unittest.TestCase):
    """Tests that both backends honour the BaseChatStore contract."""

    def _make_backend(self):
        backend = SimpleChatStoreBackend()
        backend.connect(BackendConfig(connection_string=""))
        return backend

    def test_backends_are_base_chat_stores(self):
        """Backends are usable wherever LlamaIndex expects a chat store."""
        for cls in (SimpleChatStoreBackend, PostgresChatStoreBackend):
            self.assertTrue(issubclass(cls, BaseChatStore), f"{cls.__name__}")

    def test_set_and_get_messages(self):
        """set_messages / get_messages round-trip."""
        backend = self._make_backend()
        messages = [ChatMessage(role="user", content="one")]
        backend.set_messages("key-1", messages)
        self.assertEqual(len(backend.get_messages("key-1")), 1)
        self.assertEqual(backend.get_messages("key-1")[0].content, "one")

    def test_add_message_appends(self):
        """add_message appends to the existing history."""
        backend = self._make_backend()
        backend.add_message("key-1", ChatMessage(role="user", content="one"))
        backend.add_message("key-1", ChatMessage(role="assistant", content="two"))
        self.assertEqual(len(backend.get_messages("key-1")), 2)

    def test_delete_message_by_index(self):
        """delete_message removes the message at the given index."""
        backend = self._make_backend()
        backend.set_messages(
            "key-1",
            [
                ChatMessage(role="user", content="one"),
                ChatMessage(role="assistant", content="two"),
            ],
        )
        removed = backend.delete_message("key-1", 0)
        self.assertIsNotNone(removed)
        self.assertEqual(removed.content, "one")
        self.assertEqual(len(backend.get_messages("key-1")), 1)

    def test_delete_message_out_of_range(self):
        """Deleting an out-of-range index returns None."""
        backend = self._make_backend()
        backend.set_messages("key-1", [ChatMessage(role="user", content="one")])
        self.assertIsNone(backend.delete_message("key-1", 99))

    def test_delete_last_message(self):
        """delete_last_message removes the most recent message."""
        backend = self._make_backend()
        backend.set_messages(
            "key-1",
            [
                ChatMessage(role="user", content="one"),
                ChatMessage(role="assistant", content="two"),
            ],
        )
        removed = backend.delete_last_message("key-1")
        self.assertEqual(removed.content, "two")
        self.assertEqual(len(backend.get_messages("key-1")), 1)

    def test_delete_last_message_on_empty_history(self):
        """Deleting the last message of an empty history returns None."""
        backend = self._make_backend()
        self.assertIsNone(backend.delete_last_message("key-1"))

    def test_get_keys_lists_stored_keys(self):
        """get_keys reports every key that holds messages."""
        backend = self._make_backend()
        backend.set_messages("key-a", [ChatMessage(role="user", content="a")])
        backend.set_messages("key-b", [ChatMessage(role="user", content="b")])
        self.assertEqual(sorted(backend.list_keys()), ["key-a", "key-b"])

    def test_delete_messages_clears_key(self):
        """delete_messages removes every message under a key."""
        backend = self._make_backend()
        backend.set_messages("key-1", [ChatMessage(role="user", content="one")])
        backend.delete_messages("key-1")
        self.assertEqual(len(backend.get_messages("key-1")), 0)

    def test_usable_as_chat_memory_buffer_store(self):
        """The backend can be handed to ChatMemoryBuffer.from_defaults."""
        backend = self._make_backend()
        buffer = ChatMemoryBuffer.from_defaults(
            token_limit=100,
            chat_store=backend,
            chat_store_key="session-key",
        )
        buffer.put(ChatMessage(role="user", content="hello"))
        self.assertEqual(len(buffer.get()), 1)
        self.assertEqual(buffer.chat_store_key, "session-key")

    def test_messages_persist_per_key(self):
        """Different keys keep separate histories."""
        backend = self._make_backend()
        buffer_a = ChatMemoryBuffer.from_defaults(
            token_limit=100, chat_store=backend, chat_store_key="a"
        )
        buffer_b = ChatMemoryBuffer.from_defaults(
            token_limit=100, chat_store=backend, chat_store_key="b"
        )
        buffer_a.put(ChatMessage(role="user", content="only in a"))
        buffer_b.put(ChatMessage(role="user", content="only in b"))

        self.assertEqual(len(buffer_a.get()), 1)
        self.assertEqual(len(buffer_b.get()), 1)
        self.assertEqual(buffer_a.get()[0].content, "only in a")
        self.assertEqual(buffer_b.get()[0].content, "only in b")


class TestBackendErrors(unittest.TestCase):
    """Tests for backend error handling."""

    def test_postgres_connect_raises_on_failure(self):
        """connect() propagates the failure so callers can fall back."""
        backend = PostgresChatStoreBackend()
        with self.assertRaises(Exception):
            backend.connect(
                BackendConfig(
                    connection_string="postgresql://bad:bad@127.0.0.1:1/nonexistent"
                )
            )

    def test_operations_require_connection(self):
        """Using a backend before connect() raises RuntimeError."""
        backend = SimpleChatStoreBackend()
        with self.assertRaises(RuntimeError):
            backend.get_messages("key")

    def test_close_is_safe(self):
        """close() may be called even when never connected."""
        backend = SimpleChatStoreBackend()
        backend.close()
        backend.close()


if __name__ == "__main__":
    unittest.main()
