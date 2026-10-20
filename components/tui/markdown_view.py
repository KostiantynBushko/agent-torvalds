"""
Markdown View for Torvalds Multi-Window Console.

Renders the primary document pane with:
- Live formatted Markdown (headings, tables, syntax-highlighted code blocks)
- Real-time animated spinner and status indicators during processing
- Virtual buffer pagination and scrolling via PgUp / PgDn
"""
from typing import Optional
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from components.tui.state_bridge import TuiState

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
- `\\stats` : View request statistics summary
- `\\toggle-hitl` : Toggle Human-In-The-Loop confirmation at runtime
- `\\hitl-status` : Inspect HITL settings and question counts
- `\\clear` : Clear this document viewer pane
- `\\help` : Show help and navigation cheat sheet
- `\\exit` or `\\quit` : Gracefully terminate agent session
- `PgUp` / `PgDn` : Scroll up and down through document responses
- `Up` / `Down` : Browse command history in the input bar

*Type your command below and press Enter to begin.*
"""


class MarkdownView:
    """
    Renders the persistent Markdown Document Viewer with pagination and status overlays.
    """

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self._capture_console = Console(
            color_system="truecolor",
            force_terminal=True,
            width=80,
        )

    def render(self, state: TuiState, max_height: Optional[int] = None) -> Panel:
        """
        Render the Markdown panel according to current state.
        
        Args:
            state: Current TuiState snapshot
            max_height: Approximate visible height in lines for pagination
            
        Returns:
            Rich Panel to place inside layout['markdown_pane']
        """
        # Determine Title with animated spinner when busy
        state.spinner_frame = (state.spinner_frame + 1) % len(SPINNER_FRAMES)
        spinner_char = SPINNER_FRAMES[state.spinner_frame]

        if state.is_busy:
            title = f"[bold yellow]{spinner_char} {state.status_message}[/bold yellow]"
            border_style = "yellow"
        else:
            title = "[bold blue]📄 Markdown Document Viewer[/bold blue]"
            border_style = "blue"

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

        # Adjust capture console width based on current window width
        estimated_width = max(40, int(self.console.width * 0.62))
        self._capture_console.width = estimated_width

        # Render markdown to ANSI lines for buffer slicing
        md_obj = Markdown(content_to_render)
        with self._capture_console.capture() as capture:
            self._capture_console.print(md_obj)

        rendered_text = capture.get()
        lines = rendered_text.splitlines()
        state.total_rendered_lines = len(lines)

        # Slice lines according to scroll offset and visible height
        height_limit = max_height if max_height and max_height > 4 else max(10, self.console.height - 10)
        start_idx = max(0, min(state.scroll_offset, max(0, len(lines) - 1)))
        end_idx = min(len(lines), start_idx + height_limit)

        sliced_lines = lines[start_idx:end_idx]
        sliced_ansi = "\n".join(sliced_lines)
        pane_renderable = Text.from_ansi(sliced_ansi)

        # Build subtitle with scroll indicators
        subtitles = []
        if start_idx > 0:
            subtitles.append(f"▲ Line {start_idx}/{len(lines)}")
        if end_idx < len(lines):
            subtitles.append(f"▼ {len(lines) - end_idx} more lines (PgDn)")
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
