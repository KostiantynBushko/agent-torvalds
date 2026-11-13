"""
Probe: the TUI asks which chat session to work in — and the answer works.

The operator reported that running the TUI agent did not offer a choice
of the chats in the database: the agent loaded the last session and
started working in it.

This probe runs **both** entry points on a pty of their own and drives
them the way an operator does:

1. it waits for the **question** of the agent — the menu of the classic
   console, the picker of the TUI;
2. it writes the **answer** — the number of a session;
3. it looks for the **outcome** in the byte stream the operator
   receives.

The answer is written when the question appears, and not before: the
TUI puts the terminal into cbreak mode with ``TCSAFLUSH`` when it
starts, and a key that arrives before that is discarded on purpose.

The name and the id of the session are **not** printed: they belong to
the operator's own database, and this repository is public.  What the
probe reports is whether a session was chosen, its type, and whether
**both** modes chose the same one — the last comparison is made here,
on the two captures, without the session ever being printed.

Usage:
    python investigate/tui-session-selection/probe_session_selection.py
    python investigate/tui-session-selection/probe_session_selection.py --seconds 20
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import os
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import termios
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))

# The probe reads the sessions of the operator to answer with the number
# of the session that is active.  The repository has to be on the path:
# the script lives two folders deep, and Python puts the folder of the
# script on the path, not the working directory.
if REPO not in sys.path:
    sys.path.insert(0, REPO)

#: The question of the **classic console**: the menu is plain text,
#: printed in the terminal before the REPL.
CLASSIC_QUESTION = "Available sessions:"

#: The question of the **multi-window TUI**: the picker is a Markdown
#: document in the document pane of the layout.
TUI_QUESTION = "Select a Chat Session"

#: The outcome of the two front-ends.
CLASSIC_ANSWER_MARKER = "Switched to session"
TUI_ANSWER_MARKER = "The agent works in"

#: The number of the session that is typed into both.  It is the number
#: of the session that is **already active**, so the probe leaves the
#: active session of the operator the way it found it.
SESSION_NUMBER = "1"


def active_session_number() -> str:
    """The number of the session that is active right now.

    The probe answers with it, so the session that is active when the
    probe is over is the session that was active when it started.

    Activating a session bumps the ``updated_at`` of the sessions of the
    user - it creates, renames and deletes nothing, and it changes
    nothing but the timestamp.

    Returns:
        The number of the active session, or ``"1"`` when it cannot be
        read.
    """
    from chat_manager.startup import (
        initialize_chat_manager,
        shutdown_chat_manager,
    )

    manager = initialize_chat_manager()
    try:
        sessions = manager.list_sessions()
        active = manager.get_active_session()
        if active is not None:
            for index, session in enumerate(sessions, start=1):
                if session.session_id == active.session_id:
                    return str(index)
    finally:
        # The singleton of the module is cleared as well: a manager that
        # was shut down and still handed out is a manager that answers
        # nothing.
        shutdown_chat_manager()

    return "1"

#: The ANSI escape sequences are removed before the text is searched: the
#: menu is painted with colours, and the colours break the plain text.
ANSI_RE = re.compile(rb"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[()][A-B]|\r")


def capture(
    command: list[str],
    seconds: float,
    question: str,
    answer: bytes,
    until: str = "",
) -> bytes:
    """Run *command* on a pty and answer its question.

    Args:
        command: The command to run.
        seconds: How long the child is given.
        question: The text that means the agent is asking.
        answer: The bytes that answer it.
        until: The text that ends the capture - the outcome.  The
            capture stops a moment after it appears, so the probe does
            not wait for the whole budget when the answer was accepted.

    Returns:
        The captured byte stream.
    """
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))

    child = subprocess.Popen(
        command,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        cwd=REPO,
        env=dict(os.environ),
        close_fds=True,
        start_new_session=True,
    )
    os.close(slave)

    chunks: list[bytes] = []
    seen = b""
    answered = False
    grace_until = None
    deadline = time.time() + seconds

    try:
        while time.time() < deadline:
            ready, _, _ = select.select([master], [], [], 0.2)
            if ready:
                try:
                    data = os.read(master, 65536)
                except OSError:
                    break
                if not data:
                    break
                chunks.append(data)
                seen += data

                # The answer goes in when the question is on the screen.
                if not answered and question.encode() in seen:
                    os.write(master, answer)
                    answered = True

                # The outcome ends the capture - with a moment of grace
                # for the frame that carries it.
                if until and until.encode() in seen:
                    grace_until = time.time() + 1.5
                    if time.time() >= grace_until:
                        break
    finally:
        if child.poll() is None:
            try:
                os.killpg(os.getpgid(child.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(child.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    child.kill()
        os.close(master)

    return b"".join(chunks)


def analyse(label: str, payload: bytes, question: str, outcome: str) -> dict:
    """Look for the question and the outcome in a captured byte stream.

    The name and the id of the session are **not** reported: they belong
    to the operator's own database, and this repository is public.  What
    matters is *that* a session was chosen, its type, and whether both
    modes chose the **same** one — and that comparison is made on the
    two captures, without the session ever being printed.

    Args:
        label: The name of the mode that was captured.
        payload: The captured bytes.
        question: The text that means the agent is asking.
        outcome: The text that means the session was chosen.

    Returns:
        A dict with the findings.
    """
    text = ANSI_RE.sub(b"", payload).decode("utf-8", errors="replace")

    active = ""
    match = re.search(r"Chat session:\s*(.+)", text)
    if match:
        active = match.group(1).strip()

    # The session is split into its name and its type, so the name can
    # be dropped and the type kept.
    name, _, session_type = active.rpartition(" (")
    session_type = session_type.rstrip(")")

    chosen = ""
    match = re.search(r"works in:\s*(.+)", text)
    if match:
        chosen = match.group(1).strip()
    match = re.search(r"Switched to session:\s*'(.+?)'", text)
    if match:
        chosen = match.group(1).strip()

    return {
        "label": label,
        "asked": question in text,
        "outcome": outcome in text,
        "session_loaded": bool(active),
        "session_type": session_type or "-",
        "session_fingerprint": hashlib.sha256(name.encode()).hexdigest()[:12],
        "chosen": chosen,
        "bytes": len(payload),
        "text": text,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seconds",
        type=float,
        default=90.0,
        help=(
            "How long each mode is given.  The TUI needs the time: the "
            "tool retriever embeds every tool before the layout is drawn."
        ),
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="The interpreter the agent is run with.",
    )
    args = parser.parse_args()

    # The answer is the number of the session that is active now, so the
    # probe leaves the operator's active session the way it found it.
    global SESSION_NUMBER
    SESSION_NUMBER = active_session_number()

    findings = []

    # 1. The TUI mode - the mode the operator runs.
    findings.append(
        analyse(
            "TUI  (agent-torvalds-mw.py)",
            capture(
                [args.python, "agent-torvalds-mw.py"],
                args.seconds,
                question=TUI_QUESTION,
                answer=f"{SESSION_NUMBER}\r".encode(),
                until=TUI_ANSWER_MARKER,
            ),
            question=TUI_QUESTION,
            outcome=TUI_ANSWER_MARKER,
        )
    )

    # 2. The classic REPL - the menu in the terminal.
    findings.append(
        analyse(
            "REPL (agent-torvalds.py)",
            capture(
                [args.python, "agent-torvalds.py"],
                args.seconds,
                question=CLASSIC_QUESTION,
                answer=f"{SESSION_NUMBER}\n".encode(),
                until=CLASSIC_ANSWER_MARKER,
            ),
            question=CLASSIC_QUESTION,
            outcome=CLASSIC_ANSWER_MARKER,
        )
    )

    print()
    print("=" * 72)
    print("Does the mode ask which chat session to work in - and does the answer work?")
    print("=" * 72)
    print(f"the answer is the number of the session that is active: {SESSION_NUMBER}")

    for finding in findings:
        print()
        print(f"[{finding['label']}]")
        print(f"  the operator was asked   : {'YES' if finding['asked'] else 'NO'}")
        print(f"  the answer was accepted  : {'YES' if finding['outcome'] else 'NO'}")
        print(f"  a session was loaded     : {'YES' if finding['session_loaded'] else 'NO'}")
        print(f"  type of that session     : {finding['session_type']}")

    tui = findings[0]
    repl = findings[1]

    print()
    print("=" * 72)
    if tui["asked"] and tui["outcome"] and repl["asked"] and repl["outcome"]:
        verdict = (
            "FIXED: both modes ask which session to work in, and the answer "
            "switches the session in both."
        )
    elif not tui["asked"] and repl["asked"]:
        verdict = (
            "CONFIRMED: the TUI loads a session without proposing the "
            "choice, while the classic REPL proposes it."
        )
    else:
        verdict = (
            "NOT CONFIRMED - the markers say something else; read the table above."
        )
    print(verdict)
    print("=" * 72)


if __name__ == "__main__":
    main()
