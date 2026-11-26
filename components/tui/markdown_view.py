"""
Markdown View for Torvalds Multi-Window Console.

Renders the primary document pane with:
- Live formatted Markdown (headings, tables, syntax-highlighted code blocks)
- Real-time animated spinner and status indicators during processing
- Virtual buffer pagination and scrolling via PgUp / PgDn

**The pane that has the focus is marked.**  The border is brighter,
the title carries the marker ``▶``, and the subtitle says where the
operator is -- the three marks of a selected pane, the same the
progress pane and the telemetry pane carry.
"""
from typing import Optional
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from components.tui.hotkeys import FOCUS_GAP, FOCUS_MARKER
from components.tui.layout_manager import document_pane_width
from components.tui.state_bridge import TuiState
from components.tui.terminal_size import build_console

#: The cells the panel of the document pane spends on its border and on
#: its padding: two for the border, two for the padding.  What is left
#: of the width of the pane is the width of the content.
PANEL_OVERHEAD = 4

# Smooth 10-frame braille spinner
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

WELCOME_MESSAGE = """# Torvalds AI Agent — Multi-Window Workspace

Welcome to the **Torvalds Multi-Window Terminal User Interface**.
Capabilities:
- System environment manipulation (files, processes, commands)
- Full developer assistance (code review, refactoring, git workflows)
- Dynamic tool retrieval with semantic similarity matching
- Background progress monitoring & real-time telemetry

### Commands & Shortcuts:
- `\\help` : Show every available command with its description
- `\\stats` : View request statistics summary
- `\\toggle-hitl` : Toggle Human-In-The-Loop confirmation at runtime
- `\\hitl-status` : Inspect HITL settings and question counts
- `\\question` : Ask a predefined question through the Human-in-the-Loop (a HITL test)
- `\\clear` : Clear this document viewer pane
- `\\exit` or `\\quit` : Gracefully terminate agent session
- `PgUp` / `PgDn` : Scroll up and down through document responses
- `Up` / `Down` : Browse command history in the input bar

### Tools, Projects & Chat History:
- `\\tools` : Open the interactive tool category selection menu
- `\\tool-list` : List every available tool
- `\\projects` : List registered projects in the workspace
- `\\project-info <name>` : Show details for a registered project
- `\\project-status` : Show the git status of the active project
- `\\project-summary` : Show a full workspace summary
- `\\chat-sessions` : List all chat sessions
- `\\chat-select <id>` : Switch the active chat session
- `\\chat-info` : Show details of the active chat session, and what it holds (messages, size, tokens)

*Type your command below and press Enter to begin.*
"""


