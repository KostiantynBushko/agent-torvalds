"""
Layout Manager for Torvalds Multi-Window Console.

Constructs and manages the hierarchical Rich layout partitions:
- Header: Agent title, active model, memory count, HITL status, session clock
- Body (split 65% / 35%):
  - Left (65%): Persistent Markdown Document Viewer
  - Right (35%):
    - Top: Workflow iterations and active/recent tool progress
    - Bottom: Agent telemetry, tokens, cache hits, and loaded toolkits
- Footer: Interactive non-blocking command bar and HITL confirmation dialog
"""
import time
from fractions import Fraction
from typing import Iterable, List, Optional, Sequence

from rich.console import Console, Group
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.markup import escape

from components.tui.input_text import (
    DEFAULT_WIDTH,
    MAX_INPUT_LINES,
    visible_line_count,
    visible_window,
)

#: The share of the width of the body that the document pane takes.
DOCUMENT_RATIO = 65

#: The share of the width of the body that the sidebar takes.  The
#: sidebar carries the progress pane above and the telemetry pane
#: below it, and both of them are as wide as the sidebar is.
SIDEBAR_RATIO = 35

#: The panes of the sidebar, in the order they are drawn in it.  They
#: are the panes the operator can hide, and the panes a sidebar that
#: has no pane left leaves the layout with.
SIDEBAR_PANES = ("progress_pane", "telemetry_pane")

#: The smallest a column of the body may be.  Rich gives a column that
#: would be narrower than this its minimum, and the repository divides
#: the body the way Rich divides it.
MINIMUM_COLUMN = 1

#: The footer partition is three lines tall: a border, one line of
#: content, a border.  The command bar needs exactly that -- and one
#: line more for every line the operator adds to the input.
FOOTER_HEIGHT = 3

#: The header partition is three lines tall: a border, one line of
#: content, a border.  The notice of the TUI is the line below the
#: content, and the header grows by one line while a notice is up.
HEADER_HEIGHT = 3

#: The lines a panel spends on its border: one on the top and one on
#: the bottom.  The padding of the panes is horizontal, so the content
#: of a pane is the height of the pane without these two lines.
PANEL_BORDER = 2

#: The prompt of the command bar.
INPUT_PROMPT = ">>> "

#: The prompt of the command bar while the agent is busy.
BUSY_PROMPT = ">>> (busy) "

#: The labels of the answer of the agent, by the kind of answer.
ANSWER_LABELS = {
    "yesno": "Yes/No: ",
    "menu": "Option: ",
    "password": "Password: ",
}

#: The label of the answer of the agent.
DEFAULT_ANSWER_LABEL = "Answer: "

#: The share of the width of the bar that the text takes: the question
#: of the agent and its answer in the agent-question mode, and the text
#: of the operator in the command bar.  The rest of the bar belongs to
#: the invitation to press Enter.
TEXT_COLUMN_RATIO = 75

#: The share of the width of the bar that the hot commands take while
#: the bar is empty.  They need more room than the invitation, and
#: there is no text of the operator to wrap while they are there.
HINTS_COLUMN_RATIO = 35

#: The invitation to press Enter, in the command bar: what Enter does
#: with the text the operator wrote.
SEND_INVITATION = "[Enter to send]"

#: The invitation to press Enter, in the agent-question mode: what
#: Enter does with the answer the operator wrote.
CONFIRM_INVITATION = "[Enter to confirm]"

#: The cells the panel of the bar takes for its border and for its
#: padding.
PANEL_OVERHEAD = 4


def input_text_width(
    console_width: int,
    hitl_active: bool = False,
    is_busy: bool = False,
    hitl_input_type: str = "text",
) -> int:
    """The number of cells the bar gives the text of the operator.

    The text of the operator is wrapped at this width: a text that
    reaches it moves to the next line, the way the question of the agent
    moves to the next line in the agent-question mode.

    The text has a column of its own — three quarters of the bar, the
    way the question of the agent and its answer have one in the
    agent-question mode.  The rest of the bar belongs to the invitation
    to press Enter, and to nothing else.

    Args:
        console_width: The width of the terminal.
        hitl_active: Whether a question of the agent is waiting.
        is_busy: Whether the agent is busy.
        hitl_input_type: The kind of answer the question wants.

    Returns:
        The number of cells of the text on one line.
    """
    content = console_width - PANEL_OVERHEAD
    column = content * TEXT_COLUMN_RATIO // 100

    if hitl_active:
        label = ANSWER_LABELS.get(hitl_input_type, DEFAULT_ANSWER_LABEL)
        return max(1, column - len(label))

    prompt = BUSY_PROMPT if is_busy else INPUT_PROMPT
    return max(1, column - len(prompt))


