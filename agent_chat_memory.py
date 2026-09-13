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
"""
import os
from llama_index.storage.chat_store.postgres import PostgresChatStore
from llama_index.core.memory import ChatMemoryBuffer


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _build_pg_uri() -> str:
    """
    Build PostgreSQL connection URI from environment variables.

    Falls back to hardcoded defaults if env vars are not set.
    """
    host = os.environ.get("TORVALDS_PG_HOST", "127.0.0.1")
    port = os.environ.get("TORVALDS_PG_PORT", "5432")
    user = os.environ.get("TORVALDS_PG_USER", "postgres")
    password = os.environ.get("TORVALDS_PG_PASSWORD", "postgres")
    database = os.environ.get("TORVALDS_PG_DATABASE", "llama_index_db")

    return f"postgres+asyncpg://{user}:{password}@{host}:{port}/{database}"


def _get_chat_store_key() -> str:
    """Get the unique chat store key from env or default."""
    return os.environ.get("TORVALDS_CHAT_KEY", "user1-abliterated")


def _get_token_limit() -> int:
    """Get the token limit from env or default."""
    try:
        return int(os.environ.get("TORVALDS_TOKEN_LIMIT", "3000"))
    except ValueError:
        return 3000


# ---------------------------------------------------------------------------
# Chat store & memory initialization
# ---------------------------------------------------------------------------

_chat_store = None
_chat_memory = None


def get_chat_store() -> PostgresChatStore:
    """
    Get (and lazily create) the PostgreSQL chat store singleton.

    Returns:
        PostgresChatStore instance
    """
    global _chat_store
    if _chat_store is None:
        try:
            _chat_store = PostgresChatStore.from_uri(
                uri=_build_pg_uri(),
            )
        except Exception as e:
            print(f"Warning: Could not connect to PostgreSQL chat store: {e}")
            print("Falling back to in-memory chat store.")
            _chat_store = None
    return _chat_store


def get_chat_memory(
    chat_store_key: str = None,
    token_limit: int = None,
) -> ChatMemoryBuffer:
    """
    Get (and lazily create) the chat memory buffer singleton.

    If PostgreSQL is available, memory is backed by the DB.
    Otherwise, falls back to an in-memory buffer.

    Args:
        chat_store_key: Unique key for this conversation (default: from env)
        token_limit: Token limit for the buffer (default: from env)

    Returns:
        ChatMemoryBuffer instance
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
        else:
            # Fallback: in-memory only
            _chat_memory = ChatMemoryBuffer.from_defaults(
                token_limit=limit,
            )

    return _chat_memory


# ---------------------------------------------------------------------------
# Convenience: expose chat_memory as a module-level attribute for backward compat
# ---------------------------------------------------------------------------

def _init():
    """Initialize chat memory on first access."""
    return get_chat_memory()

# Lazy property-like access
class _ChatMemoryProxy:
    def __getattr__(self, name):
        return getattr(get_chat_memory(), name)

    def __repr__(self):
        return repr(get_chat_memory())

chat_memory = _ChatMemoryProxy()