class MarkdownView:
    """
    Renders the persistent Markdown Document Viewer with pagination and status overlays.
    """

    def __init__(self, console: Optional[Console] = None):
        self.console = console or build_console()
        # The capture console renders the markdown to text of its own.
        # Its width is set for every frame, and its height is fixed
        # here: the LINES of the environment must not reach it either.
        self._capture_console = build_console(
            color_system="truecolor",
            force_terminal=True,
            width=80,
            height=200,
        )

    def render(
        self,
        state: TuiState,
        max_height: Optional[int] = None,
        focused: bool = False,
        width: Optional[int] = None,
    ) -> Panel:
        """
        Render the Markdown panel according to current state.

        Args:
            state: Current TuiState snapshot
            max_height: Approximate visible height in lines for pagination
            focused: Whether the pane has the focus.  The pane that has
                the focus carries a brighter border and the marker in
                its title.
            width: The number of cells the pane has on the screen.  The
                content is wrapped to it: a pane that grows is a pane
                whose content is re-wrapped.  None means the width is
                not known, and the width of the document pane of this
                console is used.

        Returns:
            Rich Panel to place inside layout['markdown_pane']
        """
        # Determine Title with animated spinner when busy
        state.spinner_frame = (state.spinner_frame + 1) % len(SPINNER_FRAMES)
        spinner_char = SPINNER_FRAMES[state.spinner_frame]

        # The pane that has the focus carries the marker in front of
        # the title: the operator must see which pane the keys go to.
        # The marker stands in front of the icon of the pane, exactly
        # as it does in the progress pane and in the telemetry pane.
        marker = f"{FOCUS_MARKER}{FOCUS_GAP}" if focused else ""

        if state.is_busy:
            title = (
                "[bold yellow]"
                f"{marker}{spinner_char} {state.status_message}"
                "[/bold yellow]"
            )
            # The busy pane is yellow, and the border of the pane that
            # has the focus is the brighter one of the two.
            border_style = "bright_yellow" if focused else "yellow"
        else:
            title = f"[bold blue]{marker}📄 Markdown Document Viewer[/bold blue]"
            border_style = "bright_blue" if focused else "blue"

        # Determine raw markdown content to render
        content_to_render = state.markdown_content.strip()

        if not content_to_render:
            if state.is_busy:
                # Show waiting screen with current query
                waiting_content = (
                    f"### Current Query\n"
                    f"> **{state.current_query}**\n\n"
                    f"---\n"
                    f"*{spinner_char} {state.status_message}*\n"
                )
                if state.active_tool:
                    waiting_content += f"\n- **Active Tool**: `{state.active_tool}`"
                content_to_render = waiting_content
            else:
                content_to_render = WELCOME_MESSAGE

        # The content is wrapped to the width of the pane that carries
        # it, and not to a share of the width of the terminal: the
        # document pane is two thirds of the body while the sidebar is
        # on the screen, and the whole of the body when the operator
        # has closed both of its panes.  A pane that grows is a pane
        # whose content is re-wrapped -- and a pane whose content is
        # wrapped to a width it does not have is a pane with a column
        # of nothing at its right.
        pane_width = width
        if pane_width is None:
            pane_width = document_pane_width(self.console.width)
        self._capture_console.width = max(1, pane_width - PANEL_OVERHEAD)

        # Render markdown to ANSI lines for buffer slicing
        md_obj = Markdown(content_to_render)
        with self._capture_console.capture() as capture:
            self._capture_console.print(md_obj)

        rendered_text = capture.get()
        lines = rendered_text.splitlines()

        # The number of lines the pane shows.
        height_limit = max_height if max_height and max_height > 4 else max(10, self.console.height - 10)

        # The window of the pane is the scroll of the pane, and the
        # scroll knows where the window is.  The document is a **log
        # that grows downwards** -- the answer of the agent is written
        # while the operator watches it -- and the window of the pane
        # **follows the end of it**: every line that is written appears
        # at the bottom of the frame, and the operator watches the
        # answer as it is written.
        #
        # The operator may move the window himself -- `Up`, `Down`,
        # `Home`, `End` -- and the answer that grows does not move it
        # back: the window holds the place the operator put it in, and
        # the text he reads does not slide away under him.  `End` puts
        # the window at the end of the answer again, and the window
        # follows the end from then on.
        scroll = state.document_scroll
        scroll.set_frame(lines, height=height_limit, follow_end=True)

        # The lines of the window -- the ones the operator sees.
        sliced_lines = scroll.window()
        start_idx = scroll.offset
        end_idx = start_idx + len(sliced_lines)
        sliced_ansi = "\n".join(sliced_lines)
        pane_renderable = Text.from_ansi(sliced_ansi)

        # Build subtitle with scroll indicators
        subtitles = []
        if start_idx > 0:
            subtitles.append(f"▲ Line {start_idx}/{len(lines)}")
        if end_idx < len(lines):
            subtitles.append(f"▼ {len(lines) - end_idx} more lines (PgDn)")
        if state.answer_is_writing:
            # The answer is written while the operator watches it, and
            # the window of the pane follows the end of it.  The pane
            # says so, so that the pane that moves is not a pane that
            # is broken -- and so that the pane that stands still says
            # that it stands still on purpose.
            subtitles.append("the answer is being written")
            if scroll.stuck:
                subtitles.append("the window follows the end")
            else:
                subtitles.append("the window holds its place")
        if not subtitles:
            subtitles.append("PgUp/PgDn to scroll")

        subtitle_str = f"[dim]{' │ '.join(subtitles)}[/dim]"

        return Panel(
            pane_renderable,
            title=title,
            subtitle=subtitle_str,
            border_style=border_style,
            padding=(0, 1),
        )