def _row_cells(total: int, ratios: Sequence[int]) -> List[int]:
    """
    The cells every column of a row takes, the way Rich divides a row.

    Rich divides the width of a row with exact fractions and carries
    the remainder of the division to the next column: the columns add
    up to the whole width, and none of them is a cell short of its
    share.  A column that would be narrower than the minimum gets the
    minimum instead, and the rest of the row is divided again.

    The repository divides its own body the same way, so that a pane
    knows how many cells it has before the layout is drawn.

    Args:
        total: The number of cells the row has.
        ratios: The share of every column of the row.

    Returns:
        The number of cells of every column of the row.
    """
    sizes: List[Optional[int]] = [None] * len(ratios)
    while None in sizes:
        flexible = [index for index, size in enumerate(sizes) if size is None]
        remaining = total - sum(size or 0 for size in sizes)
        if remaining <= 0:
            # No room for the flexible columns: they get the minimum.
            return [
                MINIMUM_COLUMN if size is None else size for size in sizes
            ]
        portion = Fraction(remaining, sum(ratios[index] for index in flexible))
        for index in flexible:
            if portion * ratios[index] <= MINIMUM_COLUMN:
                sizes[index] = MINIMUM_COLUMN
                break
        else:
            # The remainder of the division is carried to the next
            # column, and the columns add up to the whole width.
            remainder = Fraction(0)
            for index in flexible:
                size, remainder = divmod(portion * ratios[index] + remainder, 1)
                sizes[index] = size
            break
    return [int(size or 0) for size in sizes]


def progress_pane_width(console_width: int) -> int:
    """
    The number of cells the progress pane has on the screen.

    The pane is a third and a half of the width of the body, and the
    body is as wide as the terminal.  The pane of the progress is
    asked this number before the layout is drawn, so that the detail
    of a tool is split to the width the pane really has.

    The number is the one the layout really uses.  A check asks the
    real layout for the region of the pane and compares it with this
    number: a Rich that divides its layout another way is caught by
    the check, and not by a pane that splits its text in the wrong
    place.

    Args:
        console_width: The width of the terminal.

    Returns:
        The number of cells of the pane.
    """
    return _row_cells(max(0, int(console_width)), (DOCUMENT_RATIO, SIDEBAR_RATIO))[
        1
    ]


def build_torvalds_layout() -> Layout:
    """
    Build the hierarchical Rich Layout for Torvalds Multi-Window Console.
    
    Structure:
    root
    ├── header (size: 3)
    ├── body (ratio: 1)
    │   ├── markdown_pane (ratio: 65)
    │   └── sidebar (ratio: 35)
    │       ├── progress_pane (ratio: 1)
    │       └── telemetry_pane (ratio: 1)
    └── footer (size: 3)
    
    Returns:
        Configured root Layout instance.
    """
    root = Layout(name="root")

    # Primary vertical division: Header, Body, Footer
    root.split_column(
        Layout(name="header", size=3),
        Layout(name="body", ratio=1),
        Layout(name="footer", size=FOOTER_HEIGHT),
    )

    # Body horizontal division: Document Pane (65%) vs Sidebar (35%)
    root["body"].split_row(
        Layout(name="markdown_pane", ratio=DOCUMENT_RATIO),
        Layout(name="sidebar", ratio=SIDEBAR_RATIO),
    )

    # Sidebar vertical division: Background Progress (top) vs Telemetry (bottom)
    root["sidebar"].split_column(
        Layout(name="progress_pane", ratio=1),
        Layout(name="telemetry_pane", ratio=1),
    )

    return root


