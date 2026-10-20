"""
Cross-Platform Non-Blocking Keyboard Input Reader for Torvalds TUI.

Provides non-blocking keystroke polling and key event normalization across
Windows and Linux/POSIX operating systems.

Key mappings normalized:
- "ENTER", "BACKSPACE", "DELETE", "TAB", "ESCAPE"
- "UP", "DOWN", "LEFT", "RIGHT"
- "PGUP", "PGDN", "HOME", "END"
- "CTRL_C", "CTRL_D"
- Regular characters (e.g. 'a', 'Z', '1', '\\', ' ')
"""
import os
import sys
from typing import Optional

# Platform detection
IS_WINDOWS = sys.platform.startswith("win")

if IS_WINDOWS:
    import msvcrt
else:
    import select
    import termios
    import tty


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
        self._is_active = True

    def stop(self) -> None:
        """Restore terminal settings on POSIX."""
        if not self._is_active:
            return
        if not IS_WINDOWS and self._is_tty and self._old_termios is not None:
            try:
                fd = self._fd if self._fd is not None else sys.stdin.fileno()
                termios.tcsetattr(fd, termios.TCSADRAIN, self._old_termios)
            except Exception:
                pass
            self._old_termios = None
        self._fd = None
        self._pending = ""
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
            or the single character string typed, or None if no key pressed.
        """
        if not self.is_available():
            return None

        if IS_WINDOWS:
            return self._poll_windows()
        else:
            return self._poll_posix()

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
            return "ESCAPE"
        if ch == "\x03":
            return "CTRL_C"
        if ch == "\x04":
            return "CTRL_D"

        # Printable character
        return ch

    def _read_raw(self) -> str:
        """
        Read a chunk of pending input from the terminal.

        Uses ``os.read`` on the raw file descriptor rather than
        ``sys.stdin.read(1)``: in cbreak mode the buffered reader waits for a
        full line, which would stall the render loop and swallow every
        character after the first one.

        Returns:
            The raw characters read, or an empty string when nothing is
            available.
        """
        if self._pending:
            return self._pending

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

        # Check for escape sequences (arrows, home, end, pgup, pgdn, delete)
        if ch == "\x1b":
            # Check if additional characters follow immediately
            r, _, _ = select.select([sys.stdin], [], [], 0.05)
            if not r and not self._pending:
                return "ESCAPE"

            seq = self._next_char()
            if not seq:
                return "ESCAPE"
            self._consume(1)

            if seq == "[":
                code = self._next_char()
                if not code:
                    return "ESCAPE"
                self._consume(1)
                if code == "A":
                    return "UP"
                elif code == "B":
                    return "DOWN"
                elif code == "C":
                    return "RIGHT"
                elif code == "D":
                    return "LEFT"
                elif code == "H":
                    return "HOME"
                elif code == "F":
                    return "END"
                elif code in ("1", "2", "3", "4", "5", "6"):
                    # Extended codes like \x1b[3~ (delete), \x1b[5~ (pgup), \x1b[6~ (pgdn)
                    next_ch = self._next_char()
                    if not next_ch:
                        return "ESCAPE"
                    self._consume(1)
                    if next_ch == "~":
                        if code == "3":
                            return "DELETE"
                        elif code == "5":
                            return "PGUP"
                        elif code == "6":
                            return "PGDN"
                        elif code == "1":
                            return "HOME"
                        elif code == "4":
                            return "END"
            return "ESCAPE"

        return ch
