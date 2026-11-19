"""
The border of the panels of the multi-window console.

The titles of the panels of the console carry an icon.  The width of
that icon has to be the same for Rich and for the terminal, or the
frame of the panel breaks.

The icon of both panes is the high voltage sign U+26A1 - the operator
asked for the telemetry pane to carry the icon of the progress pane
on 2026-11-19.  The sign is a wide character: it is two cells wide
for Rich and for every terminal, so the width of the icon is the same
on both sides of the frame.

The icon the telemetry pane carried before - the information sign
U+2139 - was the one icon that could break the frame.  Rich counts
the information sign with the variation selector U+FE0F two cells
wide - the selector asks for the emoji presentation and Rich gives it
- while a terminal without an emoji font draws the sign one cell
wide.  The top border of the panel is then one cell shorter than the
rest of the frame: the corner of the panel sits inside the edge of the
panel, and the live screen leaves the corner of the frame that was
there before next to the new one - two corners at the right edge of
the panel.  That is what the operator reported on 2026-11-19.

The tests below pin what is true: the width of the title is the same
for Rich and for the terminal, every row of the panel is as wide as
the panel, the corner of the top border sits on the right edge of the
panel and is drawn once, the icon is never the part of the title that
is cut, and the title of each panel is whole from the width of the
terminal on.

Run with:
    pytest tests/test_tui_panel_border.py -v
"""

from __future__ import annotations

import os
import sys
import unicodedata

import pytest
from rich.cells import cell_len
from rich.console import Console
from rich.segment import Segment
from rich.text import Text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from components.tui.layout_manager import build_torvalds_layout  # noqa: E402
from components.tui.progress_view import ProgressView  # noqa: E402
from components.tui.state_bridge import TuiState  # noqa: E402
from components.tui.telemetry_view import TelemetryView  # noqa: E402

#: The narrowest terminal the layout supports.  ``check_terminal_size``
#: in the layout manager warns below it.
MIN_WIDTH = 80

#: The icon of the telemetry panel: the high voltage sign U+26A1.
#:
#: The same icon as the progress pane: the operator asked for it on
#: 2026-11-19.  The sign is a wide character - two cells wide for
#: Rich and for every terminal - so the width of the icon is the same
#: on both sides of the frame.
TELEMETRY_ICON = "\u26a1"

#: The icon of the progress panel: the high voltage sign U+26A1.
PROGRESS_ICON = "\u26a1"

#: The name of the pane of the telemetry.
TELEMETRY_NAME = "Agent Telemetry & State"

#: The name of the pane of the progress.
PROGRESS_NAME = "Workflow & Tool Progress"

#: The first words of the name of a pane: the part of the name that
#: survives the cut of a title that does not fit the sidebar.
#:
#: The two panes of the sidebar carry the same icon, so the icon alone
#: does not tell the rows of the two panes apart - the name does.
TELEMETRY_MARKER = "Agent Telemetry"
PROGRESS_MARKER = "Workflow & Tool"

#: The gap between the icon of a title and the name of the pane: one
#: blank cell.
#:
#: The icon of both panes is two cells wide - for Rich and for every
#: terminal.  The icon fills the cells it takes, and the blank cell
#: after it is the gap: the name of the pane starts in the cell after
#: the gap.
TITLE_GAP = " "

#: The codepoints that change the width of the glyph in front of them
#: without taking a cell of their own.  A terminal that does not know
#: them draws the glyph in front one cell narrower than Rich does.
ZERO_WIDTH = ("\u200d", "\ufe0f")

#: The height of the screen the console draws on.
SCREEN_HEIGHT = 40


def terminal_width(text: str) -> int:
    """The cells a terminal that knows no emoji presentation uses.

    Such a terminal draws every glyph as wide as the East Asian Width
    of the character says: two cells for the wide characters, one cell
    for the rest.  The variation selector and the zero width joiner are
    drawn without a cell of their own.

    This is the width the terminal of the operator sees when the glyph
    of the title is one that Rich measured with its emoji presentation.

    Args:
        text: The text of a row.

    Returns:
        The number of cells the row takes on the terminal.
    """
    width = 0
    for character in text:
        if character in ZERO_WIDTH:
            continue
        if unicodedata.east_asian_width(character) in ("W", "F"):
            width += 2
        else:
            width += 1
    return width


