"""
While the TUI is up, the log goes into the file — never onto the screen.

The multi-window TUI owns the terminal while it runs.  The Live display
writes the whole screen on every frame, and the terminal folds the
frame when it does not fit.  A log line written to ``stderr`` in that
moment is written **on top of the layout**, and it scrolls the screen:
the scroll is visible as a blink, and it is visible exactly while a
request runs, because that is when the agent logs.

The operator decided on 2026-11-13:

    *the log must go into file, not painted over*

So the root logger loses its terminal handlers for the time of the TUI,
and gains a file handler in their place:

*   the **file handler the operator configured** (``--log-file``), when
    there is one — the log lands where the operator expects it;
*   otherwise a **default file handler** in the log directory, so the
    log is not lost and not thrown at the terminal either.

The file handler rotates, so the file does not grow without bound, and
it is private (``0600``), because the log of this agent carries the
prompts, the tool output and the answers of the model.

When the TUI is done the terminal handlers come back: the classic REPL
logs on the terminal exactly as it always has.

Nothing here is fatal.  A log directory that cannot be created, a log
file that cannot be opened — the module that builds the handler
(``components/file_logging.py``) reports it and returns ``None``.  The
TUI then runs with the terminal handlers in place: the layout is
painted over by the log, which is what the agent did before, and the
agent still works.

See ``investigate/tui-selection-and-flicker/`` for the investigation
that led here.

Category: Infrastructure / Logging
Retriever Keywords: logging, log file, stderr, terminal, TUI, alternate
                    screen, rotate, blink, flicker
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Iterator, List, Optional

from components.file_logging import (
    DEFAULT_LOG_DIR,
    DEFAULT_MAX_FILES,
    DEFAULT_MAX_SIZE,
    ENV_LOG_DIR,
    ENV_LOG_FILE,
    ENV_LOG_MAX_FILES,
    ENV_LOG_MAX_SIZE,
    LogFileConfig,
    build_file_handler,
    resolve_config,
)

__all__ = [
    "DEFAULT_TUI_LOG_FILE",
    "log_to_file",
    "resolve_tui_log_config",
    "terminal_handlers",
]


#: The name of the log file the TUI writes when the operator did not
#: ask for one.  It sits in the log directory of the project.
DEFAULT_TUI_LOG_FILE = "agent.log"


def terminal_handlers(
    root: Optional[logging.Logger] = None,
) -> List[logging.Handler]:
    """The handlers of *root* that write to the terminal.

    A handler that writes to a **file** is not one of them — that is
    where the log is supposed to go.  Every other stream handler
    writes to a stream of the process: to ``stderr``, to ``stdout``,
    or to something else that is not a file.  While the TUI is up, all
    of them are in the way.

    Args:
        root: The logger to look at.  Defaults to the root logger.

    Returns:
        The handlers that write to the terminal.
    """
    logger = logging.getLogger() if root is None else root
    found = []
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            # A file handler writes to a file.
            continue
        if isinstance(handler, logging.StreamHandler):
            found.append(handler)
    return found


def resolve_tui_log_config(
    config: Optional[LogFileConfig] = None,
    environ: Optional[dict] = None,
) -> LogFileConfig:
    """The configuration of the log file the TUI writes into.

    The configuration the operator asked for wins.  When there is none,
    the TUI still needs a file — the log must not land on the terminal
    — and it gets one in the log directory of the project, with the
    same rotation as every other log file.

    Args:
        config: The configuration the operator asked for, or ``None``.
        environ: The environment to read.  Defaults to ``os.environ``.

    Returns:
        The resolved configuration.  It is never ``None``: the TUI always
        has a file to write into.
    """
    if config is not None:
        return config

    env = dict(os.environ if environ is None else environ)
    resolved = resolve_config(
        log_file=env.get(ENV_LOG_FILE) or DEFAULT_TUI_LOG_FILE,
        log_dir=env.get(ENV_LOG_DIR),
        max_size=env.get(ENV_LOG_MAX_SIZE, DEFAULT_MAX_SIZE),
        max_files=env.get(ENV_LOG_MAX_FILES, str(DEFAULT_MAX_FILES)),
        environ=env,
    )
    if resolved is None:
        # resolve_config() only returns None when the file is empty, and
        # a name was given.  The default name is therefore always there.
        raise RuntimeError(
            "the log file of the TUI could not be resolved - "
            f"the log directory is {DEFAULT_LOG_DIR}"
        )
    return resolved


@contextmanager
def log_to_file(
    config: Optional[LogFileConfig] = None,
    level: Optional[int] = None,
    root: Optional[logging.Logger] = None,
) -> Iterator[Optional[logging.Handler]]:
    """Keep the log off the terminal while the TUI is up.

    The terminal handlers of the root logger are removed for the time of
    the block, and a file handler takes their place.  Everything is put
    back when the block ends.

    Args:
        config: The configuration of the log file.  When it is ``None``,
            the default of the project is resolved.
        level: The level of the file handler.  Defaults to the level of
            the root logger.
        root: The logger to route.  Defaults to the root logger.

    Yields:
        The file handler, or ``None`` when the file could not be opened
        — the log then stays where it was.
    """
    logger = logging.getLogger() if root is None else root
    effective_level = logger.level if level is None else level

    saved = list(logger.handlers)
    to_remove = terminal_handlers(logger)

    # The file handler is built **before** the terminal handlers go
    # away: a warning about a log file that cannot be opened has to
    # reach the operator, and the terminal is the only place it can.
    handler: Optional[logging.Handler] = None
    added = False
    try:
        handler = build_file_handler(resolve_tui_log_config(config), effective_level)
    except Exception:  # noqa: BLE001 - the log is never worth a run
        handler = None

    if handler is not None:
        logger.addHandler(handler)
        added = True

    if to_remove:
        for terminal_handler in to_remove:
            logger.removeHandler(terminal_handler)

    try:
        yield handler
    finally:
        if added and handler is not None and handler in logger.handlers:
            logger.removeHandler(handler)
        for previous in saved:
            if previous not in logger.handlers:
                logger.addHandler(previous)
