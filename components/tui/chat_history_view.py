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


#: The contexts the picker is shown in.  The answer of the operator is
#: the same in both — a number — but what he has to type is not: at the
#: startup of the TUI he types the number alone, and in the middle of a
#: session he types the whole command.
PICKER_CONTEXT_STARTUP = "startup"
PICKER_CONTEXT_COMMAND = "command"

#: How the answer is given, per context.
PICKER_INSTRUCTIONS = {
    PICKER_CONTEXT_STARTUP: [
        "Type the number of the session and press Enter.",
        "Press Enter alone to keep the session that is active now.",
    ],
    PICKER_CONTEXT_COMMAND: [
        "Type `\\chat-select <number>` in the command bar and press Enter.",
    ],
}


def render_session_picker_markdown(
    manager,
    note: str = "",
    context: str = PICKER_CONTEXT_COMMAND,
) -> str:
    """
    Render the numbered picker of the chat sessions.

    The picker is what ``\\chat-select`` opens when the operator names no
    session, and what the TUI opens on at startup.  It is **compact on
    purpose**: the list of :func:`render_chat_sessions_markdown` carries
    the full id of every session, and a row of that table is wider than
    the document pane of the TUI — the id is folded in the middle and
    has to be copied by hand.  The picker leaves the id out and fits.

    The numbering is the numbering of the list: the sessions come from
    the same call, in the same order.  The number the operator sees here
    is the number the startup menu shows, and the number
    ``\\chat-select <number>`` takes.

    The instructions come **before** the table: the table of a user with
    many sessions is longer than the pane, and an instruction below the
    fold is an instruction nobody reads.

    Args:
        manager: An initialized ChatHistoryManager instance.
        note: A line under the header — what went wrong with the answer
            of the operator, for instance.  Empty when there is nothing
            to say.
        context: Where the picker is shown — the startup of the TUI, or
            the command bar of a running one.

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
    ]

    if note:
        lines.extend([f"**{note}**", ""])

    lines.append("**How to select:**")
    for instruction in PICKER_INSTRUCTIONS.get(
        context, PICKER_INSTRUCTIONS[PICKER_CONTEXT_COMMAND]
    ):
        lines.append(f"- {instruction}")
    lines.append("- `\\chat-select <session_id>` also works — the id is in "
                 "`\\chat-sessions`.")
    lines.extend([
        "",
        "| # | Session | Type | Created |",
        "| ---: | :--- | :--- | :--- |",
    ])

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


def render_session_loading_markdown(answer: str = "") -> str:
    """
    Render the pane that is shown while the session is being loaded.

    The answer of the operator is shown here, and not only in the
    command bar: the job that applies it runs in the background, and
    the operator must see that his answer was taken — the digit he
    typed must not wait for the session to be loaded.

    Args:
        answer: What the operator typed into the command bar.

    Returns:
        str: Markdown document with the answer and the state of the work.
    """
    given = (answer or "").strip()
    if given:
        answer_line = f"**Answer:** `{given}`"
    else:
        answer_line = (
            "**Answer:** *(Enter — the session that is active now is kept)*"
        )

    return "\n".join([
        "# 💬 Select a Chat Session",
        "",
        answer_line,
        "",
        "⏳ Loading the session…",
        "",
        "The work runs in the background: the layout keeps painting while "
        "the database and the tokenizer do their part.",
    ])


def render_session_chosen_markdown(session) -> str:
    """
    Render the confirmation of a session that was chosen.

    Args:
        session: The session that is active now.

    Returns:
        str: Markdown document with the confirmation.
    """
    if session is None:
        return "# 💬 Chat Session\n\nNo active session."

    created = (
        session.created_at.strftime("%Y-%m-%d %H:%M")
        if session.created_at else "N/A"
    )

    return "\n".join([
        "# 💬 Chat Session",
        "",
        f"**The agent works in:** {session.session_name} "
        f"({session.session_type.value})",
        "",
        f"- **Created:** {created}",
        f"- **Id:** `{session.session_id}`",
        "",
        "Type `\\chat-info` to see what the session holds, "
        "`\\chat-select` to choose another one.",
    ])


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
    "PICKER_CONTEXT_STARTUP",
    "PICKER_CONTEXT_COMMAND",
    "render_chat_sessions_markdown",
    "render_session_picker_markdown",
    "render_session_loading_markdown",
    "render_session_chosen_markdown",
    "render_chat_info_markdown",
    "render_chat_user_markdown",
    "render_command_result_markdown",
    "handle_chat_command_markdown",
]
