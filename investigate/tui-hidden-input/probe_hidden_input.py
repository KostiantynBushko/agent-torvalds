"""
The typed text in the TUI footer.

The operator reported (2026-11-09):

  > *after agent response sometime by typint I do not see what is typed
  > looks like it is hidded even after leaving agent app the typing in
  > terminal is hidden*

Two things are checked here, and both are checked the way the running
TUI does it — the real layout, the real panels, the real reader:

  1. **Is the typed text on the screen?**  The footer partition is a
     fixed number of lines tall, and a panel that is taller than its
     partition is cropped from the bottom.  The HITL panel carries the
     question of the agent *and* the line the answer is typed on, and
     the answer is the last line of the panel — so the answer is the
     first thing to go.

  2. **Is the terminal given back?**  The reader puts the terminal into
     cbreak mode: the echo is off, and the TUI draws the typed text
     itself.  That state belongs to the *terminal*, not to the process,
     so it outlives the agent: an exit that does not give the terminal
     back leaves the operator with a terminal that shows nothing of
     what they type.

Usage:
    python investigate/tui-hidden-input/probe_hidden_input.py

The exit code is 0 when both hold, 1 when either does not.
"""
from __future__ import annotations

import io
import os
import pty
import sys
import termios
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from rich.console import Console  # noqa: E402
from rich.live import Live  # noqa: E402

from components.tui.input_reader import NonBlockingInputReader  # noqa: E402
from components.tui.layout_manager import (  # noqa: E402
    build_torvalds_layout,
    render_footer,
)

try:  # the fix of 2026-11-09
    from components.tui.layout_manager import fit_footer  # noqa: E402
except ImportError:  # the code before the fix
    fit_footer = None

#: The text an operator types while a question of the agent is waiting.
TYPED = "rm -rf [a-z] now"


def render_the_tui(width: int = 120, height: int = 24) -> str:
    """Render the TUI with a question waiting, and return the screen.

    Args:
        width: The width of the terminal.
        height: The height of the terminal.

    Returns:
        The text of the screen.
    """
    console = Console(width=width, height=height, file=io.StringIO())
    layout = build_torvalds_layout()
    panel = render_footer(
        input_buffer=TYPED,
        cursor_pos=len(TYPED),
        hitl_active=True,
        hitl_prompt="Which file should I read?",
    )
    if fit_footer is not None:
        # The app gives the footer the room the panel needs.  Without
        # it, the partition keeps the height it was built with and the
        # panel is cropped.
        fit_footer(layout, console, panel, True)
    layout["footer"].update(panel)

    with Live(layout, console=console, screen=False, auto_refresh=False) as live:
        live.update(layout, refresh=True)

    return console.file.getvalue()


def echo_is_on(fd: int) -> bool:
    """Whether the terminal echoes what is typed.

    Args:
        fd: The file descriptor of the terminal.

    Returns:
        ``True`` when the echo is on.
    """
    try:
        attributes = termios.tcgetattr(fd)
    except Exception:
        return True
    return bool(attributes[3] & termios.ECHO)


def check_the_typed_text() -> bool:
    """Whether the typed text reaches the screen.

    Returns:
        ``True`` when the operator sees what they type.
    """
    screen = render_the_tui()

    print("--- the footer of the TUI, with a question waiting ---")
    for line in screen.splitlines():
        if "AGENT QUESTION" in line or "Answer:" in line:
            print("   " + line.strip()[:120])

    visible = TYPED in screen
    print()
    print("the typed text      : %r" % TYPED)
    print("the operator sees it: %s" % ("yes" if visible else "NO"))
    return visible


def check_the_terminal() -> bool:
    """Whether the reader gives the terminal back.

    The check runs against a pty of its own, so the terminal of the
    operator is never touched — a probe that leaves a mute terminal
    behind is not a probe.

    Returns:
        ``True`` when the terminal is as it was found.
    """
    print("--- the terminal ---")

    master, slave = pty.openpty()
    saved_stdin = sys.stdin
    stream = None
    try:
        stream = os.fdopen(slave, "rb", buffering=0)
        sys.stdin = stream

        before = echo_is_on(slave)
        reader = NonBlockingInputReader()
        reader.start()
        during = echo_is_on(slave)
        reader.stop()
        after = echo_is_on(slave)
    finally:
        sys.stdin = saved_stdin
        # The stream owns the slave descriptor once it was opened.
        if stream is not None:
            stream.close()
        else:
            os.close(slave)
        os.close(master)

    print("   echo before the reader : %s" % ("on" if before else "off"))
    print("   echo while the TUI runs: %s" % ("on" if during else "off"))
    print("   echo after the reader  : %s" % ("on" if after else "off"))

    if during:
        print("   the reader did not switch the echo off — the TUI would "
              "print every key twice")
    if not after:
        print("   the terminal was left mute — the operator would type into "
              "a terminal that shows nothing")

    return after and not during


def main() -> int:
    """Run both checks.

    Returns:
        The exit code: 0 when both hold.
    """
    typed_ok = check_the_typed_text()
    terminal_ok = check_the_terminal()

    print()
    if typed_ok and terminal_ok:
        print(
            "both hold: the operator sees what they type, and the "
            "terminal is given back"
        )
        return 0

    print("something does not hold")
    return 1


if __name__ == "__main__":
    sys.exit(main())
