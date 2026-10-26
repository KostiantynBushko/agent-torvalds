"""Startup integration for ChatHistoryManager.

Handles initialization and shutdown hooks for the ChatHistoryManager,
providing a clean integration point with the agent's lifecycle, plus the
interactive session selection flow required at startup.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

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


# ---------------------------------------------------------------------------
# Memory buffer
# ---------------------------------------------------------------------------

# The in-memory buffer is cached process-wide, exactly as the legacy
# ``agent_chat_memory`` module cached its own.  Every caller has to see the
# same conversation, so a fresh buffer per call would silently split the
# history in half.
_in_memory_buffer: Any = None
_in_memory_buffer_limit: int | None = None


def _default_token_limit() -> int:
    """Resolve the token limit for the in-memory buffer.

    The manager resolves the limit from the user's own setting.  The
    in-memory buffer has no user and no setting behind it, so it falls back
    to the environment variable and then to the package default.

    Returns:
        int: The effective chat-token limit.
    """
    from chat_manager.settings import DEFAULT_CHAT_TOKEN_LIMIT

    raw = os.environ.get("TORVALDS_TOKEN_LIMIT")
    if raw is None or raw == "":
        return DEFAULT_CHAT_TOKEN_LIMIT
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            f"TORVALDS_TOKEN_LIMIT={raw!r} is not an integer - "
            f"using the default of {DEFAULT_CHAT_TOKEN_LIMIT}."
        )
        return DEFAULT_CHAT_TOKEN_LIMIT


def get_in_memory_buffer(chat_token_limit: int | None = None) -> Any:
    """Get a process-wide chat memory buffer that persists nothing.

    This is the buffer used when the ChatHistoryManager is switched off
    (``--no-chat-history``): the conversation still works, it just does not
    outlive the process.

    Args:
        chat_token_limit: Explicit token limit, or None to use
            ``TORVALDS_TOKEN_LIMIT`` (or the package default).

    Returns:
        ChatMemoryBuffer instance with no chat store attached.
    """
    global _in_memory_buffer, _in_memory_buffer_limit

    limit = chat_token_limit if chat_token_limit is not None else _default_token_limit()

    if _in_memory_buffer is not None and _in_memory_buffer_limit == limit:
        return _in_memory_buffer

    from llama_index.core.memory import ChatMemoryBuffer

    _in_memory_buffer = ChatMemoryBuffer.from_defaults(token_limit=limit)
    _in_memory_buffer_limit = limit
    logger.info(f"Initialized in-memory chat memory (limit={limit})")

    return _in_memory_buffer


def get_memory_buffer(chat_token_limit: int | None = None) -> Any:
    """Get the chat memory buffer for the active session.

    Returns the manager's buffer, which is bound to the active session's
    chat key, when the manager is up.  When it is not - the manager was
    never started, or it could not provide a buffer - an in-memory buffer
    is returned instead, so the agent always has a usable memory.

    This replaces the legacy ``agent_chat_memory.get_chat_memory()``: the
    manager is the source of truth, and the in-memory buffer is the last
    resort rather than a parallel implementation.

    Args:
        chat_token_limit: Explicit token limit, or None to use the user's
            own setting (or the package default).

    Returns:
        ChatMemoryBuffer instance.
    """
    manager = get_chat_manager()

    if manager is not None and manager.is_initialized:
        try:
            return manager.get_memory_buffer(chat_token_limit)
        except Exception as e:
            logger.warning(f"ChatHistoryManager could not provide a memory buffer: {e}")

    return get_in_memory_buffer(chat_token_limit)


# ---------------------------------------------------------------------------
# Interactive startup session selection
# ---------------------------------------------------------------------------

def select_startup_session(
    input_func=None,
    output_func=None,
) -> None:
    """Run the interactive startup session selection.

    Presents the current user's sessions and lets them pick one, create a new
    one, or keep the currently active session. The choice is persisted to the
    database as the user's active session.

    Args:
        input_func: Optional callable used to read user input (defaults to
            the built-in ``input``).
        output_func: Optional callable used to write prompts (defaults to
            the built-in ``print``).
    """
    from chat_manager.session_selector import select_session_interactively

    manager = get_chat_manager()
    if manager is None:
        if output_func:
            output_func("ChatHistoryManager not initialized.")
        return

    select_session_interactively(
        manager,
        input_func=input_func or input,
        output_func=output_func or print,
    )