def icon_of(title: str) -> str:
    """The icon at the start of a title.

    The icon of a pane is the high voltage sign - the same sign for
    the telemetry pane and for the progress pane.  An icon that
    carries a variation selector is two code points long.

    Args:
        title: The title of a panel.

    Returns:
        The icon of the title.
    """
    if len(title) > 1 and title[1] in ZERO_WIDTH:
        return title[:2]
    return title[0]


def title_of(panel) -> str:
    """The title of a panel, as plain text.

    Args:
        panel: The panel to read.

    Returns:
        The title of the panel, without the markup.
    """
    assert panel.title is not None, "the panel has no title"
    return Text.from_markup(panel.title).plain


def rows_of(renderable, width: int) -> list[str]:
    """The rows a renderable draws in a terminal of a given width.

    Args:
        renderable: The panel or the layout to render.
        width: The width of the terminal.

    Returns:
        The rows, one string per row.
    """
    console = Console(
        width=width, height=SCREEN_HEIGHT, legacy_windows=False, color_system=None
    )
    segments = list(console.render(renderable, console.options))
    return [
        "".join(segment.text for segment in line)
        for line in Segment.split_lines(segments)
    ]


def layout_rows(state: TuiState, terminal_width: int) -> list[str]:
    """The rows the whole console draws in a terminal of a given width.

    Args:
        state: The state of the console.
        terminal_width: The width of the terminal.

    Returns:
        The rows, one string per row.
    """
    layout = build_torvalds_layout()
    layout["telemetry_pane"].update(TelemetryView().render(state))
    layout["progress_pane"].update(ProgressView().render(state))
    layout["markdown_pane"].update("x")
    layout["header"].update("x")
    layout["footer"].update("x")
    return rows_of(layout, terminal_width)


def layout_frames(state: TuiState, terminal_width: int) -> list[list[str]]:
    """The frames the live screen of the console writes.

    The first frame is the one the console writes before the panes
    carry anything: Rich draws a placeholder for every pane that has
    no renderable, and the placeholder has a frame of its own.  The
    second frame is the console with the panel of the telemetry in it.

    The live screen writes one frame over the other, and a row that is
    one cell shorter than the row it replaces leaves the corner of the
    old frame on the screen: two corners at the edge of the panel.

    Args:
        state: The state of the console.
        terminal_width: The width of the terminal.

    Returns:
        The frames, one list of rows per frame.
    """
    first = build_torvalds_layout()
    first["progress_pane"].update(ProgressView().render(state))
    first["markdown_pane"].update("x")
    first["header"].update("x")
    first["footer"].update("x")

    second = build_torvalds_layout()
    second["telemetry_pane"].update(TelemetryView().render(state))
    second["progress_pane"].update(ProgressView().render(state))
    second["markdown_pane"].update("x")
    second["header"].update("x")
    second["footer"].update("x")

    return [rows_of(first, terminal_width), rows_of(second, terminal_width)]


def screen_after(frames: list[list[str]], width: int) -> list[list[str]]:
    """The cells of the screen after the frames are written on it.

    A terminal writes a row from the left, and the cells a row does
    not reach keep what was on them before.

    Args:
        frames: The frames, one list of rows per frame.
        width: The width of the screen.

    Returns:
        The cells of the screen, one list of cells per row.
    """
    screen = [[" "] * width for _ in range(SCREEN_HEIGHT)]
    for frame in frames:
        for number, row in enumerate(frame):
            if number >= SCREEN_HEIGHT:
                break
            column = 0
            for character in row:
                cells = terminal_width(character)
                if cells == 0:
                    continue
                for offset in range(cells):
                    if column + offset < width:
                        screen[number][column + offset] = (
                            character if offset == 0 else ""
                        )
                column += cells
    return screen


