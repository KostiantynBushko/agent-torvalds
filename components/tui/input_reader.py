"""
Cross-Platform Non-Blocking Keyboard Input Reader for Torvalds TUI.

Provides non-blocking keystroke polling and key event normalization across
Windows and Linux/POSIX operating systems.

Key mappings normalized:
- "ENTER", "BACKSPACE", "DELETE", "TAB", "ESCAPE"
- "UP", "DOWN", "LEFT", "RIGHT"
- "PGUP", "PGDN", "HOME", "END"
- "CTRL_C", "CTRL_D"
- "CTRL_A" ... "CTRL_Z" -- the control chords.  A terminal sends them
  as the control byte itself, and the reader names them.
- "SHIFT_UP", "CTRL_UP", "ALT_UP" ... -- the *modified* keys.  The
  modifier is a part of the name, because a key with a modifier and the
  same key without it are two different keys.
- "F1" ... "F20" -- the function keys
- "ALT_a" ... -- the Alt chords.  The terminal sends the ESC, and then
  the key itself.
- Regular characters (e.g. 'a', 'Z', '1', '\\', ' ')

The name of a key is what a binding is written against, and it is
always the same word: the modifiers are named in a fixed order -- the
Ctrl, the Alt, the Shift -- in front of the name of the key.

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
from typing import List, Optional

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

#: How long the reader waits for the rest of a control sequence that
#: has not arrived whole yet.  A key pressed on its own is an escape,
#: and the operator has to wait this long to be told so.
ESCAPE_TIMEOUT = 0.05


#: The keys of a control sequence whose final byte says everything.
_CSI_FINAL_KEYS = {
    "A": "UP",
    "B": "DOWN",
    "C": "RIGHT",
    "D": "LEFT",
    "H": "HOME",
    "F": "END",
    "Z": "SHIFT_TAB",
    # The function keys of the "CSI" form: "ESC [ 1 ; 5 P" is the
    # Ctrl+F1, and the final byte is the "P".
    "P": "F1",
    "Q": "F2",
    "R": "F3",
    "S": "F4",
}

#: The keys of a control sequence that ends with a tilde.  The number
#: is the key, and the numbers after the ";" are the modifiers.
_CSI_TILDE_KEYS = {
    "1": "HOME",
    "2": "INSERT",
    "3": "DELETE",
    "4": "END",
    "5": "PGUP",
    "6": "PGDN",
    "7": "HOME",
    "8": "END",
}

#: The function keys of the tilde form: "ESC [ 15 ~" is the F5, and
#: "ESC [ 24 ~" is the F12.  The numbers that are not there are the
#: ones no terminal sends -- the F6 is the "17" and not the "16".
_FUNCTION_KEYS = {
    "11": "F1",
    "12": "F2",
    "13": "F3",
    "14": "F4",
    "15": "F5",
    "17": "F6",
    "18": "F7",
    "19": "F8",
    "20": "F9",
    "21": "F10",
    "23": "F11",
    "24": "F12",
    "25": "F13",
    "26": "F14",
    "28": "F15",
    "29": "F16",
    "31": "F17",
    "32": "F18",
    "33": "F19",
    "34": "F20",
}

#: The keys of a control sequence that starts with "ESC O" -- the
#: application cursor mode, and the first four function keys.
_SS3_KEYS = {
    "A": "UP",
    "B": "DOWN",
    "C": "RIGHT",
    "D": "LEFT",
    "H": "HOME",
    "F": "END",
    "P": "F1",
    "Q": "F2",
    "R": "F3",
    "S": "F4",
}

#: The keys of the "CSI u" form, where the key is the first number and
#: the modifiers follow it.
_CSI_U_KEYS = {
    "13": "ENTER",
}

#: The bits of the modifier of a key.  The terminal sends the modifier
#: as the number of the last parameter of the sequence, and the number
#: is the sum of these bits, plus one.
MOD_SHIFT = 1
MOD_ALT = 2
MOD_CTRL = 4

#: The names of the modifiers, in the order they are written in a name.
#: The order is fixed, so that the name of a key is always the same
#: word -- the name of a key is what a binding is written against.
_MOD_NAMES = ((MOD_CTRL, "CTRL"), (MOD_ALT, "ALT"), (MOD_SHIFT, "SHIFT"))


def _modifier_mask(parameter: str) -> int:
    """The bits of the modifier a control sequence carries.

    The terminal sends the modifier as a number that is the sum of the
    bits of the modifiers, plus one: "ESC [ 1 ; 5 A" is the Ctrl+Up,
    and the "5" is the Ctrl.

    Args:
        parameter: The last parameter of the sequence.

    Returns:
        The bits of the modifier, and zero when there is none.
    """
    try:
        value = int(parameter)
    except (TypeError, ValueError):
        return 0
    if value <= 1:
        return 0
    return value - 1


def _name_with_modifiers(name: str, mask: int) -> str:
    """The name of a key with the modifiers it was pressed with.

    Args:
        name: The name of the key, without a modifier.
        mask: The bits of the modifiers.

    Returns:
        The name of the key, with the modifiers in front of it.
    """
    if not mask:
        return name
    parts = [label for bit, label in _MOD_NAMES if mask & bit]
    return "_".join(parts + [name])


def _control_key(character: str) -> Optional[str]:
    """The name of a control character.

    A terminal does not send "Ctrl+T" as a chord of its own: it sends
    the control byte, 0x14.  The byte is the key, and the reader has
    to name it -- otherwise a hot-key has nothing to bind.

    The four bytes that are not there are the ones another key already
    claimed: the 0x08 is the backspace, the 0x09 is the tab, and the
    0x0A and the 0x0D are the enter.

    Args:
        character: The character the terminal sent.

    Returns:
        The name of the control chord, or None when the character is
        not one.
    """
    code = ord(character)
    if code < 0x01 or code > 0x1A:
        return None
    return "CTRL_" + chr(ord("A") + code - 1)


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
        # When the control sequence that is not whole yet was first
        # seen, so that a sequence the terminal never finishes is given
        # up on instead of waiting for the rest of it forever.
        self._escape_started: float = 0.0
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
        self._escape_started = 0.0
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
        self._escape_started = 0.0
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

    def poll_keys(self) -> List[str]:
        """The keys that are waiting at the terminal, in one piece.

        The terminal is read once, and the keys that are in the buffer
        are parsed out of it.  A key that arrives while they are parsed
        is left for the next call.

        The reader waits for the terminal to go quiet nowhere: a
        terminal repeats a key that is held, and a reader that waits
        for the quiet would never give the screen back -- the cursor
        of the operator would stand still while the key was held, and
        would jump to the place it belongs to when the key was
        released.

        Returns:
            The keys, in the order the terminal sent them.  An empty
            list when nothing is waiting.
        """
        if not self.is_available():
            return []

        if IS_WINDOWS:
            keys = []
            while msvcrt.kbhit():
                key = self._poll_windows()
                if key is None:
                    break
                keys.append(key)
            return keys

        self._read_available()

        keys = []
        while True:
            key = self._poll_buffered()
            if key is None:
                break
            keys.append(key)
        return keys

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

        # The other control characters are the Ctrl chords: the
        # terminal sends them as the control byte itself.
        control = _control_key(ch)
        if control is not None:
            return control

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

    def _read_available(self) -> None:
        """Read what the terminal has right now, and keep it.

        The terminal is not waited for: the bytes that are there are
        taken, and the bytes that arrive later are taken by the next
        call.
        """
        try:
            r, _, _ = select.select([sys.stdin], [], [], 0)
        except Exception:
            return
        if not r:
            return
        data = self._read_fd()
        if data:
            self._pending += data

    def _key_of(self, character: str) -> Optional[str]:
        """The key of a character that is not a part of a sequence.

        Args:
            character: The character the operator pressed.

        Returns:
            The name of the key, or None when the character is a
            character of its own.
        """
        if character in ("\r", "\n"):
            return "ENTER"
        if character in ("\x7f", "\x08"):
            return "BACKSPACE"
        if character == "\t":
            return "TAB"
        if character == "\x03":
            return "CTRL_C"
        if character == "\x04":
            return "CTRL_D"
        # The other control characters are the Ctrl chords: the
        # terminal sends them as the control byte itself.
        return _control_key(character)

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

    def _peek_char(self) -> str:
        """
        The next character of the pending buffer, without waiting.

        Unlike :meth:`_next_char` this never reads from the terminal:
        it only looks at what the reader already has.  The reader of a
        control sequence needs it: the sequence may already be whole in
        the buffer, and waiting for it would cost the operator fifty
        milliseconds for every key of a key that repeats.

        Returns:
            The character, or an empty string when the buffer is empty.
        """
        if not self._pending:
            return ""
        return self._pending[0]

    def _wait_for_input(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for the terminal to give more, and keep what it gives.

        Args:
            timeout: How long to wait, in seconds.  None waits for as
                long as it takes: the terminal is in the middle of
                writing a control sequence, and the rest of it comes.

        Returns:
            True when more arrived, False when nothing came in time.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            if deadline is None:
                wait = 0.05
            else:
                wait = deadline - time.monotonic()
                if wait <= 0:
                    return False
            try:
                r, _, _ = select.select([sys.stdin], [], [], wait)
            except Exception:
                return False
            if r:
                break
        data = self._read_fd()
        if not data:
            return False
        self._pending += data
        return True

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
        key = self._key_of(ch)
        if key is not None:
            return key

        # An escape sequence: the cursor keys, and the marker that
        # opens a paste.
        if ch == "\x1b":
            return self._poll_escape()

        return ch

    def _poll_buffered(self) -> Optional[str]:
        """One key out of the pending buffer, and nothing more.

        The buffer is not filled from the terminal: a control sequence
        that has not arrived whole is left in it, and the terminal is
        read by the caller.

        Returns:
            The key, or None when the buffer holds no whole key.
        """
        if not self._pending:
            return None

        ch = self._pending[0]
        if ch == "\x1b":
            return self._poll_escape_buffered()

        self._consume(1)
        self._escape_started = 0.0
        key = self._key_of(ch)
        return key if key is not None else ch

    def _poll_escape_buffered(self) -> Optional[str]:
        """The key of the sequence in the buffer, without waiting for the
        quiet of the terminal.

        A sequence the terminal is still writing is waited for -- the
        rest of it comes.  An escape that is alone in the buffer is
        reported when nothing comes after it: the operator pressed
        ESC, and nothing else.

        Returns:
            The key of the sequence, "ESCAPE", or None while the
            sequence may still arrive.
        """
        # The sequence is ESC [ <parameters> <final byte>.
        if len(self._pending) < 2:
            # Nothing behind the ESC yet.  The escape is left in the
            # buffer: the terminal may still be writing the sequence.
            return self._escape_given_up()

        introducer = self._pending[1]

        if introducer == "O":
            # The application cursor mode, and the first four function
            # keys: "ESC O P" is the F1.
            self._consume(2)
            final = self._peek_char()
            if not final:
                if not self._wait_for_input():
                    return "ESCAPE"
                final = self._peek_char()
                if not final:
                    return "ESCAPE"
            self._consume(1)
            self._escape_started = 0.0
            return _SS3_KEYS.get(final, "ESCAPE")

        if introducer != "[":
            # Not a control sequence: the escape is a key of its own,
            # and the byte behind it is the key of the Alt chord.
            self._consume(2)
            self._escape_started = 0.0
            if introducer.isprintable():
                return "ALT_" + ("SPACE" if introducer == " " else introducer)
            return "ESCAPE"

        # The escape and the introducer are behind us.
        self._consume(2)

        params = ""
        final = ""
        while True:
            character = self._peek_char()
            if not character:
                # The terminal is in the middle of the sequence: the
                # rest of it comes, and it is waited for.
                if not self._wait_for_input():
                    # The terminal gave nothing: the escape is a key
                    # of its own.
                    self._escape_started = 0.0
                    self._consume(1)
                    return "ESCAPE"
                continue
            self._consume(1)
            if "0" <= character <= "?":
                params += character
                continue
            if " " <= character <= "/":
                # An intermediate byte: it is part of the sequence and
                # it says nothing about the key.
                continue
            final = character
            break

        self._escape_started = 0.0
        if params == "200" and final == "~":
            # The marker that opens a paste.
            return self._collect_paste()
        return self._decode_csi(params, final)

    def _escape_given_up(self) -> Optional[str]:
        """The escape of a sequence that never arrived whole.

        A sequence that is not whole yet is left in the buffer, and the
        terminal may still be writing it.  When it has waited long
        enough, the escape it began with is reported: the operator
        pressed ESC, and nothing else came.

        Returns:
            "ESCAPE" when the sequence has waited long enough, and None
            while it may still arrive.
        """
        if self._escape_started == 0.0:
            self._escape_started = time.monotonic()
            return None
        if time.monotonic() - self._escape_started < ESCAPE_TIMEOUT:
            return None
        # The rest of the sequence never came.
        self._escape_started = 0.0
        self._consume(1)
        return "ESCAPE"

    def _poll_escape(self) -> Optional[str]:
        """Read and decode an escape sequence on POSIX.

        The sequence is read as a whole: the parameter bytes, the
        intermediate bytes and the final byte.  A sequence the reader
        does not know is an escape, as it always was.

        The reader waits for the rest of the sequence only when it does
        not have it yet.  A terminal that repeats a key sends the
        sequences faster than the screen is drawn -- and a reader that
        waits fifty milliseconds for the rest of every sequence would
        never catch up with them: the cursor of the operator would
        stand still while the key was held, and would jump to the place
        it belongs to when the key was released.

        Returns:
            The key of the sequence, or "ESCAPE" when there is none.
        """
        # The introducer: the byte behind the ESC.  It may not have
        # arrived yet: a key pressed on its own is an escape.
        if not self._pending and not self._wait_for_input(ESCAPE_TIMEOUT):
            return "ESCAPE"

        introducer = self._peek_char()
        if not introducer:
            return "ESCAPE"
        self._consume(1)

        if introducer == "[":
            params = ""
            final = ""
            while True:
                c = self._peek_char()
                if not c:
                    # The rest of the sequence has not arrived yet: the
                    # terminal is still writing it.
                    if not self._wait_for_input(ESCAPE_TIMEOUT):
                        return "ESCAPE"
                    continue
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

        if introducer == "O":
            # The application cursor mode, and the first four function
            # keys: "ESC O P" is the F1.
            final = self._peek_char()
            if not final:
                if not self._wait_for_input(ESCAPE_TIMEOUT):
                    return "ESCAPE"
                final = self._peek_char()
                if not final:
                    return "ESCAPE"
            self._consume(1)
            return _SS3_KEYS.get(final, "ESCAPE")

        if introducer.isprintable():
            # The Alt chord: the terminal sends the ESC, and then the
            # key itself.
            return "ALT_" + ("SPACE" if introducer == " " else introducer)

        return "ESCAPE"

    def _decode_csi(self, params: str, final: str) -> Optional[str]:
        """The key of a control sequence, from its parameters.

        The parameters are the numbers of the sequence, and the last of
        them may be the modifier of the key: "ESC [ 1 ; 5 A" is the
        Ctrl+Up, and the "5" is the Ctrl.

        Args:
            params: The parameter bytes of the sequence.
            final: The final byte of the sequence.

        Returns:
            The key of the sequence, or "ESCAPE" when it is unknown.
        """
        numbers = [part for part in params.split(";") if part]

        if final == "~":
            return self._decode_tilde(numbers)
        if final == "u":
            return self._decode_csi_u(numbers)

        name = _CSI_FINAL_KEYS.get(final)
        if name is None:
            return "ESCAPE"

        # The modifier is the last of the parameters -- and there is one
        # only when the sequence carries more than one: "ESC [ 1 ; 5 A".
        mask = _modifier_mask(numbers[-1]) if len(numbers) > 1 else 0
        return _name_with_modifiers(name, mask)

    def _decode_tilde(self, numbers: List[str]) -> str:
        """The key of a control sequence that ends with a tilde.

        The number of the key is the one before the modifier: the
        "ESC [ 3 ; 5 ~" is the Ctrl+Delete, and the "ESC [ 15 ~" is the
        F5.

        Args:
            numbers: The numbers of the sequence.

        Returns:
            The key of the sequence, or "ESCAPE" when it is unknown.
        """
        if len(numbers) >= 2:
            key_number = numbers[-2]
            mask = _modifier_mask(numbers[-1])
        elif numbers:
            key_number = numbers[0]
            mask = 0
        else:
            return "ESCAPE"

        name = _CSI_TILDE_KEYS.get(key_number) or _FUNCTION_KEYS.get(key_number)
        if name is None:
            return "ESCAPE"
        return _name_with_modifiers(name, mask)

    def _decode_csi_u(self, numbers: List[str]) -> str:
        """The key of a control sequence in the "CSI u" form.

        The key is the first number, and the modifier is the last one:
        the "ESC [ 13 ; 5 u" is the Ctrl+Enter.

        Args:
            numbers: The numbers of the sequence.

        Returns:
            The key of the sequence, or "ESCAPE" when it is unknown.
        """
        if not numbers:
            return "ESCAPE"
        name = _CSI_U_KEYS.get(numbers[0])
        if name is None:
            return "ESCAPE"
        mask = _modifier_mask(numbers[-1]) if len(numbers) > 1 else 0
        return _name_with_modifiers(name, mask)

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
