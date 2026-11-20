"""
Cross-Platform Non-Blocking Keyboard Input Reader for Torvalds TUI.

Provides non-blocking keystroke polling and key event normalization across
Windows and Linux/POSIX operating systems.

Key mappings normalized:
- "ENTER", "BACKSPACE", "DELETE", "TAB", "ESCAPE"
- "UP", "DOWN", "LEFT", "RIGHT"
- "PGUP", "PGDN", "HOME", "END"
- "SHIFT_ENTER" — the operator adds a line to the input with it
- "CTRL_C", "CTRL_D"
- Regular characters (e.g. 'a', 'Z', '1', '\\', ' ')

A paste is not a keystroke: it arrives as one piece of text, and it is
handed over as one piece — a :class:`PastedText`, which is a string of
its own kind, so the caller can tell a paste from a key that was typed.

The terminal is asked to mark the pastes when the reader starts, and it
is given back when the reader stops.  The mode is asked for on POSIX:
on Windows the mode is a property of the console, and writing it needs
the console handle of the output — the reader does not touch it, and a
paste there arrives as plain text.
"""
import atexit
import os
import sys
import time
from typing import Optional

# Platform detection
IS_WINDOWS = sys.platform.startswith("win")

if IS_WINDOWS:
    import msvcrt
else:
    import select
    import termios
    import tty


#: The marker that closes a paste.  The terminal opens a paste with
#: "\x1b[200~" and closes it with this one, and the text of the
#: clipboard is what is between the two.
PASTE_END = "\x1b[201~"

#: The mode of the terminal that marks the pastes.  Without it a paste
#: arrives as the text itself, and every newline in it is an ENTER.
BRACKETED_PASTE_ON = "\x1b[?2004h"

#: The mode is given back when the reader stops.
BRACKETED_PASTE_OFF = "\x1b[?2004l"

#: How long a paste may wait for its closing marker before the reader
#: gives up on it.  A paste that never closes would swallow everything
#: the operator types after it -- and the operator has no way of
#: knowing that.
PASTE_IDLE_TIMEOUT = 2.0


#: The keys of a control sequence whose final byte says everything.
_CSI_FINAL_KEYS = {
    "A": "UP",
    "B": "DOWN",
    "C": "RIGHT",
    "D": "LEFT",
    "H": "HOME",
    "F": "END",
    "Z": "SHIFT_TAB",
}

#: The keys of a control sequence that ends with a tilde.  The number
#: is the key, and the numbers after the ";" are the modifiers: "2" is
#: Shift, which is how Shift+Enter arrives.
_CSI_TILDE_KEYS = {
    "1": "HOME",
    "2": "INSERT",
    "3": "DELETE",
    "4": "END",
    "5": "PGUP",
    "6": "PGDN",
    "7": "HOME",
    "8": "END",
    "13;2": "SHIFT_ENTER",
    "27;2;13": "SHIFT_ENTER",
}

#: The keys of the "CSI u" form, where the key is the first number and
#: the modifiers follow it.
_CSI_U_KEYS = {
    "13;2": "SHIFT_ENTER",
    "13;5": "CTRL_ENTER",
    "27;2;13": "SHIFT_ENTER",
}


class PastedText(str):
    """The text of a paste.

    A paste is a string like the text the operator types, but it
    arrives in one piece and it may carry newlines.  The reader hands
    it over as a string of its own kind, so the caller can tell a
    paste from a key that was typed.
    """


