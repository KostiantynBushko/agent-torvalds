"""
The arrow keys of the operator — the cursor that hangs.

The operator reported on 2026-11-20 that the cursor of the command bar
stands still while an arrow key is held, and that it jumps to the place
it belongs to when the key is released.

The reader of the keyboard was the cause, and the probe measures it:

  1. **How long does the reader take for the keys that are waiting?**
     Twenty arrow keys are written into a pseudo-terminal in one piece,
     the way a terminal writes them when the screen is slow.  The
     reader must hand them over at once.

  2. **How long does the drain of the keyboard last while a key is
     held?**  The app reads the keys and then draws the screen, so a
     drain that never ends is a screen that is never drawn.

  3. **Do the keys still arrive whole?**  A paste is one key, an
     escape alone is an escape, and a sequence the terminal writes in
     two pieces is one key.

Everything is measured against the real reader, driven from a
pseudo-terminal, and against the real loop of the app.

Usage:
    python investigate/tui-arrow-key-repeat/probe_arrow_key_repeat.py

The exit code is 0 when every check holds, 1 when one does not.
"""
from __future__ import annotations

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

#: The marker the reader writes when it starts: the terminal is asked
#: to mark the pastes.  The probe waits for it before it writes, so
#: that the bytes are read by the reader and not swallowed by the line
#: discipline of the terminal.
READY = b"\x1b[?2004h"

#: The number of the arrow keys of a burst.
BURST = 20

#: The time between two repeats of a held key.  A terminal repeats a
#: key about thirty times a second.
REPEAT = 0.033

#: How long a burst of keys may take to be read.
BURST_LIMIT = 0.5

#: How long the drain of the keyboard may last while a key is held.
DRAIN_LIMIT = 0.25

#: The way the app reads the keys.  A reader without it is given the
#: old one -- one key after the other, until the terminal goes quiet --
#: so that both are measured by the same ruler.
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


