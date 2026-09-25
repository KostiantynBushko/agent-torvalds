"""
Chat Memory Module - Persistent chat memory backed by PostgreSQL.

This module provides a PostgreSQL-backed chat memory buffer for the Torvalds agent.
Connection parameters can be configured via environment variables or a config file.

Environment Variables:
    TORVALDS_PG_HOST        - PostgreSQL host (default: 127.0.0.1)
    TORVALDS_PG_PORT        - PostgreSQL port (default: 5432)
    TORVALDS_PG_USER        - PostgreSQL user (default: postgres)
    TORVALDS_PG_PASSWORD    - PostgreSQL password
    TORVALDS_PG_DATABASE    - PostgreSQL database name (default: llama_index_db)
    TORVALDS_CHAT_KEY       - Unique chat store key (default: user1-abliterated)
    TORVALDS_TOKEN_LIMIT    - Token limit for memory buffer (default: 3000)

Category: Infrastructure / Chat Memory
Retriever Keywords: chat, memory, conversation, history, buffer, postgres, persistent
"""
import os
import logging
from llama_index.storage.chat_store.postgres import PostgresChatStore
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.tools import FunctionTool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _build_pg_uri() -> str:
    """
    Build PostgreSQL connection URI from environment variables.
    
    Falls back to hardcoded defaults if environment variables are not set.
    
    Returns:
        str: PostgreSQL connection URI string
        
    Example:
        >>> _build_pg_uri()
        'postgres+asyncpg://postgres:postgres@127.0.0.1:5432/llama_index_db'
        
    Keywords: postgresql, uri, connection, database, config
    """
    host = os.environ.get("TORVALDS_PG_HOST", "127.0.0.1")
    port = os.environ.get("TORVALDS_PG_PORT", "5432")
    user = os.environ.get("TORVALDS_PG_USER", "postgres")
    password = os.environ.get("TORVALDS_PG_PASSWORD", "postgres1")
    database = os.environ.get("TORVALDS_PG_DATABASE", "llama_index_db")

    uri = f"postgres+asyncpg://{user}:{password}@{host}:{port}/{database}"
    logger.debug(f"Built PostgreSQL URI: {host}:{port}/{database}")
    return uri


def _get_chat_store_key() -> str:
    """
    Get the unique chat store key from environment or default.
    
    Returns:
        str: Chat store key identifier
        
    Example:
        >>> _get_chat_store_key()
        'user1-abliterated'
        
    Keywords: chat key, identifier, session, user
    """
    key = os.environ.get("TORVALDS_CHAT_KEY", "user1-abliterated")
    logger.debug(f"Using chat store key: {key}")
    return key


def _get_token_limit() -> int:
    """
    Get the token limit from environment or default.
    
    Returns:
        int: Token limit for the memory buffer (default: 5000)
        
    Example:
        >>> _get_token_limit()
        5000
        
    Keywords: token limit, buffer size, memory limit
    """
    try:
        limit = int(os.environ.get("TORVALDS_TOKEN_LIMIT", "5000"))
    except ValueError:
        limit = 5000
    logger.debug(f"Using token limit: {limit}")
    return limit


# ---------------------------------------------------------------------------
# Chat store & memory initialization
# ---------------------------------------------------------------------------

_chat_store = None
_chat_memory = None


def get_chat_store() -> PostgresChatStore:
    """
    Get (and lazily create) the PostgreSQL chat store singleton.
    
    Use this tool to access the shared PostgreSQL chat store instance.
    If PostgreSQL is unavailable, falls back to None (in-memory mode).
    
    Returns:
        PostgresChatStore: The chat store instance, or None if unavailable
        
    Example:
        >>> store = get_chat_store()
        >>> store is not None
        True
        
    Keywords: chat store, postgresql, database, connection, singleton
    """
    global _chat_store
    if _chat_store is None:
        try:
            _chat_store = PostgresChatStore.from_uri(
                uri=_build_pg_uri(),
            )
            logger.info("Successfully connected to PostgreSQL chat store.")
        except Exception as e:
            logger.warning(f"Could not connect to PostgreSQL chat store: {e}")
            logger.info("Falling back to in-memory chat store.")
            _chat_store = None
    return _chat_store


def get_chat_memory(
    chat_store_key: str = None,
    token_limit: int = None,
) -> ChatMemoryBuffer:
    """
    Get (and lazily create) the chat memory buffer singleton.
    
    Use this tool to access the shared chat memory buffer. If PostgreSQL is available,
    memory is backed by the database. Otherwise, falls back to an in-memory buffer.
    
    Args:
        chat_store_key (str, optional): Unique key for this conversation (default: from env)
        token_limit (int, optional): Token limit for the buffer (default: from env)
        
    Returns:
        ChatMemoryBuffer: The chat memory buffer instance
        
    Example:
        >>> memory = get_chat_memory()
        >>> memory.put("Hello", "assistant")
        
    Keywords: chat memory, buffer, conversation, history, persistent memory
    """
    global _chat_memory
    if _chat_memory is None:
        key = chat_store_key or _get_chat_store_key()
        limit = token_limit or _get_token_limit()

        chat_store = get_chat_store()
        if chat_store is not None:
            _chat_memory = ChatMemoryBuffer.from_defaults(
                token_limit=limit,
                chat_store=chat_store,
                chat_store_key=key,
            )
            logger.info(f"Initialized PostgreSQL-backed chat memory (key={key}, limit={limit})")
        else:
            # Fallback: in-memory only
            _chat_memory = ChatMemoryBuffer.from_defaults(
                token_limit=limit,
            )
            logger.info(f"Initialized in-memory chat memory (limit={limit})")

    return _chat_memory


# ---------------------------------------------------------------------------
# Convenience: expose chat_memory as a module-level attribute for backward compat
# ---------------------------------------------------------------------------

def _init():
    """
    Initialize chat memory on first access.
    
    Returns:
        ChatMemoryBuffer: The initialized chat memory buffer
        
    Keywords: init, initialize, setup, start
    """
    logger.info("Initializing chat memory via _init()")
    return get_chat_memory()


class _ChatMemoryProxy:
    """
    Proxy object that lazily forwards attribute access to the chat memory singleton.
    
    This allows backward-compatible access to chat memory as a module-level attribute.
    """
    def __getattr__(self, name):
        return getattr(get_chat_memory(), name)

    def __repr__(self):
        return repr(get_chat_memory())


chat_memory = _ChatMemoryProxy()


# ---------------------------------------------------------------------------
# Tool exports
# ---------------------------------------------------------------------------

def get_all_tools() -> list[FunctionTool]:
    """
    Return all Chat Memory tools as FunctionTool objects for on-demand loading.
    
    Each tool includes category metadata for better retrieval.
    
    Returns:
        list[FunctionTool]: List of Chat Memory FunctionTool objects
        
    Keywords: tools, functions, export, register
    """
    logger.info("get_all_tools called for chat memory module")
    return [
        FunctionTool.from_defaults(
            fn=get_chat_store,
            description="Get the PostgreSQL chat store singleton. Use for accessing the shared chat store. Category: Infrastructure",
        ),
        FunctionTool.from_defaults(
            fn=get_chat_memory,
            description="Get the chat memory buffer singleton. Use for accessing persistent conversation memory. Category: Infrastructure",
        ),
    ]