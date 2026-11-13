"""
Chat History View for Torvalds Multi-Window Console.

Renders the ChatHistoryManager session information as Markdown so that the
multi-window agent can expose the same chat history features as the classic
orchestrator (``agent-torvalds.py``):
  - ``\\chat-sessions`` — list all sessions for the current user
  - ``\\chat-select`` — open the numbered picker of the sessions
  - ``\\chat-select <id | number>`` — switch the active session
  - ``\\chat-create <name> [type]`` — create a new session
  - ``\\chat-delete <id>`` — delete a session
  - ``\\chat-rename <id> <new name>`` — rename a session
  - ``\\chat-info`` — show details of the active session
  - ``\\chat-clear`` — clear the active session message history
  - ``\\chat-user`` — show or change the current user's own settings

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
        "| # | Active | ID | Name | Type | Created |",
        "| ---: | :---: | :--- | :--- | :--- | :--- |",
    ]

    for index, session in enumerate(sessions, start=1):
        marker = "✓" if session.is_active else ""
        created = (
            session.created_at.strftime("%Y-%m-%d %H:%M")
            if session.created_at else "N/A"
        )
        lines.append(
            f"| {index} | {marker} | `{session.session_id}` | {session.session_name} "
            f"| {session.session_type.value} | {created} |"
        )

    lines.extend([
        "",
        "Switch sessions with `\\chat-select <number>` — the number of the "
        "session in this list — or with `\\chat-select <session_id>`.",
    ])

    return "\n".join(lines)


def render_session_picker_markdown(manager) -> str:
    """
    Render the numbered picker of the chat sessions.

    The picker is what ``\\chat-select`` opens when the operator names no
    session.  It is **compact on purpose**: the list of
    :func:`render_chat_sessions_markdown` carries the full id of every
    session, and a row of that table is wider than the document pane of
    the TUI — the id is folded in the middle and has to be copied by
    hand.  The picker leaves the id out and fits.

    The numbering is the numbering of the list: the sessions come from
    the same call, in the same order.  The number the operator sees here
    is the number the startup menu shows, and the number
    ``\\chat-select <number>`` takes.

    Args:
        manager: An initialized ChatHistoryManager instance.

    Returns:
        str: Markdown document with the picker.
    """
    if manager is None or not manager.is_initialized:
        return "# 💬 Select a Chat Session\n\nChatHistoryManager is not initialized."

    sessions = manager.list_sessions()
    if not sessions:
        return "# 💬 Select a Chat Session\n\nNo sessions found."

    lines = [
        "# 💬 Select a Chat Session",
        "",
        f"**Sessions:** {len(sessions)}  •  the active one is marked ★",
        "",
        "| # | Session | Type | Created |",
        "| ---: | :--- | :--- | :--- |",
    ]

    for index, session in enumerate(sessions, start=1):
        marker = "★ " if session.is_active else ""
        created = (
            session.created_at.strftime("%Y-%m-%d %H:%M")
            if session.created_at else "N/A"
        )
        lines.append(
            f"| {index} | {marker}{session.session_name} "
            f"| {session.session_type.value} | {created} |"
        )

    lines.extend([
        "",
        "**How to select:**",
        "- Type `\\chat-select <number>` in the command bar and press Enter.",
        "- `\\chat-select <session_id>` also works — the id is in "
        "`\\chat-sessions`.",
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

    # What the session holds: how many messages, how large they are, and
    # how many tokens they are worth.  The same numbers the classic
    # console shows, formatted by the same helpers.
    try:
        from chat_manager.stats import format_size, format_tokens

        stats = manager.get_history_stats()
        lines.append(f"| Messages | {stats.message_count} |")
        lines.append(f"| Size | {format_size(stats.total_bytes)} |")
        lines.append(f"| Tokens | {format_tokens(stats)} |")
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("The chat history of the session could not be measured: %s", exc)

    return "\n".join(lines)


def render_chat_user_markdown(manager) -> str:
    """
    Render the current user's settings as Markdown.

    Args:
        manager: An initialized ChatHistoryManager instance.

    Returns:
        str: Markdown document describing every user setting.
    """
    if manager is None or not manager.is_initialized:
        return "# 👤 User Settings\n\nChatHistoryManager is not initialized."

    try:
        settings = manager.get_user_settings()
    except RuntimeError as exc:
        return f"# 👤 User Settings\n\nCould not read the user settings: {exc}"

    user = manager.current_user.username if manager.current_user else "unknown"

    lines = [
        "# 👤 User Settings",
        "",
        f"**User:** `{user}`",
        "",
        "| Setting | Value | Range |",
        "| :--- | :--- | :--- |",
    ]

    for key, spec, value in settings.as_rows():
        if spec.writable:
            accepted = spec.range_text
        else:
            accepted = "read-only"
        lines.append(f"| `{key}` | {value} | {accepted} |")

    lines.extend([
        "",
        "Change a setting with `\\chat-user set <key> <value>`.",
    ])

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

    # The operator named no session: he wants to choose one, so the
    # picker of the sessions is the answer.  The shared handler answers
    # the same way in the classic console.
    if cmd_lower == "\\chat-select":
        from chat_manager.startup import get_chat_manager

        return render_session_picker_markdown(get_chat_manager())

    # The list, info and user views get a dedicated, richer rendering.
    if cmd_lower in ("\\chat-sessions", "\\chat-list", "\\chat-info", "\\chat-user"):
        from chat_manager.startup import get_chat_manager

        manager = get_chat_manager()
        if cmd_lower == "\\chat-info":
            return render_chat_info_markdown(manager)
        if cmd_lower == "\\chat-user":
            return render_chat_user_markdown(manager)
        return render_chat_sessions_markdown(manager)

    try:
        result = handle_chat_command(cmd)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Chat command failed: %s", exc)
        result = f"Error: {exc}"

    return render_command_result_markdown(cmd, result)


__all__ = [
    "render_chat_sessions_markdown",
    "render_session_picker_markdown",
    "render_chat_info_markdown",
    "render_chat_user_markdown",
    "render_command_result_markdown",
    "handle_chat_command_markdown",
]
