"""PostgreSQL backend for chat message storage via LlamaIndex."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from chat_manager.backend.base import BackendConfig, ChatStoreBackend

if TYPE_CHECKING:
    from llama_index.storage.chat_store.postgres import PostgresChatStore

logger = logging.getLogger(__name__)


class PostgresChatStoreBackend(ChatStoreBackend):
    """PostgreSQL-backed chat store wrapping LlamaIndex PostgresChatStore.

    Uses a separate LlamaIndex connector for message storage, isolated from
    the custom DB connector that manages users and sessions.
    """

    def __init__(self) -> None:
        self._store: PostgresChatStore | None = None
        self._config: BackendConfig | None = None

    def connect(self, config: BackendConfig) -> None:
        """Establish connection to PostgreSQL message storage.

        Args:
            config: Backend configuration with connection URI.
        """
        self._config = config
        try:
            from llama_index.storage.chat_store.postgres import PostgresChatStore

            self._store = PostgresChatStore.from_uri(uri=config.connection_string)
            logger.info("Connected to PostgreSQL chat store backend")
        except Exception as e:
            logger.warning(f"Failed to connect to PostgreSQL chat store: {e}")
            self._store = None

    def _ensure_connected(self) -> None:
        """Raise if not connected."""
        if self._store is None:
            raise RuntimeError("PostgresChatStoreBackend is not connected")

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
        if self._store is not None:
            self._store = None
            logger.info("PostgreSQL chat store backend closed")
