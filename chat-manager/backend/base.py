"""Abstract base class for chat store backends.

Defines the interface that all backend implementations must follow for
storing and retrieving chat messages via LlamaIndex.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


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


class ChatStoreBackend(ABC):
    """Abstract interface for SQL-based chat message storage.

    This backend wraps LlamaIndex's ChatStore functionality, providing
    a unified interface for message operations regardless of the
    underlying database engine.
    """

    @abstractmethod
    def connect(self, config: BackendConfig) -> None:
        """Establish connection to the message storage backend.

        Args:
            config: Backend configuration with connection details.
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
