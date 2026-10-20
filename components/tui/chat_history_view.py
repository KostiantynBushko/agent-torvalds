"""
Chat History View for Torvalds Multi-Window Console.

Renders the ChatHistoryManager session information as Markdown so that the
multi-window agent can expose the same chat history features as the classic
orchestrator (``agent-torvalds.py``):
  - ``\\chat-sessions`` — list all sessions for the current user
  - ``\\chat-select <id>`` — switch the active session
  - ``\\chat-create <name> [type]`` — create a new session
  - ``\\chat-delete <id>`` — delete a session
  - ``\\chat-rename <id> <new name>`` — rename a session
  - ``\\chat-info`` — show details of the active session
  - ``\\chat-clear`` — clear the active session message history

The command dispatch itself is delegated to
:func:`chat_manager.commands.handler.handle_chat_command` so both
orchestrators stay behaviourally identical; this module only takes care of
formatting the result for the TUI document pane.

Category: Infrastructure
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Markdown rendering helpers
# ---------------------------------------------------------------------------

def render_chat_sessions_markdown(manager) -> str:
    """
    Render the list of chat sessions as a Markdown table.

    Args:
        manager: An initialized ChatHistoryManager instance.

    Returns:
        str: Markdown document describing every session.
    """
    if manager is None or not manager.is_initialized:
        return "# 💬 Chat Sessions\n\nChatHistoryManager is not initialized."

    sessions = manager.list_sessions()
    if not sessions:
        return "# 💬 Chat Sessions\n\nNo sessions found."

    user = manager.current_user.username if manager.current_user else "unknown"

    lines = [
        "# 💬 Chat Sessions",
        "",
        f"**User:** `{user}`  •  **Sessions:** {len(sessions)}",
        "",
        "| Active | ID | Name | Type | Created |",
        "| :---: | :--- | :--- | :--- | :--- |",
    ]

    for session in sessions:
        marker = "✓" if session.is_active else ""
        created = (
            session.created_at.strftime("%Y-%m-%d %H:%M")
            if session.created_at else "N/A"
        )
        lines.append(
            f"| {marker} | `{session.session_id}` | {session.session_name} "
            f"| {session.session_type.value} | {created} |"
        )

    lines.extend([
        "",
        "Switch sessions with `\\chat-select <session_id>`.",
    ])

    return "\n".join(lines)


def render_chat_info_markdown(manager) -> str:
    """
    Render details about the active chat session as Markdown.

    Args:
        manager: An initialized ChatHistoryManager instance.

    Returns:
        str: Markdown document describing the active session.
    """
    if manager is None or not manager.is_initialized:
        return "# 💬 Active Chat Session\n\nChatHistoryManager is not initialized."

    session = manager.get_active_session()
    if session is None:
        return "# 💬 Active Chat Session\n\nNo active session."

    user = manager.current_user.username if manager.current_user else "unknown"
    created = session.created_at.strftime("%Y-%m-%d %H:%M") if session.created_at else "N/A"
    updated = session.updated_at.strftime("%Y-%m-%d %H:%M") if session.updated_at else "N/A"

    lines = [
        "# 💬 Active Chat Session",
        "",
        "| Field | Value |",
        "| :--- | :--- |",
        f"| User | `{user}` |",
        f"| Name | {session.session_name} |",
        f"| Type | {session.session_type.value} |",
        f"| ID | `{session.session_id}` |",
        f"| Chat Key | `{session.chat_key}` |",
        f"| Created | {created} |",
        f"| Updated | {updated} |",
    ]

    return "\n".join(lines)


def render_command_result_markdown(command: str, result: Optional[str]) -> str:
    """
    Render the outcome of a chat command as Markdown.

    Args:
        command: The command that was executed.
        result: The textual result returned by the command handler.

    Returns:
        str: Markdown document describing the command outcome.
    """
    body = result if result else "(no output)"

    return "\n".join([
        "# 💬 Chat Command",
        "",
        f"**Command:** `{command}`",
        "",
        "```text",
        body,
        "```",
    ])


# ---------------------------------------------------------------------------
# Command dispatch
# ---------------------------------------------------------------------------

def handle_chat_command_markdown(cmd: str) -> Optional[str]:
    """
    Execute a chat history command and return a Markdown rendering.

    Args:
        cmd: The chat command to execute.

    Returns:
        str: Markdown document with the result, or None if the command was
        not a chat command.
    """
    from chat_manager.commands.handler import is_chat_command, handle_chat_command

    if not is_chat_command(cmd):
        return None

    cmd_lower = cmd.strip().lower()

    # The list and info views get a dedicated, richer rendering.
    if cmd_lower in ("\\chat-sessions", "\\chat-list", "\\chat-info"):
        from chat_manager.startup import get_chat_manager

        manager = get_chat_manager()
        if cmd_lower == "\\chat-info":
            return render_chat_info_markdown(manager)
        return render_chat_sessions_markdown(manager)

    try:
        result = handle_chat_command(cmd)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Chat command failed: %s", exc)
        result = f"Error: {exc}"

    return render_command_result_markdown(cmd, result)


__all__ = [
    "render_chat_sessions_markdown",
    "render_chat_info_markdown",
    "render_command_result_markdown",
    "handle_chat_command_markdown",
]
