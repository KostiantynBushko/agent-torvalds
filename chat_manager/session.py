"""Session data model for ChatHistoryManager."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SessionType(str, Enum):
    """Type of chat session."""

    GENERAL = "general"
    PROJECT = "project"
    CUSTOM = "custom"

    def __str__(self) -> str:
        return self.value


@dataclass
class Session:
    """Represents a chat session scoped to a user.

    Attributes:
        session_id: Unique identifier for the session.
        user_id: Foreign key to the owning user.
        session_name: Human-readable session name.
        session_type: Type of session (general, project, custom).
        chat_key: Key mapping to LlamaIndex message storage.
        metadata: Optional JSON metadata.
        created_at: Session creation timestamp.
        updated_at: Last update timestamp.
        is_active: Whether this is the user's active session.
    """

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    session_name: str = ""
    session_type: SessionType = SessionType.GENERAL
    chat_key: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    is_active: bool = False

    def __post_init__(self) -> None:
        """Ensure session_id is a valid UUID string and session_type is enum."""
        if not self.session_id:
            self.session_id = str(uuid.uuid4())
        if isinstance(self.session_type, str) and self.session_type != self.session_type.lower():
            self.session_type = SessionType(self.session_type.lower())

    def update_timestamp(self) -> None:
        """Update the updated_at timestamp to now."""
        self.updated_at = datetime.now()

    def to_dict(self) -> dict:
        """Serialize session to dictionary for database storage."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "session_name": self.session_name,
            "session_type": self.session_type.value if isinstance(self.session_type, SessionType) else self.session_type,
            "chat_key": self.chat_key,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Session:
        """Deserialize session from dictionary (e.g. database row)."""
        created_at = None
        if data.get("created_at"):
            val = data["created_at"]
            created_at = val if isinstance(val, datetime) else datetime.fromisoformat(str(val))

        updated_at = None
        if data.get("updated_at"):
            val = data["updated_at"]
            updated_at = val if isinstance(val, datetime) else datetime.fromisoformat(str(val))

        session_type_val = data.get("session_type", "general")
        if isinstance(session_type_val, str):
            session_type = SessionType(session_type_val)
        else:
            session_type = SessionType.GENERAL

        metadata = data.get("metadata", {})
        if isinstance(metadata, str):
            import json
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                metadata = {}

        return cls(
            session_id=data["session_id"],
            user_id=data["user_id"],
            session_name=data["session_name"],
            session_type=session_type,
            chat_key=data["chat_key"],
            metadata=metadata,
            created_at=created_at,
            updated_at=updated_at,
            is_active=bool(data.get("is_active", False)),
        )
