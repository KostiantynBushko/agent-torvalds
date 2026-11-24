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

The first answer was to show **every** argument of **every** call.  The
operator read the answer, found that the second half of it was too
much, and said so:

    not every tool must show everything it takes as an argument, for
    example write_file, it would be nice to see the path to the file
    but I'm not sure it is ok to print the content it writes

So the pane knows two kinds of argument, and it shows them differently:

* a **target** -- a path, a name, a flag, the command of the shell --
  is shown **whole**.  It is where the work happens, and the operator
  reads it at a glance;
* a **payload** -- the body of a file, the message of a commit, the
  rows of a table, the environment of a command, a password -- is
  **measured**, and never printed: the pane says how much of it there
  is, and not what is in it.

A payload is measured for two reasons.  It is where the **secrets**
are: a key that is written in a file is on the screen of the pane with
the text of the file, and the pane is the thing that is shared, that
is scrolled past, and that is read over the shoulder of the operator.
And it is where the **bulk** is: a file of three hundred lines takes
eight lines of the pane away from the log of everything else, and the
pane is a monitor -- it says what the agent is doing, and not what is
in every byte of it.

Nothing is lost by this.  The payload is at the **path** that is shown
beside it, and the agent says what it wrote in the document pane.  The
measure is honest in the way the marker of a folded value is honest,
and it is more exact than the marker: the operator knows how many
lines there are and how big they are, and not only that there is more.

The **command of the shell** is not a payload.  It is the act, and the
operator has to see every character of what runs.  It stays whole, the
way it has been shown since it was shown whole.

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
* an argument that carries a **payload** keeps its name and is shown as
  its **measure** -- the payload is never printed, not even its head;
* a value that the pane does not know -- a table, an object of a
  toolkit -- is shown as its **kind** and as how much of it there is:
  the arguments of a call come from the model, and the pane does not
  print what it does not know;
* a value that is **not** a payload and carries **more lines than the
  pane shows** is **folded**: the head of the value is shown, and a
  marker says how many lines were left out.  The body of a script is
  not a line of the pane, and a pane that carries it whole is a pane
  that carries nothing else.

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
#: body of a file, which is long by its nature, is measured and not
#: folded.
MAX_VALUE_LINES = 6

#: The marker that says how much of a value was left out.
FOLDED = "… {count} more {word} …"

#: The names of the arguments that carry a **payload**.
#:
#: The names are the names the tools of the agent use -- they are taken
#: from the toolkits themselves -- and the match does not care about
#: the case of the name.  A name that is not on this list is a
#: **target**: a path, a name, a flag, or the command of the shell, and
#: it is shown whole.
#:
#: The list is the whole contract between the tools and the pane: a
#: tool that hands over a body under another name is a tool whose body
#: is printed, and the name of that argument belongs on this list.
#:
#: Three names were added on 2026-11-24, after the rule was read
#: against the toolkits themselves: **value** -- the content of a cell
#: of a table, **description** -- the text of an entry of a changelog
#: -- and **condition** -- the condition of a filter of a table.  The
#: three carry a body under a name that says nothing of it, and a body
#: that is printed is a body that is on the screen.
PAYLOAD_ARGUMENTS = frozenset(
    {
        "body",
        "comment",
        "commit_message",
        "condition",
        "content",
        "data",
        "description",
        "env_vars",
        "message",
        "password",
        "payload",
        "sudo_password",
        "text",
        "value",
    }
)

#: The units a size is said in.
SIZE_UNITS = ("B", "KB", "MB", "GB")


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


def is_a_payload(name: Any) -> bool:
    """
    Does the argument with this name carry a payload?

    A **payload** carries the body of the work: the text of a file, the
    message of a commit, the rows of a table, the environment of a
    command, a password.  The pane measures a payload and never prints
    it.

    Every other argument is a **target**: it names a place, a name, a
    flag, or the act that runs.  The pane shows a target whole.

    The names are the names the tools of the agent use, and the match
    does not care about the case of the name.

    Args:
        name: The name of the argument.

    Returns:
        True when the argument carries a payload.
    """
    return str(name).lower() in PAYLOAD_ARGUMENTS


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


def is_opaque(value: Any) -> bool:
    """
    Is the value one whose inside the pane does not know?

    The arguments of a call come from the model, and they are JSON: a
    text, a number, a flag, a list, a mapping.  A value of another kind
    -- a table, an object of a toolkit -- is **opaque**: the pane does
    not know what is inside it, and it says so instead of printing it.

    A number and a flag are not opaque: there is nothing in them that
    has to be hidden, and the operator reads them at a glance.

    Args:
        value: The value of the argument.

    Returns:
        True when the pane does not know what is inside the value.
    """
    if value is None:
        return False
    if isinstance(value, (str, bytes, bytearray, bool, int, float)):
        return False
    if isinstance(value, (Mapping, list, tuple, set, frozenset)):
        return False
    return True


