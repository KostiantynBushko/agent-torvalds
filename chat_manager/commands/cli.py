"""CLI commands for ChatHistoryManager.

Provides interactive commands for session management:
- \\chat-sessions / \\chat-list: List all sessions
- \\chat-select <id|n>: Switch to a session, by its id or by its number
- \\chat-create <name> [type]: Create a new session
- \\chat-delete <id>: Delete a session
- \\chat-rename <id> <new name>: Rename a session
- \\chat-info: Show details of the active session
- \\chat-clear: Clear the active session's message history
- \\chat-export [path]: Print the content of the active session, or write it to a file

and for the user's own configuration:
- \\chat-user: Show the current user's settings
- \\chat-user get <key>: Show one setting
- \\chat-user set <key> <value>: Change one setting
- \\chat-user help: List the settings and their accepted values
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from chat_manager.export import (
    FORMAT_JSON,
    FORMAT_TEXT,
    SOURCE_BUFFER,
    SOURCE_NOUN,
    SOURCE_STORED,
    render_session,
    resolve_path,
    write_export,
)
from chat_manager.session import Session, SessionType
from chat_manager.stats import format_size, format_tokens
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
    lines.append(
        f"{'#':<4} {'ID':<38} {'Name':<20} {'Type':<10} {'Active':<8} {'Created'}"
    )
    lines.append("-" * 104)

    for index, s in enumerate(sessions, start=1):
        active_marker = "✓" if s.is_active else " "
        created = s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else "N/A"
        lines.append(
            f"{index:<4} {s.session_id:<38} {s.session_name:<20} "
            f"{s.session_type.value:<10} {active_marker:<8} {created}"
        )

    lines.append("")
    lines.append("Switch to a session with \\chat-select <number> (or <id>).")

    return "\n".join(lines)


def resolve_session_reference(
    manager: ChatHistoryManager, reference: str
) -> Optional[Session]:
    """Resolve a reference to a session: its id, or its number in the list.

    The operator is offered the sessions as a numbered list, so the
    number is what he types - the id is 36 characters long and has to be
    copied out of a table.  The number is the position in the list of
    the manager, which is the same list (and the same order) the startup
    menu shows.

    A reference that is neither a known id nor a number in the list
    resolves to None.

    Args:
        manager: The ChatHistoryManager instance.
        reference: The id of a session, or its number.

    Returns:
        The Session the reference points at, or None.
    """
    reference = (reference or "").strip()
    if not reference:
        return None

    if reference.isdigit():
        sessions = manager.list_sessions()
        index = int(reference)
        if 1 <= index <= len(sessions):
            return sessions[index - 1]
        return None

    return manager.get_session(reference)


def cmd_chat_select(manager: ChatHistoryManager, reference: str) -> str:
    """Switch to a different session.

    The session is named by its id, or by its number in the list of the
    sessions of the user - the number the startup menu and the picker
    of the TUI show.

    Args:
        manager: The ChatHistoryManager instance.
        reference: The id of the session to activate, or its number.

    Returns:
        Status message.
    """
    if not manager.is_initialized:
        return "ChatHistoryManager not initialized."

    reference = (reference or "").strip()

    if reference.isdigit():
        session = resolve_session_reference(manager, reference)
        if session is None:
            count = len(manager.list_sessions())
            return (
                f"There is no session {reference} - "
                f"the list holds {count} session(s)."
            )
        activated = manager.switch_session(session.session_id)
    else:
        # The id is passed on untouched: the manager is the one that
        # decides whether the session exists and belongs to the user.
        activated = manager.switch_session(reference)

    if activated is None:
        return f"Session '{reference}' not found."

    return f"Switched to session: '{activated.session_name}' ({activated.session_type.value})"


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

    # What the session holds: how many messages, how large they are, and
    # how many tokens they are worth.  A session that cannot be measured is
    # still a session — the rest of the information is worth showing, and
    # the reason is worth a line in the log.
    try:
        stats = manager.get_history_stats()
        lines.append(f"  Messages: {stats.message_count}")
        lines.append(f"  Size:     {format_size(stats.total_bytes)}")
        lines.append(f"  Tokens:   {format_tokens(stats)}")
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("The chat history of the session could not be measured: %s", exc)

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


def cmd_chat_export(
    manager: ChatHistoryManager,
    path: str | None = None,
    source: str = SOURCE_STORED,
    output_format: str = FORMAT_TEXT,
) -> str:
    """Print the content of the active session, or write it to a file.

    Two things are called "the session", and the export can carry either
    one:

    * ``SOURCE_STORED`` — everything the session keeps.  It grows with
      every turn and is never trimmed;
    * ``SOURCE_BUFFER`` — the tail of the history that survives the
      chat-token limit, and is what the model is actually sent.

    The header of the export says which one it carries, so a file is
    never a mystery.

    And it can be written in two formats: the text a person reads, and
    the JSON a program reads.

    Without a path the content is returned, and the caller prints it.
    With one it is written to that file, and the caller is told where.

    Args:
        manager: The ChatHistoryManager instance.
        path: The file to write the export to.  ``None`` prints it.
        source: Which part of the session to export.
        output_format: The format of the export — ``FORMAT_TEXT`` or
            ``FORMAT_JSON``.

    Returns:
        The content of the session, or a status message.
    """
    if not manager.is_initialized:
        return "ChatHistoryManager not initialized."

    session = manager.get_active_session()
    if session is None:
        return "No active session."

    if source == SOURCE_BUFFER:
        try:
            messages = list(manager.get_messages())
        except RuntimeError as exc:
            return f"Could not read the buffer of the session: {exc}"
    else:
        messages = manager.get_stored_messages()

    text = render_session(session, messages, source, output_format)

    if path is None:
        return text

    target = resolve_path(path)

    try:
        written = write_export(target, text)
    except OSError as exc:
        return f"Could not write '{target}': {exc}"

    noun = SOURCE_NOUN.get(source, "messages")
    as_json = "as JSON " if output_format == FORMAT_JSON else ""

    return (
        f"Wrote {len(messages)} {noun} {as_json}({format_size(written)}) "
        f"to '{target}'."
    )


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
