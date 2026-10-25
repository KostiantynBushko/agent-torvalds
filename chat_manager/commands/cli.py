"""CLI commands for ChatHistoryManager.

Provides interactive commands for session management:
- \\chat-sessions / \\chat-list: List all sessions
- \\chat-select <id>: Switch to a session
- \\chat-create <name> [type]: Create a new session
- \\chat-delete <id>: Delete a session
- \\chat-rename <id> <new name>: Rename a session
- \\chat-info: Show details of the active session
- \\chat-clear: Clear the active session's message history

and for the user's own configuration:
- \\chat-user: Show the current user's settings
- \\chat-user get <key>: Show one setting
- \\chat-user set <key> <value>: Change one setting
- \\chat-user help: List the settings and their accepted values
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from chat_manager.session import SessionType
from chat_manager.settings import (
    SETTINGS_BY_KEY,
    SettingError,
    UserSettings,
    normalize_setting_key,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from chat_manager.manager import ChatHistoryManager


def cmd_chat_sessions(manager: ChatHistoryManager) -> str:
    """List all sessions for the current user.

    Args:
        manager: The ChatHistoryManager instance.

    Returns:
        Formatted session list string.
    """
    if not manager.is_initialized:
        return "ChatHistoryManager not initialized."

    sessions = manager.list_sessions()
    if not sessions:
        return "No sessions found."

    lines = [f"Sessions for user '{manager.current_user.username}':"]
    lines.append(f"{'ID':<38} {'Name':<20} {'Type':<10} {'Active':<8} {'Created'}")
    lines.append("-" * 100)

    for s in sessions:
        active_marker = "✓" if s.is_active else " "
        created = s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else "N/A"
        lines.append(
            f"{s.session_id:<38} {s.session_name:<20} {s.session_type.value:<10} "
            f"{active_marker:<8} {created}"
        )

    return "\n".join(lines)


def cmd_chat_select(manager: ChatHistoryManager, session_id: str) -> str:
    """Switch to a different session.

    Args:
        manager: The ChatHistoryManager instance.
        session_id: The session ID to activate.

    Returns:
        Status message.
    """
    if not manager.is_initialized:
        return "ChatHistoryManager not initialized."

    session = manager.switch_session(session_id)
    if session is None:
        return f"Session '{session_id}' not found."

    return f"Switched to session: '{session.session_name}' ({session.session_type.value})"


def cmd_chat_create(
    manager: ChatHistoryManager, name: str, session_type: str = "custom"
) -> str:
    """Create a new session.

    Args:
        manager: The ChatHistoryManager instance.
        name: Human-readable session name.
        session_type: Type of session ('general', 'project', 'custom').

    Returns:
        Status message with new session ID.
    """
    if not manager.is_initialized:
        return "ChatHistoryManager not initialized."

    try:
        stype = SessionType(session_type.lower())
    except ValueError:
        return f"Invalid session type '{session_type}'. Must be: general, project, custom."

    session = manager.create_session(name=name, session_type=stype)
    return (
        f"Created session: '{session.session_name}' "
        f"(ID: {session.session_id}, type: {session.session_type.value})\n"
        f"Use \\chat-select {session.session_id} to switch to it."
    )


def cmd_chat_delete(manager: ChatHistoryManager, session_id: str) -> str:
    """Delete a session.

    Args:
        manager: The ChatHistoryManager instance.
        session_id: The session ID to delete.

    Returns:
        Status message.
    """
    if not manager.is_initialized:
        return "ChatHistoryManager not initialized."

    if manager.get_active_session() and manager.get_active_session().session_id == session_id:
        return "Cannot delete the active session. Switch to another session first."

    success = manager.delete_session(session_id)
    if success:
        return f"Session '{session_id}' deleted."
    return f"Session '{session_id}' not found or could not be deleted."


def cmd_chat_rename(manager: ChatHistoryManager, session_id: str, new_name: str) -> str:
    """Rename a session.

    Args:
        manager: The ChatHistoryManager instance.
        session_id: The session to rename.
        new_name: The new human-readable name.

    Returns:
        Status message.
    """
    if not manager.is_initialized:
        return "ChatHistoryManager not initialized."

    if not new_name or not new_name.strip():
        return "Session name cannot be empty."

    session = manager.rename_session(session_id, new_name.strip())
    if session is None:
        return f"Session '{session_id}' not found."

    return f"Renamed session to: '{session.session_name}' ({session.session_id})"


def cmd_chat_info(manager: ChatHistoryManager) -> str:
    """Show details of the active session.

    Args:
        manager: The ChatHistoryManager instance.

    Returns:
        Formatted session details.
    """
    if not manager.is_initialized:
        return "ChatHistoryManager not initialized."

    session = manager.get_active_session()
    if session is None:
        return "No active session."

    created = session.created_at.strftime("%Y-%m-%d %H:%M") if session.created_at else "N/A"
    updated = session.updated_at.strftime("%Y-%m-%d %H:%M") if session.updated_at else "N/A"
    user = manager.current_user.username if manager.current_user else "unknown"

    lines = [
        f"Active session for user '{user}':",
        f"  ID:       {session.session_id}",
        f"  Name:     {session.session_name}",
        f"  Type:     {session.session_type.value}",
        f"  Chat key: {session.chat_key}",
        f"  Created:  {created}",
        f"  Updated:  {updated}",
    ]

    # Where the metadata lives — a local fallback means the history is not
    # shared with the other machines, and the operator should know that.
    storage_mode = getattr(manager, "storage_mode", "primary")
    if storage_mode == "fallback":
        lines.append("  Storage:  local fallback (the primary database is unreachable)")
    else:
        lines.append(f"  Storage:  {storage_mode}")

    return "\n".join(lines)


def cmd_chat_clear(manager: ChatHistoryManager) -> str:
    """Clear the message history of the active session.

    Args:
        manager: The ChatHistoryManager instance.

    Returns:
        Status message.
    """
    if not manager.is_initialized:
        return "ChatHistoryManager not initialized."

    session = manager.get_active_session()
    if session is None:
        return "No active session."

    try:
        manager.clear_messages()
    except RuntimeError as e:
        return f"Could not clear messages: {e}"

    return f"Cleared message history for session '{session.session_name}'."


# ---------------------------------------------------------------------------
# User settings commands
# ---------------------------------------------------------------------------

def _settings_rows(settings: UserSettings) -> list[str]:
    """Render the settings as aligned text rows.

    Args:
        settings: The settings snapshot to render.

    Returns:
        A list of formatted lines.
    """
    rows = settings.as_rows()
    if not rows:
        return ["No settings available."]

    width = max(len(key) for key, _, _ in rows)
    lines = []
    for key, spec, value in rows:
        suffix = f" {spec.unit}" if spec.unit else ""
        lines.append(f"  {key.ljust(width)}  {value}{suffix}")
    return lines


def cmd_chat_user(manager: ChatHistoryManager) -> str:
    """Show the current user's settings.

    Args:
        manager: The ChatHistoryManager instance.

    Returns:
        Formatted settings overview.
    """
    if not manager.is_initialized:
        return "ChatHistoryManager not initialized."

    try:
        settings = manager.get_user_settings()
    except RuntimeError as e:
        return f"Could not read the user settings: {e}"

    user = manager.current_user.username if manager.current_user else "unknown"

    lines = [f"Settings for user '{user}':"]
    lines.extend(_settings_rows(settings))
    lines.append("")
    lines.append("Change a setting with: \\chat-user set <key> <value>")
    lines.append("Show one setting with: \\chat-user get <key>")

    return "\n".join(lines)


def cmd_chat_user_get(manager: ChatHistoryManager, key: str) -> str:
    """Show one of the current user's settings.

    Args:
        manager: The ChatHistoryManager instance.
        key: The name of the setting.

    Returns:
        The current value of the setting, or an error message.
    """
    if not manager.is_initialized:
        return "ChatHistoryManager not initialized."

    try:
        canonical = normalize_setting_key(key)
    except SettingError as e:
        return str(e)

    try:
        settings = manager.get_user_settings()
    except RuntimeError as e:
        return f"Could not read the user settings: {e}"

    spec = SETTINGS_BY_KEY[canonical]
    value = settings.get(canonical)
    suffix = f" {spec.unit}" if spec.unit else ""

    return f"{canonical} = {value}{suffix}"


def cmd_chat_user_set(manager: ChatHistoryManager, key: str, value: str) -> str:
    """Change one of the current user's settings.

    Args:
        manager: The ChatHistoryManager instance.
        key: The name of the setting.
        value: The new value.

    Returns:
        A status message.
    """
    if not manager.is_initialized:
        return "ChatHistoryManager not initialized."

    try:
        canonical = normalize_setting_key(key)
    except SettingError as e:
        return str(e)

    try:
        settings = manager.update_user_settings(**{canonical: value})
    except SettingError as e:
        return str(e)
    except RuntimeError as e:
        return f"Could not update the user settings: {e}"

    spec = SETTINGS_BY_KEY[canonical]
    suffix = f" {spec.unit}" if spec.unit else ""

    message = f"Set {canonical} = {settings.get(canonical)}{suffix}."

    if canonical == "chat_token_limit":
        message += (
            " The memory buffer was rebuilt, so the new limit applies from "
            "the next message on."
        )

    return message


def cmd_chat_user_help(manager: ChatHistoryManager) -> str:
    """List the user settings and their accepted values.

    Args:
        manager: The ChatHistoryManager instance.

    Returns:
        A formatted description of every setting.
    """
    if not manager.is_initialized:
        return "ChatHistoryManager not initialized."

    lines = ["User settings:", ""]
    for key, spec in SETTINGS_BY_KEY.items():
        writable = "read-write" if spec.writable else "read-only"
        lines.append(f"  {key}  ({writable})")
        lines.append(f"      {spec.description}")
        if spec.choices:
            lines.append(f"      Allowed: {', '.join(spec.choices)}")
        elif spec.writable:
            lines.append(f"      Accepted range: {spec.range_text}")
        else:
            lines.append(f"      Default: {spec.default}")
        lines.append("")

    lines.append("Usage:")
    lines.append("  \\chat-user                     show every setting")
    lines.append("  \\chat-user get <key>            show one setting")
    lines.append("  \\chat-user set <key> <value>    change one setting")
    lines.append("  \\chat-user help                 show this text")

    return "\n".join(lines)
