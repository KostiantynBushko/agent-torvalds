"""
Unit tests for the TUI non-blocking input reader.

Covers the buffered-reading behaviour that keeps the multi-window TUI
responsive: keystrokes typed as a burst must all be captured, not just the
first one.

And the keys that arrive while a key is held.  The operator reported on
2026-11-20 that the cursor of the command bar stands still while an arrow
key is held, and that it jumps to the place it belongs to when the key is
released.  The reader was the cause, and the tests at the end of this file
measure it:

* the reader waited fifty milliseconds for the rest of every control
  sequence, even when the sequence was already in its buffer -- twenty
  arrow keys took a second to be read;
* the app asked it for one key after the other until the terminal went
  quiet, and a terminal that repeats a key that is held never goes quiet --
  the drain of the keyboard lasted as long as the key was held, and the
  screen is drawn after the drain.

The reader reads the keys that are waiting, in one piece, and the app draws
the screen between them.

Run with:
    pytest tests/test_tui_input_reader.py -v
"""
import os
import pty
import select
import signal
import struct
import sys
import termios
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from components.tui.input_reader import NonBlockingInputReader  # noqa: E402


def _read_all_available(reader, seconds=1.5):
    """Poll the reader until the timeout expires, collecting every key."""
    keys = []
    end = time.time() + seconds
    while time.time() < end:
        if reader.is_available():
            key = reader.poll_key()
            if key:
                keys.append(key)
        time.sleep(0.02)
    return keys


class TestInputReaderInPseudoTerminal(unittest.TestCase):
    """Drive the reader from a real pseudo-terminal."""

    def _spawn_reader(self, script):
        """Run a script that uses the reader, returning the pty master fd."""
        pid, fd = pty.fork()
        if pid == 0:  # pragma: no cover - child process
            os.environ["TERM"] = "xterm"
            os.chdir(str(ROOT))
            os.execv(
                sys.executable,
                [sys.executable, "-c", script],
            )
        return pid, fd

    def test_burst_of_keystrokes_is_fully_captured(self):
        """A burst of characters must not be truncated to the first one."""
        script = (
            "import sys, time\n"
            f"sys.path.insert(0, {str(ROOT)!r})\n"
            "from components.tui.input_reader import NonBlockingInputReader\n"
            "r = NonBlockingInputReader()\n"
            "r.start()\n"
            "got = []\n"
            "end = time.time() + 5\n"
            "while time.time() < end:\n"
            "    if r.is_available():\n"
            "        k = r.poll_key()\n"
            "        if k: got.append(k)\n"
            "    time.sleep(0.02)\n"
            "r.stop()\n"
            "print('KEYS:' + repr(got), flush=True)\n"
        )
        pid, fd = self._spawn_reader(script)

        try:
            time.sleep(1.5)
            os.write(fd, b"\\projects")
            time.sleep(0.5)
            os.write(fd, b"\r")

            out = b""
            deadline = time.time() + 6
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
        self.assertIn("KEYS:", text, f"reader produced no output: {text[:400]!r}")

        keys_line = text.split("KEYS:")[1].split("\n")[0]
        keys = eval(keys_line)  # noqa: S307 - controlled literal from our own child

        # Every character of "\projects" plus the ENTER must be present.
        for expected in ("\\", "p", "r", "o", "j", "e", "c", "t", "s", "ENTER"):
            self.assertIn(
                expected,
                keys,
                f"keystroke {expected!r} missing from captured keys {keys}",
            )

    def test_enter_is_normalized(self):
        """The ENTER key must be reported as the 'ENTER' token."""
        script = (
            "import sys, time\n"
            f"sys.path.insert(0, {str(ROOT)!r})\n"
            "from components.tui.input_reader import NonBlockingInputReader\n"
            "r = NonBlockingInputReader()\n"
            "r.start()\n"
            "got = []\n"
            "end = time.time() + 4\n"
            "while time.time() < end:\n"
            "    if r.is_available():\n"
            "        k = r.poll_key()\n"
            "        if k: got.append(k)\n"
            "    time.sleep(0.02)\n"
            "r.stop()\n"
            "print('KEYS:' + repr(got), flush=True)\n"
        )
        pid, fd = self._spawn_reader(script)

        try:
            time.sleep(1.5)
            os.write(fd, b"\r")

            out = b""
            deadline = time.time() + 5
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
        self.assertIn("KEYS:", text)
        keys_line = text.split("KEYS:")[1].split("\n")[0]
        keys = eval(keys_line)  # noqa: S307 - controlled literal from our own child
        self.assertIn("ENTER", keys)


