"""
The input bar of the TUI — one line, or three.

The operator asked (2026-11-20) for a command bar that takes more
than one line:

  1. the hot commands on the right go away while there is text in the
     bar, and they come back when the last character is deleted;
  2. the operator withdrew the Shift+Enter on 2026-11-20: the bar
     carries no line-break key, and the lines of the input come from a
     paste;
  3. a paste arrives in one piece; a paste that is longer than the
     window ends with its last lines on the screen, and the operator
     can walk the cursor back into the text and edit it.

Everything is checked the way the running TUI does it — the real
layout, the real panels, the real reader, the real key handling:

  1. **Are the hot commands hidden while the operator writes?**  The
     screen is rendered the way the app renders it, and the commands
     are looked for in it.

  2. **Is the Shift+Enter dropped?**  The reader is driven from a
     pseudo-terminal with the sequence a terminal sends, and the bar
     must not change: there is no line-break key.

  3. **Does a paste arrive in one piece?**  The reader is driven with
     a bracketed paste, and the text it reports is put into the real
     app: the view of the input has to end with the last lines of the
     paste, and the text above them has to be there to be edited.

Usage:
    python investigate/tui-multiline-input/probe_multiline_input.py

The exit code is 0 when every check holds, 1 when one does not.
"""
from __future__ import annotations

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

from components.tui.input_reader import (  # noqa: E402
    BRACKETED_PASTE_OFF,
    BRACKETED_PASTE_ON,
    NonBlockingInputReader,
    PastedText,
)
from components.tui.input_text import (  # noqa: E402
    MAX_INPUT_LINES,
    cursor_line,
    visible_line_count,
    visible_window,
)
from components.tui.layout_manager import (  # noqa: E402
    build_torvalds_layout,
    fit_footer,
    render_footer,
)
from components.tui.tui_app import TuiApp  # noqa: E402


#: The text of a paste that is longer than the window of the input.
LONG_PASTE = "\n".join("line %d" % number for number in range(1, 11))


def render(input_buffer: str, cursor_pos: int, width: int = 120) -> str:
    """Render the TUI the way the app does, and return the screen.

    Args:
        input_buffer: The text in the command bar.
        cursor_pos: The position of the cursor in the text.
        width: The width of the terminal.

    Returns:
        The text of the screen.
    """
    console = Console(width=width, height=24, file=io.StringIO())
    layout = build_torvalds_layout()
    panel = render_footer(input_buffer=input_buffer, cursor_pos=cursor_pos)
    fit_footer(
        layout,
        console,
        panel,
        False,
        input_lines=visible_line_count(input_buffer),
    )
    layout["footer"].update(panel)

    with Live(layout, console=console, screen=False, auto_refresh=False) as live:
        live.update(layout, refresh=True)

    return console.file.getvalue()


def keys_from_pty(data: bytes, seconds: float = 3.0):
    """Type bytes into a pseudo-terminal and collect the keys of the reader.

    Args:
        data: The bytes to write into the terminal.
        seconds: How long the reader is given to collect the keys.

    Returns:
        A tuple of the keys the reader reported and the raw output of
        the terminal.
    """
    script = (
        "import sys, time\n"
        "sys.path.insert(0, %r)\n" % str(REPO)
        + "from components.tui.input_reader import NonBlockingInputReader\n"
        "r = NonBlockingInputReader()\n"
        "r.start()\n"
        "got = []\n"
        "end = time.time() + 2\n"
        "while time.time() < end:\n"
        "    if r.is_available():\n"
        "        k = r.poll_key()\n"
        "        if k is not None: got.append((type(k).__name__, k))\n"
        "    time.sleep(0.02)\n"
        "r.stop()\n"
        "print('KEYS:' + repr(got), flush=True)\n"
    )

    pid, fd = pty.fork()
    if pid == 0:  # pragma: no cover - the child process
        os.environ["TERM"] = "xterm"
        os.chdir(str(REPO))
        os.execv(sys.executable, [sys.executable, "-c", script])

    out = b""
    try:
        time.sleep(1.2)
        os.write(fd, data)

        deadline = time.time() + seconds
        while time.time() < deadline:
            r, _, _ = select.select([fd], [], [], 0.3)
            if not r:
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
        return [], text
    keys_line = text.split("KEYS:")[1].split("\n")[0]
    return eval(keys_line), text  # noqa: S307 - a literal from our own child


