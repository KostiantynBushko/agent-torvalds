"""
Console Input Module for HITL (Human-in-the-Loop)

Provides async terminal input methods with timeout support.  All methods
return sensible defaults when the user does not respond within the
specified timeout period.

The default timeout is ``-1``, which means *no timeout*: the prompt waits
for the human indefinitely.  See ``components.hitl_timeout.py``.

Readline Integration
--------------------
This module initializes Python's ``readline`` library at import time,
enabling full cursor navigation (left/right arrows), multiline editing
(proper backspace across lines), and command history (up/down arrows)
for all console input prompts.

Usage:
    from components.console_input_module import ConsoleInputModule

    console_input = ConsoleInputModule()

    # Text prompt
    name = await console_input.prompt("What is your name?", default="Anonymous", timeout=30)

    # Wait forever for the answer
    name = await console_input.prompt("What is your name?", default="Anonymous")

    # Yes/No confirmation
    ok = await console_input.confirm("Proceed with installation?", default_yes=True, timeout=30)

    # Menu selection
    choice = await console_input.menu("Choose a tool:", ["vim", "nano", "emacs"], timeout=30)

    # Password
    pwd = await console_input.password(timeout=60)
"""

from __future__ import annotations

import asyncio
import atexit
import os
import select
import sys
import time
from typing import List, Optional

from rich.console import Console

from components.hitl_timeout import NO_TIMEOUT, normalize_timeout

try:  # POSIX
    import termios
except ImportError:  # pragma: no cover - not a POSIX system
    termios = None  # type: ignore[assignment]

try:  # Windows
    import msvcrt
except ImportError:  # pragma: no cover - not Windows
    msvcrt = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Readline initialization for cursor navigation and multiline editing
# ---------------------------------------------------------------------------
#
# Python's readline module provides:
#   - Cursor movement with arrow keys (left/right to navigate within a line)
#   - Multiline editing support (proper backspace across lines)
#   - Command history (up/down arrows to navigate previous commands)
#   - Emacs-style line editing (Ctrl+A, Ctrl+E, Ctrl+K, etc.)
#
# This is initialized once at module import time so all input() calls
# throughout the application benefit from readline capabilities.
# ---------------------------------------------------------------------------

_readline_initialized = False


def init_readline() -> None:
    """Initialize readline for enhanced console input.

    Enables cursor navigation, multiline editing, and command history
    for all subsequent input() calls.  Safe to call multiple times.
    """
    global _readline_initialized
    if _readline_initialized:
        return

    try:
        import readline
        import rlcompleter

        # Use readline history file if available (persistent history)
        history_file = None
        try:
            import os
            from pathlib import Path

            # Store history in user's home directory
            home = Path.home()
            history_dir = home / ".cache" / "agent-torvalds"
            history_dir.mkdir(parents=True, exist_ok=True)
            history_file = str(history_dir / "input_history")
        except Exception:
            pass

        # Load history from file if it exists
        if history_file and os.path.exists(history_file):
            readline.read_history_file(history_file)
            # Increase history size limit
            readline.set_history_length(1000)

        # Configure readline for better editing experience
        readline.parse_and_bind("tab: complete")

        # Enable emacs-style key bindings (default on Unix)
        # This gives us:
        #   Ctrl+A - move to beginning of line
        #   Ctrl+E - move to end of line
        #   Ctrl+K - kill to end of line
        #   Ctrl+U - kill to beginning of line
        #   Ctrl+W - kill previous word
        #   Ctrl+Y - yank (paste) killed text
        #   Alt+Backspace - kill previous word
        readline.parse_and_bind("set editing-mode emacs")

        # Enable multiline editing - allows proper cursor movement
        # across multiple lines when text wraps
        readline.parse_and_bind("set horizontal-scroll-mode off")

        # Save history on exit
        import atexit

        def _save_history() -> None:
            if history_file:
                try:
                    readline.write_history_file(history_file)
                except Exception:
                    pass

        atexit.register(_save_history)

        _readline_initialized = True
    except ImportError:
        # readline is not available on Windows by default;
        # fall back gracefully without it
        pass


