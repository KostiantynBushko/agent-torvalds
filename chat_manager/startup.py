"""Startup integration for ChatHistoryManager.

Handles initialization and shutdown hooks for the ChatHistoryManager,
providing a clean integration point with the agent's lifecycle.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from chat_manager.manager import ChatHistoryManager


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_chat_manager: ChatHistoryManager | None = None


def initialize_chat_manager(
    storage_uri: str | None = None,
    llama_uri: str | None = None,
) -> ChatHistoryManager:
    """Initialize the global ChatHistoryManager singleton.

    Called during agent startup to set up user identification, session
    management, and message storage backends.

    Args:
        storage_uri: Custom DB connection URI (defaults to TORVALDS_STORAGE_URI).
        llama_uri: LlamaIndex message storage URI (defaults to TORVALDS_LLAMA_URI).

    Returns:
        The initialized ChatHistoryManager instance.
    """
    global _chat_manager

    if _chat_manager is not None:
        logger.info("ChatHistoryManager already initialized, returning existing instance")
        return _chat_manager

    from chat_manager.manager import ChatHistoryManager

    _chat_manager = ChatHistoryManager(
        storage_uri=storage_uri,
        llama_uri=llama_uri,
    )
    _chat_manager.initialize()

    logger.info(
        f"ChatHistoryManager initialized: user={_chat_manager.current_user.username}, "
        f"session={_chat_manager.get_active_session().session_name if _chat_manager.get_active_session() else 'none'}"
    )

    return _chat_manager


def get_chat_manager() -> ChatHistoryManager | None:
    """Get the global ChatHistoryManager singleton.

    Returns:
        The ChatHistoryManager instance or None if not initialized.
    """
    return _chat_manager


def shutdown_chat_manager() -> None:
    """Shut down the global ChatHistoryManager.

    Called during agent shutdown to clean up connections.
    """
    global _chat_manager

    if _chat_manager is not None:
        _chat_manager.shutdown()
        _chat_manager = None
        logger.info("ChatHistoryManager shut down")


def is_chat_manager_initialized() -> bool:
    """Check if ChatHistoryManager is initialized.

    Returns:
        True if initialized, False otherwise.
    """
    return _chat_manager is not None and _chat_manager.is_initialized