def check_the_hot_commands() -> bool:
    """The hot commands go away while there is text, and they come back.

    Returns:
        True when they do.
    """
    print("the hot commands of the bar")

    empty = render("", 0, width=240)
    written = render("hello", 5, width=240)

    print("   with an empty bar   : %s"
          % ("shown" if "\\stats" in empty else "hidden"))
    print("   with text in the bar : %s"
          % ("shown" if "\\stats" in written else "hidden"))

    app = TuiApp(agent=None, prompt_handler_fn=None)
    app._handle_key("x")
    app._handle_key("BACKSPACE")
    back = render(app.state.input_buffer, app.state.cursor_pos, width=240)
    print("   after the last character is deleted : %s"
          % ("shown" if "\\stats" in back else "hidden"))

    ok = "\\stats" in empty and "\\stats" not in written and "\\stats" in back
    if not ok:
        print("   the hot commands did not do what they must")
    return ok


def check_the_shift_enter_is_dropped() -> bool:
    """The Shift+Enter is not a key: the bar has no line-break key.

    Returns:
        True when the sequence changes nothing.
    """
    print()
    print("the Shift+Enter")

    keys, _ = keys_from_pty(b"\x1b[13;2~")
    values = [value for _, value in keys]
    print("   the reader reports : %r" % (values,))

    app = TuiApp(agent=None, prompt_handler_fn=None)
    app._handle_key("a")
    app._handle_key("ESCAPE")
    app._handle_key("b")

    screen = render(app.state.input_buffer, app.state.cursor_pos)
    print("   the input holds     : %r" % (app.state.input_buffer,))
    print("   the bar shows       :")
    for line in screen.splitlines()[-4:]:
        print("     " + line)

    ok = "SHIFT_ENTER" not in values and app.state.input_buffer == "ab"
    if not ok:
        print("   the Shift+Enter was not dropped")
    return ok


def check_the_paste() -> bool:
    """A paste arrives in one piece and the view scrolls to its end.

    Returns:
        True when it does.
    """
    print()
    print("the paste")

    keys, raw = keys_from_pty(
        b"\x1b[200~" + LONG_PASTE.encode("utf-8") + b"\x1b[201~"
    )
    pastes = [value for kind, value in keys if kind == "PastedText"]
    print("   the paste arrives in %d piece(s)" % len(pastes))
    print("   the terminal is asked to mark the pastes : %s"
          % ("yes" if BRACKETED_PASTE_ON in raw else "no"))
    print("   the terminal is given back              : %s"
          % ("yes" if BRACKETED_PASTE_OFF in raw else "no"))

    app = TuiApp(agent=None, prompt_handler_fn=None)
    app._handle_key(PastedText(LONG_PASTE))

    screen = render(app.state.input_buffer, app.state.cursor_pos)
    print("   the bar shows       :")
    for line in screen.splitlines()[-5:]:
        print("     " + line)

    lines, row, _ = visible_window(app.state.input_buffer, app.state.cursor_pos)
    print("   the window holds    : %r" % (lines,))
    print("   the cursor is on the last line : %s" % (row == len(lines) - 1,))

    # The text above the window is still there, and it can be edited.
    app._handle_key("UP")
    app._handle_key("UP")
    on_line = cursor_line(app.state.input_buffer, app.state.cursor_pos)
    app._handle_key("X")
    edited = "line 8X" in app.state.input_buffer
    print("   the cursor walked back to the line %r" % (on_line,))
    print("   the text above the window can be edited : %s" % (edited,))

    ok = (
        len(pastes) == 1
        and pastes[0] == LONG_PASTE
        and BRACKETED_PASTE_ON in raw
        and BRACKETED_PASTE_OFF in raw
        and lines == ["line 8", "line 9", "line 10"]
        and len(lines) == MAX_INPUT_LINES
        and edited
    )
    if not ok:
        print("   the paste did not do what it must")
    return ok


def main() -> int:
    """Run every check.

    Returns:
        The exit code: 0 when every check holds.
    """
    commands_ok = check_the_hot_commands()
    shift_ok = check_the_shift_enter_is_dropped()
    paste_ok = check_the_paste()

    print()
    if commands_ok and shift_ok and paste_ok:
        print("everything holds: the bar takes three lines, and the hot "
              "commands come and go with the text")
        return 0

    print("something does not hold")
    return 1


if __name__ == "__main__":
    sys.exit(main())
