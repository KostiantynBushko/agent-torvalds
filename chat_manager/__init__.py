"""
ChatHistoryManager — Multi-user chat session management with SQL-backed persistence.

Provides session lifecycle management, user identification, and backend-agnostic
message storage via LlamaIndex integration.

The user's own configuration — the *settings* — is part of the public surface
as well: :class:`UserSettings` describes the values, and
:meth:`ChatHistoryManager.get_user_settings` /
:meth:`ChatHistoryManager.update_user_settings` read and write them.
"""

from chat_manager.user import User
from chat_manager.session import Session, SessionType
from chat_manager.settings import (
    DEFAULT_CHAT_TOKEN_LIMIT,
    MAX_CHAT_TOKEN_LIMIT,
    MIN_CHAT_TOKEN_LIMIT,
    SETTING_SPECS,
    SettingError,
    SettingSpec,
    UserSettings,
    normalize_setting_key,
    validate_chat_token_limit,
    validate_setting_value,
)
from chat_manager.manager import ChatHistoryManager

__all__ = [
    "ChatHistoryManager",
    "User",
    "Session",
    "SessionType",
    # Settings
    "UserSettings",
    "SettingSpec",
    "SettingError",
    "SETTING_SPECS",
    "DEFAULT_CHAT_TOKEN_LIMIT",
    "MIN_CHAT_TOKEN_LIMIT",
    "MAX_CHAT_TOKEN_LIMIT",
    "normalize_setting_key",
    "validate_chat_token_limit",
    "validate_setting_value",
]
