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
"""

from components.tui.layout_manager import build_torvalds_layout
from components.tui.state_bridge import TuiState, TuiEventAdapter, TuiInputModule
from components.tui.input_reader import NonBlockingInputReader
from components.tui.markdown_view import MarkdownView
from components.tui.progress_view import ProgressView
from components.tui.telemetry_view import TelemetryView
from components.tui.tui_app import TuiApp

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
]
