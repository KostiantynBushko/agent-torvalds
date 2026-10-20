"""SQLAlchemy ORM models for user and session metadata.

These models map to the `users` and `chat_sessions` tables managed by
the CustomDBConnector, separate from LlamaIndex message storage.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class User(Base):
    """SQLAlchemy model for the `users` table."""

    __tablename__ = "users"

    user_id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(Text, nullable=False, unique=True)
    backend_type = Column(Text, nullable=False, default="postgres")
    token_limit = Column(Integer, nullable=False, default=5000)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationship to sessions
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User(id={self.user_id}, username={self.username})>"


class Session(Base):
    """SQLAlchemy model for the `chat_sessions` table."""

    __tablename__ = "chat_sessions"

    session_id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Text, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    session_name = Column(Text, nullable=False)
    session_type = Column(Text, nullable=False, default="general")
    chat_key = Column(Text, nullable=False, unique=True)
    session_metadata = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    is_active = Column(Boolean, default=False)

    # Check constraint for session_type
    __table_args__ = (
        CheckConstraint(
            "session_type IN ('general', 'project', 'custom')",
            name="chk_session_type",
        ),
    )

    # Relationship to user
    user = relationship("User", back_populates="sessions")

    def __repr__(self) -> str:
        return f"<Session(id={self.session_id}, name={self.session_name}, active={self.is_active})>"