class NonBlockingInputReader:
    """
    Non-blocking keyboard input reader supporting Windows and POSIX.
    
    Translates platform-specific keystrokes and escape sequences into
    normalized key identifiers or printable unicode strings.
    """

    def __init__(self):
        self._is_active = False
        self._old_termios = None
        self._is_tty = sys.stdin.isatty() if hasattr(sys.stdin, "isatty") else False
        self._pending: str = ""
        self._fd: Optional[int] = None
        # The text of a paste that has not arrived whole yet.  It is
        # None when no paste is being collected.
        self._paste_text: Optional[str] = None
        # When the paste started, so that a paste that never closes is
        # given up on instead of swallowing the keys of the operator.
        self._paste_started: float = 0.0
        # The reader puts the terminal into cbreak mode: the echo is off,
        # and the TUI draws the typed text itself.  An exit that does not
        # go through ``stop()`` would leave the operator with a terminal
        # that shows nothing of what they type -- and that state belongs
        # to the terminal, not to the process, so it outlives the agent.
        # The hook covers every exit that runs the atexit handlers.
        atexit.register(self.stop)

    def start(self) -> None:
        """Initialize non-blocking raw/cbreak terminal mode on POSIX."""
        if self._is_active:
            return
        if not IS_WINDOWS and self._is_tty:
            try:
                self._fd = sys.stdin.fileno()
                self._old_termios = termios.tcgetattr(self._fd)
                tty.setcbreak(self._fd)
            except Exception:
                self._fd = None
        self._pending = ""
        self._paste_text = None
        self._paste_started = 0.0
        self._is_active = True
        # The terminal is asked to mark the pastes.  Without the mark a
        # paste arrives as the text itself, and every newline in it is
        # an ENTER: the command bar would submit the first line of what
        # the operator pasted.
        self._write_terminal(BRACKETED_PASTE_ON)

    def stop(self) -> None:
        """Restore terminal settings on POSIX."""
        if not self._is_active:
            return
        # The mode of the terminal is given back before the fd is
        # forgotten: it belongs to the terminal, and the next program
        # that runs in it has to find it as it was.
        self._write_terminal(BRACKETED_PASTE_OFF)
        if not IS_WINDOWS and self._is_tty and self._old_termios is not None:
            try:
                fd = self._fd if self._fd is not None else sys.stdin.fileno()
                termios.tcsetattr(fd, termios.TCSADRAIN, self._old_termios)
            except Exception:
                pass
            self._old_termios = None
        self._fd = None
        self._pending = ""
        self._paste_text = None
        self._paste_started = 0.0
        self._is_active = False

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    def is_available(self) -> bool:
        """Check if keystroke is currently available in the buffer."""
        if not self._is_tty:
            return False
        if IS_WINDOWS:
            try:
                return msvcrt.kbhit() != 0
            except Exception:
                return False
        else:
            if self._pending:
                return True
            try:
                r, _, _ = select.select([sys.stdin], [], [], 0)
                return bool(r)
            except Exception:
                return False

    def poll_key(self) -> Optional[str]:
        """
        Poll for a single key press without blocking.
        
        Returns:
            Normalized key name (e.g. 'ENTER', 'UP', 'PGUP', 'BACKSPACE')
            or the single character string typed, the text of a paste
            (a :class:`PastedText`), or None if no key pressed.
        """
        if not self.is_available():
            return None

        if IS_WINDOWS:
            return self._poll_windows()
        else:
            return self._poll_posix()

    # ------------------------------------------------------------------
    # The terminal
    # ------------------------------------------------------------------

    def _write_terminal(self, data: str) -> None:
        """Write to the terminal, when there is one.

        Args:
            data: The bytes to write, as a string.
        """
        fd = self._fd
        if fd is None:
            return
        try:
            os.write(fd, data.encode("utf-8"))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Windows
    # ------------------------------------------------------------------

    def _poll_windows(self) -> Optional[str]:
        """Read and decode keystroke on Windows using msvcrt."""
        try:
            ch = msvcrt.getwch()
        except Exception:
            return None

        # Check for special extended key prefixes (\x00 or \xe0)
        if ch in ("\x00", "\xe0"):
            try:
                scan = msvcrt.getwch()
            except Exception:
                return None

            scan_map = {
                "H": "UP",
                "P": "DOWN",
                "K": "LEFT",
                "M": "RIGHT",
                "I": "PGUP",
                "Q": "PGDN",
                "S": "DELETE",
                "G": "HOME",
                "O": "END",
            }
            return scan_map.get(scan, None)

        # Standard control keys
        if ch in ("\r", "\n"):
            return "ENTER"
        if ch == "\x08":
            return "BACKSPACE"
        if ch == "\t":
            return "TAB"
        if ch == "\x1b":
            return self._poll_windows_escape()
        if ch == "\x03":
            return "CTRL_C"
        if ch == "\x04":
            return "CTRL_D"

        # Printable character
        return ch

    def _poll_windows_escape(self) -> Optional[str]:
        """Read and decode an escape sequence on Windows.

        The keys are read only when they are already there: the reader
        never waits for a character that may never come.

        Returns:
            The key of the sequence, or "ESCAPE" when there is none.
        """
        try:
            if not msvcrt.kbhit():
                return "ESCAPE"
            introducer = msvcrt.getwch()
        except Exception:
            return "ESCAPE"

        if introducer != "[":
            return "ESCAPE"

        params = ""
        final = ""
        try:
            while True:
                if not msvcrt.kbhit():
                    return "ESCAPE"
                c = msvcrt.getwch()
                if "0" <= c <= "?":
                    params += c
                    continue
                if " " <= c <= "/":
                    # An intermediate byte: it says nothing about the key.
                    continue
                final = c
                break
        except Exception:
            return "ESCAPE"

        if params == "200" and final == "~":
            return self._collect_paste_windows()
        return self._decode_csi(params, final)

    def _collect_paste_windows(self) -> Optional[str]:
        """Collect the text of a paste on Windows.

        Returns:
            The text of the paste, or None when the paste has not
            arrived whole yet.
        """
        text = ""
        try:
            while True:
                if not msvcrt.kbhit():
                    return None
                ch = msvcrt.getwch()
                if ch != "\x1b":
                    text += ch
                    continue

                # The closing marker of the paste.
                marker = ""
                while len(marker) < len(PASTE_END):
                    if not msvcrt.kbhit():
                        break
                    marker += msvcrt.getwch()
                    if marker.endswith("~"):
                        break
                if marker == PASTE_END[1:]:
                    return PastedText(text)
                text += "\x1b" + marker
        except Exception:
            return None

    # ------------------------------------------------------------------
    # POSIX
    # ------------------------------------------------------------------

    def _read_raw(self) -> str:
        """
        Read a chunk of pending input from the terminal.

        Returns:
            The raw characters read, or an empty string when nothing is
            available.
        """
        if self._pending:
            return self._pending
        return self._read_fd()

    def _read_fd(self) -> str:
        """
        Read a chunk of input straight from the terminal.

        Uses ``os.read`` on the raw file descriptor rather than
        ``sys.stdin.read(1)``: in cbreak mode the buffered reader waits for a
        full line, which would stall the render loop and swallow every
        character after the first one.

        The pending buffer is not touched: the caller is the one that
        decides what to do with the chunk -- the collector of a paste
        keeps the tail of the closing marker, and it has to read past
        it.

        Returns:
            The raw characters read, or an empty string when nothing is
            available.
        """
        fd = self._fd if self._fd is not None else None
        if fd is None:
            try:
                fd = sys.stdin.fileno()
            except Exception:
                return ""

        try:
            data = os.read(fd, 1024)
        except (BlockingIOError, InterruptedError):
            return ""
        except Exception:
            return ""

        if not data:
            return ""

        return data.decode("utf-8", "replace")

    def _next_char(self) -> str:
        """
        Return the next character from the pending buffer.

        Returns:
            A single character, or an empty string when the buffer is empty.
        """
        if not self._pending:
            self._pending = self._read_raw()
        if not self._pending:
            return ""
        return self._pending[0]

    def _consume(self, count: int = 1) -> None:
        """
        Drop the first ``count`` characters from the pending buffer.

        Args:
            count: Number of characters to discard.
        """
        self._pending = self._pending[count:]

    def _poll_posix(self) -> Optional[str]:
        """Read and decode keystroke on POSIX using the raw terminal fd."""
        # A paste that was cut in two by the reader: the rest of it is
        # collected before anything else is read.
        if self._paste_text is not None:
            return self._collect_paste()

        ch = self._next_char()
        if not ch:
            return None
        self._consume(1)

        # Standard control keys
        if ch in ("\r", "\n"):
            return "ENTER"
        if ch in ("\x7f", "\x08"):
            return "BACKSPACE"
        if ch == "\t":
            return "TAB"
        if ch == "\x03":
            return "CTRL_C"
        if ch == "\x04":
            return "CTRL_D"

        # An escape sequence: the cursor keys, Shift+Enter, and the
        # marker that opens a paste.
        if ch == "\x1b":
            return self._poll_escape()

        return ch

    def _poll_escape(self) -> Optional[str]:
        """Read and decode an escape sequence on POSIX.

        The sequence is read as a whole: the parameter bytes, the
        intermediate bytes and the final byte.  A sequence the reader
        does not know is an escape, as it always was.

        Returns:
            The key of the sequence, or "ESCAPE" when there is none.
        """
        # The rest of the sequence may not have arrived yet: a key
        # pressed on its own is an escape.
        r, _, _ = select.select([sys.stdin], [], [], 0.05)
        if not r and not self._pending:
            return "ESCAPE"

        introducer = self._next_char()
        if not introducer:
            return "ESCAPE"
        self._consume(1)

        if introducer != "[":
            return "ESCAPE"

        params = ""
        final = ""
        while True:
            c = self._next_char()
            if not c:
                return "ESCAPE"
            self._consume(1)
            if "0" <= c <= "?":
                params += c
                continue
            if " " <= c <= "/":
                # An intermediate byte: it is part of the sequence and
                # it says nothing about the key.
                continue
            final = c
            break

        if params == "200" and final == "~":
            # The marker that opens a paste.
            return self._collect_paste()
        return self._decode_csi(params, final)

    def _decode_csi(self, params: str, final: str) -> Optional[str]:
        """The key of a control sequence, from its parameters.

        Args:
            params: The parameter bytes of the sequence.
            final: The final byte of the sequence.

        Returns:
            The key of the sequence, or "ESCAPE" when it is unknown.
        """
        if final in _CSI_FINAL_KEYS:
            return _CSI_FINAL_KEYS[final]
        if final == "~":
            return _CSI_TILDE_KEYS.get(params, "ESCAPE")
        if final == "u":
            return _CSI_U_KEYS.get(params, "ESCAPE")
        return "ESCAPE"

    def _collect_paste(self) -> Optional[str]:
        """Collect the text of a paste.

        The terminal sends a paste between two markers: the text is
        read until the closing marker arrives.  A paste that is longer
        than the buffer of the reader arrives in pieces, and the reader
        keeps the text it has until the rest comes.

        Returns:
            The text of the paste, or None when the paste has not
            arrived whole yet.
        """
        if self._paste_text is None:
            self._paste_text = ""
            self._paste_started = time.monotonic()

        while True:
            index = self._pending.find(PASTE_END)
            if index != -1:
                text = self._paste_text + self._pending[:index]
                self._consume(index + len(PASTE_END))
                self._paste_text = None
                return PastedText(text)

            # The closing marker has not arrived yet.  It may be cut in
            # two by the buffer of the reader, so its tail is kept and
            # the rest is waited for.
            keep = len(PASTE_END) - 1
            if len(self._pending) > keep:
                self._paste_text += self._pending[:-keep]
                self._pending = self._pending[-keep:]

            try:
                r, _, _ = select.select([sys.stdin], [], [], 0.05)
            except Exception:
                return None
            if not r:
                # Nothing came for a while: the paste is not going to
                # close.  What was collected is handed over, and the
                # keys the operator types after it are his again.
                if time.monotonic() - self._paste_started > PASTE_IDLE_TIMEOUT:
                    text = self._paste_text + self._pending
                    self._pending = ""
                    self._paste_text = None
                    return PastedText(text)
                return None
            data = self._read_fd()
            if not data:
                return None
            self._pending += data
            self._paste_started = time.monotonic()
