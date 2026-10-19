"""Custom DB connector for user and session metadata.

Uses SQLAlchemy to manage the `users` and `chat_sessions` tables,
isolated from the LlamaIndex message storage connector.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from chat_manager.storage.models import Base, User, Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id       TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    backend_type  TEXT NOT NULL DEFAULT 'postgres',
    token_limit   INTEGER NOT NULL DEFAULT 5000,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id    TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL,
    session_name  TEXT NOT NULL,
    session_type  TEXT NOT NULL CHECK(session_type IN ('general', 'project', 'custom')),
    chat_key      TEXT NOT NULL UNIQUE,
    metadata      TEXT DEFAULT '{}',
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active     BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON chat_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_type ON chat_sessions(session_type);
CREATE INDEX IF NOT EXISTS idx_sessions_active ON chat_sessions(user_id, is_active);
"""


# ---------------------------------------------------------------------------
# Connector
# ---------------------------------------------------------------------------

class CustomDBConnector:
    """SQLAlchemy-based connector for user and session metadata.

    Manages the `users` and `chat_sessions` tables independently from
    the LlamaIndex message storage connector.
    """

    def __init__(self, connection_uri: str | None = None) -> None:
        self._uri = connection_uri or self._resolve_uri()
        self._engine: Any = None
        self._session_factory: Any = None
        self._connected = False

    @staticmethod
    def _resolve_uri() -> str:
        """Resolve database URI from environment or default."""
        uri = os.environ.get("TORVALDS_STORAGE_URI")
        if uri:
            return uri
        # Default: use same DB as LlamaIndex but separate connector
        host = os.environ.get("TORVALDS_PG_HOST", "127.0.0.1")
        port = os.environ.get("TORVALDS_PG_PORT", "5432")
        user = os.environ.get("TORVALDS_PG_USER", "postgres")
        password = os.environ.get("TORVALDS_PG_PASSWORD", "postgres")
        database = os.environ.get("TORVALDS_PG_DATABASE", "llama_index_db")
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Establish connection and create schema if needed."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        try:
            self._engine = create_engine(self._uri, echo=False)
            self._session_factory = sessionmaker(bind=self._engine)
            # Create tables if they don't exist
            Base.metadata.create_all(self._engine)
            self._connected = True
            logger.info(f"CustomDBConnector connected to {self._uri}")
        except Exception as e:
            logger.warning(f"CustomDBConnector failed to connect: {e}")
            self._connected = False

    def close(self) -> None:
        """Close the connection and release resources."""
        if self._engine:
            self._engine.dispose()
            self._connected = False
            logger.info("CustomDBConnector closed")

    @property
    def is_connected(self) -> bool:
        """Whether the connector is active."""
        return self._connected

    def _ensure_connected(self) -> None:
        """Raise if not connected."""
        if not self._connected:
            raise RuntimeError("CustomDBConnector is not connected")

    # ------------------------------------------------------------------
    # User operations
    # ------------------------------------------------------------------

    def get_user_by_username(self, username: str) -> User | None:
        """Look up a user by username.

        Args:
            username: The OS username to look up.

        Returns:
            User object or None if not found.
        """
        self._ensure_connected()
        session = self._session_factory()
        try:
            return session.query(User).filter(User.username == username).first()
        finally:
            session.close()

    def get_user_by_id(self, user_id: str) -> User | None:
        """Look up a user by user_id.

        Args:
            user_id: The UUID of the user.

        Returns:
            User object or None if not found.
        """
        self._ensure_connected()
        session = self._session_factory()
        try:
            return session.query(User).filter(User.user_id == user_id).first()
        finally:
            session.close()

    def create_user(self, user: User) -> User:
        """Create a new user record.

        Args:
            user: User object to persist.

        Returns:
            The persisted User object.
        """
        self._ensure_connected()
        session = self._session_factory()
        try:
            session.add(user)
            session.commit()
            session.refresh(user)
            logger.info(f"Created user: {user.username} ({user.user_id})")
            return user
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_user(self, user: User) -> User:
        """Update an existing user record.

        Args:
            user: User object with updated fields.

        Returns:
            The updated User object.
        """
        self._ensure_connected()
        session = self._session_factory()
        try:
            existing = session.query(User).filter(User.user_id == user.user_id).first()
            if existing:
                existing.backend_type = user.backend_type
                existing.token_limit = user.token_limit
                existing.updated_at = user.updated_at
                session.commit()
                session.refresh(existing)
                return existing
            return user
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Session operations
    # ------------------------------------------------------------------

    def get_session_by_id(self, session_id: str) -> Session | None:
        """Look up a session by session_id.

        Args:
            session_id: The UUID of the session.

        Returns:
            Session object or None if not found.
        """
        self._ensure_connected()
        session = self._session_factory()
        try:
            return session.query(Session).filter(Session.session_id == session_id).first()
        finally:
            session.close()

    def get_active_session(self, user_id: str) -> Session | None:
        """Get the active session for a user.

        Args:
            user_id: The UUID of the user.

        Returns:
            Active Session object or None if not found.
        """
        self._ensure_connected()
        session = self._session_factory()
        try:
            return (
                session.query(Session)
                .filter(Session.user_id == user_id, Session.is_active.is_(True))
                .first()
            )
        finally:
            session.close()

    def list_sessions(self, user_id: str) -> list[Session]:
        """List all sessions for a user.

        Args:
            user_id: The UUID of the user.

        Returns:
            List of Session objects ordered by created_at descending.
        """
        self._ensure_connected()
        session = self._session_factory()
        try:
            return (
                session.query(Session)
                .filter(Session.user_id == user_id)
                .order_by(Session.created_at.desc())
                .all()
            )
        finally:
            session.close()

    def create_session(self, session_obj: Session) -> Session:
        """Create a new session record.

        Args:
            session_obj: Session object to persist.

        Returns:
            The persisted Session object.
        """
        self._ensure_connected()
        session = self._session_factory()
        try:
            session.add(session_obj)
            session.commit()
            session.refresh(session_obj)
            logger.info(f"Created session: {session_obj.session_name} ({session_obj.session_id})")
            return session_obj
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def activate_session(self, session_id: str, user_id: str) -> Session | None:
        """Activate a session, deactivating all others for the user.

        Args:
            session_id: The session to activate.
            user_id: The owning user.

        Returns:
            The activated Session object or None if not found.
        """
        self._ensure_connected()
        session = self._session_factory()
        try:
            from datetime import datetime

            # Deactivate all sessions for this user
            session.query(Session).filter(
                Session.user_id == user_id, Session.is_active.is_(True)
            ).update({"is_active": False, "updated_at": datetime.now()})

            # Activate the target session
            target = (
                session.query(Session)
                .filter(Session.session_id == session_id)
                .first()
            )
            if target:
                target.is_active = True
                target.updated_at = datetime.now()
                session.commit()
                session.refresh(target)
                logger.info(f"Activated session: {target.session_name}")
                return target
            return None
        finally:
            session.close()

    def delete_session(self, session_id: str) -> bool:
        """Delete a session by ID.

        Args:
            session_id: The session to delete.

        Returns:
            True if deleted, False if not found.
        """
        self._ensure_connected()
        session = self._session_factory()
        try:
            target = (
                session.query(Session)
                .filter(Session.session_id == session_id)
                .first()
            )
            if target:
                session.delete(target)
                session.commit()
                logger.info(f"Deleted session: {session_id}")
                return True
            return False
        finally:
            session.close()
