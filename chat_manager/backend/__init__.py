"""Backend interface exports for ChatHistoryManager."""

from chat_manager.backend.base import ChatStoreBackend, BackendConfig
from chat_manager.backend.postgres import PostgresChatStoreBackend
from chat_manager.backend.simple import SimpleChatStoreBackend

__all__ = [
    "ChatStoreBackend",
    "BackendConfig",
    "PostgresChatStoreBackend",
    "SimpleChatStoreBackend",
]
