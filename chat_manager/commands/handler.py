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
    "\\chat-list": "list",
    "\\chat-select": "select",
    "\\chat-create": "create",
    "\\chat-delete": "delete",
    "\\chat-rename": "rename",
    "\\chat-info": "info",
    "\\chat-clear": "clear",
}

# Prefixes of the commands that accept an argument.
CHAT_COMMAND_PREFIXES = tuple(f"{cmd} " for cmd in CHAT_COMMANDS)


def is_chat_command(cmd: str) -> bool:
    """Check if a command is a chat management command.

    Args:
        cmd: The command string to check.

    Returns:
        True if it's a chat command, False otherwise.
    """
    cmd_lower = cmd.strip().lower()
    if not cmd_lower:
        return False
    return cmd_lower in CHAT_COMMANDS or cmd_lower.startswith(CHAT_COMMAND_PREFIXES)


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
        cmd_chat_rename,
        cmd_chat_info,
        cmd_chat_clear,
    )

    manager = get_chat_manager()
    if manager is None:
        return "ChatHistoryManager not initialized."

    cmd_lower = cmd.strip().lower()

    # \chat-sessions / \chat-list
    if cmd_lower in ("\\chat-sessions", "\\chat-list"):
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

    # \chat-rename <session_id> <new name>
    if cmd_lower.startswith("\\chat-rename "):
        parts = cmd.strip().split(maxsplit=2)
        if len(parts) < 3:
            return "Usage: \\chat-rename <session_id> <new name>"
        session_id = parts[1].strip()
        new_name = parts[2].strip()
        if not session_id or not new_name:
            return "Usage: \\chat-rename <session_id> <new name>"
        return cmd_chat_rename(manager, session_id, new_name)

    # \chat-info
    if cmd_lower == "\\chat-info":
        return cmd_chat_info(manager)

    # \chat-clear
    if cmd_lower == "\\chat-clear":
        return cmd_chat_clear(manager)

    return None