class TestInputReaderUnitBehaviour(unittest.TestCase):
    """Non-TTY / inactive behaviour of the reader."""

    def test_is_available_false_when_not_a_tty(self):
        reader = NonBlockingInputReader()
        reader._is_tty = False
        self.assertFalse(reader.is_available())
        self.assertIsNone(reader.poll_key())

    def test_start_and_stop_are_idempotent(self):
        reader = NonBlockingInputReader()
        reader.start()
        reader.start()
        reader.stop()
        reader.stop()
        self.assertFalse(reader._is_active)

    def test_pending_buffer_is_cleared_on_stop(self):
        reader = NonBlockingInputReader()
        reader.start()
        reader._pending = "abc"
        reader.stop()
        self.assertEqual(reader._pending, "")

    def test_next_char_consumes_from_pending(self):
        reader = NonBlockingInputReader()
        reader._pending = "xy"
        self.assertEqual(reader._next_char(), "x")
        reader._consume(1)
        self.assertEqual(reader._pending, "y")
        self.assertEqual(reader._next_char(), "y")
        reader._consume(1)
        self.assertEqual(reader._pending, "")


#: The marker the reader writes when it starts: the terminal is asked
#: to mark the pastes.  The parent waits for it before it writes, so
#: that the bytes are read by the reader and not swallowed by the line
#: discipline of the terminal.
READY = b"\x1b[?2004h"

#: The body of the child that reads the keys the way the app reads
#: them: the keys that are waiting, in one piece.  A reader without
#: that way of reading is given the old one -- one key after the other,
#: until the terminal goes quiet -- so that both are measured by the
#: same ruler.
COLLECT = (
    "def collect():\n"
    "    batch = []\n"
    "    read = getattr(r, 'poll_keys', None)\n"
    "    if read is not None:\n"
    "        return read()\n"
    "    while r.is_available():\n"
    "        key = r.poll_key()\n"
    "        if key is None:\n"
    "            break\n"
    "        batch.append(key)\n"
    "    return batch\n"
)