def drive(body: str, writes, timeout: float = 30.0) -> str:
    """Run a piece of the reader in a pseudo-terminal.

    The child runs the body with the reader ``r`` in it.  The probe
    writes the bytes of ``writes`` into the terminal, once the reader
    has announced itself.

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
        f"sys.path.insert(0, {str(REPO)!r})\n"
        "from components.tui.input_reader import NonBlockingInputReader\n"
        "r = NonBlockingInputReader()\n"
        "r.start()\n"
        + body
        + "\nr.stop()\n"
    )

    pid, fd = pty.fork()
    if pid == 0:  # pragma: no cover - the child process
        os.environ["TERM"] = "xterm"
        os.chdir(str(REPO))
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
                    pending = [(ready + delay, data) for delay, data in writes]
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
        return ""
    return text.split("RESULT:", 1)[1].split("\n")[0].strip()


def collect_in_pty(writes) -> tuple:
    """The keys the reader reports, and the time the drain took.

    Args:
        writes: The bytes to write into the terminal.

    Returns:
        A pair: the keys, and the seconds the drain of the keyboard
        took.
    """
    body = (
        COLLECT
        + "keys = []\n"
        "took = -1\n"
        "end = time.time() + 8\n"
        "while time.time() < end and len(keys) < %d:\n" % BURST
        + "    start = time.monotonic()\n"
        "    batch = collect()\n"
        "    if batch and len(keys) + len(batch) >= %d:\n" % BURST
        + "        took = time.monotonic() - start\n"
        "    keys.extend(batch)\n"
        "    time.sleep(0.02)\n"
        "print('RESULT:' + repr([str(k) for k in keys]) + '|' + repr(took), "
        "flush=True)\n"
    )
    result = drive(body, writes)
    if not result:
        return [], -1
    keys, took = result.split("|")
    return eval(keys), float(took)  # noqa: S307 - a literal from our own child


def drain_in_pty(writes) -> float:
    """The longest drain of the keyboard while a key is held.

    Args:
        writes: The bytes to write into the terminal.

    Returns:
        The seconds the longest drain took.
    """
    body = (
        COLLECT
        + "worst = 0.0\n"
        "for _ in range(20):\n"
        "    start = time.monotonic()\n"
        "    for _key in collect():\n"
        "        pass\n"
        "    worst = max(worst, time.monotonic() - start)\n"
        "    time.sleep(0.066)\n"
        "print('RESULT:' + repr(worst), flush=True)\n"
    )
    result = drive(body, writes)
    if not result:
        return -1
    return float(result)  # noqa: S307 - a literal from our own child


def the_keys(writes) -> list:
    """The keys the reader reports, one by one, until it has some.

    Args:
        writes: The bytes to write into the terminal.

    Returns:
        The keys, as strings.
    """
    body = (
        "keys = []\n"
        "end = time.time() + 5\n"
        "while time.time() < end and not keys:\n"
        "    read = getattr(r, 'poll_keys', None)\n"
        "    if read is not None:\n"
        "        keys.extend(read())\n"
        "    else:\n"
        "        while r.is_available():\n"
        "            key = r.poll_key()\n"
        "            if key is None:\n"
        "                break\n"
        "            keys.append(key)\n"
        "    time.sleep(0.02)\n"
        "print('RESULT:' + repr([str(k) for k in keys]), flush=True)\n"
    )
    result = drive(body, writes)
    if not result:
        return []
    return eval(result)  # noqa: S307 - a literal from our own child


def check_the_burst() -> bool:
    """The keys of a burst are handed over at once."""
    print("1. a burst of %d arrow keys" % BURST)

    keys, took = collect_in_pty([(0.0, b"\x1b[C" * BURST)])

    if len(keys) != BURST:
        print("   the reader reported %d keys of %d -- the repeats of the "
              "key were lost" % (len(keys), BURST))
        return False
    if not all(key == "RIGHT" for key in keys):
        print("   the reader reported %s -- they are not the arrow keys"
              % keys[:3])
        return False
    print("   the reader reported %d arrow keys in %.3f s" % (len(keys), took))
    if took > BURST_LIMIT:
        print("   too slow: the limit is %.3f s -- the reader waits for the "
              "rest of a sequence it already has" % BURST_LIMIT)
        return False
    print("   the limit is %.3f s" % BURST_LIMIT)
    return True


def check_the_drain() -> bool:
    """The drain of the keyboard ends while the key is held."""
    print("2. a key that is held")

    writes = [(0.1 + index * REPEAT, b"\x1b[C") for index in range(20)]
    worst = drain_in_pty(writes)

    print("   the longest drain of the keyboard: %.3f s" % worst)
    if worst < 0:
        print("   the reader reported nothing")
        return False
    if worst > DRAIN_LIMIT:
        print("   too long: the limit is %.3f s -- the screen is drawn "
              "after the drain, and the cursor stands still while the key "
              "is held" % DRAIN_LIMIT)
        return False
    print("   the limit is %.3f s" % DRAIN_LIMIT)
    return True


def check_the_keys() -> bool:
    """The keys still arrive whole."""
    print("3. the keys that are not repeats")

    holds = True

    keys, _ = collect_in_pty([(0.0, b"\x1b[200~hello world\x1b[201~")])
    if keys != ["hello world"]:
        print("   a paste: the reader reported %s -- the paste did not "
              "arrive whole" % (keys,))
        holds = False
    else:
        print("   a paste arrives in one piece")

    keys = the_keys([(0.0, b"\x1b")])
    if keys != ["ESCAPE"]:
        print("   a lone escape: the reader reported %s -- it is not an "
              "escape" % (keys,))
        holds = False
    else:
        print("   a lone escape is an escape")

    keys = the_keys([(0.0, b"\x1b["), (0.3, b"C")])
    if keys != ["RIGHT"]:
        print("   a sequence in two pieces: the reader reported %s -- it is "
              "not one key" % (keys,))
        holds = False
    else:
        print("   a sequence in two pieces is one key")

    return holds


def main() -> int:
    """Run every check and report what was seen."""
    failures = []
    for check in (check_the_burst, check_the_drain, check_the_keys):
        print()
        if not check():
            failures.append(check.__name__)
        print()

    if failures:
        print("what does not hold: %s" % ", ".join(failures))
        return 1

    print(
        "everything holds: the keys that are waiting are read at once, the "
        "drain of the keyboard ends while the key is held, and the keys "
        "still arrive whole"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
