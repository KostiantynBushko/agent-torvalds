"""
The console of the TUI must believe the terminal, not the environment.

Rich reads ``COLUMNS`` and ``LINES`` from the environment before it
asks the terminal, and the shell exports them as a snapshot of the
size the terminal had when the shell started.  A console that believes
them lays the multi-window layout out for a terminal that is not there:
the frame is wider than the screen, the terminal folds it, the panes
leave their columns, and the screen scrolls on every frame.

The console of the TUI is therefore built with an environment that
carries no ``COLUMNS`` and no ``LINES``.  Everything else in the
environment stays, so ``TERM``, ``NO_COLOR`` and the rest keep
working.

Nothing is forced: the size is asked of the terminal on every access,
so the layout follows the terminal when it is resized.

See ``investigate/tui-selection-and-flicker/`` for the investigation
that led here.

Category: Infrastructure / Terminal
Retriever Keywords: console, terminal, size, LINES, COLUMNS, rich, TUI,
                    layout, resize
"""

from __future__ import annotations

import os
from typing import Mapping, Optional

from rich.console import Console

__all__ = [
    "SIZE_VARIABLES",
    "build_console",
    "console_environ",
]


#: The variables that describe a terminal that is not there.  They are a
#: snapshot the shell exported, and they do not follow a resize.
SIZE_VARIABLES = ("COLUMNS", "LINES")


def console_environ(environ: Optional[Mapping[str, str]] = None) -> dict:
    """The environment for a console that asks the terminal for its size.

    Args:
        environ: The environment to start from.  Defaults to
            ``os.environ``.

    Returns:
        A copy of the environment without ``COLUMNS`` and without
        ``LINES``.
    """
    source = os.environ if environ is None else environ
    return {
        key: value
        for key, value in source.items()
        if key not in SIZE_VARIABLES
    }


def build_console(
    environ: Optional[Mapping[str, str]] = None,
    **kwargs,
) -> Console:
    """Build a console that believes the size of the terminal.

    Args:
        environ: The environment to start from.  Defaults to
            ``os.environ``.
        **kwargs: Passed on to ``rich.console.Console``.

    Returns:
        A console that asks the terminal for its size, and that follows
        it when the terminal is resized.
    """
    return Console(_environ=console_environ(environ), **kwargs)
