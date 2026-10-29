"""
File logging for the Torvalds agent — a rotating log file with a symlink
to the current one.

The operator asked for it on 2026-10-27:

    *"I want be able to redirect logging into file, this solution must have
    a posibility to rotare log when reaching current log file predefined
    size. Inside directory we must have soft link to current log file the
    files"*

Three requirements, one directory:

1.  the logging goes into a **file**;
2.  the file is **rotated** when it reaches a **predefined size**;
3.  the directory holds a **symlink to the current log file**, next to the
    rotated ones.

This module is the implementation of that request.  It is the **standard
library only** — ``logging``, ``logging.handlers``, ``os``, ``pathlib`` —
and it is self-contained, so it can be imported by either orchestrator
and copied into a temporary directory by the verification harness.

The design
----------

The rotation is ``logging.handlers.RotatingFileHandler``: it rotates when
the file reaches ``maxBytes`` and keeps ``backupCount`` generations
(``agent.log.1``, ``agent.log.2``, ...).  The subclass adds the two
things the standard handler does not have:

*   **the symlink** to the live log file, and
*   **the file mode** — ``0600``, because the standard handler creates
    the file with ``0666 & ~umask`` (``0664`` on this machine), and a log
    of this agent carries the system prompt, the user's requests, the
    tool output and the model's answers.

The symlink points at the **path** of the live log file, not at its
inode.  ``doRollover()`` renames ``agent.log`` to ``agent.log.1`` and
reopens ``agent.log`` — the path does not change, only the file at it
does.  A symlink to the path is therefore valid at every moment, before
and after every rotation, and it never has to be re-pointed.  A symlink
to an *inode* would have been dangling for an instant at every rotation.

What degrades and what does not
--------------------------------

The project's rule is that a missing feature **degrades** — it does not
take the agent down:

| Failure | What happens |
|---|---|
| The log directory cannot be created | A warning, the stderr logging continues, the agent boots. |
| The log file cannot be opened | A warning, the stderr logging continues, the agent boots. |
| The symlink cannot be created (Windows without the symlink privilege, a filesystem without symlinks) | A warning, the file logging continues. The symlink is a convenience, not the log. |
| The size cannot be parsed | The agent **stops** with the message. A typo is not a degradation: a log that never rotates is the exact failure this feature exists to prevent. |
| ``--log-max-files 0`` | The agent **stops** with the message. Zero generations means no rotation at all, and the file grows until the disk is full. |

The file logging is **off by default**.  The agent's behaviour does not
change until the operator asks for it, and a file that nobody asked for
is a file nobody cleans up.  When it is on, the file is a **tee**: the
stderr handler stays, so the operator still sees the output in the
terminal and the file carries the history.

Usage
-----

::

    from components.file_logging import (
        add_logging_arguments,
        build_file_handler,
        resolve_config,
    )

    # in parse_args():
    add_logging_arguments(parser)

    # in main(), after the arguments are parsed:
    config = resolve_config(
        log_file=args.log_file,
        log_dir=args.log_dir,
        max_size=args.log_max_size,
        max_files=args.log_max_files,
        symlink=args.log_symlink,
    )
    handler = build_file_handler(config, level)   # None when it degrades

Category: Infrastructure / Logging
Retriever Keywords: logging, file, rotate, rotation, symlink, log file,
                    rotating file handler, logrotate, stdout, stderr
"""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

__all__ = [
    "DEFAULT_LOG_DIR",
    "DEFAULT_MAX_FILES",
    "DEFAULT_MAX_SIZE",
    "ENV_LOG_DIR",
    "ENV_LOG_FILE",
    "ENV_LOG_MAX_FILES",
    "ENV_LOG_MAX_SIZE",
    "ENV_LOG_SYMLINK",
    "LogFileConfig",
    "SIZE_UNITS",
    "SymlinkedRotatingFileHandler",
    "add_logging_arguments",
    "build_file_handler",
    "default_symlink_path",
    "install_file_logging",
    "parse_size",
    "positive_int",
    "resolve_config",
    "size_argument",
]


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# The configuration surface
# ---------------------------------------------------------------------------

