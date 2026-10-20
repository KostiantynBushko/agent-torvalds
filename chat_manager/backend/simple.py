"""Simple in-memory backend for chat message storage via LlamaIndex."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from chat_manager.backend.base import BackendConfig, ChatStoreBackend

if TYPE_CHECKING:
    from llama_index.core.storage.chat_store.simple_chat_store import SimpleChatStore

logger = logging.getLogger(__name__)


class SimpleChatStoreBackend(ChatStoreBackend):
    """In-memory chat store wrapping LlamaIndex SimpleChatStore.

    Used as a fallback when PostgreSQL is unavailable or for testing.
    """

    def __init__(self) -> None:
        self._store: SimpleChatStore | None = None
        self._config: BackendConfig | None = None

    def connect(self, config: BackendConfig) -> None:
        """Initialize the in-memory chat store.

        Args:
            config: Backend configuration (ignored for in-memory, but required by interface).
        """
        from llama_index.core.storage.chat_store.simple_chat_store import SimpleChatStore

        self._config = config
        self._store = SimpleChatStore()
        logger.info("Initialized SimpleChatStore (in-memory) backend")

    def _ensure_connected(self) -> None:
        """Raise if not connected."""
        if self._store is None:
            raise RuntimeError("SimpleChatStoreBackend is not connected")

    def put_messages(self, chat_key: str, messages: list) -> None:
        """Store messages for a given chat key.

        Args:
            chat_key: Unique identifier for the chat session.
            messages: List of message objects to store.
        """
        self._ensure_connected()
        self._store.set_messages(chat_key, messages)

    def get_messages(self, chat_key: str) -> list:
        """Retrieve messages for a given chat key.

        Args:
            chat_key: Unique identifier for the chat session.

        Returns:
            List of message objects, empty list if none found.
        """
        self._ensure_connected()
        return self._store.get_messages(chat_key)

    def delete_messages(self, chat_key: str) -> None:
        """Delete all messages for a given chat key.

        Args:
            chat_key: Unique identifier for the chat session.
        """
        self._ensure_connected()
        self._store.delete_messages(chat_key)

    def list_keys(self) -> list[str]:
        """List all available chat keys.

        Returns:
            List of chat key strings.
        """
        self._ensure_connected()
        return self._store.get_keys()

    def close(self) -> None:
        """Close the backend connection and release resources."""
        self._store = None
        logger.info("SimpleChatStore backend closed")
