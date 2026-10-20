"""Custom DB connector for user and session metadata.

Uses SQLAlchemy to manage the `users` and `chat_sessions` tables,
isolated from the LlamaIndex message storage connector.

Converts between dataclass models (chat_manager.user.User, chat_manager.session.Session)
and SQLAlchemy ORM models (chat_manager.storage.models.User, chat_manager.storage.models.Session).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

from chat_manager.storage.models import Base, User as ORMUser, Session as ORMSession
from chat_manager.user import User
from chat_manager.session import Session, SessionType

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
# Conversion helpers
# ---------------------------------------------------------------------------

def _orm_user_to_dataclass(orm_user: ORMUser) -> User:
    """Convert ORM User to dataclass User."""
    return User(
        user_id=orm_user.user_id,
        username=orm_user.username,
        backend_type=orm_user.backend_type,
        token_limit=orm_user.token_limit,
        created_at=orm_user.created_at,
        updated_at=orm_user.updated_at,
    )


def _dataclass_to_orm_user(user: User) -> ORMUser:
    """Convert dataclass User to ORM User."""
    return ORMUser(
        user_id=user.user_id,
        username=user.username,
        backend_type=user.backend_type,
        token_limit=user.token_limit,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def _parse_metadata(raw: str | None) -> dict:
    """Parse a JSON metadata blob into a dict.

    Args:
        raw: Raw JSON string from the database (may be None or invalid).

    Returns:
        Parsed metadata dict, or an empty dict when the value is missing or
        cannot be parsed.
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"Could not parse session metadata: {raw!r}")
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _orm_session_to_dataclass(orm_session: ORMSession) -> Session:
    """Convert ORM Session to dataclass Session."""
    return Session(
        session_id=orm_session.session_id,
        user_id=orm_session.user_id,
        session_name=orm_session.session_name,
        session_type=SessionType(orm_session.session_type) if isinstance(orm_session.session_type, str) else orm_session.session_type,
        chat_key=orm_session.chat_key,
        metadata=_parse_metadata(orm_session.session_metadata),
        created_at=orm_session.created_at,
        updated_at=orm_session.updated_at,
        is_active=bool(orm_session.is_active),
    )


def _dataclass_to_orm_session(session: Session) -> ORMSession:
    """Convert dataclass Session to ORM Session."""
    session_type_val = session.session_type.value if isinstance(session.session_type, SessionType) else session.session_type
    try:
        metadata_json = json.dumps(session.metadata or {})
    except (TypeError, ValueError):
        logger.warning("Could not serialise session metadata, storing empty object")
        metadata_json = "{}"

    return ORMSession(
        session_id=session.session_id,
        user_id=session.user_id,
        session_name=session.session_name,
        session_type=session_type_val,
        chat_key=session.chat_key,
        session_metadata=metadata_json,
        created_at=session.created_at,
        updated_at=session.updated_at,
        is_active=session.is_active,
    )


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
            self._engine = None
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
            orm_user = session.query(ORMUser).filter(ORMUser.username == username).first()
            return _orm_user_to_dataclass(orm_user) if orm_user else None
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
            orm_user = session.query(ORMUser).filter(ORMUser.user_id == user_id).first()
            return _orm_user_to_dataclass(orm_user) if orm_user else None
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
            orm_user = _dataclass_to_orm_user(user)
            session.add(orm_user)
            session.commit()
            session.refresh(orm_user)
            logger.info(f"Created user: {user.username} ({user.user_id})")
            return _orm_user_to_dataclass(orm_user)
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
            existing = session.query(ORMUser).filter(ORMUser.user_id == user.user_id).first()
            if existing:
                existing.backend_type = user.backend_type
                existing.token_limit = user.token_limit
                existing.updated_at = user.updated_at
                session.commit()
                session.refresh(existing)
                return _orm_user_to_dataclass(existing)
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
            orm_session = session.query(ORMSession).filter(ORMSession.session_id == session_id).first()
            return _orm_session_to_dataclass(orm_session) if orm_session else None
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
            orm_session = (
                session.query(ORMSession)
                .filter(ORMSession.user_id == user_id, ORMSession.is_active.is_(True))
                .first()
            )
            return _orm_session_to_dataclass(orm_session) if orm_session else None
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
            orm_sessions = (
                session.query(ORMSession)
                .filter(ORMSession.user_id == user_id)
                .order_by(ORMSession.created_at.desc())
                .all()
            )
            return [_orm_session_to_dataclass(s) for s in orm_sessions]
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
            orm_session = _dataclass_to_orm_session(session_obj)
            session.add(orm_session)
            session.commit()
            session.refresh(orm_session)
            logger.info(f"Created session: {session_obj.session_name} ({session_obj.session_id})")
            return _orm_session_to_dataclass(orm_session)
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
            # Deactivate all sessions for this user
            session.query(ORMSession).filter(
                ORMSession.user_id == user_id, ORMSession.is_active.is_(True)
            ).update({"is_active": False, "updated_at": datetime.now()})

            # Activate the target session (must belong to the given user)
            target = (
                session.query(ORMSession)
                .filter(
                    ORMSession.session_id == session_id,
                    ORMSession.user_id == user_id,
                )
                .first()
            )
            if target:
                target.is_active = True
                target.updated_at = datetime.now()
                session.commit()
                session.refresh(target)
                logger.info(f"Activated session: {target.session_name}")
                return _orm_session_to_dataclass(target)
            logger.warning(
                f"Session '{session_id}' not found for user '{user_id}'"
            )
            return None
        finally:
            session.close()

    def delete_session(self, session_id: str, user_id: str | None = None) -> bool:
        """Delete a session by ID.

        Args:
            session_id: The session to delete.
            user_id: Optional owner. When given, the session is only deleted
                if it belongs to this user (multi-user isolation).

        Returns:
            True if deleted, False if not found or not owned by the user.
        """
        self._ensure_connected()
        session = self._session_factory()
        try:
            query = session.query(ORMSession).filter(
                ORMSession.session_id == session_id
            )
            if user_id is not None:
                query = query.filter(ORMSession.user_id == user_id)

            target = query.first()
            if target:
                session.delete(target)
                session.commit()
                logger.info(f"Deleted session: {session_id}")
                return True
            return False
        finally:
            session.close()

    def update_session(self, session_obj: Session) -> Session | None:
        """Update an existing session record.

        Args:
            session_obj: Session object carrying the new field values.

        Returns:
            The updated Session, or None if it does not exist.
        """
        self._ensure_connected()
        session = self._session_factory()
        try:
            target = (
                session.query(ORMSession)
                .filter(ORMSession.session_id == session_obj.session_id)
                .first()
            )
            if target is None:
                logger.warning(f"Session '{session_obj.session_id}' not found")
                return None

            target.session_name = session_obj.session_name
            target.session_type = (
                session_obj.session_type.value
                if isinstance(session_obj.session_type, SessionType)
                else session_obj.session_type
            )
            target.session_metadata = _dataclass_to_orm_session(
                session_obj
            ).session_metadata
            target.updated_at = datetime.now()

            session.commit()
            session.refresh(target)
            logger.info(f"Updated session: {target.session_name}")
            return _orm_session_to_dataclass(target)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