def the_measure_of_an_opaque_value(value: Any) -> str:
    """
    The measure of a value the pane does not know: its kind, and how
    much of it there is.

    The pane says what kind of value it was given -- "DataFrame, 294
    items" -- and not one line of what is inside it.  The kind is what
    the operator needs: the table that is filtered is known by its
    name, and the rows of it are the business of the agent and of the
    document pane.

    Args:
        value: The value of the argument.

    Returns:
        The text of the measure.
    """
    kind = type(value).__name__
    try:
        count = len(value)
    except TypeError:
        return kind
    return f"{kind}, {count} items"


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

    A value that the pane does not know is measured and not printed:
    the kind of it is said, and not one line of what is inside it.

    Args:
        value: The value of the argument.
        lines: How many lines of the value the pane shows.

    Returns:
        The lines of the value.
    """
    if is_opaque(value):
        # The pane does not know what is inside the value: it says the
        # kind of it and how much of it there is, and prints nothing
        # of it.
        return [the_measure_of_an_opaque_value(value)]

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


def the_size_in_bytes(count: int) -> str:
    """
    A size, the way a person says it.

    512 B, 8.2 KB, 1.4 MB.

    Args:
        count: The number of bytes.

    Returns:
        The text of the size.
    """
    size = float(count)
    for unit in SIZE_UNITS:
        if size < 1024 or unit == SIZE_UNITS[-1]:
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{int(count)} B"


def the_measure_of_a_text(text: str) -> str:
    """
    The measure of a text: how many lines it has, and how big it is.

    A text that is empty has no lines at all.

    Args:
        text: The text of the payload.

    Returns:
        The text of the measure -- "294 lines, 8.2 KB".
    """
    if not text:
        return "0 lines, 0 B"
    lines = text.count("\n") + 1
    word = "line" if lines == 1 else "lines"
    size = the_size_in_bytes(len(text.encode("utf-8")))
    return f"{lines} {word}, {size}"


def the_measure_of_a_value(value: Any) -> str:
    """
    The measure of a payload: how much of it there is, and not what is in it.

    A text is measured in lines and in size, a list in items, and a
    mapping in keys.  A number and a flag are shown as they are: there
    is nothing in them that has to be hidden.  A value of another kind
    is measured by its kind: the pane does not know what is inside it,
    and it says so.

    Args:
        value: The value of the payload.

    Returns:
        The text of the measure.
    """
    if isinstance(value, str):
        return the_measure_of_a_text(value)
    if isinstance(value, (bytes, bytearray)):
        return the_measure_of_a_text(
            bytes(value).decode("utf-8", errors="replace")
        )
    if isinstance(value, Mapping):
        return f"{len(value)} keys"
    if isinstance(value, (list, tuple, set, frozenset)):
        return f"{len(value)} items"
    if value is None:
        return "none"
    if isinstance(value, (bool, int, float)):
        # A number and a flag are shown as they are: there is nothing
        # in them that has to be hidden.
        return the_value_of(value)
    return the_measure_of_an_opaque_value(value)


def format_arguments(
    arguments: Any,
    lines: int = MAX_VALUE_LINES,
) -> str:
    """
    The detail of a tool call: the arguments of the call.

    A call with one argument shows the value alone, and a call with
    several arguments names them -- one argument per line, so that each
    of them is read on its own.  An argument that carries a **payload**
    keeps its name and is shown as its **measure**: the payload is
    never printed.

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

    if len(arguments) == 1 and not is_a_payload(given[0][0]):
        # One argument: the value alone.  The name of the argument
        # would only add noise, and the command of the operator keeps
        # the look it has had since it is shown whole.  A payload keeps
        # its name: a measure without a name says nothing.
        return "\n".join(the_lines_of_a_value(given[0][1], lines))

    detail: List[str] = []
    for name, value in given:
        if is_a_payload(name):
            # The payload is measured and not printed: not its text,
            # and not its head either.
            detail.append(f"{name}={the_measure_of_a_value(value)}")
            continue
        parts = the_lines_of_a_value(value, lines)
        detail.append(f"{name}={parts[0]}")
        detail.extend(parts[1:])
    return "\n".join(detail)
