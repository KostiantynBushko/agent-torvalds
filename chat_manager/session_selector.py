"""Interactive startup session selection for ChatHistoryManager.

Implements the startup flow required by the implementation plan:

  1. Identify the current user (OS username).
  2. Load that user's sessions from the database.
  3. Propose the previously active session (restored from the DB).
  4. Present the sessions as a numbered list.
  5. Let the user select an existing session, create a new one, or skip.
  6. Persist the choice as the user's active session.

The selector is intentionally free of terminal dependencies so it can be
tested headlessly: the input function and the output function are injectable.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from chat_manager.session import Session, SessionType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------

def format_session_list(sessions: list[Session]) -> str:
    """Render the session list as a numbered menu.

    Args:
        sessions: Sessions belonging to the current user.

    Returns:
        A formatted, numbered listing of the sessions.
    """
    if not sessions:
        return "No sessions available."

    lines = ["Available sessions:"]
    for index, session in enumerate(sessions, start=1):
        marker = "*" if session.is_active else " "
        created = (
            session.created_at.strftime("%Y-%m-%d %H:%M")
            if session.created_at
            else "N/A"
        )
        lines.append(
            f"  {marker} {index}. {session.session_name} "
            f"[{session.session_type.value}] (created {created})"
        )
    lines.append("  * = currently active")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def select_session_interactively(
    manager,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
) -> Optional[Session]:
    """Interactively choose the session to use for this run.

    The user can:
      - pick an existing session by its number,
      - type ``new <name>`` to create a custom session,
      - press Enter to keep the currently active (or default) session.

    Args:
        manager: An initialized ChatHistoryManager instance.
        input_func: Callable used to read user input.
        output_func: Callable used to write prompts and results.

    Returns:
        The selected Session, or None if the session list is empty and the
        user declined to create one.
    """
    if manager is None or not manager.is_initialized:
        output_func("ChatHistoryManager not initialized.")
        return None

    while True:
        sessions = manager.list_sessions()

        if not sessions:
            output_func("No sessions found.")
            answer = input_func("Create a new session? [name, or Enter to skip]: ").strip()
            if not answer:
                return None
            session = _create_session(manager, answer)
            if session is not None:
                output_func(f"Created and activated session: '{session.session_name}'")
                return session
            continue

        active = manager.get_active_session()
        if active is not None:
            output_func(f"Active session: '{active.session_name}'")
        else:
            output_func("No active session yet.")

        output_func(format_session_list(sessions))
        output_func(
            "Select a session [1-%d], 'new <name>' to create one, or Enter to keep "
            "the current one:" % len(sessions)
        )

        try:
            raw = input_func("> ").strip()
        except (EOFError, KeyboardInterrupt):
            output_func("\nSelection aborted, keeping the current session.")
            return active

        if not raw:
            # Keep the currently active session (or fall back to the first).
            return active or sessions[0]

        lowered = raw.lower()

        if lowered == "new" or lowered.startswith("new "):
            name = raw[3:].strip()
            if not name:
                output_func("A name is required to create a session.")
                continue
            session = _create_session(manager, name)
            if session is not None:
                output_func(f"Created and activated session: '{session.session_name}'")
                return session
            continue

        try:
            index = int(raw)
        except ValueError:
            output_func(f"'{raw}' is not a valid selection.")
            continue

        if not 1 <= index <= len(sessions):
            output_func(f"Please enter a number between 1 and {len(sessions)}.")
            continue

        chosen = sessions[index - 1]
        activated = manager.switch_session(chosen.session_id)
        if activated is None:
            output_func(f"Could not activate session '{chosen.session_name}'.")
            continue

        output_func(f"Switched to session: '{activated.session_name}'")
        return activated


def _create_session(manager, name: str) -> Optional[Session]:
    """Create a custom session and make it active.

    Args:
        manager: An initialized ChatHistoryManager instance.
        name: Human-readable name for the new session.

    Returns:
        The newly created and activated Session, or None on failure.
    """
    try:
        session = manager.create_session(name=name, session_type=SessionType.CUSTOM)
    except Exception as e:
        logger.error(f"Failed to create session '{name}': {e}")
        return None

    return manager.switch_session(session.session_id)
