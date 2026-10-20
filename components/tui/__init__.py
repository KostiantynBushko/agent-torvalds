"""
Torvalds Multi-Window Terminal User Interface (TUI) Package.

Provides a persistent multi-pane terminal workspace for Torvalds AI Agent:
- Layout Manager: Hierarchical Layout construction & styling
- State Bridge: Thread-safe state synchronization and event bridge
- Input Reader: Cross-platform non-blocking keyboard input
- Markdown View: Persistent Markdown document viewer with buffer pagination
- Progress View: Background task and tool execution monitor
- Telemetry View: Live agent telemetry and session statistics
- TUI App: Main application orchestrator with Live(screen=True)
- Tool Selection View: Startup tool category selection for the TUI
- Chat History View: Chat session management commands for the TUI
- Project Manager View: Project/workspace inspection commands for the TUI
"""

from components.tui.layout_manager import build_torvalds_layout
from components.tui.state_bridge import TuiState, TuiEventAdapter, TuiInputModule
from components.tui.input_reader import NonBlockingInputReader
from components.tui.markdown_view import MarkdownView
from components.tui.progress_view import ProgressView
from components.tui.telemetry_view import TelemetryView
from components.tui.tui_app import TuiApp
from components.tui.tool_selection_view import (
    discover_all_tools,
    render_categories_markdown,
    render_tool_list_markdown,
    select_tools_interactive_tui,
    is_tool_selection_command,
)
from components.tui.chat_history_view import (
    render_chat_sessions_markdown,
    render_chat_info_markdown,
    handle_chat_command_markdown,
)
from components.tui.project_manager_view import (
    is_project_command,
    handle_project_command_markdown,
)

__all__ = [
    "build_torvalds_layout",
    "TuiState",
    "TuiEventAdapter",
    "TuiInputModule",
    "NonBlockingInputReader",
    "MarkdownView",
    "ProgressView",
    "TelemetryView",
    "TuiApp",
    "discover_all_tools",
    "render_categories_markdown",
    "render_tool_list_markdown",
    "select_tools_interactive_tui",
    "is_tool_selection_command",
    "render_chat_sessions_markdown",
    "render_chat_info_markdown",
    "handle_chat_command_markdown",
    "is_project_command",
    "handle_project_command_markdown",
]