def run_in_pty(body, writes, timeout=25.0):
    """Run a piece of the reader in a pseudo-terminal.

    The child runs the body with the reader ``r`` in it, and with the
    way of reading the keys the app uses.  The parent writes the bytes
    of ``writes`` into the terminal, once the reader has announced
    itself.

    Args:
        body: The body of the child, as Python source.
        writes: A list of pairs: the delay in seconds from the moment
            the reader is ready, and the bytes to write.
        timeout: How long the parent waits for the child.

    Returns:
        The line the child printed after the marker "RESULT:".
    """
    script = (
        "import sys, time\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "from components.tui.input_reader import NonBlockingInputReader\n"
        "r = NonBlockingInputReader()\n"
        "r.start()\n"
        + COLLECT
        + body
        + "\nr.stop()\n"
    )

    pid, fd = pty.fork()
    if pid == 0:  # pragma: no cover - the child process
        os.environ["TERM"] = "xterm"
        os.chdir(str(ROOT))
        os.execv(sys.executable, [sys.executable, "-c", script])

    out = b""
    pending = []
    ready = None
    try:
        deadline = time.time() + timeout
        while time.time() < deadline:
            readable, _, _ = select.select([fd], [], [], 0.02)
            if readable:
                try:
                    chunk = os.read(fd, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                out += chunk
                if ready is None and READY in out:
                    ready = time.monotonic()
                    pending = [
                        (ready + delay, data) for delay, data in writes
                    ]
            now = time.monotonic()
            while pending and pending[0][0] <= now:
                _, data = pending.pop(0)
                os.write(fd, data)
            if b"RESULT:" in out:
                break
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        os.waitpid(pid, os.WNOHANG)

    text = out.decode("utf-8", "replace")
    if "RESULT:" not in text:
        return None
    return text.split("RESULT:", 1)[1].split("\n")[0].strip()


class TestTheRepeatedKey(unittest.TestCase):
    """The keys that arrive while a key is held."""

    def test_a_burst_of_repeated_keys_comes_in_one_piece(self):
        """Twenty arrow keys are twenty keys, and they come at once."""
        body = (
            "keys = []\n"
            "took = -1\n"
            "end = time.time() + 8\n"
            "while time.time() < end and len(keys) < 20:\n"
            "    start = time.monotonic()\n"
            "    batch = collect()\n"
            "    if batch and len(keys) + len(batch) >= 20:\n"
            "        took = time.monotonic() - start\n"
            "    keys.extend(batch)\n"
            "    time.sleep(0.02)\n"
            "print('RESULT:' + repr([str(k) for k in keys]) + '|' "
            "+ repr(took), flush=True)\n"
        )

        result = run_in_pty(body, [(0.0, b"\x1b[C" * 20)])

        self.assertIsNotNone(result, "the reader reported nothing")
        keys, span = result.split("|")
        keys = eval(keys)  # noqa: S307 - a literal from our own child
        span = float(span)  # noqa: S307 - a literal from our own child
        self.assertEqual(
            len(keys),
            20,
            f"the reader reported {len(keys)} keys of twenty -- the "
            "repeats of the key were lost",
        )
        self.assertTrue(
            all(value == "RIGHT" for value in keys),
            f"the reader did not report the arrow keys -- it reported "
            f"{keys[:3]}",
        )
        self.assertLess(
            span,
            0.5,
            f"the twenty keys took {span:.3f} s to be read -- the reader "
            "waits for the rest of a sequence it already has",
        )

    def test_the_drain_of_the_keyboard_ends_while_the_key_is_held(self):
        """The screen is drawn while the key is held, and not after it."""
        body = (
            "worst = 0.0\n"
            "for _ in range(20):\n"
            "    start = time.monotonic()\n"
            "    for _key in collect():\n"
            "        pass\n"
            "    worst = max(worst, time.monotonic() - start)\n"
            "    time.sleep(0.066)\n"
            "print('RESULT:' + repr(worst), flush=True)\n"
        )

        # A key that repeats, the way a terminal repeats a held key.
        writes = [(0.1 + index * 0.033, b"\x1b[C") for index in range(20)]

        result = run_in_pty(body, writes)

        self.assertIsNotNone(result, "the reader reported nothing")
        worst = float(result)  # noqa: S307 - a literal from our own child
        self.assertLess(
            worst,
            0.25,
            f"the drain of the keyboard lasted {worst:.3f} s -- the screen "
            "is drawn after the drain, and the cursor of the operator "
            "stands still while the key is held",
        )


class TestTheKeysOfTheReader(unittest.TestCase):
    """The keys the reader reports."""

    def test_a_paste_arrives_in_one_piece(self):
        """A paste is one key, and not one key per line of it."""
        body = (
            "keys = []\n"
            "end = time.time() + 8\n"
            "while time.time() < end and not keys:\n"
            "    keys.extend(collect())\n"
            "    time.sleep(0.02)\n"
            "print('RESULT:' + repr([(type(k).__name__, str(k)) "
            "for k in keys]), flush=True)\n"
        )

        result = run_in_pty(
            body, [(0.0, b"\x1b[200~hello world\x1b[201~")]
        )

        self.assertIsNotNone(result, "the reader reported nothing")
        keys = eval(result)  # noqa: S307 - a literal from our own child
        self.assertEqual(
            len(keys),
            1,
            f"the reader reported {len(keys)} keys for one paste -- the "
            "paste did not arrive whole",
        )
        self.assertEqual(keys[0][0], "PastedText", "the paste is not a paste")
        self.assertEqual(keys[0][1], "hello world", "the paste is not whole")

    def test_a_lone_escape_is_an_escape(self):
        """The operator pressed ESC, and nothing else came."""
        body = (
            "keys = []\n"
            "end = time.time() + 5\n"
            "while time.time() < end and not keys:\n"
            "    keys.extend(collect())\n"
            "    time.sleep(0.02)\n"
            "print('RESULT:' + repr([str(k) for k in keys]), flush=True)\n"
        )

        result = run_in_pty(body, [(0.0, b"\x1b")])

        self.assertIsNotNone(result, "the reader reported nothing")
        keys = eval(result)  # noqa: S307 - a literal from our own child
        self.assertEqual(
            keys,
            ["ESCAPE"],
            f"the reader reported {keys} -- the escape of the operator was "
            "not reported",
        )

    def test_a_sequence_that_comes_in_two_pieces_is_one_key(self):
        """The terminal may be slow: the sequence is still one key."""
        body = (
            "keys = []\n"
            "end = time.time() + 6\n"
            "while time.time() < end and not keys:\n"
            "    keys.extend(collect())\n"
            "    time.sleep(0.02)\n"
            "print('RESULT:' + repr([str(k) for k in keys]), flush=True)\n"
        )

        result = run_in_pty(body, [(0.0, b"\x1b["), (0.3, b"C")])

        self.assertIsNotNone(result, "the reader reported nothing")
        keys = eval(result)  # noqa: S307 - a literal from our own child
        self.assertEqual(
            keys,
            ["RIGHT"],
            f"the reader reported {keys} -- the sequence was not read as "
            "one key",
        )


# ---------------------------------------------------------------------------
# The modified keys
# ---------------------------------------------------------------------------


def _the_keys_of(sequence: bytes):
    """The keys the reader reports for a sequence of bytes."""
    body = (
        "keys = []\n"
        "end = time.time() + 6\n"
        "while time.time() < end and not keys:\n"
        "    keys.extend(collect())\n"
        "    time.sleep(0.02)\n"
        "print('RESULT:' + repr([str(k) for k in keys]), flush=True)\n"
    )

    result = run_in_pty(body, [(0.0, sequence)])

    assert result is not None, f"the reader reported nothing for {sequence!r}"
    return eval(result)  # noqa: S307 - a literal from our own child


class TestTheModifiedKeys(unittest.TestCase):
    """The reader has to name the modified keys.

    The hot-keys need something to bind: without a name for the
    Ctrl+<letter> chords, every hot-key would have to take a key away
    from the operator's typing.
    """

    def test_a_ctrl_chord_is_named(self):
        """A terminal sends the Ctrl+<letter> as the control byte."""
        keys = _the_keys_of(b"\x14")  # Ctrl+T

        self.assertEqual(keys, ["CTRL_T"])

    def test_every_ctrl_letter_is_named(self):
        """Every chord the terminal delivers is named.

        The Ctrl+Z is not among them: the kernel raises the SIGTSTP
        before the byte is read, and the TUI is suspended.  It is named
        all the same -- see the test below -- but the byte never
        reaches the reader.
        """
        for letter in "ABEFGKLNOPRTUVXY":
            with self.subTest(letter=letter):
                keys = _the_keys_of(bytes([ord(letter) - 64]))

                self.assertEqual(keys, [f"CTRL_{letter}"])

    def test_the_ctrl_z_is_named_by_the_reader(self):
        """The kernel takes the byte, and the reader still names it."""
        from components.tui.input_reader import NonBlockingInputReader

        reader = NonBlockingInputReader()

        self.assertEqual(reader._key_of("\x1a"), "CTRL_Z")

    def test_the_ctrl_chords_the_terminal_claims_are_not_named_away(self):
        """The four bytes another key already claimed keep their name."""
        for sequence, expected in (
            (b"\x08", "BACKSPACE"),  # Ctrl+H
            (b"\x09", "TAB"),        # Ctrl+I
            (b"\x0a", "ENTER"),      # Ctrl+J
            (b"\x0d", "ENTER"),      # Ctrl+M
        ):
            with self.subTest(expected=expected):
                keys = _the_keys_of(sequence)

                self.assertEqual(keys, [expected])

    def test_a_modified_arrow_is_not_the_arrow(self):
        """The modifier is a part of the name of the key."""
        keys = _the_keys_of(b"\x1b[1;5A")  # Ctrl+Up

        self.assertNotIn("UP", keys, "the modifier was thrown away")
        self.assertEqual(keys, ["CTRL_UP"])

    def test_a_shifted_arrow_is_named(self):
        keys = _the_keys_of(b"\x1b[1;2B")  # Shift+Down

        self.assertEqual(keys, ["SHIFT_DOWN"])

    def test_a_function_key_is_named(self):
        keys = _the_keys_of(b"\x1b[15~")  # F5

        self.assertEqual(keys, ["F5"])

    def test_a_function_key_of_the_application_mode_is_named(self):
        keys = _the_keys_of(b"\x1bOP")  # F1

        self.assertEqual(keys, ["F1"])

    def test_an_alt_chord_is_named(self):
        """The terminal sends the ESC, and then the key itself."""
        keys = _the_keys_of(b"\x1ba")

        self.assertEqual(keys, ["ALT_a"])

    def test_the_plain_keys_are_not_named_away(self):
        """The keys the TUI has always had keep their name."""
        for sequence, expected in (
            (b"\x1b[A", "UP"),
            (b"\x1b[B", "DOWN"),
            (b"\x1b[5~", "PGUP"),
            (b"\x1b[6~", "PGDN"),
            (b"\x1b[H", "HOME"),
            (b"\x1b[F", "END"),
            (b"\x1b[Z", "SHIFT_TAB"),
            (b"\t", "TAB"),
            (b"\r", "ENTER"),
        ):
            with self.subTest(expected=expected):
                keys = _the_keys_of(sequence)

                self.assertEqual(keys, [expected])


if __name__ == "__main__":
    unittest.main()
