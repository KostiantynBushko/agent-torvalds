"""CLI command handler for ChatHistoryManager.

Integrates chat session commands into the agent's interactive loop.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    pass  # Avoid circular imports


# ---------------------------------------------------------------------------
# Command registry
# ---------------------------------------------------------------------------

CHAT_COMMANDS = {
    "\\chat-sessions": "list",
    "\\chat-select": "select",
    "\\chat-create": "create",
    "\\chat-delete": "delete",
}


def is_chat_command(cmd: str) -> bool:
    """Check if a command is a chat management command.

    Args:
        cmd: The command string to check.

    Returns:
        True if it's a chat command, False otherwise.
    """
    cmd_lower = cmd.strip().lower()
    return cmd_lower in CHAT_COMMANDS or cmd_lower.startswith(
        (k + " " for k in CHAT_COMMANDS)
    )


def handle_chat_command(cmd: str) -> str | None:
    """Process a chat management command.

    Args:
        cmd: The command string to process.

    Returns:
        Response message if it was a chat command, None otherwise.
    """
    from chat_manager.startup import get_chat_manager
    from chat_manager.commands import (
        cmd_chat_sessions,
        cmd_chat_select,
        cmd_chat_create,
        cmd_chat_delete,
    )

    manager = get_chat_manager()
    if manager is None:
        return "ChatHistoryManager not initialized."

    cmd_lower = cmd.strip().lower()

    # \chat-sessions
    if cmd_lower == "\\chat-sessions":
        return cmd_chat_sessions(manager)

    # \chat-select <session_id>
    if cmd_lower.startswith("\\chat-select "):
        session_id = cmd.strip().split(maxsplit=1)[1].strip()
        if not session_id:
            return "Usage: \\chat-select <session_id>"
        return cmd_chat_select(manager, session_id)

    # \chat-create <name> [type]
    if cmd_lower.startswith("\\chat-create "):
        parts = cmd.strip().split(maxsplit=2)
        if len(parts) < 2:
            return "Usage: \\chat-create <name> [type]"
        name = parts[1]
        session_type = parts[2] if len(parts) > 2 else "custom"
        return cmd_chat_create(manager, name=name, session_type=session_type)

    # \chat-delete <session_id>
    if cmd_lower.startswith("\\chat-delete "):
        session_id = cmd.strip().split(maxsplit=1)[1].strip()
        if not session_id:
            return "Usage: \\chat-delete <session_id>"
        return cmd_chat_delete(manager, session_id)

    return None