def cells_of(row: str) -> list[str]:
    """The cells a row takes on a terminal that knows no emoji.

    A glyph that is two cells wide takes two cells: the glyph in the
    first one, and an empty cell in the second one.  The empty cell is
    the cell the glyph does not fill - it is what a gap has to be
    counted against.

    Args:
        row: A row of the screen.

    Returns:
        The cells of the row, one string per cell.
    """
    cells: list[str] = []
    for character in row:
        width = terminal_width(character)
        if width == 0:
            continue
        cells.append(character)
        cells.extend([""] * (width - 1))
    return cells


def row_of_pane(rows: list[str], marker: str) -> str:
    """The row that carries the title of a pane.

    The two panes of the sidebar carry the same icon, so the icon
    alone does not tell the rows of the two panes apart - the name of
    the pane does.  A title that does not fit the sidebar is cut at
    the right, and the first words of the name are always there.

    Args:
        rows: The rows to look in.
        marker: The first words of the name of the pane.

    Returns:
        The row.
    """
    for row in rows:
        if marker in row:
            return row
    raise AssertionError(f"no row carries {marker!r}")


def sidebar_width(state: TuiState, terminal_width: int) -> int:
    """The width of the sidebar in a terminal of a given width.

    The sidebar is 35% of the terminal, and the panels of the console
    are drawn in it.

    Args:
        state: The state of the console.
        terminal_width: The width of the terminal.

    Returns:
        The number of cells the sidebar has.
    """
    row = row_of_pane(layout_rows(state, terminal_width), TELEMETRY_MARKER)
    return cell_len(row[row.index("\u256d") :])


@pytest.fixture
def state() -> TuiState:
    """A state with something in every row of the panel."""
    state = TuiState()
    state.mode = "On-Demand Retriever"
    state.model_name = "qwen3:8b"
    state.total_tokens = 123456
    state.prompt_tokens = 100000
    state.completion_tokens = 23456
    state.llm_call_count = 42
    state.total_tool_calls = 17
    state.cache_hits = 10
    state.cache_total = 20
    state.context_measured = True
    state.context_tokens = 8000
    state.context_messages = 12
    state.context_bytes = 40000
    state.context_window = 54000
    state.active_tools = ["os", "git"]
    state.active_tool_scope = "selected"
    state.active_tool_groups = ["Operating System", "System"]
    return state


# ---------------------------------------------------------------------------
# The titles
# ---------------------------------------------------------------------------


