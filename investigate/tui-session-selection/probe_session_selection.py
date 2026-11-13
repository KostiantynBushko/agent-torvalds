"""
Probe: the TUI never proposes to select a chat session - it loads the last one.

The operator reports that running the TUI agent does not offer a choice of
the chats in the database: the agent loads the last session and starts
working in it.  The classic orchestrator (``agent-torvalds.py``) offers the
menu.

This probe runs **both** entry points on a pty of their own, captures the
byte stream each of them writes, and looks for the markers of the startup
session menu:

    "Session selection:"      - printed by the orchestrator before the menu
    "Available sessions:"     - the first line of the menu itself
    "Select a session [1-"    - the prompt of the menu
    "Chat session:"           - the line that names the session that is used

The first three markers belong to the proposal; the last one is printed by
both modes and tells us that a session was loaded.

The name and the id of the session are **not** printed: they belong to the
operator's own database, and this repository is public.  What the probe
reports is whether a session was loaded, its type, and whether **both**
modes loaded the *same* session - the last comparison is made here, on the
two captures, without the session ever being printed.

The probe answers one question: **does the mode the operator runs present
the menu, and does it load a session without asking?**

Usage:
    python investigate/tui-session-selection/probe_session_selection.py
    python investigate/tui-session-selection/probe_session_selection.py --seconds 12
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

#: The markers of the startup session proposal.
MENU_MARKERS = (
    "Session selection:",
    "Available sessions:",
    "Select a session [1-",
)

#: The marker of the session that was loaded, printed by both modes.
ACTIVE_MARKER = "Chat session:"

#: The ANSI escape sequences are removed before the text is searched: the
#: menu is painted with colours, and the colours break the plain text.
ANSI_RE = re.compile(rb"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07|\x1b[()][A-B]|\r")


def capture(command: list[str], seconds: float, answers: list[bytes]) -> bytes:
    """Run *command* on a pty and return everything it wrote.

    Args:
        command: The command to run.
        seconds: How long the child is given to reach the prompt.
        answers: Bytes written to the pty once the child asks something.

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
    pending = list(answers)
    deadline = time.time() + seconds
    next_answer_at = time.time() + 3.0

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

            # The menu waits for an answer.  Enter keeps the session that
            # is already active - the answer the operator would give when
            # the menu does not interest him.
            if pending and time.time() >= next_answer_at:
                try:
                    os.write(master, pending.pop(0))
                except OSError:
                    break
                next_answer_at = time.time() + 2.0
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


def analyse(label: str, payload: bytes) -> dict:
    """Look for the markers of the menu in a captured byte stream.

    The name and the id of the session are **not** reported: they belong
    to the operator's own database, and this repository is public.  What
    matters for the investigation is *that* a session was loaded, its
    type, and whether both modes loaded the **same** one - and that
    comparison is made on the two captures, without the session itself
    being printed.

    Args:
        label: The name of the mode that was captured.
        payload: The captured bytes.

    Returns:
        A dict with the findings.
    """
    text = ANSI_RE.sub(b"", payload).decode("utf-8", errors="replace")

    menu = [marker for marker in MENU_MARKERS if marker in text]

    active = ""
    match = re.search(r"Chat session:\s*(.+)", text)
    if match:
        active = match.group(1).strip()

    # The session is split into its name and its type, so the name can be
    # dropped and the type kept.
    name, _, session_type = active.rpartition(" (")
    session_type = session_type.rstrip(")")

    return {
        "label": label,
        "menu_markers": menu,
        "menu_offered": bool(menu),
        "session_loaded": bool(active),
        "session_type": session_type or "-",
        "session_fingerprint": hashlib.sha256(name.encode()).hexdigest()[:12],
        "bytes": len(payload),
        "text": text,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seconds",
        type=float,
        default=14.0,
        help="How long each mode is given to reach its prompt.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="The interpreter the agent is run with.",
    )
    args = parser.parse_args()

    findings = []

    # 1. The TUI mode - the mode the operator runs.  Enter answers the
    #    menu: the session that is already active is kept.
    findings.append(
        analyse(
            "TUI  (agent-torvalds-mw.py)",
            capture(
                [args.python, "agent-torvalds-mw.py"],
                args.seconds,
                answers=[b"\n"],
            ),
        )
    )

    # 2. The classic REPL - the mode that is known to propose the menu.
    #    Enter answers the menu (the active session is kept), and
    #    "\exit" leaves the REPL.
    findings.append(
        analyse(
            "REPL (agent-torvalds.py)",
            capture(
                [args.python, "agent-torvalds.py"],
                args.seconds,
                answers=[b"\n", b"\\exit\n"],
            ),
        )
    )

    print()
    print("=" * 72)
    print("Does the mode propose to select a chat session from the database?")
    print("=" * 72)

    for finding in findings:
        print()
        print(f"[{finding['label']}]")
        print(f"  menu proposed        : {'YES' if finding['menu_offered'] else 'NO'}")
        print(f"  markers found        : {finding['menu_markers'] or '-'}")
        print(f"  a session was loaded : {'YES' if finding['session_loaded'] else 'NO'}")
        print(f"  type of that session : {finding['session_type']}")

    tui = findings[0]
    repl = findings[1]

    same = (
        tui["session_loaded"]
        and repl["session_loaded"]
        and tui["session_fingerprint"] == repl["session_fingerprint"]
    )
    print()
    print(f"  both modes loaded the same session: {'YES' if same else 'NO'}")

    print()
    print("=" * 72)
    if tui["menu_offered"] and repl["menu_offered"]:
        verdict = (
            "FIXED: both modes propose the choice - the TUI asks which "
            "session to work in, exactly as the classic REPL does."
        )
    elif not tui["menu_offered"] and repl["menu_offered"]:
        verdict = (
            "CONFIRMED: the TUI loads a session without proposing the "
            "choice, while the classic REPL proposes it."
        )
    else:
        verdict = (
            "NOT CONFIRMED - the markers say something else; read the "
            "table above."
        )
    print(verdict)
    print("=" * 72)


if __name__ == "__main__":
    main()
