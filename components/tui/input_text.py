"""
The text of the input bar of the TUI.

The command bar carries what the operator types.  It carries up to
three lines: the operator adds a line with Shift+Enter, and a paste
that is longer than that is seen through a window of three lines that
follows the cursor.

The buffer itself is flat — a string with newlines in it — and this
module is the one place that knows how that string is *seen*: which
lines are on the screen, and where the cursor is inside them.

The view never grows past three lines.  A text that is longer is not
truncated: the operator can still walk the cursor through it and edit
it, and the window follows the cursor.
"""
from typing import List, Tuple

#: The number of lines the input bar shows.  The view never grows past
#: it: a text that is longer is seen through a window.
MAX_INPUT_LINES = 3

#: The control characters that are dropped from a paste.  The terminal
#: acts on them -- an escape sequence in a pasted text would move the
#: cursor of the TUI and change the state of the terminal, and a
#: pasted text is not allowed to do that.  The line break and the tab
#: are kept: they are text.
_CONTROL_CHARACTERS = "".join(
    chr(code) for code in range(32) if chr(code) not in "\n\t"
) + "".join(chr(code) for code in range(128, 160)) + "\x7f"


def normalize_paste(text: str) -> str:
    """The text of a paste, as the input bar takes it.

    The clipboard carries the line endings of the system it was copied
    on: a paste from Windows arrives with CRLF, and a paste from a
    Linux terminal arrives with LF.  Both are one line break here.

    The control characters are dropped: the terminal acts on them, and
    a pasted text is not allowed to move the cursor of the TUI or to
    change the state of the terminal.

    Args:
        text: The text as it came from the terminal.

    Returns:
        The text with every line ending turned into a single line break
        and without the control characters.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.translate({ord(character): None for character in _CONTROL_CHARACTERS})


def split_lines(text: str) -> List[str]:
    """The lines of the text.

    Args:
        text: The text of the input bar.

    Returns:
        The lines of the text.  An empty text is one empty line.
    """
    return text.split("\n")


def line_count(text: str) -> int:
    """The number of lines the text holds.

    Args:
        text: The text of the input bar.

    Returns:
        The number of lines.  An empty text is one line.
    """
    return text.count("\n") + 1


def cursor_line(text: str, pos: int) -> int:
    """The line the cursor is on.

    Args:
        text: The text of the input bar.
        pos: The position of the cursor in the text.

    Returns:
        The number of the line, counted from zero.
    """
    pos = max(0, min(len(text), pos))
    return text.count("\n", 0, pos)


def cursor_column(text: str, pos: int) -> int:
    """The column of the cursor inside its line.

    Args:
        text: The text of the input bar.
        pos: The position of the cursor in the text.

    Returns:
        The number of cells from the start of the line.
    """
    pos = max(0, min(len(text), pos))
    start = text.rfind("\n", 0, pos) + 1
    return pos - start


def visible_window(
    text: str,
    pos: int,
    max_lines: int = MAX_INPUT_LINES,
) -> Tuple[List[str], int, int]:
    """The lines of the text that are on the screen, and the cursor.

    When the text holds more lines than the view shows, the view is a
    window over the text: it follows the cursor, and the cursor is kept
    at the bottom of the window.  A paste that is longer than the
    window therefore ends with its last lines on the screen — and the
    operator can walk the cursor back into the text above and edit it.

    Args:
        text: The text of the input bar.
        pos: The position of the cursor in the text.
        max_lines: The number of lines the view shows.

    Returns:
        A tuple of the lines of the window, the row of the cursor
        inside the window and the column of the cursor.
    """
    lines = split_lines(text)
    row = cursor_line(text, pos)
    column = cursor_column(text, pos)

    if len(lines) <= max_lines:
        return lines, row, column

    start = max(0, min(row - max_lines + 1, len(lines) - max_lines))
    window = lines[start:start + max_lines]
    return window, row - start, column


def visible_line_count(text: str, max_lines: int = MAX_INPUT_LINES) -> int:
    """The number of lines the input bar shows.

    Args:
        text: The text of the input bar.
        max_lines: The number of lines the view shows.

    Returns:
        The number of lines on the screen.
    """
    return min(line_count(text), max_lines)


def move_cursor_up(text: str, pos: int) -> int:
    """The position of the cursor one line up.

    The column of the cursor is kept when the line above is long
    enough, and the cursor stops at the end of that line when it is
    not.

    Args:
        text: The text of the input bar.
        pos: The position of the cursor in the text.

    Returns:
        The new position of the cursor.
    """
    pos = max(0, min(len(text), pos))
    if pos == 0:
        return 0

    line_start = text.rfind("\n", 0, pos) + 1
    if line_start == 0:
        # The cursor is on the first line already.
        return 0

    column = pos - line_start
    previous_start = text.rfind("\n", 0, line_start - 1) + 1
    previous_end = line_start - 1
    return min(previous_start + column, previous_end)


def move_cursor_down(text: str, pos: int) -> int:
    """The position of the cursor one line down.

    Args:
        text: The text of the input bar.
        pos: The position of the cursor in the text.

    Returns:
        The new position of the cursor.
    """
    pos = max(0, min(len(text), pos))
    line_end = text.find("\n", pos)
    if line_end == -1:
        # The cursor is on the last line already.
        return pos

    column = pos - (text.rfind("\n", 0, pos) + 1)
    next_start = line_end + 1
    next_end = text.find("\n", next_start)
    if next_end == -1:
        next_end = len(text)
    return next_start + min(column, next_end - next_start)
