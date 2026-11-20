"""
The text of the input bar of the TUI.

The command bar carries what the operator types.  It carries up to
three lines of the screen: the text moves to the next line when it
reaches the end of the view, a paste brings the lines of its own, and a
paste that is longer than the window is seen through a window of three
lines that follows the cursor.

The buffer itself is flat — a string with newlines in it — and this
module is the one place that knows how that string is *seen*: which
lines are on the screen, and where the cursor is inside them.

The view never grows past three lines.  A text that is longer is not
truncated: the operator can still walk the cursor through it and edit
it, and the window follows the cursor.
"""
from typing import List, Optional, Tuple

from rich.cells import cell_len

#: The number of lines the input bar shows.  The view never grows past
#: it: a text that is longer is seen through a window.
MAX_INPUT_LINES = 3

#: The width of the text of the bar when the width is not known: a
#: width that no text of the operator reaches, so nothing is wrapped.
DEFAULT_WIDTH = 10000

#: The number of cells a tab takes on the screen.
TAB_CELLS = 8

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
    """The parts of the text between its line breaks.

    Args:
        text: The text of the input bar.

    Returns:
        The parts of the text.  An empty text is one empty part.
    """
    return text.split("\n")


def _cell_width(character: str) -> int:
    """The number of cells a character takes on the screen.

    Args:
        character: The character to measure.

    Returns:
        The number of cells of the character.  A tab takes the width
        of a tab stop, and a character that is not on the screen takes
        none.
    """
    if character == "\t":
        return TAB_CELLS
    return cell_len(character)


def _lines_of_part(part: str, start: int, width: int) -> List[Tuple[str, int]]:
    """The lines one part of the text takes, and where each one starts.

    Args:
        part: The part of the text, without its line break.
        start: The offset of the first character of the part in the
            text of the bar.
        width: The number of cells the text has on one line.

    Returns:
        A list of pairs: the text of the line, and the offset of its
        first character in the text of the bar.
    """
    if width <= 0:
        return [(part, start)]

    lines: List[Tuple[str, int]] = []
    position = 0

    while True:
        cells = 0
        cut = position
        while cut < len(part):
            cells += _cell_width(part[cut])
            if cells > width:
                break
            cut += 1

        if cut >= len(part):
            # The rest of the part fits on the line.
            lines.append((part[position:], start + position))
            break

        if cut == position:
            # One character is wider than the view: it is taken as it
            # is, and the line overflows by a cell.
            cut = position + 1

        space = part.rfind(" ", position, cut)
        if space <= position:
            # There is no space to break at: the word is folded over
            # the lines.
            lines.append((part[position:cut], start + position))
            position = cut
        else:
            # The line is broken at the space, and the space is eaten
            # by the break.
            lines.append((part[position:space], start + position))
            position = space + 1

    return lines


def wrap_lines(text: str, width: int = DEFAULT_WIDTH) -> List[Tuple[str, int]]:
    """The lines of the screen the text takes.

    A text that reaches the end of the view moves to the next line —
    the way the question of the agent moves to the next line in the
    agent-question mode.  The text is not truncated: every character
    of it is on some line.

    Args:
        text: The text of the input bar.
        width: The number of cells the text has on one line.

    Returns:
        A list of pairs: the text of the line, and the offset of its
        first character in the text of the bar.
    """
    lines: List[Tuple[str, int]] = []
    offset = 0

    for part in split_lines(text):
        lines.extend(_lines_of_part(part, offset, width))
        offset += len(part) + 1

    return lines


def line_count(text: str, width: int = DEFAULT_WIDTH) -> int:
    """The number of lines the text takes on the screen.

    Args:
        text: The text of the input bar.
        width: The number of cells the text has on one line.

    Returns:
        The number of lines.  An empty text is one line.
    """
    return len(wrap_lines(text, width))