def apply_pane_visibility(layout: Layout, hidden_panes: Iterable[str]) -> None:
    """Show or hide the panes of the sidebar.

    A hidden pane leaves the layout, and the space goes to its sibling:
    the sidebar carries one pane instead of two, and the pane that is
    left takes the whole of it.  The visibility is applied from the
    state on every frame, so it is idempotent and it survives a
    resize.

    **The sidebar leaves the layout with its last pane.**  A Rich
    partition whose children are *all* invisible is a partition
    without a content of its own, and Rich draws such a partition as
    *itself*: the layout draws the sidebar, the sidebar draws the
    layout, and the operator gets a stack of a thousand frames instead
    of a screen.  The sidebar is therefore hidden together with the
    last of its panes, and the document pane takes the whole of the
    body.

    Args:
        layout: The TUI layout.
        hidden_panes: The names of the panes the operator has hidden.
    """
    hidden = set(hidden_panes)

    for pane in SIDEBAR_PANES:
        layout[pane].visible = pane not in hidden

    # The sidebar keeps a pane on the screen, or it leaves the layout
    # with them: a partition without a visible child is drawn as
    # itself, and that is an endless recursion.
    layout["sidebar"].visible = any(
        pane not in hidden for pane in SIDEBAR_PANES
    )


def render_header(
    model_name: str,
    memory_count: int,
    hitl_enabled: bool,
    session_start_time: float,
    is_busy: bool = False,
    notice: str = "",
) -> Panel:
    """
    Render the top Header Panel.

    The **notice** of the TUI is drawn here, and not in a pane: a
    notice that lives in a pane is silenced by the pane that hides it,
    and the operator has to be told what happened even when he has
    hidden everything.

    Args:
        model_name: Current model name
        memory_count: Number of messages in chat memory
        hitl_enabled: True if Human-In-The-Loop is active
        session_start_time: Monotonic or epoch timestamp of session start
        is_busy: True if agent is currently processing
        notice: The notice of the TUI, and an empty string when there
            is none.

    Returns:
        Rich Panel containing formatted header
    """
    now_str = time.strftime("%H:%M:%S")
    uptime_sec = int(time.time() - session_start_time)
    uptime_min, uptime_s = divmod(uptime_sec, 60)
    uptime_h, uptime_min = divmod(uptime_min, 60)
    uptime_str = f"{uptime_h:02d}:{uptime_min:02d}:{uptime_s:02d}"

    header_table = Table.grid(expand=True)
    header_table.add_column(justify="left", ratio=30)
    header_table.add_column(justify="center", ratio=45)
    header_table.add_column(justify="right", ratio=25)

    # Title with activity indicator
    status_dot = "🟡 BUSY" if is_busy else "🟢 READY"
    left_text = Text.from_markup(f"[bold cyan]⚡ TORVALDS AGENT[/bold cyan]  [dim]{status_dot}[/dim]")

    # Middle info: Model, Memory, HITL
    hitl_badge = "[bold green]HITL: ON[/bold green]" if hitl_enabled else "[dim red]HITL: OFF[/dim red]"
    center_text = Text.from_markup(
        f"[dim]Model:[/dim] [bold white]{model_name}[/bold white]  │  "
        f"[dim]Mem:[/dim] [white]{memory_count} msgs[/white]  │  "
        f"{hitl_badge}"
    )

    # Right info: Session time and Clock
    right_text = Text.from_markup(
        f"[dim]Uptime:[/dim] [white]{uptime_str}[/white]  [dim]Clock:[/dim] [white]{now_str}[/white]"
    )

    header_table.add_row(left_text, center_text, right_text)

    content = header_table
    if notice:
        # The notice is the line under the content of the header.  The
        # text of the operator may carry square brackets, and Rich
        # reads them as markup: the text between them would disappear
        # from the screen.
        notice_text = Text.from_markup(
            f"[bold yellow]Notice:[/bold yellow] [yellow]{escape(notice)}[/yellow]"
        )
        content = Group(header_table, notice_text)

    return Panel(
        content,
        border_style="cyan",
        padding=(0, 1),
    )


def header_height(console: Console, panel: Panel) -> int:
    """The number of terminal lines a header panel needs.

    Args:
        console: The console the panel is rendered into.
        panel: The header panel about to be shown.

    Returns:
        The number of lines the panel occupies.
    """
    options = console.options.update(height=None)
    return len(console.render_lines(panel, options))


