"""Probe: the choice of the chat session must not freeze the TUI.

The operator reported that the TUI hangs for a couple of seconds when
he picks a chat session, and that the digit he typed only appears when
the session is loaded.

The probe measures the three moments of the choice:

  * **the Enter key** — what the loop that paints the layout pays for
    the answer.  This is the number that decides whether the screen
    stands still;
  * **the confirmation** — when the pane says which session the agent
    works in now;
  * **the count of the header** — when the number of the messages of the
    session reaches the header.  The count is read from the whole
    history of the session, and it is the slowest part of the work.

It also counts the **frames painted while the work is done**: a frozen
layout paints none.

The probe switches to a session of the operator's own database and
**restores the session that was active before it ran**.

Run with:
    .venv/bin/python investigate/tui-session-selection/probe_session_selection_background.py
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import sys
import time
from unittest.mock import MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))

# The probe talks to the database of the operator: the repository has to
# be on the path.  The script lives two folders deep, and Python puts
# the folder of the script on the path, not the working directory.
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from rich.console import Console

from chat_manager.startup import initialize_chat_manager, shutdown_chat_manager
from components.tui.state_bridge import TuiState
from components.tui.tui_app import TuiApp

logging.disable(logging.CRITICAL)


def _header(title: str) -> None:
    """Print a header of a section of the probe."""
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def _longest_history(manager, sessions):
    """The session of the user that holds the most messages.

    The size of the history is asked of the database directly: reading
    every history of the user would take minutes, and the probe only
    needs to know which one is the heaviest.

    Args:
        manager: The chat history manager of the operator.
        sessions: The sessions of the operator.

    Returns:
        The session with the largest history — the active one when the
        database cannot answer.
    """
    from sqlalchemy import text

    try:
        with manager._db._engine.connect() as connection:
            rows = connection.execute(
                text("select key, length(value::text) from chatstore")
            ).fetchall()
    except Exception as exc:
        print(f"The sizes of the histories are unknown: {exc}")
        return manager.get_active_session() or sessions[0]

    sizes = {key: size for key, size in rows}
    return max(sessions, key=lambda s: sizes.get(s.chat_key, 0))


async def _probe() -> None:
    """Run the probe."""
    manager = initialize_chat_manager()

    sessions = manager.list_sessions()
    active_before = manager.get_active_session()
    print(f"The user has {len(sessions)} sessions.")
    print(f"The active one is: {active_before.session_name}")

    # The session with the longest history: it is the one that takes the
    # most time to read.
    longest = _longest_history(manager, sessions)
    print(f"The longest history: {longest.session_name}")

    app = TuiApp(
        agent=MagicMock(),
        prompt_handler_fn=MagicMock(),
        state=TuiState(),
        console=Console(file=io.StringIO()),
        select_session_at_startup=True,
    )

    app._show_session_picker()

    # The frames of the layout: one every 20 ms while the work is done.
    frames: list[float] = []

    async def _heartbeat() -> None:
        """Stand in for the render loop of the TUI."""
        while True:
            frames.append(time.monotonic())
            await asyncio.sleep(0.02)

    beat = asyncio.create_task(_heartbeat())

    number = str(sessions.index(longest) + 1)
    app.state.input_buffer = number

    _header("The answer is taken")
    start = time.monotonic()
    app._handle_enter_pressed()
    taken = time.monotonic() - start

    print(f"The Enter key cost the loop: {taken * 1000:.1f} ms")
    print(
        "The digit is on the screen at once: "
        f"{'**Answer:** `' + number + '`' in app.state.markdown_content}"
    )
    print(f"The command bar is empty: {app.state.input_buffer == ''}")

    _header("The session is loaded")
    # The version of the TUI that applies the answer in the loop has no
    # job to wait for: the work is already done, and it was done in the
    # loop.
    job = getattr(app, "_session_task", None)
    if job is not None:
        await job
    confirmed = time.monotonic() - start

    print(f"The pane named the session after {confirmed:.2f} s")
    print(f"The frames painted while it was loaded: {len(frames)}")

    _header("What one turn of the agent costs")
    # The agent asks the buffer for its messages every time a request
    # is built.  This is what a turn pays.
    started = time.monotonic()
    messages = manager.get_messages()
    turn = time.monotonic() - started
    print(f"The messages of the session: {len(messages)}")
    print(f"One turn of the agent: {turn:.2f} s")

    _header("The count of the header arrives")
    refresh = getattr(app, "_state_refresh_task", None)
    if refresh is not None:
        await refresh
    counted = time.monotonic() - start

    print(f"The count of the header arrived after {counted:.2f} s")
    print(f"The frames painted in the whole run: {len(frames)}")
    print(
        "The session that is active now: "
        f"{manager.get_active_session().session_name}"
    )

    beat.cancel()

    # The operator's own session is put back.
    if active_before is not None:
        manager.switch_session(active_before.session_id)
        print(
            "The session that was active before is active again: "
            f"{manager.get_active_session().session_name}"
        )


if __name__ == "__main__":
    try:
        asyncio.run(_probe())
    finally:
        shutdown_chat_manager()