#: The directory that holds the log, the symlink and the rotated files.
#: It follows the convention the project already uses — ``~/.torvalds/``
#: for the chat history, ``~/.cache/torvalds/`` for the cache — and it is
#: **not** the working tree: the agent runs from wherever it is started.
DEFAULT_LOG_DIR = "~/.torvalds/logs"

#: The size at which the log is rotated.
DEFAULT_MAX_SIZE = "10MB"

#: How many generations are kept next to the live log file.
DEFAULT_MAX_FILES = 5

#: The environment variables.  They matter for the runs the agent does
#: not start itself — a ``systemd`` unit, a ``supervisord`` program, a
#: shell profile.  The flag wins over the environment.
ENV_LOG_FILE = "TORVALDS_LOG_FILE"
ENV_LOG_DIR = "TORVALDS_LOG_DIR"
ENV_LOG_MAX_SIZE = "TORVALDS_LOG_MAX_SIZE"
ENV_LOG_MAX_FILES = "TORVALDS_LOG_MAX_FILES"
ENV_LOG_SYMLINK = "TORVALDS_LOG_SYMLINK"


# ---------------------------------------------------------------------------
# The size limit
# ---------------------------------------------------------------------------

#: The units the operator may write in the command line.
SIZE_UNITS: dict[str, int] = {
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
    never rotates because the size was not understood is the exact failure
    this feature exists to prevent.

    Args:
        value: The size as the operator wrote it, or a number of bytes.

    Returns:
        The size in bytes.

    Raises:
        ValueError: The size is empty, carries no number, carries an
            unknown unit, or is not greater than zero.
    """
    if isinstance(value, bool):  # bool is an int — and it is never a size
        raise ValueError(f"the size is not a number: {value!r}")
    if isinstance(value, int):
        if value <= 0:
            raise ValueError(f"the size must be greater than zero: {value}")
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


def size_argument(value: str) -> int:
    """The ``argparse`` type of ``--log-max-size``.

    It turns the :class:`ValueError` of :func:`parse_size` into the
    ``ArgumentTypeError`` that ``argparse`` reports as a usage error, so
    a typo stops the agent with a message instead of a traceback.
    """
    try:
        return parse_size(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def positive_int(value: str | int) -> int:
    """Parse a number that must be at least one.

    Zero generations would disable the rotation entirely — the handler
    would reopen the same file in append mode and it would grow until the
    disk is full.  Zero is therefore **refused**, not accepted.
    """
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"not a number: {value!r}") from exc
    if number < 1:
        raise ValueError(
            f"the number of log files must be at least 1 — {number} would "
            f"disable the rotation"
        )
    return number


def positive_int_argument(value: str) -> int:
    """The ``argparse`` type of ``--log-max-files``."""
    try:
        return positive_int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


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
        self._symlink_reported = False
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
                self._report_symlink_problem(
                    f"{link} exists and is not a symlink — the pointer was left alone"
                )
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
        except (OSError, NotImplementedError) as exc:
            self._report_symlink_problem(
                f"the symlink {link} could not be created ({exc})"
            )
            return False

    def _report_symlink_problem(self, message: str) -> None:
        """Warn about a symlink that cannot be maintained — once.

        The warning is written to the log itself, so it is reported once
        per handler: a rollover that happens every ten megabytes must
        not fill the log with the same line.
        """
        if self._symlink_reported:
            return
        self._symlink_reported = True
        logger.warning(
            "%s — the file logging continues without it.", message
        )

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
# The configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LogFileConfig:
    """The resolved configuration of the file logging.

    It is resolved **once**, after the command line is parsed, and handed
    to the logging configuration as one object — the configuration is
    called twice in each orchestrator (once at module level, once after
    the arguments are parsed) and the second call replaces the handlers
    of the first, so the file handler must be built by the call that
    knows the flags.
    """

    #: The live log file — a real file, never a symlink.
    log_file: Path

    #: The size at which the file is rotated.
    max_bytes: int

    #: How many generations are kept next to the live file.
    backup_count: int

    #: The symlink to the live file, or ``None`` when the operator does
    #: not want one.
    symlink: Optional[Path] = None


def default_symlink_path(log_file: Path) -> Path:
    """The default name of the symlink: ``<stem>-current<suffix>``.

    It sits **next to** the log file, so the directory holds the live
    file, the pointer and the rotated generations together.
    """
    return log_file.parent / f"{log_file.stem}-current{log_file.suffix or '.log'}"


def resolve_config(
    log_file: str | None = None,
    log_dir: str | None = None,
    max_size: str | int | None = None,
    max_files: str | int | None = None,
    symlink: str | None = None,
    environ: Optional[Mapping[str, str]] = None,
) -> Optional[LogFileConfig]:
    """Resolve the file-logging configuration from the flags and the environment.

    The **flag wins over the environment**, and the environment wins over
    the default — the same order ``components/ollama_config.py`` uses
    for ``TORVALDS_OLLAMA_HOST``.

    Args:
        log_file: The log file.  A bare name goes into the log directory.
        log_dir: The directory that holds the log, the symlink and the
            rotated files.
        max_size: The size at which the log is rotated (``10MB``).
        max_files: How many generations are kept.
        symlink: The name of the symlink.  A bare name goes next to the
            log file.
        environ: The environment to read.  Defaults to ``os.environ``.

    Returns:
        The resolved configuration, or ``None`` when the file logging is
        **off** — which is the default.

    Raises:
        ValueError: The size or the number of files is not usable.  These
            are **not** degradations: they are typos, and a typo is
            reported rather than ignored.
    """
    env = os.environ if environ is None else environ

    # -- the file: the flag wins over the environment --------------------
    raw_file = log_file if log_file is not None else env.get(ENV_LOG_FILE)
    if raw_file is None or not str(raw_file).strip():
        # Off.  The agent logs to stderr exactly as it does today.
        return None

    # -- the directory ----------------------------------------------------
    raw_dir = log_dir if log_dir is not None else env.get(ENV_LOG_DIR)
    directory = (
        Path(str(raw_dir)).expanduser()
        if raw_dir and str(raw_dir).strip()
        else Path(DEFAULT_LOG_DIR).expanduser()
    )

    # -- the file itself --------------------------------------------------
    file_path = Path(str(raw_file)).expanduser()
    if not file_path.parent.parts:
        # A bare name goes into the log directory.
        file_path = directory / file_path
    elif not file_path.is_absolute():
        # A relative path with a directory in it is relative to the
        # working directory of the agent.
        file_path = Path(os.getcwd()) / file_path

    # -- the size ---------------------------------------------------------
    if max_size is None:
        raw_size = env.get(ENV_LOG_MAX_SIZE, DEFAULT_MAX_SIZE)
        max_bytes = parse_size(raw_size)
    elif isinstance(max_size, int) and not isinstance(max_size, bool):
        max_bytes = parse_size(max_size)
    else:
        max_bytes = parse_size(max_size)

    # -- the number of generations ----------------------------------------
    if max_files is None:
        raw_files = env.get(ENV_LOG_MAX_FILES, str(DEFAULT_MAX_FILES))
        backup_count = positive_int(raw_files)
    elif isinstance(max_files, int) and not isinstance(max_files, bool):
        backup_count = positive_int(max_files)
    else:
        backup_count = positive_int(max_files)

    # -- the symlink ------------------------------------------------------
    raw_symlink = symlink if symlink is not None else env.get(ENV_LOG_SYMLINK)
    if raw_symlink is None or not str(raw_symlink).strip():
        # The default: "<stem>-current<suffix>" next to the log file, so
        # the directory holds the live file, the pointer and the
        # generations together.
        symlink_path: Optional[Path] = default_symlink_path(file_path)
    elif str(raw_symlink).strip().lower() == "none":
        # The operator asked for no pointer at all.  It has to be said
        # explicitly: an empty variable is an unset variable, and it must
        # not silently take the symlink away.
        symlink_path = None
    else:
        candidate = Path(str(raw_symlink)).expanduser()
        if not candidate.parent.parts:
            candidate = file_path.parent / candidate
        symlink_path = candidate

    return LogFileConfig(
        log_file=file_path,
        max_bytes=max_bytes,
        backup_count=backup_count,
        symlink=symlink_path,
    )


def add_logging_arguments(
    parser: argparse.ArgumentParser,
    defaults: Optional[Mapping[str, str]] = None,
) -> None:
    """Add the five file-logging flags to an argument parser.

    The flags follow the pattern the project already uses: the
    **environment variable** first, the **flag** second, the flag wins.
    The environment variable is read as the *default* of the argument, so
    ``argparse`` validates it with the same type as the flag — a typo in
    ``TORVALDS_LOG_MAX_SIZE`` stops the agent with the same message as a
    typo in ``--log-max-size``.

    Args:
        parser: The parser the flags are added to.
        defaults: The values the **configuration file** resolved, used as
            the default of the flags.  They are already resolved — the
            environment variable won over the file — so the parser only
            has to validate them, exactly as it validates the environment
            variable today.
    """
    values = dict(defaults or {})

    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Write the log into this file. A bare name goes into the log "
             f"directory ({DEFAULT_LOG_DIR}). The file logging is off when "
             "the flag is absent.",
    )
    parser.add_argument(
        "--log-dir",
        type=str,
        default=None,
        help=f"The directory that holds the log, the symlink and the rotated "
             f"files (default: {DEFAULT_LOG_DIR}).",
    )
    parser.add_argument(
        "--log-max-size",
        type=size_argument,
        default=values.get(
            "max_size", os.environ.get(ENV_LOG_MAX_SIZE, DEFAULT_MAX_SIZE)
        ),
        help="The size at which the log is rotated (default: %(default)s). "
             "Units: B, KB, MB, GB.",
    )
    parser.add_argument(
        "--log-max-files",
        type=positive_int_argument,
        default=values.get(
            "max_files", os.environ.get(ENV_LOG_MAX_FILES, str(DEFAULT_MAX_FILES))
        ),
        help="How many rotated generations are kept next to the live log "
             "file (default: %(default)s).",
    )
    parser.add_argument(
        "--log-symlink",
        type=str,
        default=None,
        help="The name of the symlink that points at the live log file "
             "(default: <stem>-current.log next to it).",
    )


# ---------------------------------------------------------------------------
# The wiring
# ---------------------------------------------------------------------------

def build_file_handler(
    config: Optional[LogFileConfig],
    level: int = logging.INFO,
) -> Optional[SymlinkedRotatingFileHandler]:
    """Build the rotating file handler for a resolved configuration.

    The handler is **not** attached to the root logger here: the
    orchestrators manage the root logger themselves, and the second
    ``configure_logging()`` call replaces the handlers of the first.

    Returns ``None`` — with a warning — when the file logging cannot be
    set up.  The caller keeps the stderr handler, and the agent boots.
    """
    if config is None:
        return None

    try:
        config.log_file.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning(
            "The log directory %s could not be created (%s) — the logging "
            "stays on stderr.",
            config.log_file.parent,
            exc,
        )
        return None

    try:
        handler = SymlinkedRotatingFileHandler(
            str(config.log_file),
            max_bytes=config.max_bytes,
            backup_count=config.backup_count,
            symlink_path=str(config.symlink) if config.symlink else None,
        )
    except OSError as exc:
        logger.warning(
            "The log file %s could not be opened (%s) — the logging stays "
            "on stderr.",
            config.log_file,
            exc,
        )
        return None

    handler.setLevel(level)
    return handler


def install_file_logging(
    log_file: str,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = DEFAULT_MAX_FILES,
    symlink_path: str | None = None,
    level: int = logging.INFO,
) -> Optional[SymlinkedRotatingFileHandler]:
    """Attach a rotating file handler to the root logger.

    The stderr handler is left alone: the file is a **tee**, not a
    replacement, so the operator still sees the output in the terminal.

    This is the convenience API — the orchestrators use
    :func:`build_file_handler` instead, because they hand the handler to
    ``logging.basicConfig()`` themselves.
    """
    path = Path(str(log_file)).expanduser()
    config = LogFileConfig(
        log_file=path,
        max_bytes=max_bytes,
        backup_count=backup_count,
        symlink=(
            Path(str(symlink_path)).expanduser()
            if symlink_path
            else default_symlink_path(path)
        ),
    )
    handler = build_file_handler(config, level)
    if handler is None:
        return None

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    return handler
