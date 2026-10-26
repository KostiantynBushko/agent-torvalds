"""User settings for the ChatHistoryManager.

The ``users`` table is the documented home of the user's *preferences*.  This
module is the single source of truth for what those preferences are, what
their valid ranges are, and how a raw operator input is validated before it
reaches the database.

The central setting is ``chat_token_limit`` — the maximum number of **chat
history** tokens the agent keeps in the ``ChatMemoryBuffer`` of the active
session.  It was called ``token_limit`` until the rename documented in
``investigate/chat-manager-user-settings/PROPOSAL_chat_token_limit.md``; the
old name survives as a deprecated alias (see :data:`SETTING_ALIASES`).

Category: Infrastructure
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

# ---------------------------------------------------------------------------
# Defaults and bounds
# ---------------------------------------------------------------------------

#: Default number of chat-history tokens kept in the memory buffer.
DEFAULT_CHAT_TOKEN_LIMIT = 5000

#: Smallest accepted chat-token limit.  Below this the buffer cannot hold a
#: single useful exchange, and the agent would forget the question it was
#: asked a moment ago.
MIN_CHAT_TOKEN_LIMIT = 256

#: Largest accepted chat-token limit.  A value beyond this is a mistake (a
#: stray zero, a paste of the wrong number) and would ask the model to hold
#: more history than any local model can take.
MAX_CHAT_TOKEN_LIMIT = 1_000_000


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class SettingError(ValueError):
    """Raised when a setting key or value is not acceptable.

    The message is written for the operator, not for a log file: it is shown
    verbatim by the ``\\chat-user`` command.
    """


# ---------------------------------------------------------------------------
# Setting specifications
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SettingSpec:
    """Description of a single user setting.

    Attributes:
        key: Canonical name of the setting.
        description: One-line, human-readable explanation.
        unit: The unit the value is measured in (``tokens``, ``string``, …).
        default: The value used when the user has never changed it.
        minimum: Smallest accepted value (``None`` when unbounded).
        maximum: Largest accepted value (``None`` when unbounded).
        choices: The accepted values, when the setting is an enumeration.
        writable: Whether the operator may change the value at runtime.
    """

    key: str
    description: str
    unit: str = ""
    default: Any = None
    minimum: int | None = None
    maximum: int | None = None
    choices: Tuple[str, ...] = ()
    writable: bool = True

    @property
    def range_text(self) -> str:
        """Human-readable description of the accepted range."""
        if self.choices:
            return ", ".join(self.choices)
        if self.minimum is not None and self.maximum is not None:
            return f"{self.minimum} - {self.maximum}"
        if self.minimum is not None:
            return f">= {self.minimum}"
        if self.maximum is not None:
            return f"<= {self.maximum}"
        return "any"


#: Every user setting the manager understands, in display order.
SETTING_SPECS: Tuple[SettingSpec, ...] = (
    SettingSpec(
        key="chat_token_limit",
        description=(
            "Maximum number of chat-history tokens kept in the memory buffer "
            "of the active session. Older messages are dropped when the budget "
            "is exceeded."
        ),
        unit="tokens",
        default=DEFAULT_CHAT_TOKEN_LIMIT,
        minimum=MIN_CHAT_TOKEN_LIMIT,
        maximum=MAX_CHAT_TOKEN_LIMIT,
    ),
    SettingSpec(
        key="backend_type",
        description=(
            "Storage backend provisioned for this user. Assigned when the user "
            "is first seen; it is shown for reference and cannot be changed "
            "at runtime."
        ),
        unit="string",
        default="postgres",
        choices=("postgres",),
        writable=False,
    ),
)

#: Canonical setting key -> its specification.
SETTINGS_BY_KEY: Dict[str, SettingSpec] = {spec.key: spec for spec in SETTING_SPECS}

#: Deprecated / convenience names -> canonical key.
SETTING_ALIASES: Dict[str, str] = {
    # The pre-rename name of chat_token_limit.
    "token_limit": "chat_token_limit",
    "tokens": "chat_token_limit",
    "limit": "chat_token_limit",
    "chat_tokens": "chat_token_limit",
}


# ---------------------------------------------------------------------------
# Key handling
# ---------------------------------------------------------------------------

def normalize_setting_key(key: str) -> str:
    """Resolve a user-supplied setting key to its canonical name.

    Args:
        key: The key as typed by the operator.

    Returns:
        The canonical setting key.

    Raises:
        SettingError: If the key is empty or unknown.
    """
    if key is None:
        raise SettingError("No setting name given.")

    needle = str(key).strip().lower().replace("-", "_")
    if not needle:
        raise SettingError("No setting name given.")

    if needle in SETTINGS_BY_KEY:
        return needle

    if needle in SETTING_ALIASES:
        return SETTING_ALIASES[needle]

    raise SettingError(
        f"Unknown setting '{key}'. Known settings: {', '.join(SETTINGS_BY_KEY)}."
    )


# ---------------------------------------------------------------------------
# Value validation
# ---------------------------------------------------------------------------

def validate_chat_token_limit(value: Any) -> int:
    """Validate and normalise a chat-token limit.

    Args:
        value: The raw value, as typed by the operator.

    Returns:
        The validated limit as an ``int``.

    Raises:
        SettingError: If the value is not a number or is out of range.
    """
    try:
        limit = int(str(value).strip())
    except (TypeError, ValueError):
        raise SettingError(
            f"'{value}' is not a number. The chat token limit must be a whole "
            f"number of tokens ({MIN_CHAT_TOKEN_LIMIT}-{MAX_CHAT_TOKEN_LIMIT})."
        ) from None

    if limit < MIN_CHAT_TOKEN_LIMIT:
        raise SettingError(
            f"The chat token limit must be at least {MIN_CHAT_TOKEN_LIMIT} "
            f"(got {limit})."
        )

    if limit > MAX_CHAT_TOKEN_LIMIT:
        raise SettingError(
            f"The chat token limit must be at most {MAX_CHAT_TOKEN_LIMIT} "
            f"(got {limit})."
        )

    return limit


def validate_setting_value(key: str, value: Any) -> Any:
    """Validate a value for the given setting.

    Args:
        key: The canonical setting key.
        value: The raw value, as typed by the operator.

    Returns:
        The validated value, ready to be persisted.

    Raises:
        SettingError: If the setting is unknown, read-only, or the value is
            not acceptable for it.
    """
    spec = SETTINGS_BY_KEY.get(key)
    if spec is None:
        raise SettingError(
            f"Unknown setting '{key}'. Known settings: {', '.join(SETTINGS_BY_KEY)}."
        )

    if not spec.writable:
        raise SettingError(
            f"The setting '{spec.key}' is read-only — it is assigned when the "
            f"user is provisioned."
        )

    if spec.key == "chat_token_limit":
        return validate_chat_token_limit(value)

    if spec.choices:
        text = str(value).strip().lower()
        if text not in spec.choices:
            raise SettingError(
                f"Invalid value '{value}' for '{spec.key}'. "
                f"Allowed: {', '.join(spec.choices)}."
            )
        return text

    return value


# ---------------------------------------------------------------------------
# The settings snapshot
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class UserSettings:
    """An immutable snapshot of the current user's preferences.

    Attributes:
        chat_token_limit: The chat-history token budget of the memory buffer.
        backend_type: The storage backend provisioned for the user.
    """

    chat_token_limit: int = DEFAULT_CHAT_TOKEN_LIMIT
    backend_type: str = "postgres"

    @classmethod
    def from_user(cls, user: Any) -> "UserSettings":
        """Build a snapshot from a ``User`` object.

        Args:
            user: The user whose preferences are read.  ``None`` yields the
                default settings.

        Returns:
            A ``UserSettings`` snapshot.
        """
        if user is None:
            return cls()

        return cls(
            chat_token_limit=int(
                getattr(user, "chat_token_limit", DEFAULT_CHAT_TOKEN_LIMIT)
            ),
            backend_type=str(getattr(user, "backend_type", "postgres")),
        )

    def to_dict(self) -> dict:
        """Serialize the settings to a plain dictionary."""
        return {
            "chat_token_limit": self.chat_token_limit,
            "backend_type": self.backend_type,
        }

    def get(self, key: str) -> Any:
        """Read one setting by (canonical) key.

        Args:
            key: The setting key.

        Returns:
            The current value.

        Raises:
            SettingError: If the key is unknown.
        """
        canonical = normalize_setting_key(key)
        return getattr(self, canonical)

    def as_rows(self) -> Tuple[Tuple[str, SettingSpec, Any], ...]:
        """Return the settings as ``(key, spec, value)`` rows for display.

        Returns:
            A tuple of rows, one per known setting.
        """
        return tuple(
            (spec.key, spec, getattr(self, spec.key)) for spec in SETTING_SPECS
        )


__all__ = [
    "DEFAULT_CHAT_TOKEN_LIMIT",
    "MIN_CHAT_TOKEN_LIMIT",
    "MAX_CHAT_TOKEN_LIMIT",
    "SettingError",
    "SettingSpec",
    "SETTING_SPECS",
    "SETTINGS_BY_KEY",
    "SETTING_ALIASES",
    "UserSettings",
    "normalize_setting_key",
    "validate_chat_token_limit",
    "validate_setting_value",
]
