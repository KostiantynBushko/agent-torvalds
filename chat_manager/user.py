"""User data model for ChatHistoryManager."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from chat_manager.settings import DEFAULT_CHAT_TOKEN_LIMIT


@dataclass(eq=False)
class User:
    """Represents a user identity and preferences.

    Attributes:
        user_id: Unique identifier for the user.
        username: OS username, unique constraint.
        backend_type: Preferred storage backend (e.g. 'postgres', 'mysql').
        chat_token_limit: Maximum number of chat-history tokens kept in the
            memory buffer of the active session.  Renamed from
            ``token_limit`` — see
            ``investigate/chat-manager-user-settings/PROPOSAL_chat_token_limit.md``.
            The old name survives as a deprecated property.
        created_at: User creation timestamp.
        updated_at: Last update timestamp.
    """

    user_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    username: str = ""
    backend_type: str = "postgres"
    chat_token_limit: int = DEFAULT_CHAT_TOKEN_LIMIT
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        """Ensure user_id is a valid UUID string."""
        if not self.user_id:
            self.user_id = str(uuid.uuid4())

    def __eq__(self, other: object) -> bool:
        """Users are equal if user_id matches."""
        if isinstance(other, User):
            return self.user_id == other.user_id
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.user_id)

    # ------------------------------------------------------------------
    # Deprecated alias
    # ------------------------------------------------------------------

    @property
    def token_limit(self) -> int:
        """Deprecated alias of :attr:`chat_token_limit`.

        Kept so that code written before the rename keeps working.  Use
        ``chat_token_limit`` in new code.
        """
        return self.chat_token_limit

    @token_limit.setter
    def token_limit(self, value: int) -> None:
        """Deprecated alias of :attr:`chat_token_limit` (setter)."""
        self.chat_token_limit = value

    def update_timestamp(self) -> None:
        """Update the updated_at timestamp to now."""
        self.updated_at = datetime.now()

    def to_dict(self) -> dict:
        """Serialize user to dictionary for database storage.

        The canonical ``chat_token_limit`` key is emitted together with the
        deprecated ``token_limit`` mirror, so a reader of the old shape keeps
        working.
        """
        return {
            "user_id": self.user_id,
            "username": self.username,
            "backend_type": self.backend_type,
            "chat_token_limit": self.chat_token_limit,
            "token_limit": self.chat_token_limit,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> User:
        """Deserialize user from dictionary (e.g. database row).

        Both ``chat_token_limit`` and the deprecated ``token_limit`` are
        accepted; the canonical key wins when both are present.
        """
        created_at = None
        if data.get("created_at"):
            val = data["created_at"]
            created_at = val if isinstance(val, datetime) else datetime.fromisoformat(str(val))

        updated_at = None
        if data.get("updated_at"):
            val = data["updated_at"]
            updated_at = val if isinstance(val, datetime) else datetime.fromisoformat(str(val))

        raw_limit = data.get("chat_token_limit")
        if raw_limit is None:
            raw_limit = data.get("token_limit", DEFAULT_CHAT_TOKEN_LIMIT)

        return cls(
            user_id=data["user_id"],
            username=data["username"],
            backend_type=data.get("backend_type", "postgres"),
            chat_token_limit=raw_limit,
            created_at=created_at,
            updated_at=updated_at,
        )


# ---------------------------------------------------------------------------
# Legacy constructor keyword
# ---------------------------------------------------------------------------

# ``User(token_limit=5000)`` was the documented way to build a user before the
# rename.  The dataclass field is now ``chat_token_limit``, so the generated
# __init__ no longer accepts the old keyword.  This wrapper adds it back as a
# deprecated alias, without touching the generated signature.
_dataclass_init = User.__init__


def _user_init(
    self: User,
    *args: Any,
    token_limit: Optional[int] = None,
    **kwargs: Any,
) -> None:
    """Initialise a User, accepting the deprecated ``token_limit`` keyword."""
    if token_limit is not None:
        if kwargs.get("chat_token_limit") is not None:
            raise TypeError(
                "User() got both 'chat_token_limit' and the deprecated "
                "'token_limit' — pass only 'chat_token_limit'."
            )
        kwargs["chat_token_limit"] = token_limit
    _dataclass_init(self, *args, **kwargs)


User.__init__ = _user_init  # type: ignore[method-assign]


__all__ = ["User"]
