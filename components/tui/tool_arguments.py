"""
The arguments of a tool call, as the pane shows them.

The *Workflow & Tool Progress* pane shows the tool that runs and, under
its name, the line that says what it works on.  That line carried the
arguments of **one** tool -- the shell command -- and the call of every
other tool was a name with nothing under it: the operator saw

    ✔ write_file (3ms)

and did not see the file that was written, the folder it was written
in, or the text that was written in it.

The operator asked on 2026-11-23 for the same for every tool:

    currently only execute shell command shows a list of arguments in
    Workflow & Tool Progress window, I think the same must be applied
    to all tools call

This module is the **rule** that turns the arguments of a call into the
text of that line:

* a call with **one** argument shows the **value** alone -- the name of
  the argument would only add noise, and the command of the operator
  keeps the look it has had since it is shown whole;
* a call with **several** arguments names them -- ``name=value``, one
  argument per line, so that each of them is read on its own and the
  operator can tell which argument is which.  The names are shown when
  the call **has** several arguments, and not only when several of them
  carry a value: an argument that was not given is not shown, and the
  argument beside it keeps its name;
* an argument that was **not given** is not shown -- a tool that is
  called with ``path=None`` was called without a path;
* a value that carries **more lines than the pane shows** is
  **folded**: the head of the value is shown, and a marker says how
  many lines were left out.  The body of a file is not a line of the
  pane, and a pane that carries it whole is a pane that carries
  nothing else.

The **state** keeps the arguments as they were given, and the **view**
uses this rule: the screen decides what is shown of them, the way it
decides where the home of the operator is hidden.
"""

from __future__ import annotations

from typing import Any, List, Mapping, Tuple

#: How many lines of a value the pane shows.  A value that carries more
#: lines than that is folded -- the head of it is shown, and the marker
#: says how many lines were left out.
#:
#: The number is a number of the **pane**, not of the screen: the pane
#: shows the task that runs now on top of it and a few of the tasks
#: that are done below it, and a value that takes the whole pane is a
#: value that hides the log.  A command that is a script of a few lines
#: is shown whole -- the operator asked for the whole command -- and a
#: body of a file, which is long by its nature, is folded.
MAX_VALUE_LINES = 6

#: The marker that says how much of a value was left out.
FOLDED = "… {count} more {word} …"


def the_folded_marker(count: int) -> str:
    """
    The marker that says how much of a value was left out.

    The marker is honest: the operator knows that there is more of the
    value, and how much of it there is.

    Args:
        count: The number of the lines that were left out.

    Returns:
        The text of the marker.
    """
    word = "line" if count == 1 else "lines"
    return FOLDED.format(count=count, word=word)


def the_arguments_that_were_given(
    arguments: Any,
) -> List[Tuple[str, Any]]:
    """
    The arguments of a call that carry a value.

    An argument whose value is ``None`` was **not given**: a tool that
    is called with ``path=None`` was called without a path, and a line
    that shows it says that the tool was called with something.

    Arguments that are not a mapping are not arguments at all: the
    event that carries them is not a call of a tool, and the pane shows
    nothing for it.

    Args:
        arguments: The arguments of the call.

    Returns:
        The name of every argument that was given, and its value.
    """
    if not isinstance(arguments, Mapping):
        return []
    return [
        (str(name), value)
        for name, value in arguments.items()
        if value is not None
    ]


def the_value_of(argument: Any) -> str:
    """
    The value of an argument, as the screen shows it.

    A string is shown as it is.  Every other value is shown the way
    Python writes it: the pane says what the tool was given, and a
    number, a flag and a dictionary are shown as they are.

    Args:
        argument: The value of the argument.

    Returns:
        The text of the value.
    """
    if isinstance(argument, str):
        return argument
    if isinstance(argument, (bytes, bytearray)):
        return bytes(argument).decode("utf-8", errors="replace")
    return str(argument)


def the_lines_of_a_value(
    value: Any,
    lines: int = MAX_VALUE_LINES,
) -> List[str]:
    """
    The lines of a value, and the marker of the lines that were left out.

    The line breaks that are in the value are kept: a value may be a
    script of more than one line.  A value that carries more lines than
    the pane shows is **folded** -- the head of it is shown, and the
    marker says how many lines were left out.  The marker is honest:
    the operator knows that there is more, and how much of it there is.

    Args:
        value: The value of the argument.
        lines: How many lines of the value the pane shows.

    Returns:
        The lines of the value.
    """
    text = the_value_of(value)
    limit = max(1, int(lines))
    # The value is split **as far as it is shown**: the lines that are
    # left out are counted, and not built.  The pane is drawn again and
    # again, and a body of a file is split into its lines on every
    # frame otherwise.
    parts = text.split("\n", limit)
    if len(parts) <= limit:
        return parts
    kept = parts[:limit]
    hidden = text.count("\n") - (limit - 1)
    kept.append(the_folded_marker(hidden))
    return kept


def format_arguments(
    arguments: Any,
    lines: int = MAX_VALUE_LINES,
) -> str:
    """
    The detail of a tool call: the arguments of the call.

    A call with one argument shows the value alone, and a call with
    several arguments names them -- one argument per line, so that each
    of them is read on its own.

    Args:
        arguments: The arguments of the call.
        lines: How many lines of a value the pane shows.

    Returns:
        The text of the detail of the call -- an empty text when the
        call was made without arguments.
    """
    given = the_arguments_that_were_given(arguments)
    if not given:
        return ""

    if len(arguments) == 1:
        # One argument: the value alone.  The name of the argument
        # would only add noise, and the command of the operator keeps
        # the look it has had since it is shown whole.
        return "\n".join(the_lines_of_a_value(given[0][1], lines))

    detail: List[str] = []
    for name, value in given:
        parts = the_lines_of_a_value(value, lines)
        detail.append(f"{name}={parts[0]}")
        detail.extend(parts[1:])
    return "\n".join(detail)
