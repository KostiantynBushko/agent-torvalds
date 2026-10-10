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
from typing import Optional
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.markup import escape


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
        Layout(name="footer", size=3),
    )

    # Body horizontal division: Document Pane (65%) vs Sidebar (35%)
    root["body"].split_row(
        Layout(name="markdown_pane", ratio=65),
        Layout(name="sidebar", ratio=35),
    )

    # Sidebar vertical division: Background Progress (top) vs Telemetry (bottom)
    root["sidebar"].split_column(
        Layout(name="progress_pane", ratio=1),
        Layout(name="telemetry_pane", ratio=1),
    )

    return root


def render_header(
    model_name: str,
    memory_count: int,
    hitl_enabled: bool,
    session_start_time: float,
    is_busy: bool = False,
) -> Panel:
    """
    Render the top Header Panel.
    
    Args:
        model_name: Current model name
        memory_count: Number of messages in chat memory
        hitl_enabled: True if Human-In-The-Loop is active
        session_start_time: Monotonic or epoch timestamp of session start
        is_busy: True if agent is currently processing
        
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

    return Panel(
        header_table,
        border_style="cyan",
        padding=(0, 1),
    )


def render_footer(
    input_buffer: str,
    cursor_pos: int,
    hitl_active: bool = False,
    hitl_prompt: str = "",
    hitl_time_remaining: Optional[float] = None,
    hitl_default_answer: str = "",
    is_busy: bool = False,
) -> Panel:
    """
    Render the bottom interactive command bar / HITL prompt.
    
    Args:
        input_buffer: Currently typed command text
        cursor_pos: Index of the cursor inside input_buffer
        hitl_active: Whether a HITL prompt is currently awaiting user input
        hitl_prompt: Question text if HITL is active
        hitl_time_remaining: Remaining timeout seconds for HITL prompt
        hitl_default_answer: Default answer if HITL times out
        is_busy: True if agent is busy
        
    Returns:
        Rich Panel containing formatted input bar
    """
    if hitl_active:
        # HITL Input Dialog Mode (Prominent warning/prompt style)
        prompt_table = Table.grid(expand=True)
        prompt_table.add_column(justify="left", ratio=75)
        prompt_table.add_column(justify="right", ratio=25)

        # Format input buffer with cursor
        safe_pos = max(0, min(len(input_buffer), cursor_pos))
        before_cur = input_buffer[:safe_pos]
        cur_char = input_buffer[safe_pos] if safe_pos < len(input_buffer) else " "
        after_cur = input_buffer[safe_pos + 1:] if safe_pos < len(input_buffer) else ""

        cursor_rendered = f"{before_cur}[black on bright_yellow]{cur_char}[/black on bright_yellow]{after_cur}"

        left_content = Text.from_markup(
            f"[bold bright_yellow]🤖 AGENT QUESTION:[/bold bright_yellow] [white]{hitl_prompt}[/white]\n"
            f"[bold bright_cyan]Answer: [/bold bright_cyan][white]{cursor_rendered}[/white]"
        )

        timeout_info = ""
        if hitl_time_remaining is not None:
            timeout_info = f"[bright_yellow]⏱ {hitl_time_remaining:.0f}s[/bright_yellow]"
        def_info = f"[dim](Default: '{hitl_default_answer}')[/dim]" if hitl_default_answer else ""
        right_content = Text.from_markup(f"{timeout_info} {def_info}\n[dim][Enter to confirm][/dim]")

        prompt_table.add_row(left_content, right_content)

        return Panel(
            prompt_table,
            border_style="bright_yellow",
            padding=(0, 1),
            title="[bold bright_yellow]Human-in-the-Loop Confirmation[/bold bright_yellow]",
        )

    # Standard Command Bar Mode
    footer_table = Table.grid(expand=True)
    footer_table.add_column(justify="left", ratio=65)
    footer_table.add_column(justify="right", ratio=35)

    safe_pos = max(0, min(len(input_buffer), cursor_pos))
    before_cur = input_buffer[:safe_pos]
    cur_char = input_buffer[safe_pos] if safe_pos < len(input_buffer) else " "
    after_cur = input_buffer[safe_pos + 1:] if safe_pos < len(input_buffer) else ""

    cursor_rendered = (
        f"{escape(before_cur)}"
        f"[black on green]{escape(cur_char)}[/black on green]"
        f"{escape(after_cur)}"
    )

    prompt_label = "[green]>>> [/green]"
    if is_busy:
        prompt_label = "[dim yellow]>>> (busy) [/dim yellow]"

    input_text = Text.from_markup(f"{prompt_label}[bold white]{cursor_rendered}[/bold white]")
    hints_text = Text.from_markup(
        "[dim][\\stats | \\toggle-hitl | \\clear | \\help | \\exit | PgUp/PgDn: Scroll][/dim]"
    )

    footer_table.add_row(input_text, hints_text)

    return Panel(
        footer_table,
        border_style="green" if not is_busy else "yellow",
        padding=(0, 1),
    )


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