def fit_header(
    layout: Layout,
    console: Console,
    panel: Panel,
    has_notice: bool = False,
) -> int:
    """Give the header partition the room the panel needs.

    The header keeps the height it has always had -- one line of
    content -- and it grows by one line while a notice is up: the
    notice is not in a pane, so that it is visible whatever the
    operator has hidden.

    Args:
        layout: The TUI layout.
        console: The console the panel is rendered into.
        panel: The header panel about to be shown.
        has_notice: Whether a notice is up.

    Returns:
        The height the header partition was given.
    """
    needed = HEADER_HEIGHT
    if has_notice:
        # The header grows by one line while a notice is up.  It keeps
        # the height it has always had when there is no notice: the
        # header was never fitted to its content, and the body of the
        # layout must not lose a line to a header that wraps.
        needed = max(HEADER_HEIGHT + 1, header_height(console, panel))
    layout["header"].size = needed
    return needed


def pane_content_height(layout: Layout, name: str, default: int = 0) -> int:
    """The number of lines the content of a pane has on the screen.

    The number is the one the layout **really uses**: the region of
    the pane in the map of the last drawn frame, without the lines of
    its border.  A check asks the real layout for the region of the
    pane and compares it with the number that is computed -- a Rich
    that divides its layout another way is caught by the check, and
    not by a pane that cuts its text in the wrong place.

    Args:
        layout: The TUI layout.
        name: The name of the pane in the layout.
        default: The number of lines when the layout does not know the
            pane yet -- before the first frame was drawn.

    Returns:
        The number of lines of the content of the pane.
    """
    try:
        region = layout.map[layout[name]].region
    except (KeyError, TypeError, AttributeError):
        # The pane is not in the map: it was never drawn, or it is
        # hidden and it is not on the screen at all.
        return default
    return max(0, region.height - PANEL_BORDER)


def _input_markup(
    input_buffer: str,
    cursor_pos: int,
    indent: int,
    cursor_style: str,
    width: int = DEFAULT_WIDTH,
    max_lines: int = MAX_INPUT_LINES,
) -> str:
    """The markup of the text of the input, with the cursor in its place.

    The view shows at most ``max_lines`` lines of the text: the text
    that reaches the end of the view moves to the next line, a paste
    brings the lines of its own, and a text that is longer than the
    window is seen through it -- the window follows the cursor, so a
    paste that is longer than the window ends with its last lines on
    the screen, and the operator can walk the cursor back into the
    text above and edit it.

    Args:
        input_buffer: The text of the input.
        cursor_pos: The position of the cursor in the text.
        indent: The number of cells the lines after the first are
            indented by, so that they stand under the first one.
        cursor_style: The style of the cell the cursor is on.
        width: The number of cells the text has on one line.
        max_lines: The number of lines the view shows.

    Returns:
        The markup of the lines of the input.
    """
    lines, row, column = visible_window(
        input_buffer, cursor_pos, width, max_lines
    )

    markup = []
    for index, line in enumerate(lines):
        prefix = "" if index == 0 else " " * indent
        if index == row:
            before = escape(line[:column])
            # The cursor at the end of a line sits on a space: there is
            # no character under it to paint.
            cursor_char = escape(line[column]) if column < len(line) else " "
            after = escape(line[column + 1:])
            markup.append(
                f"{prefix}[bold white]{before}"
                f"[{cursor_style}]{cursor_char}[/{cursor_style}]"
                f"{after}[/bold white]"
            )
        else:
            markup.append(f"{prefix}[bold white]{escape(line)}[/bold white]")

    return "\n".join(markup)


def _last_row(
    input_buffer: str,
    cursor_pos: int,
    width: int = DEFAULT_WIDTH,
    max_lines: int = MAX_INPUT_LINES,
) -> int:
    """The last line of the bar.

    The invitation to press Enter stands on it.  The invitation of the
    agent-question mode stands on the last line of its panel too -- the
    answer of the operator is typed on it, and it is the last line of
    the panel -- and the two invitations are in the same place on the
    screen: the lower right corner of the bar.

    Args:
        input_buffer: The text of the input.
        cursor_pos: The position of the cursor in the text.
        width: The number of cells the text has on one line.
        max_lines: The number of lines the view shows.

    Returns:
        The number of the last line, counted from zero.
    """
    lines, _, _ = visible_window(input_buffer, cursor_pos, width, max_lines)
    return max(0, len(lines) - 1)


