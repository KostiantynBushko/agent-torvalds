"""
The Shift+Enter of the TUI — the line break the operator adds.

The operator was told (2026-11-20) that the Shift+Enter of a terminal
that sends another sequence was left alone, and that the trailing line
break was eaten when the bar was submitted.  Both are closed now.

The question is checked the way the running TUI does it:

  1. **Does the reader know the Shift+Enter of every terminal?**  The
     terminals do not write it the same way: xterm writes
     `ESC [ 13 ; 2 ~`, the kitty keyboard protocol writes
     `ESC [ 27 ; 2 ; 13 ~` and `ESC [ 13 ; 2 u`, and a terminal may add
     a parameter of its own.  The bytes are typed into a real
     pseudo-terminal, and the reader is asked what it saw.

  2. **Does the bar show the line the operator added?**  The bar is
     rendered at the width of a real terminal, and the text is looked
     for on the lines of the screen.

  3. **Does the agent get the text as it was written?**  The
     indentation of a pasted block is a part of the text, and the
     empty last line that the last Shift+Enter left is not.

Usage:
    python investigate/tui-shift-enter/probe_shift_enter.py

The exit code is 0 when every check holds, 1 when one does not.
"""
from __future__ import annotations

import asyncio
import io
import os
import pty
import select
import signal
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from rich.console import Console  # noqa: E402
from rich.live import Live  # noqa: E402

from components.tui.input_reader import NonBlockingInputReader  # noqa: E402
from components.tui.input_text import visible_line_count  # noqa: E402
from components.tui.layout_manager import (  # noqa: E402
    build_torvalds_layout,
    fit_footer,
    input_text_width,
    render_footer,
)
from components.tui.tui_app import TuiApp  # noqa: E402

#: The width of the terminal the checks are made at.
TERMINAL_WIDTH = 100

#: The ways a terminal writes the Shift+Enter.  The key is 13 and the
#: modifier is 2 in all of them -- but the order, the form and the
#: number of the parameters are not the same.
SHIFT_ENTER_SEQUENCES = {
    "xterm": b"\x1b[13;2~",
    "the kitty keyboard protocol": b"\x1b[27;2;13~",
    "the CSI u form": b"\x1b[13;2u",
    "the parameters in the other order": b"\x1b[2;13~",
    "a parameter more": b"\x1b[13;2;3~",
}


def keys_from_pty(data: bytes, seconds: float = 4.0, collect: float = 2.0):
    """Type bytes into a pseudo-terminal and collect the keys of the reader.

    Args:
        data: The bytes to write into the terminal.
        seconds: How long the parent waits for the output.
        collect: How long the reader in the child collects the keys.

    Returns:
        The values of the keys the reader reported.
    """
    script = (
        "import sys, time\n"
        f"sys.path.insert(0, {str(REPO)!r})\n"
        "from components.tui.input_reader import NonBlockingInputReader\n"
        "r = NonBlockingInputReader()\n"
        "r.start()\n"
        "got = []\n"
        "end = time.time() + %r\n" % collect
        +         "while time.time() < end:\n"
        "    if r.is_available():\n"
        "        k = r.poll_key()\n"
        "        if k is not None: got.append(k)\n"
        "    time.sleep(0.02)\n"
        "r.stop()\n"
        "print('KEYS:' + repr(got), flush=True)\n"
    )

    pid, fd = pty.fork()
    if pid == 0:  # pragma: no cover - child process
        os.environ["TERM"] = "xterm"
        os.chdir(str(REPO))
        os.execv(sys.executable, [sys.executable, "-c", script])

    out = b""
    try:
        time.sleep(1.2)
        os.write(fd, data)

        deadline = time.time() + seconds
        while time.time() < deadline:
            ready, _, _ = select.select([fd], [], [], 0.3)
            if not ready:
                continue
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
            if b"KEYS:" in out:
                break
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        os.waitpid(pid, os.WNOHANG)

    text = out.decode("utf-8", "replace")
    if "KEYS:" not in text:
        return []
    return eval(text.split("KEYS:")[1].split("\n")[0])  # noqa: S307