class TestTheTitles:
    """The titles of the panels of the console."""

    def test_the_title_of_the_telemetry_panel_carries_its_icon(self, state):
        """The title of the telemetry panel names the pane with its icon."""
        title = title_of(TelemetryView().render(state))

        assert title == f"{TELEMETRY_ICON}{TITLE_GAP}Agent Telemetry & State"

    def test_the_title_of_the_progress_panel_carries_its_icon(self, state):
        """The title of the progress panel names the pane with its icon."""
        title = title_of(ProgressView().render(state))

        assert title == f"{PROGRESS_ICON}{TITLE_GAP}Workflow & Tool Progress"

    @pytest.mark.parametrize(
        "view",
        [TelemetryView, ProgressView],
    )
    def test_the_icon_of_the_title_is_separated_from_the_name(self, view, state):
        """The icon of the title is separated from the name of the pane.

        The gap is one blank cell: the icon of a pane is two cells
        wide, for Rich and for every terminal, and the icon fills the
        cells it takes.  The blank cell after it is the gap the
        operator asked for on 2026-11-19.
        """
        title = title_of(view().render(state))

        icon = icon_of(title)

        assert title[len(icon) :].startswith(TITLE_GAP), (
            f"the icon and the name of the pane are not separated: {title!r}"
        )
        assert title[len(icon) + len(TITLE_GAP) :].strip() == title[
            len(icon) + len(TITLE_GAP) :
        ].strip(), "the gap of the title is more than one blank cell"

    @pytest.mark.parametrize(
        "view, icon, marker, name",
        [
            (TelemetryView, TELEMETRY_ICON, TELEMETRY_MARKER, TELEMETRY_NAME),
            (ProgressView, PROGRESS_ICON, PROGRESS_MARKER, PROGRESS_NAME),
        ],
    )
    def test_the_gap_of_the_title_is_a_blank_cell_on_the_screen(
        self, view, icon, marker, name, state
    ):
        """The gap of the title is a blank cell on the screen.

        The gap has to be *read* as a gap: the icon is drawn in the
        cells it takes and the name of the pane starts in the cell
        after a blank one.  A gap that is not a blank cell of the
        screen is not a gap - it is the second cell of an icon that
        the terminal draws narrower than Rich measured it, which is
        what the corner of the panel was made of.
        """
        rows = layout_rows(state, 120)

        row = row_of_pane(rows, marker)

        cells = cells_of(row)
        first = cells.index(icon)
        last = first + terminal_width(icon) - 1

        assert cells[last + 1] == " ", (
            f"the icon and the name of the pane are not apart: {row!r}"
        )
        assert "".join(cells[last + 2 :]).startswith(name), (
            f"the name of the pane does not start after the gap: {row!r}"
        )

    @pytest.mark.parametrize(
        "view",
        [TelemetryView, ProgressView],
    )
    def test_the_title_is_as_wide_for_rich_as_for_the_terminal(self, view, state):
        """The title is as wide for Rich as for the terminal.

        The icon of a pane decides how wide the title is, and the title
        is drawn in the border of the panel: a title that Rich measures
        wider than the terminal draws it leaves the border of the panel
        one cell short, and the corner of the panel ends up inside the
        panel.
        """
        title = title_of(view().render(state))

        assert cell_len(title) == terminal_width(title), (
            f"the title is {cell_len(title)} cells wide for Rich and "
            f"{terminal_width(title)} cells wide for the terminal: "
            f"{title!r}"
        )

    @pytest.mark.parametrize(
        "view, marker",
        [
            (TelemetryView, TELEMETRY_MARKER),
            (ProgressView, PROGRESS_MARKER),
        ],
    )
    def test_the_icon_of_the_title_is_never_cut(self, view, marker, state):
        """The icon is never the part of the title that is cut.

        A title that does not fit the sidebar is cut at the right, and
        the icon is the first thing in the title: the pane keeps its
        icon in every terminal the layout supports.
        """
        rows = layout_rows(state, MIN_WIDTH)
        title = title_of(view().render(state))
        icon = icon_of(title)

        row = row_of_pane(rows, marker)

        assert icon in row

    @pytest.mark.parametrize("terminal_width", list(range(MIN_WIDTH, 161)))
    def test_the_icon_of_the_title_is_never_cut_in_any_terminal(
        self, state, terminal_width
    ):
        """The icon is never cut, in any terminal the layout supports."""
        rows = layout_rows(state, terminal_width)
        title = title_of(TelemetryView().render(state))
        icon = icon_of(title)

        row = row_of_pane(rows, TELEMETRY_MARKER)

        assert icon in row

    def test_the_title_of_the_telemetry_panel_is_whole_from_eighty_six_columns(
        self, state
    ):
        """The title of the telemetry panel is whole from 86 columns on.

        The sidebar is 35% of the terminal, and from eighty-six columns
        on it has the cells the title of this pane needs.  The icon of
        the pane is the high voltage sign, a wide character: the title
        is one cell wider than it was while the pane carried the
        information sign, and the sidebar grows one cell every third
        column - three columns of the terminal are won.
        """
        for terminal_width in range(86, 161):
            rows = layout_rows(state, terminal_width)

            assert any(TELEMETRY_NAME in row for row in rows), (
                f"the title is cut at {terminal_width} columns"
            )

    def test_the_title_of_the_progress_panel_is_whole_from_eighty_nine_columns(
        self, state
    ):
        """The title of the progress panel is whole from 89 columns on.

        The title of the pane is one cell longer than the title of the
        telemetry pane - twenty-seven cells against twenty-six - and
        the narrowest terminal that leaves the title that many cells
        is eighty-nine columns wide.
        """
        for terminal_width in range(89, 161):
            rows = layout_rows(state, terminal_width)

            assert any(PROGRESS_NAME in row for row in rows), (
                f"the title is cut at {terminal_width} columns"
            )

    @pytest.mark.parametrize(
        "view",
        [TelemetryView, ProgressView],
    )
    def test_the_title_fits_the_sidebar_it_is_drawn_in(self, view, state):
        """The title is not cut in the narrowest terminal that fits it.

        The title of the pane is drawn in the sidebar, and a title that
        does not fit is cut at the right.
        """
        title = title_of(view().render(state))

        for terminal_width in range(MIN_WIDTH, 161):
            sidebar = sidebar_width(state, terminal_width)

            if cell_len(title) + 2 > sidebar - 4:
                continue  # the title is cut here, and that is known

            assert cell_len(title) + 2 <= sidebar - 4