def render_footer(
    input_buffer: str,
    cursor_pos: int,
    hitl_active: bool = False,
    hitl_prompt: str = "",
    hitl_time_remaining: Optional[float] = None,
    hitl_default_answer: str = "",
    is_busy: bool = False,
    hitl_input_type: str = "text",
    width: Optional[int] = None,
) -> Panel:
    """
    Render the bottom interactive command bar / HITL prompt.

    While there is text in the bar, the invitation to press Enter stands
    in the right column of the bar, on the last line of the bar -- the
    same place the agent-question mode has its own invitation -- and
    the text of the operator has the column on the left.  While the bar
    is empty, the hot commands stand in the right column.

    Args:
        input_buffer: Currently typed command text
        cursor_pos: Index of the cursor inside input_buffer
        hitl_active: Whether a HITL prompt is currently awaiting user input
        hitl_prompt: Question text if HITL is active
        hitl_time_remaining: Remaining timeout seconds for HITL prompt
        hitl_default_answer: Default answer if HITL times out
        is_busy: True if agent is busy
        hitl_input_type: The kind of answer the question wants — "text",
                         "yesno", "menu" or "password"
        width: The number of cells the text of the operator has on one
               line.  The text is wrapped at it: a text that reaches
               the end of the view moves to the next line.  None means
               a width no text reaches, and nothing is wrapped.

    Returns:
        Rich Panel containing formatted input bar
    """
    if width is None:
        width = DEFAULT_WIDTH

    if hitl_active:
        # HITL Input Dialog Mode (Prominent warning/prompt style)
        prompt_table = Table.grid(expand=True)
        prompt_table.add_column(justify="left", ratio=75)
        prompt_table.add_column(justify="right", ratio=25)

        # The label tells the operator what kind of answer is expected.
        answer_label = ANSWER_LABELS.get(hitl_input_type, DEFAULT_ANSWER_LABEL)

        # The typed text is operator input: it may hold square brackets,
        # which Rich would read as markup.  Without the escape the text
        # between the brackets disappears from the screen -- and a
        # bracket that closes a tag Rich never opened ends the panel
        # with a MarkupError.
        cursor_rendered = _input_markup(
            input_buffer,
            cursor_pos,
            indent=len(answer_label),
            cursor_style="black on bright_yellow",
            width=width,
        )

        # The question is agent text: it may contain square brackets, which
        # Rich would read as markup.
        safe_prompt = escape(hitl_prompt)
        left_content = Text.from_markup(
            f"[bold bright_yellow]🤖 AGENT QUESTION:[/bold bright_yellow] [white]{safe_prompt}[/white]\n"
            f"[bold bright_cyan]{answer_label}[/bold bright_cyan][white]{cursor_rendered}[/white]"
        )

        timeout_info = ""
        if hitl_time_remaining is not None:
            timeout_info = f"[bright_yellow]⏱ {hitl_time_remaining:.0f}s[/bright_yellow]"
        def_info = f"[dim](Default: '{hitl_default_answer}')[/dim]" if hitl_default_answer else ""
        right_content = Text.from_markup(
            f"{timeout_info} {def_info}\n[dim]{CONFIRM_INVITATION}[/dim]"
        )

        prompt_table.add_row(left_content, right_content)

        return Panel(
            prompt_table,
            border_style="bright_yellow",
            padding=(0, 1),
            title="[bold bright_yellow]Human-in-the-Loop Confirmation[/bold bright_yellow]",
        )

    # Standard Command Bar Mode
    footer_table = Table.grid(expand=True)

    prompt_label = "[green]>>> [/green]"
    prompt_width = len(INPUT_PROMPT)
    if is_busy:
        prompt_label = "[dim yellow]>>> (busy) [/dim yellow]"
        prompt_width = len(BUSY_PROMPT)

    cursor_rendered = _input_markup(
        input_buffer,
        cursor_pos,
        indent=prompt_width,
        cursor_style="black on green",
        width=width,
    )
    input_text = Text.from_markup(f"{prompt_label}{cursor_rendered}")

    # While there is text in the bar, the right column of the bar is
    # the invitation to press Enter: the operator has to see what Enter
    # does with what he wrote, the way the agent-question mode invites
    # him to confirm the answer.  The text of the operator does not
    # take the whole bar for itself -- the invitation has a column of
    # its own, on the right.
    #
    # The invitation stands on the last line of the bar.  The
    # agent-question mode puts its invitation on the last line of its
    # panel as well -- the answer is typed on it -- and the operator
    # finds the two in the same place on the screen: the lower right
    # corner of the bar.  The invitation does not walk with the cursor:
    # it is a fixed cell of the bar, and the operator reads it there
    # every time.
    if input_buffer:
        footer_table.add_column(justify="left", ratio=TEXT_COLUMN_RATIO)
        footer_table.add_column(justify="right", ratio=100 - TEXT_COLUMN_RATIO)
        row = _last_row(input_buffer, cursor_pos, width)
        invitation = Text.from_markup(
            "\n" * row + f"[dim]{SEND_INVITATION}[/dim]"
        )
        footer_table.add_row(input_text, invitation)
    else:
        # The hot commands are hidden while there is text in the bar:
        # the operator is writing, and the width of the bar belongs to
        # what he writes.  They come back when the bar is empty again
        # -- and the bar is empty again when the last character is
        # deleted.  Their column is the one they always had.
        footer_table.add_column(justify="left", ratio=100 - HINTS_COLUMN_RATIO)
        footer_table.add_column(justify="right", ratio=HINTS_COLUMN_RATIO)
        hints_text = Text.from_markup(
            "[dim][\\stats | \\tools | \\projects | \\chat-sessions | \\keys | \\help | \\exit][/dim]"
        )
        footer_table.add_row(input_text, hints_text)

    return Panel(
        footer_table,
        border_style="green" if not is_busy else "yellow",
        padding=(0, 1),
    )