# Initialize readline at module import time
init_readline()


# ---------------------------------------------------------------------------
# Masked input — a secret that is never shown
# ---------------------------------------------------------------------------
#
# ``getpass`` is deliberately **not** used here.  It opens ``/dev/tty``,
# which fails when the agent runs without a controlling terminal (a
# service, a container, a test harness), and it can leave the terminal with
# the echo flag cleared when the process dies inside the prompt — the
# operator is then left with a mute terminal that has to be fixed with
# ``stty sane``.
#
# The reader below switches the echo off with ``termios`` and switches it
# on again in a ``finally`` block, so neither an exception, nor a Ctrl-C,
# nor a timeout can leave the terminal mute.  An ``atexit`` hook covers a
# clean shutdown (the agent's SIGINT/SIGTERM handler ends in
# ``sys.exit()``).  The characters themselves are never shown: each one
# is echoed as an asterisk, so the operator can see that *something* was
# typed.

#: The terminal attributes saved while the echo is switched off.  The
#: ``atexit`` hook puts them back, so a shutdown inside the prompt cannot
#: leave the operator with a mute terminal.
_SAVED_TERMINAL_STATE: Optional[list] = None


def _restore_terminal_state() -> None:
    """Put the terminal back the way it was found.

    Safe to call when nothing was saved, and safe to call twice.
    """
    global _SAVED_TERMINAL_STATE
    state = _SAVED_TERMINAL_STATE
    if state is None:
        return
    _SAVED_TERMINAL_STATE = None
    try:
        if termios is not None and sys.stdin is not None:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, state)
    except Exception:
        pass


atexit.register(_restore_terminal_state)


def _read_chars(fd: int, deadline: Optional[float]) -> str:
    """Read the typed characters one at a time, until the operator hits Enter.

    The read is *polled*, so a deadline can be honoured: when it passes
    the function returns what was typed so far and the caller restores the
    terminal.  A blocking read could not do that — it would keep the
    terminal mute until the operator pressed a key.

    Args:
        fd: The file descriptor of the terminal.
        deadline: The moment the read gives up, or ``None`` for "wait
            forever".

    Returns:
        The characters that were typed.
    """
    chars: List[str] = []

    while True:
        if deadline is not None and time.monotonic() >= deadline:
            break

        wait = 0.1
        if deadline is not None:
            wait = max(0.0, min(wait, deadline - time.monotonic()))

        try:
            ready, _, _ = select.select([fd], [], [], wait)
        except (OSError, ValueError):
            break
        if not ready:
            continue

        try:
            data = os.read(fd, 1)
        except OSError:
            break
        if not data:
            break  # EOF

        char = data.decode("utf-8", errors="ignore")

        if char in ("\n", "\r"):
            break
        if char == "\x03":  # Ctrl-C
            raise KeyboardInterrupt
        if char == "\x04":  # Ctrl-D
            break
        if char in ("\x7f", "\x08"):  # Backspace
            if chars:
                chars.pop()
                sys.stdout.write("\b \b")
                sys.stdout.flush()
            continue
        if char < " ":  # any other control character
            continue

        chars.append(char)
        # The character itself is never shown — only its length.
        sys.stdout.write("*")
        sys.stdout.flush()

    return "".join(chars)


def read_masked(prompt: str, deadline: Optional[float] = None) -> str:
    """Read a secret from the terminal, hidden behind asterisks.

    Args:
        prompt: The prompt to show.
        deadline: The moment the read gives up, or ``None`` for "wait
            forever".

    Returns:
        What the operator typed.  An empty string on EOF, on Ctrl-D or
        when the deadline passes.
    """
    global _SAVED_TERMINAL_STATE

    sys.stdout.write(prompt)
    sys.stdout.flush()

    stream = sys.stdin
    try:
        interactive = bool(stream) and stream.isatty()
    except Exception:
        interactive = False

    if not interactive or termios is None:
        # Not a terminal — a pipe, a service, a test harness.  There is
        # nothing to hide the value from, and there is no echo to switch
        # off.
        try:
            line = stream.readline() if stream else ""
        except Exception:
            return ""
        return line.rstrip("\n") if isinstance(line, str) else ""

    fd = stream.fileno()
    saved = termios.tcgetattr(fd)
    _SAVED_TERMINAL_STATE = saved
    value = ""
    try:
        hidden = termios.tcgetattr(fd)
        hidden[3] &= ~termios.ECHO
        termios.tcsetattr(fd, termios.TCSADRAIN, hidden)
        value = _read_chars(fd, deadline)
    finally:
        # The terminal is given back exactly as it was found — whatever
        # happened above.
        _restore_terminal_state()
        sys.stdout.write("\n")
        sys.stdout.flush()

    return value


