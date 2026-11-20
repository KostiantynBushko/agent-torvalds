"""
The paths the TUI shows — the home of the operator is a ``~``.

The agent works with the real paths: the tools read the files the paths
name, and the paths are the paths of the machine.  The **screen** is
another thing — the home directory of the operator is private, and the
path on the screen carries it in full.

The helper hides the home in the text the TUI shows: the home becomes
``~/``, and everything behind it stays.  The path inside the text is not
touched — only the home is replaced.

It is **computed**, never written down: the home of the machine is
found at run time, and the helper is told which home to hide, so that
the check of the behaviour runs on a machine that is not the one of the
operator, and so that the repository never names a home of its own.

The window of the *Workflow & Tool Progress* pane is the same on every
machine, and the home is hidden the same way on every machine: a Linux
home, a macOS home and a Windows home are all a whole path component
that is replaced by ``~``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

#: What the home becomes on the screen.
HOME_MARK = "~"

#: The separator of a path, in both spellings: a path is written with
#: backslashes and with slashes, and the two are the same separator.
SEPARATORS = ("/", "\\")

#: The characters the name of a folder can carry.
#:
#: The home is a **whole path component**: a name that only *starts*
#: with the home is another name, and it is not the home of the
#: operator.  Every character that is not in this set ends the name —
#: a separator ends it, a quote ends it, a space ends it, and the end
#: of the text ends it.
NAME_CHARACTERS = r"A-Za-z0-9._+~@%-"


def the_home(home: Optional[str] = None) -> str:
    """
    The home directory that is to be hidden.

    The home of the machine, computed — the repository never names a
    home of its own.  A home that is given is the home to use: the
    check of the behaviour asks for a home of its own, and it runs on
    a machine that is not the one of the operator.
    """
    if home:
        return home
    try:
        return str(Path.home())
    except (RuntimeError, OSError):
        # The home of the machine cannot be found: there is nothing to
        # hide, and the text is left alone.
        return ""


def _is_a_windows_home(home: str) -> bool:
    """
    True when the home is spelled the way a Windows machine spells it.

    A Windows path is not case sensitive, and it is written with
    backslashes as well as with slashes.  The spelling of the home
    travels with the home: the same home is hidden the same way on
    every machine, and the check does not need a Windows machine to
    run to prove it.
    """
    return "\\" in home or bool(re.match(r"^[A-Za-z]:", home))


def _the_spellings(home: str) -> List[str]:
    """
    The spellings of the home that a path can carry.

    A path is written with backslashes and with slashes, and the two
    spellings of one home are hidden the same way.
    """
    spellings = {home, home.replace("\\", "/"), home.replace("/", "\\")}
    # The longest spelling first: a home that is the prefix of another
    # spelling must not be replaced by the shorter one.
    return sorted(spellings, key=len, reverse=True)


def hide_home(text: str, home: Optional[str] = None) -> str:
    """
    Hide the home of the operator in the text the screen shows.

    The home is a **whole path component**: the home of the operator is
    hidden, and a folder whose name only *starts* with the home — a
    folder named ``userdata`` next to the home ``/home/user`` — is
    another folder, and it is left alone.

    The home is hidden in front of a separator, in front of a quote, in
    front of a space, and at the end of the text — every character that
    cannot be a part of a name ends the name of the home.

    A path that ends at the home becomes ``~``, and a path that goes on
    below it becomes ``~/...`` — the way a shell writes it.  The
    separator behind the home is the one the path already uses: the
    path stays a path of its own system, and only the home is hidden.

    The text is returned unchanged when there is no home to hide, and
    when the home is the root of the filesystem: every path is below
    the root, and a ``~`` in its place would be a lie.
    """
    if not text:
        return text

    home = the_home(home)
    # The separator at the end of a home belongs to the path behind it,
    # not to the home.
    home = home.rstrip("".join(SEPARATORS))
    if not home or home.strip("".join(SEPARATORS)) == "":
        return text
    if re.fullmatch(r"[A-Za-z]:", home):
        # The root of a Windows drive: every path is below it.
        return text

    flags = re.IGNORECASE if _is_a_windows_home(home) else 0
    for spelling in _the_spellings(home):
        # The look-ahead asks that the home is not followed by a
        # character of a name: the home is a whole path component, and
        # the folder that only starts like it does not match.  A
        # separator, a quote, a space and the end of the text all end
        # the name of the home.
        pattern = re.compile(
            re.escape(spelling) + rf"(?![{NAME_CHARACTERS}])", flags
        )

        # The home becomes a "~" and the separator behind it stays: the
        # path below the home is the path of the machine, and only the
        # home is hidden.  The "~/" of a Linux path and the "~\\" of a
        # Windows path are the same thing, written the way the path
        # is written.
        text = pattern.sub(HOME_MARK, text)
    return text