def footer_height(console: Console, panel: Panel) -> int:
    """The number of terminal lines a footer panel needs.

    A panel that is taller than the partition it lives in is cropped
    from the bottom, and the bottom of the HITL panel is the line the
    operator types the answer on.  The height of the panel is therefore
    measured, not assumed.

    Args:
        console: The console the panel is rendered into.
        panel: The footer panel about to be shown.

    Returns:
        The number of lines the panel occupies.
    """
    options = console.options.update(height=None)
    return len(console.render_lines(panel, options))


def fit_footer(
    layout: Layout,
    console: Console,
    panel: Panel,
    hitl_active: bool = False,
    input_lines: int = 1,
) -> int:
    """Give the footer partition the room the panel needs.

    The command bar keeps the height it has always had -- one line of
    content -- and it grows with the lines the operator adds to the
    input: the bar shows up to three lines, and every line of them
    needs a line of the screen.

    The HITL panel is never cropped.  It carries the question *and* the
    line the answer is typed on, and the answer is the last line of the
    panel -- a panel that is taller than its partition is cut from the
    bottom, so the answer is the first thing to go.  The partition
    grows while a question is waiting and shrinks back when the answer
    is in.

    Args:
        layout: The TUI layout.
        console: The console the panel is rendered into.
        panel: The footer panel about to be shown.
        hitl_active: Whether a question of the agent is waiting.
        input_lines: The number of lines the input bar shows.

    Returns:
        The height the footer partition was given.
    """
    if hitl_active:
        needed = max(FOOTER_HEIGHT, footer_height(console, panel))
    else:
        needed = max(FOOTER_HEIGHT, FOOTER_HEIGHT + max(0, int(input_lines) - 1))
    layout["footer"].size = needed
    return needed


def check_terminal_size(console) -> tuple[bool, int, int]:
    """
    Check if the current terminal has sufficient dimensions for the multi-window TUI.
    Minimum recommended size is 80 columns by 24 rows.
    
    Returns:
        tuple (is_sufficient, width, height)
    """
    width = console.width
    height = console.height
    is_sufficient = (width >= 80 and height >= 20)
    return is_sufficient, width, height
