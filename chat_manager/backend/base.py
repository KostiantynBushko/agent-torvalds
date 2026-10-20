"""Abstract base class for chat store backends.

Defines the interface that all backend implementations must follow for
storing and retrieving chat messages via LlamaIndex.

The interface extends LlamaIndex's ``BaseChatStore`` so that instances can be
passed directly to ``ChatMemoryBuffer.from_defaults(chat_store=...)``.
LlamaIndex requires the concrete store to implement seven methods:

    set_messages, get_messages, add_message, delete_messages,
    delete_message, delete_last_message, get_keys

The backend-specific API (``put_messages`` / ``get_messages`` /
``delete_messages`` / ``list_keys``) is mapped onto those methods by this
class, so subclasses only implement the primitives they actually need.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from llama_index.core.base.llms.types import ChatMessage
from llama_index.core.storage.chat_store.base import BaseChatStore


@dataclass
class BackendConfig:
    """Configuration for a chat store backend connection.

    Attributes:
        connection_string: Database connection URI.
        table_name: Table name for LlamaIndex chat storage.
        extra_params: Additional driver-specific parameters.
    """

    connection_string: str = ""
    table_name: str = "chat_messages"
    extra_params: dict = field(default_factory=dict)


class ChatStoreBackend(BaseChatStore, ABC):
    """Abstract interface for chat message storage.

    Wraps LlamaIndex's ChatStore functionality, providing a unified
    interface for message operations regardless of the underlying database
    engine.

    Subclasses implement the backend-agnostic primitives (``put_messages``,
    ``get_messages``, ``delete_messages``, ``list_keys``); the LlamaIndex
    ``BaseChatStore`` contract is implemented here on top of them.
    """

    # ------------------------------------------------------------------
    # Backend-specific primitives
    # ------------------------------------------------------------------

    @abstractmethod
    def connect(self, config: BackendConfig) -> None:
        """Establish connection to the message storage backend.

        Implementations must raise on failure so that callers can detect an
        unavailable backend and fall back to another implementation.

        Args:
            config: Backend configuration with connection details.

        Raises:
            Exception: Propagated from the underlying store on failure.
        """
        ...

    @abstractmethod
    def put_messages(self, chat_key: str, messages: list) -> None:
        """Store messages for a given chat key.

        Args:
            chat_key: Unique identifier for the chat session.
            messages: List of message objects to store.
        """
        ...

    @abstractmethod
    def get_messages(self, chat_key: str) -> list:
        """Retrieve messages for a given chat key.

        Args:
            chat_key: Unique identifier for the chat session.

        Returns:
            List of message objects, empty list if none found.
        """
        ...

    @abstractmethod
    def delete_messages(self, chat_key: str) -> None:
        """Delete all messages for a given chat key.

        Args:
            chat_key: Unique identifier for the chat session.
        """
        ...

    @abstractmethod
    def list_keys(self) -> list[str]:
        """List all available chat keys.

        Returns:
            List of chat key strings.
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """Close the backend connection and release resources."""
        ...

    # ------------------------------------------------------------------
    # LlamaIndex BaseChatStore contract
    # ------------------------------------------------------------------

    def set_messages(self, key: str, messages: list) -> None:
        """Replace all messages stored under ``key``.

        Args:
            key: Chat key to write to.
            messages: Messages to persist.
        """
        self.put_messages(key, messages)

    def get_keys(self) -> list[str]:
        """Return every chat key known to the backend.

        Returns:
            List of chat key strings.
        """
        return self.list_keys()

    def add_message(self, key: str, message: ChatMessage) -> None:
        """Append a single message to the chat history under ``key``.

        Args:
            key: Chat key to append to.
            message: Message to append.
        """
        messages = list(self.get_messages(key))
        messages.append(message)
        self.put_messages(key, messages)

    def delete_message(self, key: str, idx: int) -> ChatMessage | None:
        """Delete the message at ``idx`` from the chat history under ``key``.

        Args:
            key: Chat key to modify.
            idx: Index of the message to remove.

        Returns:
            The removed message, or None if the index was out of range.
        """
        messages = list(self.get_messages(key))
        if not 0 <= idx < len(messages):
            return None
        removed = messages.pop(idx)
        self.put_messages(key, messages)
        return removed

    def delete_last_message(self, key: str) -> ChatMessage | None:
        """Delete the most recent message from the chat history under ``key``.

        Args:
            key: Chat key to modify.

        Returns:
            The removed message, or None if the history was empty.
        """
        messages = list(self.get_messages(key))
        if not messages:
            return None
        removed = messages.pop()
        self.put_messages(key, messages)
        return removed
