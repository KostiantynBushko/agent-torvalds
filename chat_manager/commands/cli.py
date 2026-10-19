"""CLI commands for ChatHistoryManager.

Provides interactive commands for session management:
- \\chat-sessions: List all sessions
- \\chat-select <id>: Switch to a session
- \\chat-create <name> [type]: Create a new session
- \\chat-delete <id>: Delete a session
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from chat_manager.session import SessionType

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