def type_text(app: TuiApp, text: str) -> None:
    """Type a text into the bar of the application, a key at a time.

    Args:
        app: The application the text is typed into.
        text: The text of the operator.
    """
    for character in text:
        app._handle_key(character)


def render(input_buffer: str, cursor_pos=None, width=TERMINAL_WIDTH) -> str:
    """The screen of the TUI with the given text in the command bar.

    Args:
        input_buffer: The text of the operator.
        cursor_pos: The position of the cursor; the end of the text by
            default.
        width: The width of the terminal.

    Returns:
        The text of the screen.
    """
    console = Console(width=width, height=24, file=io.StringIO())
    layout = build_torvalds_layout()
    pos = len(input_buffer) if cursor_pos is None else cursor_pos
    text_width = input_text_width(width)

    panel = render_footer(
        input_buffer=input_buffer,
        cursor_pos=pos,
        width=text_width,
    )
    fit_footer(
        layout,
        console,
        panel,
        False,
        input_lines=visible_line_count(input_buffer, text_width),
    )
    layout["footer"].update(panel)

    with Live(layout, console=console, screen=False, auto_refresh=False) as live:
        live.update(layout, refresh=True)

    return console.file.getvalue()


def sent_to_the_agent(app: TuiApp):
    """The text the last query carried.

    Args:
        app: The application the query is sent from.

    Returns:
        The text of the query, or None when nothing was sent.
    """
    sent = []

    async def handler(cmd, **kwargs):
        sent.append(cmd)
        return "ok", None

    app.prompt_handler_fn = handler

    async def run():
        app._handle_key("ENTER")
        if app._active_query_task is not None:
            await app._active_query_task

    asyncio.run(run())

    return sent[0] if sent else None


def main() -> int:
    """Run every check and report what was seen."""
    failures = []

    # 1. the reader knows the Shift+Enter of every terminal
    print("the Shift+Enter of the terminals")
    for name, sequence in SHIFT_ENTER_SEQUENCES.items():
        keys = keys_from_pty(sequence)
        seen = "SHIFT_ENTER" in keys
        print(f"   {name:32} {sequence!r:18} -> {keys}")
        if not seen:
            failures.append(
                f"the reader did not report the Shift+Enter of {name}: "
                f"{keys!r}"
            )
    print()

    # 2. the bar shows the line the operator added
    app = TuiApp(agent=None, prompt_handler_fn=None)
    type_text(app, "first")
    app._handle_key("SHIFT_ENTER")
    type_text(app, "second")

    if app.state.input_buffer != "first\nsecond":
        failures.append(
            "the Shift+Enter did not add a line to the input: "
            f"{app.state.input_buffer!r}"
        )

    screen = render(app.state.input_buffer, app.state.cursor_pos)
    if "first" not in screen or "second" not in screen:
        failures.append(
            "the line the operator added is not on the screen -- the bar "
            "does not show the whole text"
        )
    print("the bar with two lines")
    for line in screen.splitlines()[-6:]:
        if line.strip():
            print(f"   {line.rstrip()}")
    print()

    # 3. the agent gets the text as it was written
    app = TuiApp(agent=None, prompt_handler_fn=None)
    type_text(app, "    def f():")
    app._handle_key("SHIFT_ENTER")
    type_text(app, "        return 1")

    sent = sent_to_the_agent(app)
    expected = "    def f():\n        return 1"
    print("the text the agent gets")
    print(f"   {sent!r}")
    if sent != expected:
        failures.append(
            f"the agent got {sent!r} and not {expected!r} -- the text was "
            "changed on its way"
        )
    print()

    if failures:
        print("something does not hold:")
        for failure in failures:
            print(f"   - {failure}")
        return 1

    print(
        "everything holds: every terminal is known, the bar shows the line "
        "the operator added, and the agent gets the text as it was written"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
