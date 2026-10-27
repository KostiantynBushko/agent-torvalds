"""
The verification harness for the file-logging investigation.

It checks the six invariants of the proposed design against the
**public behaviour** — the files on disk and the records they carry —
and not against private helpers, so it stays valid when the
implementation is refactored.

    L1  every record reaches the log file
    L2  the log file is rotated when it reaches the size limit
    L3  the symlink points at the file that is being written *now*,
        including right after a rotation
    L4  the number of retained generations is bounded
    L5  a symlink that cannot be created degrades the pointer, never the
        logging
    L6  the log file is opened for appending, is private (0600), and is
        not truncated when the logging is reconfigured
    L7  the size limit is written the way an operator writes it
        ("10MB"), and an unknown unit is reported rather than ignored

Run it:

    self-development/.venv/bin/python \\
        self-development/investigate/logging-to-file/verify_logging_to_file.py
"""

from __future__ import annotations

import logging
import os
import stat
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from prototype_file_logging import (  # noqa: E402
    SymlinkedRotatingFileHandler,
    install_file_logging,
    parse_size,
)


# ---------------------------------------------------------------------------
# The harness
# ---------------------------------------------------------------------------

class Harness:
    """Collects the checks and prints the verdict."""

    def __init__(self) -> None:
        self.results: list[tuple[str, bool, str]] = []

    def check(self, invariant: str, ok: bool, detail: str = "") -> None:
        self.results.append((invariant, ok, detail))
        mark = "OK  " if ok else "FAIL"
        print(f"[{mark}] {invariant}  {detail}")

    def report(self) -> int:
        failed = [r for r in self.results if not r[1]]
        # The same invariant can be checked more than once; the verdict
        # names it once.
        names = list(dict.fromkeys(r[0] for r in failed))
        print()
        print(f"{len(self.results) - len(failed)}/{len(self.results)} checks hold")
        if failed:
            print("FAILED: " + ", ".join(names))
            return 1
        return 0


