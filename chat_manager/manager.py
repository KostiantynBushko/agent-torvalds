"""ChatHistoryManager — Core orchestrator for multi-user chat session management.

Ties together user identification, session lifecycle, and backend-agnostic
message storage via LlamaIndex integration.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from chat_manager.session import Session, SessionType
from chat_manager.user import User
from chat_manager.storage import CustomDBConnector
from chat_manager.backend import (
    BackendConfig,
    ChatStoreBackend,
    PostgresChatStoreBackend,
    SimpleChatStoreBackend,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from llama_index.core.base.llms.types import ChatMessage


class ChatHistoryManager:
    """Manages chat sessions, users, and message storage backends.

    Responsibilities:
    - User identification and auto-provisioning
    - Session lifecycle (create, switch, delete, list)
    - Backend selection (PostgreSQL or in-memory fallback)
    - Message buffer management via LlamaIndex ChatMemoryBuffer
    """

    def __init__(
        self,
        storage_uri: str | None = None,
        llama_uri: str | None = None,
    ) -> None:
        """Initialize the ChatHistoryManager.

        Args:
            storage_uri: Custom DB connection URI (defaults to TORVALDS_STORAGE_URI).
            llama_uri: LlamaIndex message storage URI (defaults to TORVALDS_LLAMA_URI).
        """
        self._storage_uri = storage_uri or os.environ.get("TORVALDS_STORAGE_URI")
        self._llama_uri = llama_uri or self._resolve_llama_uri()

        # Custom DB connector for user/session metadata
        self._db: CustomDBConnector | None = None

        # LlamaIndex message backend
        self._backend: ChatStoreBackend | None = None

        # Current user
        self._current_user: User | None = None

        # Active session
        self._active_session: Session | None = None

        # LlamaIndex memory buffer (lazy)
        self._memory_buffer: Any | None = None

    # ------------------------------------------------------------------
    # URI Resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_llama_uri() -> str:
        """Resolve LlamaIndex message storage URI."""
        uri = os.environ.get("TORVALDS_LLAMA_URI")
        if uri:
            return uri
        # Default to same PG as storage
        host = os.environ.get("TORVALDS_PG_HOST", "127.0.0.1")
        port = os.environ.get("TORVALDS_PG_PORT", "5432")
        user = os.environ.get("TORVALDS_PG_USER", "postgres")
        password = os.environ.get("TORVALDS_PG_PASSWORD", "postgres")
        database = os.environ.get("TORVALDS_PG_DATABASE", "llama_index_db")
        return f"postgres+asyncpg://{user}:{password}@{host}:{port}/{database}"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Initialize all connectors and identify the current user.

        This is the main entry point called at agent startup.
        """
        # 1. Connect custom DB
        self._db = CustomDBConnector(connection_uri=self._storage_uri)
        self._db.connect()

        # 2. Connect message backend (with fallback)
        self._connect_message_backend()

        # 3. Identify or create current user
        self._identify_user()

        # 4. Ensure user has sessions, restore active session
        self._ensure_user_sessions()

        logger.info(
            f"ChatHistoryManager initialized: user={self._current_user.username}, "
            f"session={self._active_session.session_name if self._active_session else 'none'}"
        )

    def shutdown(self) -> None:
        """Clean up all connections and reset the manager state.

        Safe to call more than once.
        """
        if self._db:
            self._db.close()
        if self._backend:
            self._backend.close()
        self._db = None
        self._backend = None
        self._memory_buffer = None
        self._active_session = None
        self._current_user = None
        logger.info("ChatHistoryManager shut down")

    # ------------------------------------------------------------------
    # Backend Management
    # ------------------------------------------------------------------

    def _connect_message_backend(self) -> None:
        """Connect to message storage backend with fallback."""
        config = BackendConfig(connection_string=self._llama_uri)

        try:
            self._backend = PostgresChatStoreBackend()
            self._backend.connect(config)
            logger.info("Using PostgreSQL message backend")
        except Exception as e:
            logger.warning(f"PostgreSQL backend failed ({e}), falling back to in-memory")
            self._backend = SimpleChatStoreBackend()
            self._backend.connect(config)
            logger.info("Using in-memory message backend (fallback)")

    # ------------------------------------------------------------------
    # User Identification
    # ------------------------------------------------------------------

    def identify_user(self) -> User:
        """Identify the current OS user, provisioning the record if needed.

        Idempotent: if the user has already been identified (for example
        during :meth:`initialize`), the existing user is returned without
        re-running identification. Otherwise the OS user is looked up and
        provisioned on demand.

        Returns:
            The User associated with the current OS login.
        """
        if self._current_user is not None:
            return self._current_user

        self._identify_user()
        if self._current_user is None:
            raise RuntimeError("User identification failed")
        return self._current_user

    def _identify_user(self) -> None:
        """Identify current user from OS or create new user."""
        if self._db is None:
            raise RuntimeError("Database not connected")

        os_username = self._get_os_username()
        user = self._db.get_user_by_username(os_username)

        if user is None:
            # Auto-provision
            user = User(
                user_id=str(uuid.uuid4()),
                username=os_username,
                backend_type="postgres",
                token_limit=5000,
            )
            user = self._db.create_user(user)
            logger.info(f"Auto-provisioned new user: {os_username}")

        self._current_user = user

    @staticmethod
    def _get_os_username() -> str:
        """Get OS username for user identification."""
        try:
            return os.getlogin()
        except OSError:
            try:
                import getpass
                return getpass.getuser()
            except Exception:
                return "default_user"

    # ------------------------------------------------------------------
    # Session Lifecycle
    # ------------------------------------------------------------------

    def _ensure_user_sessions(self) -> None:
        """Ensure current user has default sessions and restore active one."""
        if self._db is None or self._current_user is None:
            return

        sessions = self._db.list_sessions(self._current_user.user_id)

        if not sessions:
            # Pre-seed default sessions
            self._create_default_sessions()

        # Restore active session
        active = self._db.get_active_session(self._current_user.user_id)
        if active:
            self._active_session = active
            logger.info(f"Restored active session: {active.session_name}")
        else:
            # Activate general session as fallback
            sessions = self._db.list_sessions(self._current_user.user_id)
            general = next((s for s in sessions if s.session_type == "general"), None)
            if general:
                self._active_session = self._db.activate_session(
                    general.session_id, self._current_user.user_id
                )
                logger.info(f"Activated default general session: {general.session_name}")

    def _create_default_sessions(self) -> None:
        """Create default General and Project sessions for the current user."""
        if self._db is None or self._current_user is None:
            return

        uid = self._current_user.user_id

        # Check for legacy TORVALDS_CHAT_KEY for migration
        legacy_key = os.environ.get("TORVALDS_CHAT_KEY", "")
        general_key = legacy_key if legacy_key else f"chat-general-{uid}"
        project_key = f"chat-project-{uid}"

        # General session
        general = Session(
            session_id=str(uuid.uuid4()),
            user_id=uid,
            session_name="General Chat",
            session_type=SessionType.GENERAL,
            chat_key=general_key,
            is_active=True,
        )
        self._db.create_session(general)

        # Project session
        project = Session(
            session_id=str(uuid.uuid4()),
            user_id=uid,
            session_name="Project Chat",
            session_type=SessionType.PROJECT,
            chat_key=project_key,
            is_active=False,
        )
        self._db.create_session(project)

        self._active_session = general
        logger.info("Pre-seeded default sessions: General Chat, Project Chat")

    # ------------------------------------------------------------------
    # Public API: Session Operations
    # ------------------------------------------------------------------

    def get_active_session(self) -> Session | None:
        """Get the current active session."""
        return self._active_session

    def list_sessions(self) -> list[Session]:
        """List all sessions for the current user."""
        if self._db is None or self._current_user is None:
            return []
        return self._db.list_sessions(self._current_user.user_id)

    def create_session(
        self,
        name: str,
        session_type: SessionType = SessionType.CUSTOM,
        metadata: dict | None = None,
    ) -> Session:
        """Create a new session for the current user.

        Args:
            name: Human-readable session name.
            session_type: Type of session.
            metadata: Optional JSON-serialisable metadata stored with the
                session.

        Returns:
            The created Session object.
        """
        if self._db is None or self._current_user is None:
            raise RuntimeError("Manager not initialized")

        uid = self._current_user.user_id
        chat_key = f"chat-{session_type.value}-{uid}-{uuid.uuid4().hex[:8]}"

        session_obj = Session(
            session_id=str(uuid.uuid4()),
            user_id=uid,
            session_name=name,
            session_type=session_type,
            chat_key=chat_key,
            metadata=metadata or {},
            is_active=False,
        )
        return self._db.create_session(session_obj)

    def get_session(self, session_id: str) -> Session | None:
        """Get one of the current user's sessions by ID.

        Args:
            session_id: The session to look up.

        Returns:
            The Session, or None if it does not exist or belongs to another user.
        """
        if self._db is None or self._current_user is None:
            return None

        session = self._db.get_session_by_id(session_id)
        if session is None or session.user_id != self._current_user.user_id:
            return None
        return session

    def update_session(self, session_id: str, **kwargs) -> Session | None:
        """Update fields of one of the current user's sessions.

        Args:
            session_id: The session to update.
            **kwargs: Fields to update (e.g. ``session_name``).

        Returns:
            The updated Session, or None if it does not exist or belongs to
            another user.
        """
        if self._db is None or self._current_user is None:
            return None

        session = self.get_session(session_id)
        if session is None:
            return None

        for field_name, value in kwargs.items():
            if field_name == "session_type" and isinstance(value, str):
                value = SessionType(value.lower())
            if hasattr(session, field_name):
                setattr(session, field_name, value)

        session.update_timestamp()
        updated = self._db.update_session(session)
        if updated and self._active_session and self._active_session.session_id == session_id:
            self._active_session = updated
        return updated

    def rename_session(self, session_id: str, new_name: str) -> Session | None:
        """Rename one of the current user's sessions.

        Args:
            session_id: The session to rename.
            new_name: The new human-readable name.

        Returns:
            The updated Session, or None if it does not exist or belongs to
            another user.
        """
        if not new_name or not new_name.strip():
            raise ValueError("Session name cannot be empty")

        return self.update_session(session_id, session_name=new_name.strip())

    def get_active_chat_key(self) -> str | None:
        """Get the LlamaIndex chat key of the active session.

        Returns:
            The chat key string, or None if there is no active session.
        """
        if self._active_session is None:
            return None
        return self._active_session.chat_key

    def select_session(self, session_id: str) -> Session | None:
        """Select (activate) a session — alias for :meth:`switch_session`.

        Args:
            session_id: The session to activate.

        Returns:
            The activated Session or None if not found.
        """
        return self.switch_session(session_id)

    def switch_session(self, session_id: str) -> Session | None:
        """Switch to a different session.

        Args:
            session_id: The session to activate.

        Returns:
            The activated Session or None if not found.
        """
        if self._db is None or self._current_user is None:
            return None

        # Only sessions owned by the current user may be activated.
        if self.get_session(session_id) is None:
            logger.warning(
                f"Session '{session_id}' does not exist or does not belong to "
                f"user '{self._current_user.username}'"
            )
            return None

        self._memory_buffer = None  # Invalidate memory buffer
        self._active_session = self._db.activate_session(
            session_id, self._current_user.user_id
        )
        return self._active_session

    def delete_session(self, session_id: str) -> bool:
        """Delete a session by ID.

        Cannot delete the active session, and can only delete sessions owned
        by the current user.

        Args:
            session_id: The session to delete.

        Returns:
            True if deleted, False otherwise.
        """
        if self._db is None:
            return False

        if self._active_session and self._active_session.session_id == session_id:
            logger.warning("Cannot delete the active session")
            return False

        if self.get_session(session_id) is None:
            logger.warning(
                f"Session '{session_id}' does not exist or does not belong to "
                f"the current user"
            )
            return False

        return self._db.delete_session(
            session_id, user_id=self._current_user.user_id
        )

    # ------------------------------------------------------------------
    # Public API: Message Buffer
    # ------------------------------------------------------------------

    def get_memory_buffer(self, token_limit: int | None = None) -> Any:
        """Get the LlamaIndex ChatMemoryBuffer for the active session.

        Lazily creates and caches the buffer. The buffer is bound to the
        active session's ``chat_key`` so that each session keeps its own,
        isolated message history.

        Args:
            token_limit: Override token limit (defaults to user preference).

        Returns:
            ChatMemoryBuffer instance bound to the active session.
        """
        if self._memory_buffer is not None:
            return self._memory_buffer

        if self._active_session is None or self._backend is None:
            raise RuntimeError("No active session or backend available")

        limit = token_limit or (
            self._current_user.token_limit if self._current_user else 5000
        )

        from llama_index.core.memory import ChatMemoryBuffer

        self._memory_buffer = ChatMemoryBuffer.from_defaults(
            token_limit=limit,
            chat_store=self._backend,
            chat_store_key=self._active_session.chat_key,
        )
        logger.info(
            f"Created memory buffer for session '{self._active_session.session_name}' "
            f"(key={self._active_session.chat_key}, limit={limit})"
        )

        return self._memory_buffer

    def add_message(self, content: str, role: str = "user") -> None:
        """Add a message to the current session's memory buffer.

        Args:
            content: Message content.
            role: Message role ('user', 'assistant', 'system').

        Raises:
            ValueError: If the role is not a valid chat message role.
        """
        from llama_index.core.base.llms.types import ChatMessage

        try:
            message = ChatMessage(role=role, content=content)
        except Exception as e:
            raise ValueError(f"Invalid message role '{role}': {e}") from e

        buffer = self.get_memory_buffer()
        buffer.put(message)

    def put_message(self, content: str, role: str = "user") -> None:
        """Add a message to the current session — alias for :meth:`add_message`.

        Args:
            content: Message content.
            role: Message role ('user', 'assistant', 'system').
        """
        self.add_message(content, role)

    def get_messages(self) -> list:
        """Get all messages from the current session's memory buffer.

        Returns:
            List of ChatMessage objects.
        """
        buffer = self.get_memory_buffer()
        return buffer.get()

    def clear_messages(self) -> None:
        """Delete every message stored for the active session.

        The session itself is kept; only its message history is removed.
        """
        if self._active_session is None:
            raise RuntimeError("No active session")

        if self._backend is not None:
            self._backend.delete_messages(self._active_session.chat_key)

        # Invalidate the cached buffer so it is rebuilt empty.
        self._memory_buffer = None
        logger.info(f"Cleared messages for session '{self._active_session.session_name}'")

    def close(self) -> None:
        """Close all connections — alias for :meth:`shutdown`.

        Safe to call more than once.
        """
        self.shutdown()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def current_user(self) -> User | None:
        """Get the current user."""
        return self._current_user

    @property
    def is_initialized(self) -> bool:
        """Whether the manager is fully initialized."""
        return self._db is not None and self._current_user is not None
