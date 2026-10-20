"""
Unit tests for the TUI non-blocking input reader.

Covers the buffered-reading behaviour that keeps the multi-window TUI
responsive: keystrokes typed as a burst must all be captured, not just the
first one.

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


if __name__ == "__main__":
    unittest.main()