def _isolated_logger(name: str) -> logging.Logger:
    """A logger that writes nowhere but into the handler under test."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    return logger


def _write(logger: logging.Logger, count: int, text: str = "x" * 100) -> None:
    for i in range(count):
        logger.info("record %04d %s", i, text)


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------

def check_l1_records_reach_the_file(tmp: Path, h: Harness) -> None:
    """L1 — every record reaches the log file."""
    log_file = tmp / "l1" / "agent.log"
    handler = install_file_logging(str(log_file), max_bytes=10 * 1024 * 1024)
    logger = _isolated_logger("l1")
    logger.addHandler(handler)

    _write(logger, 25)
    handler.flush()

    content = log_file.read_text(encoding="utf-8")
    missing = [i for i in range(25) if f"record {i:04d}" not in content]
    h.check("L1", not missing, f"25 records written, {len(missing)} missing")


def check_l2_rotation_at_the_limit(tmp: Path, h: Harness) -> None:
    """L2 — the file is rotated when it reaches the size limit."""
    log_file = tmp / "l2" / "agent.log"
    limit = 4096
    handler = install_file_logging(str(log_file), max_bytes=limit, backup_count=3)
    logger = _isolated_logger("l2")
    logger.addHandler(handler)

    _write(logger, 200)
    handler.flush()

    rotated = sorted(p.name for p in log_file.parent.glob("agent.log.*"))
    live_size = log_file.stat().st_size

    # The live file may exceed the limit by the record that crossed it,
    # but it must not exceed it by a whole file's worth.
    ok = bool(rotated) and live_size <= limit * 2
    h.check(
        "L2",
        ok,
        f"limit={limit} live={live_size} rotated={len(rotated)}",
    )


def check_l3_symlink_follows_the_current_file(tmp: Path, h: Harness) -> None:
    """L3 — the symlink points at the file being written, after a rotation too."""
    log_file = tmp / "l3" / "agent.log"
    handler = install_file_logging(str(log_file), max_bytes=4096, backup_count=3)
    logger = _isolated_logger("l3")
    logger.addHandler(handler)
    link = Path(handler.symlink_path)

    _write(logger, 5)
    handler.flush()

    ok = link.is_symlink()
    h.check("L3", ok, f"the symlink exists: {link.name}")

    same = os.path.realpath(link) == os.path.realpath(log_file)
    h.check("L3", same, "the symlink resolves to the log file")

    inode_before = os.stat(log_file).st_ino

    # Cross the limit so the file is rotated.  The inode of the live file
    # changes; the symlink must follow it to the *new* file.
    _write(logger, 200)
    handler.flush()

    inode_after = os.stat(log_file).st_ino
    rotated = bool(list(log_file.parent.glob("agent.log.*")))

    still_live = os.path.realpath(link) == os.path.realpath(log_file)
    h.check(
        "L3",
        rotated and inode_before != inode_after and still_live,
        f"rotated={rotated} inode {inode_before}->{inode_after} link still live={still_live}",
    )

    # The symlink points at a *path*, and the path does not change when
    # the file is rotated — that is why it survives the rotation without
    # any maintenance.  The one thing that does need maintenance is a
    # symlink somebody deleted while the agent was running: the next
    # rollover has to bring it back.
    os.remove(link)
    _write(logger, 200)
    handler.flush()

    healed = link.is_symlink() and os.path.realpath(link) == os.path.realpath(log_file)
    h.check("L3", healed, "the symlink comes back after it was deleted")


def check_l4_retention_is_bounded(tmp: Path, h: Harness) -> None:
    """L4 — no more than `backup_count` generations are kept."""
    log_file = tmp / "l4" / "agent.log"
    handler = install_file_logging(str(log_file), max_bytes=2048, backup_count=3)
    logger = _isolated_logger("l4")
    logger.addHandler(handler)

    _write(logger, 500)
    handler.flush()

    rotated = list(log_file.parent.glob("agent.log.*"))
    ok = len(rotated) <= 3
    h.check("L4", ok, f"{len(rotated)} generations kept, limit 3")


def check_l5_degrades_without_a_symlink(tmp: Path, h: Harness) -> None:
    """L5 — a symlink that cannot be created never stops the logging."""
    log_file = tmp / "l5" / "agent.log"
    # A path in a directory that does not exist: os.symlink() fails.
    impossible = tmp / "l5" / "no-such-dir" / "current.log"

    raised = False
    handler = None
    try:
        handler = install_file_logging(
            str(log_file), max_bytes=4096, symlink_path=str(impossible)
        )
    except Exception:  # noqa: BLE001 — the point of the check
        raised = True

    ok = not raised
    h.check("L5", ok, "the handler is installed even though the symlink cannot be created")

    if handler is not None:
        logger = _isolated_logger("l5")
        logger.addHandler(handler)
        _write(logger, 10)
        handler.flush()
        written = log_file.exists() and "record 0000" in log_file.read_text(encoding="utf-8")
        h.check("L5", written, "the records still reach the log file")


def check_l6_append_and_private(tmp: Path, h: Harness) -> None:
    """L6 — the file is appended to, is private, and survives a reconfiguration."""
    log_file = tmp / "l6" / "agent.log"
    handler = install_file_logging(str(log_file), max_bytes=10 * 1024 * 1024)
    logger = _isolated_logger("l6")
    logger.addHandler(handler)

    _write(logger, 5)
    handler.flush()
    size_after_first = log_file.stat().st_size

    # Reconfigure: a second handler on the same file must append, not truncate.
    handler2 = install_file_logging(str(log_file), max_bytes=10 * 1024 * 1024)
    logger.removeHandler(handler)
    logger.addHandler(handler2)
    _write(logger, 5)
    handler2.flush()

    size_after_second = log_file.stat().st_size
    appended = size_after_second > size_after_first
    content = log_file.read_text(encoding="utf-8")
    kept = "record 0000" in content
    h.check("L6", appended and kept, f"{size_after_first} -> {size_after_second} bytes, the first records are still there")

    mode = stat.S_IMODE(log_file.stat().st_mode)
    h.check("L6", mode == 0o600, f"the file mode is {oct(mode)}")


def check_l7_the_size_is_parsed(tmp: Path, h: Harness) -> None:
    """L7 — the size limit is written the way an operator writes it."""
    cases = {
        "10MB": 10 * 1024 * 1024,
        "512K": 512 * 1024,
        "1G": 1024 ** 3,
        "2048": 2048,
    }
    wrong = {text: parse_size(text) for text, expected in cases.items()
             if parse_size(text) != expected}
    h.check("L7", not wrong, f"{len(cases) - len(wrong)}/{len(cases)} sizes parsed")

    # A unit nobody knows is a typo, and a typo must be reported — a log
    # that never rotates because the size was not understood is the exact
    # failure this feature exists to prevent.
    raised = False
    try:
        parse_size("10MBB")
    except ValueError:
        raised = True
    h.check("L7", raised, "an unknown unit is reported")


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def main() -> int:
    print("The file-logging invariants")
    print("=" * 70)
    tmp = Path(tempfile.mkdtemp(prefix="torvalds-log-verify-"))
    h = Harness()

    check_l1_records_reach_the_file(tmp, h)
    check_l2_rotation_at_the_limit(tmp, h)
    check_l3_symlink_follows_the_current_file(tmp, h)
    check_l4_retention_is_bounded(tmp, h)
    check_l5_degrades_without_a_symlink(tmp, h)
    check_l6_append_and_private(tmp, h)
    check_l7_the_size_is_parsed(tmp, h)

    return h.report()


if __name__ == "__main__":
    sys.exit(main())