class ConsoleInputModule:
    """Console-based input module for HITL interactions.

    Provides async input methods with timeout support.  All methods return
    default values on timeout, EOF, or keyboard interrupt.

    Attributes:
        console: Rich Console instance used for coloured output.
    """

    #: The consumer renders the question itself (see
    #: ``EventConsumer._render_question``), so this module only shows the
    #: short prompt.  A module that owns its own layout — a dialog, a
    #: command bar — sets this to ``True`` and asks for the question.
    renders_question = False

    def __init__(self, console: Optional[Console] = None) -> None:
        self.console = console or Console()

    # ------------------------------------------------------------------
    # Public input methods
    # ------------------------------------------------------------------

    @staticmethod
    async def prompt(
        message: str,
        default: str = "",
        timeout: int = NO_TIMEOUT,
    ) -> str:
        """Prompt user for text input via console with timeout.

        Args:
            message: Question / prompt to display.
            default: Value returned when the user times out or submits
                     an empty response.
            timeout: Seconds to wait for input.  ``-1`` (the default) means
                     *no timeout*: wait for the human indefinitely.

        Returns:
            User's response or *default* on timeout / empty input.
        """
        response, _ = await ConsoleInputModule.prompt_with_status(
            message=message, default=default, timeout=timeout
        )
        return response

    @staticmethod
    async def prompt_with_status(
        message: str,
        default: str = "",
        timeout: int = NO_TIMEOUT,
    ) -> tuple[str, bool]:
        """Prompt the user and report whether the prompt timed out.

        ``prompt()`` cannot distinguish "the user typed the default answer"
        from "the user did not answer at all" — both return *default*.  The
        HITL consumer needs that distinction to log timeouts correctly.

        Args:
            message: Question / prompt to display.
            default: Value returned when the user times out or submits
                     an empty response.
            timeout: Seconds to wait for input.  ``-1`` (the default) means
                     *no timeout*: wait for the human indefinitely.

        Returns:
            ``(response, was_timeout)`` tuple.
        """
        loop = asyncio.get_event_loop()

        def _ask() -> str:
            try:
                result = input(message)
                return result if isinstance(result, str) else default
            except (EOFError, KeyboardInterrupt):
                return default

        try:
            # ``None`` means "wait forever" for asyncio — that is what the
            # no-timeout convention (-1) translates to.
            response = await asyncio.wait_for(
                loop.run_in_executor(None, _ask),
                timeout=normalize_timeout(timeout),
            )
            if isinstance(response, str):
                if response.strip():
                    return response, False
                # An empty answer is treated as "no answer given".
                return default, True
            return default, True
        except asyncio.TimeoutError:
            return default, True

    async def confirm_with_status(
        self,
        message: str = "",
        default_yes: bool = True,
        timeout: int = NO_TIMEOUT,
    ) -> tuple[bool, bool]:
        """Ask for yes / no confirmation and report whether the human answered.

        ``confirm()`` cannot tell "the operator pressed Enter" from "the
        operator said no" — both give the default.  The HITL consumer needs
        that distinction, so it records a timeout separately from a "no".

        Args:
            message: The *complete* prompt to display.
            default_yes: Default when the human does not answer.
            timeout: Seconds to wait.  ``-1`` (the default) means *no
                     timeout*: wait for the human indefinitely.

        Returns:
            ``(confirmed, was_timeout)`` tuple.
        """
        response = await self.prompt(message, default="", timeout=timeout)
        if not response.strip():
            # No answer at all — the operator pressed Enter, or the prompt
            # timed out.  Either way it is not a "no".
            return default_yes, True
        return response.strip().lower() in ("y", "yes"), False

    async def confirm(
        self,
        message: str,
        default_yes: bool = True,
        timeout: int = NO_TIMEOUT,
    ) -> bool:
        """Ask for yes / no confirmation via console.

        Args:
            message: Question to display.
            default_yes: Default when the user times out or submits
                         an empty response.
            timeout: Seconds to wait.  ``-1`` (the default) means *no
                     timeout*: wait for the human indefinitely.

        Returns:
            ``True`` for yes, ``False`` otherwise.
        """
        suffix = " [Y/n]" if default_yes else " [y/N]"
        confirmed, _ = await self.confirm_with_status(
            message=f"{message}{suffix}",
            default_yes=default_yes,
            timeout=timeout,
        )
        return confirmed

    async def menu(
        self,
        message: str,
        options: List[str],
        timeout: int = NO_TIMEOUT,
    ) -> str:
        """Display a numbered menu and return the selected option.

        Args:
            message: Menu title / question.
            options: List of choice strings.
            timeout: Seconds to wait.  ``-1`` (the default) means *no
                     timeout*: wait for the human indefinitely.

        Returns:
            The selected option string, or the first option on timeout
            / invalid input.
        """
        self.console.print(f"\n{message}")
        for i, opt in enumerate(options, 1):
            self.console.print(f"  [bold]{i}[/bold]. {opt}")

        response = await self.__class__.prompt(
            "Select option [1]: ", default="1", timeout=timeout
        )

        try:
            idx = int(response) - 1
            if 0 <= idx < len(options):
                return options[idx]
        except ValueError:
            pass

        return options[0]

    async def menu_with_status(
        self,
        message: str = "Select option [1]: ",
        options: List[str] = None,
        timeout: int = NO_TIMEOUT,
    ) -> tuple[str, bool]:
        """Show a numbered menu and report whether the human answered.

        Unlike :meth:`menu`, this method does **not** print the menu: the
        caller renders the question and its options, so they cannot appear
        twice.

        Args:
            message: The prompt to display.  The options are *not* printed
                     here — the caller has already shown them.
            options: List of choice strings.
            timeout: Seconds to wait.  ``-1`` (the default) means *no
                     timeout*: wait for the human indefinitely.

        Returns:
            ``(selected_option, was_timeout)`` tuple.  An empty answer
            selects the first option and counts as "no answer".
        """
        choices = list(options or [])
        if not choices:
            return "", True

        response, was_timeout = await ConsoleInputModule.prompt_with_status(
            message=message, default="", timeout=timeout
        )
        if was_timeout or not response.strip():
            # The operator pressed Enter — the first option is the default.
            return choices[0], True

        try:
            index = int(response.strip()) - 1
            if 0 <= index < len(choices):
                return choices[index], False
        except ValueError:
            pass

        # Not a number, or out of range: the first option, as before.
        return choices[0], False

    async def password(
        self,
        message: str = "Enter password: ",
        timeout: int = NO_TIMEOUT,
    ) -> str:
        """Prompt for a secret, hidden behind asterisks.

        The value is read by :func:`read_masked`, which does **not** use
        ``getpass`` — see the note there.  The operator sees one asterisk
        per character, never the secret itself.

        Args:
            message: Prompt text shown to the user.
            timeout: Seconds to wait.  ``-1`` (the default) means *no
                     timeout*: wait for the human indefinitely.

        Returns:
            The entered secret or ``""`` on timeout, EOF or Ctrl-C.
        """
        loop = asyncio.get_event_loop()
        seconds = normalize_timeout(timeout)
        deadline = None if seconds is None else time.monotonic() + seconds

        def _ask() -> str:
            try:
                return read_masked(message, deadline)
            except (EOFError, KeyboardInterrupt):
                return ""

        try:
            # ``None`` means "wait forever" for asyncio.
            response = await asyncio.wait_for(
                loop.run_in_executor(None, _ask),
                timeout=seconds,
            )
            return response if isinstance(response, str) else ""
        except asyncio.TimeoutError:
            return ""