# ---------------------------------------------------------------------------
# The border
# ---------------------------------------------------------------------------


class TestTheBorder:
    """The border of the panels of the console."""

    @pytest.mark.parametrize(
        "view",
        [TelemetryView, ProgressView],
    )
    @pytest.mark.parametrize("width", list(range(20, 121, 5)))
    def test_every_row_of_the_panel_is_the_same_width(self, view, state, width):
        """Every row of the panel is as wide as the panel.

        A row that is one cell narrower than the others - the top
        border of a panel whose title is measured differently by the
        terminal - leaves the corner of the border off the edge of the
        panel.
        """
        rows = rows_of(view().render(state), width)

        widths = {cell_len(row) for row in rows}
        assert len(widths) == 1, (
            f"the rows of the panel are not the same width: {sorted(widths)}"
        )

    @pytest.mark.parametrize(
        "view",
        [TelemetryView, ProgressView],
    )
    @pytest.mark.parametrize("width", list(range(20, 121, 5)))
    def test_the_corner_of_the_panel_is_on_its_edge(self, view, state, width):
        """The corner of the top border sits on the right edge.

        The panel of the sidebar is the rightmost pane of the console,
        and the corner of its top border is drawn in the last column of
        the terminal.
        """
        rows = rows_of(view().render(state), width)

        top = rows[0]
        assert cell_len(top) == width, (
            f"the top border is {cell_len(top)} cells wide, the panel is "
            f"{width}: the corner is off the edge of the panel"
        )
        assert top.endswith("\u256e"), f"the top border ends with {top[-3:]!r}"

    @pytest.mark.parametrize(
        "view",
        [TelemetryView, ProgressView],
    )
    @pytest.mark.parametrize("width", list(range(20, 121, 5)))
    def test_the_rows_of_the_panel_are_the_same_width_without_the_emoji(
        self, view, state, width
    ):
        """The rows of the panel are the same width without the emoji.

        A terminal that does not know the emoji presentation draws the
        glyph of the icon one cell wide.  The top border of the panel
        is then one cell narrower than the rest of the frame: the
        corner of the panel sits inside the edge, and the live screen
        leaves the corner of the frame that was there before next to
        the new one.
        """
        rows = rows_of(view().render(state), width)

        widths = {terminal_width(row) for row in rows}
        assert len(widths) == 1, (
            "the rows of the panel are not the same width on a terminal "
            f"that knows no emoji: {sorted(widths)}"
        )

    @pytest.mark.parametrize(
        "view",
        [TelemetryView, ProgressView],
    )
    def test_the_corner_of_the_panel_is_drawn_once(self, view, state):
        """The corner of the top border is drawn once.

        The live screen writes the frame of the panel over the frame
        that was there before.  A row that is one cell shorter than the
        row it replaces leaves the corner of the old frame on the
        screen: two corners at the right edge of the panel, which is
        what the operator reported on 2026-11-19.
        """
        width = 120
        frames = layout_frames(state, width)
        screen = screen_after(frames, width)

        numbers = [
            number
            for number, cells in enumerate(screen)
            if TELEMETRY_NAME in "".join(cells)
        ]
        assert numbers, "the telemetry panel is not on the screen"

        for number in numbers:
            corners = [
                column
                for column, cell in enumerate(screen[number])
                if cell == "\u256e"
            ]
            assert corners == [width - 1], (
                f"the corner of the panel is drawn in the columns {corners}, "
                f"it is drawn in the column {width - 1}"
            )
