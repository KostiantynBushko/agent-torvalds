"""Backend interface exports for ChatHistoryManager."""

from chat_manager.backend.base import ChatStoreBackend, BackendConfig

__all__ = [
    "ChatStoreBackend",
    "BackendConfig",
]
