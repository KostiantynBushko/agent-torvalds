"""User data model for ChatHistoryManager."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class User:
    """Represents a user identity and preferences.

    Attributes:
        user_id: Unique identifier for the user.
        username: OS username, unique constraint.
        backend_type: Preferred storage backend (e.g. 'postgres', 'mysql').
        token_limit: Maximum tokens in memory buffer.
        created_at: User creation timestamp.
        updated_at: Last update timestamp.
    """

    user_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    username: str = ""
    backend_type: str = "postgres"
    token_limit: int = 5000
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        """Ensure user_id is a valid UUID string."""
        if not self.user_id:
            self.user_id = str(uuid.uuid4())

    def update_timestamp(self) -> None:
        """Update the updated_at timestamp to now."""
        self.updated_at = datetime.now()

    def to_dict(self) -> dict:
        """Serialize user to dictionary for database storage."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "backend_type": self.backend_type,
            "token_limit": self.token_limit,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> User:
        """Deserialize user from dictionary (e.g. database row)."""
        created_at = None
        if data.get("created_at"):
            val = data["created_at"]
            created_at = val if isinstance(val, datetime) else datetime.fromisoformat(str(val))

        updated_at = None
        if data.get("updated_at"):
            val = data["updated_at"]
            updated_at = val if isinstance(val, datetime) else datetime.fromisoformat(str(val))

        return cls(
            user_id=data["user_id"],
            username=data["username"],
            backend_type=data.get("backend_type", "postgres"),
            token_limit=data.get("token_limit", 5000),
            created_at=created_at,
            updated_at=updated_at,
        )
