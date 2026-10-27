"""
Prototype: redirect the logging into a file, rotate it at a size limit,
and keep a symlink to the current log file inside the same directory.

This is the **evidence** for ``INVESTIGATION_REPORT.md``.  It is a
prototype, not the implementation: the implementation belongs in
``components/`` and is wired into the two orchestrators.

The mechanism it proves
-----------------------

1.  ``logging.handlers.RotatingFileHandler`` already does the size-based
    rotation: it rotates when the file reaches ``maxBytes`` and keeps
    ``backupCount`` generations (``agent.log.1``, ``agent.log.2``, ...).
2.  The rotation **keeps the base path the current file** — the handler
    renames ``agent.log`` to ``agent.log.1`` and reopens ``agent.log``.
    A symlink that points at the *path* ``agent.log`` therefore stays
    valid across every rotation and never has to be re-pointed.
3.  The symlink is created once, and re-asserted after a rollover so it
    heals itself if somebody deleted it.
4.  The log file is made **private** (0600): the standard handler creates
    it with ``0666 & ~umask``, and a log carries the prompts.

Run it:

    self-development/.venv/bin/python \\
        self-development/investigate/logging-to-file/prototype_file_logging.py
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# The handler
# ---------------------------------------------------------------------------

class SymlinkedRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """A rotating file handler that keeps a symlink pointing at the live file.

    The symlink is a **convenience pointer**, never the file that is
    written: the log file itself stays a plain file, so ``du``, editors
    and log shippers see a regular file.

    The symlink points at the *path* of the live log file, and that path
    does not change when the file is rotated — the handler renames the
    file away and creates a new one at the same path.  The pointer is
    therefore valid at every moment, and it only has to be (re)created
    when it is missing.
    """

    #: The log file is private.  It carries the prompts, the tool output
    #: and the model answers, so it must not be world-readable — and the
    #: umask of the shell that started the agent is not ours to trust.
    FILE_MODE = 0o600

    def __init__(
        self,
        filename: str,
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
        symlink_path: str | None = None,
        encoding: str = "utf-8",
    ) -> None:
        super().__init__(
            filename,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding=encoding,
        )
        self.symlink_path = str(symlink_path) if symlink_path else None
        # The symlink is created eagerly so a broken setup is reported at
        # startup, not at the first rotation.
        self.refresh_symlink()

    # -- the file ----------------------------------------------------------

    def _open(self):
        """Open the log file and make it private.

        ``RotatingFileHandler`` creates the file with the default
        ``0666 & ~umask`` — on this machine ``0664``, so a log with the
        prompts in it is readable by every account on the box.  The mode
        is corrected here, on the first open and after every rollover.
        """
        stream = super()._open()
        try:
            os.chmod(self.baseFilename, self.FILE_MODE)
        except OSError:
            # A filesystem that does not support the mode is not a reason
            # to stop logging.
            pass
        return stream

    # -- the symlink -------------------------------------------------------

    def refresh_symlink(self) -> bool:
        """(Re)create the symlink so it points at the live log file.

        Returns ``True`` when the symlink is in place afterwards.  A
        failure is **reported, never raised**: a filesystem that cannot
        hold a symlink must not take the agent down.
        """
        if not self.symlink_path:
            return False

        target = os.path.abspath(self.baseFilename)
        link = os.path.abspath(self.symlink_path)

        try:
            if os.path.islink(link):
                # Already points where it should — nothing to do.
                if os.readlink(link) == target:
                    return True
            elif os.path.exists(link):
                # A real file sits where the symlink should be.  It is not
                # ours to destroy.
                return False

            # Build the new link beside the old one and move it into place:
            # os.replace() swaps the link atomically, so a reader never sees
            # a half-written link.
            tmp = f"{link}.tmp.{os.getpid()}"
            if os.path.lexists(tmp):
                os.remove(tmp)
            os.symlink(target, tmp)
            os.replace(tmp, link)
            return True
        except (OSError, NotImplementedError):
            return False

    def doRollover(self) -> None:
        """Rotate the file, then make sure the symlink is still in place."""
        super().doRollover()
        self.refresh_symlink()

    # -- the record --------------------------------------------------------

    def emit(self, record: logging.LogRecord) -> None:
        """Write the record.

        Split out from the base class so the drift harness has one place
        to break when it proves that the invariant catches a record that
        is swallowed.
        """
        super().emit(record)


# ---------------------------------------------------------------------------
# The size limit
# ---------------------------------------------------------------------------

#: The units the operator may write in the command line.
SIZE_UNITS = {
    "": 1,
    "B": 1,
    "K": 1024,
    "KB": 1024,
    "M": 1024 ** 2,
    "MB": 1024 ** 2,
    "G": 1024 ** 3,
    "GB": 1024 ** 3,
}


def parse_size(value: str | int) -> int:
    """Parse a human size — ``10MB``, ``512K``, ``1G`` — into bytes.

    A plain number is a number of bytes.  An unknown unit is a **typo**,
    and a typo must be reported rather than silently ignored: a log that
    never rotates because the size was not understood is the exact
    failure this feature exists to prevent.
    """
    if isinstance(value, int):
        if value < 0:
            raise ValueError(f"the size must not be negative: {value}")
        return value

    text = str(value).strip().upper()
    if not text:
        raise ValueError("the size is empty")

    # Split the number from the unit.
    index = 0
    while index < len(text) and (text[index].isdigit() or text[index] == "."):
        index += 1
    number, unit = text[:index], text[index:].strip()

    if not number:
        raise ValueError(f"the size has no number in it: {value!r}")
    if unit not in SIZE_UNITS:
        raise ValueError(
            f"unknown size unit {unit!r} in {value!r} — use B, KB, MB or GB"
        )

    size = int(float(number) * SIZE_UNITS[unit])
    if size <= 0:
        raise ValueError(f"the size must be greater than zero: {value!r}")
    return size


# ---------------------------------------------------------------------------
# The wiring
# ---------------------------------------------------------------------------

def install_file_logging(
    log_file: str,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    symlink_path: str | None = None,
    level: int = logging.INFO,
) -> SymlinkedRotatingFileHandler:
    """Attach a rotating file handler to the root logger.

    The stderr handler is left alone: the file is a **tee**, not a
    replacement, so the operator still sees the output in the terminal.
    """
    log_path = Path(log_file).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if symlink_path is None:
        symlink_path = str(
            log_path.with_name(f"{log_path.stem}-current{log_path.suffix}")
        )

    handler = SymlinkedRotatingFileHandler(
        str(log_path),
        max_bytes=max_bytes,
        backup_count=backup_count,
        symlink_path=symlink_path,
    )
    handler.setLevel(level)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    return handler


# ---------------------------------------------------------------------------
# The demonstration
# ---------------------------------------------------------------------------

def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="torvalds-log-"))
    log_file = tmp / "agent.log"

    print(f"log directory : {tmp}")
    print(f"log file      : {log_file}")
    print()

    handler = install_file_logging(
        str(log_file),
        max_bytes=4096,          # small, so the demo rotates
        backup_count=3,
        level=logging.INFO,
    )

    logger = logging.getLogger("prototype")
    logger.info("first record — before any rotation")

    print("=== after the first record ===")
    _show(tmp)
    print()

    # Write enough to cross the limit several times.
    for i in range(400):
        logger.info("record %03d — %s", i, "x" * 80)

    print("=== after 400 records ===")
    _show(tmp)
    print()

    # -- the checks --------------------------------------------------------

    link = Path(handler.symlink_path)
    target = Path(log_file)
    ok = True

    print("=== the checks ===")

    live = os.path.realpath(link) == os.path.realpath(target)
    print(f"[{'OK' if live else 'FAIL'}] the symlink resolves to the live log file")
    ok &= live

    # The symlink must point at the file the handler is *currently writing*.
    stat_link = os.stat(link)
    stat_file = os.stat(target)
    same_inode = stat_link.st_ino == stat_file.st_ino
    print(f"[{'OK' if same_inode else 'FAIL'}] the symlink and the live file are the same inode")
    ok &= same_inode

    rotated = sorted(p.name for p in tmp.glob("agent.log.*"))
    print(f"[{'OK' if rotated else 'FAIL'}] the rotated files exist: {rotated}")
    ok &= bool(rotated)

    kept = len(rotated) <= handler.backupCount
    print(f"[{'OK' if kept else 'FAIL'}] no more than {handler.backupCount} generations are kept")
    ok &= kept

    mode = stat_file.st_mode & 0o777
    private = mode == 0o600
    print(f"[{'OK' if private else 'FAIL'}] the log file is private ({oct(mode)})")
    ok &= private

    print()
    print("=== the tail of the live file ===")
    with open(target, encoding="utf-8") as fh:
        for line in fh.readlines()[-3:]:
            print(f"  {line.rstrip()}")

    print()
    print("RESULT:", "all checks passed" if ok else "SOMETHING FAILED")
    return 0 if ok else 1


def _show(directory: Path) -> None:
    for path in sorted(directory.iterdir()):
        kind = "symlink -> " + os.readlink(path) if path.is_symlink() else "file"
        size = path.stat().st_size if path.exists() else 0
        print(f"  {path.name:<28} {kind:<45} {size:>8} bytes")


if __name__ == "__main__":
    sys.exit(main())