def _cursor_in(
    lines: List[Tuple[str, int]],
    text: str,
    pos: int,
) -> Tuple[int, int]:
    """The line and the column of the cursor, among the lines of the text.

    Args:
        lines: The lines of the text, with the offset of each one.
        text: The text of the input bar.
        pos: The position of the cursor in the text.

    Returns:
        The number of the line the cursor is on, and the column of the
        cursor inside it.
    """
    pos = max(0, min(len(text), pos))

    for index, (line, start) in enumerate(lines):
        end = start + len(line)
        if pos < end:
            return index, pos - start
        if pos == end:
            if index + 1 < len(lines) and lines[index + 1][1] == end:
                # The line was folded: the character under the cursor is
                # the first one of the next line.
                return index + 1, 0
            return index, len(line)

    # The cursor is behind the end of the text: it sits at the end of
    # the last line.
    return len(lines) - 1, len(lines[-1][0])


def cursor_line(text: str, pos: int, width: int = DEFAULT_WIDTH) -> int:
    """The line of the view the cursor is on.

    Args:
        text: The text of the input bar.
        pos: The position of the cursor in the text.
        width: The number of cells the text has on one line.

    Returns:
        The number of the line, counted from zero.
    """
    lines = wrap_lines(text, width)
    row, _ = _cursor_in(lines, text, pos)
    return row


def cursor_column(text: str, pos: int, width: int = DEFAULT_WIDTH) -> int:
    """The column of the cursor inside its line.

    Args:
        text: The text of the input bar.
        pos: The position of the cursor in the text.
        width: The number of cells the text has on one line.

    Returns:
        The number of characters from the start of the line.
    """
    lines = wrap_lines(text, width)
    _, column = _cursor_in(lines, text, pos)
    return column


def visible_window(
    text: str,
    pos: int,
    width: int = DEFAULT_WIDTH,
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
        width: The number of cells the text has on one line.
        max_lines: The number of lines the view shows.

    Returns:
        A tuple of the lines of the window, the row of the cursor
        inside the window and the column of the cursor.
    """
    lines = wrap_lines(text, width)
    row, column = _cursor_in(lines, text, pos)

    if len(lines) <= max_lines:
        return [line for line, _ in lines], row, column

    start = max(0, min(row - max_lines + 1, len(lines) - max_lines))
    window = lines[start:start + max_lines]
    return [line for line, _ in window], row - start, column


def visible_line_count(
    text: str,
    width: int = DEFAULT_WIDTH,
    max_lines: int = MAX_INPUT_LINES,
) -> int:
    """The number of lines the input bar shows.

    Args:
        text: The text of the input bar.
        width: The number of cells the text has on one line.
        max_lines: The number of lines the view shows.

    Returns:
        The number of lines on the screen.
    """
    return min(line_count(text, width), max_lines)


def move_cursor_up(text: str, pos: int, width: int = DEFAULT_WIDTH) -> int:
    """The position of the cursor one line up.

    The column is kept when the line above is long enough, and the
    cursor stops at the end of that line when it is not.

    Args:
        text: The text of the input bar.
        pos: The position of the cursor in the text.
        width: The number of cells the text has on one line.

    Returns:
        The new position of the cursor.
    """
    lines = wrap_lines(text, width)
    row, column = _cursor_in(lines, text, pos)

    if row == 0:
        # The cursor is on the first line already.
        return pos

    content, start = lines[row - 1]
    return start + min(column, len(content))


def move_cursor_down(text: str, pos: int, width: int = DEFAULT_WIDTH) -> int:
    """The position of the cursor one line down.

    The column is kept when the line below is long enough, and the
    cursor stops at the end of that line when it is not.

    Args:
        text: The text of the input bar.
        pos: The position of the cursor in the text.
        width: The number of cells the text has on one line.

    Returns:
        The new position of the cursor.
    """
    lines = wrap_lines(text, width)
    row, column = _cursor_in(lines, text, pos)

    if row >= len(lines) - 1:
        # The cursor is on the last line already.
        return pos

    content, start = lines[row + 1]
    return start + min(column, len(content))
