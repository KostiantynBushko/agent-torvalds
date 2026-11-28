"""
Torvalds Multi-Window Terminal User Interface (TUI) Package.

Provides a persistent multi-pane terminal workspace for Torvalds AI Agent:
- Layout Manager: Hierarchical Layout construction and styling
- State Bridge: Thread-safe state synchronization and event bridge
- Input Reader: Cross-platform non-blocking keyboard input
- Input Text: The text of the input bar -- one line, or three, wrapped
- Markdown View: Persistent Markdown document viewer with buffer pagination
- Progress View: Background task and tool execution monitor
- Telemetry View: Live agent telemetry and session statistics
- TUI App: Main application orchestrator with Live(screen=True)
- Tool Selection View: Startup tool category selection for the TUI
- Chat History View: Chat session management commands for the TUI
- Project Manager View: Project/workspace inspection commands for the TUI
- Terminal Size: A console that asks the terminal for its size
- Log Routing: The log of the agent in the file, not on the screen

The modules are imported when one of their names is asked for, and not
before.  The tool selection view carries the tools of llama_index, and
the import of it costs the better part of a second: a reader that wants
one small module of the TUI -- the input reader, say, which needs
nothing but the standard library -- paid for the whole of it.
"""
import importlib
import pkgutil

#: The module of the package that carries every name of it.
_MODULES = {
    "build_torvalds_layout": "layout_manager",
    "input_text_width": "layout_manager",
    "TuiState": "state_bridge",
    "TuiEventAdapter": "state_bridge",
    "TuiInputModule": "state_bridge",
    "NonBlockingInputReader": "input_reader",
    "PastedText": "input_reader",
    "MAX_INPUT_LINES": "input_text",
    "normalize_paste": "input_text",
    "visible_line_count": "input_text",
    "visible_window": "input_text",
    "wrap_lines": "input_text",
    "MarkdownView": "markdown_view",
    "ProgressView": "progress_view",
    "TelemetryView": "telemetry_view",
    "build_console": "terminal_size",
    "console_environ": "terminal_size",
    "log_to_file": "log_routing",
    "resolve_tui_log_config": "log_routing",
    "TuiApp": "tui_app",
    "discover_all_tools": "tool_selection_view",
    "render_categories_markdown": "tool_selection_view",
    "render_loaded_tools_markdown": "tool_selection_view",
    "render_tool_list_markdown": "tool_selection_view",
    "select_tools_interactive_tui": "tool_selection_view",
    "is_tool_selection_command": "tool_selection_view",
    "render_chat_sessions_markdown": "chat_history_view",
    "render_session_picker_markdown": "chat_history_view",
    "render_chat_info_markdown": "chat_history_view",
    "handle_chat_command_markdown": "chat_history_view",
    "is_project_command": "project_manager_view",
    "handle_project_command_markdown": "project_manager_view",
}


def _submodule(name):
    """The module of the package with that name, when there is one.

    Args:
        name: The name that was asked for.

    Returns:
        The module, or None when the package carries no such module.
    """
    for _, module_name, _ in pkgutil.iter_modules(__path__):
        if module_name == name:
            return importlib.import_module(f"{__name__}.{name}")
    return None


def __getattr__(name):
    """The names of the package, imported when they are asked for.

    Args:
        name: The name that was asked for.

    Returns:
        The object the name carries.

    Raises:
        AttributeError: The package carries no such name.
    """
    module_name = _MODULES.get(name)
    if module_name is not None:
        module = importlib.import_module(f"{__name__}.{module_name}")
        value = getattr(module, name)
        globals()[name] = value
        return value

    module = _submodule(name)
    if module is not None:
        globals()[name] = module
        return module

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    """The names of the package: the loaded ones and the ones that are not."""
    return sorted(set(globals()) | set(_MODULES))


__all__ = [
    "build_torvalds_layout",
    "TuiState",
    "TuiEventAdapter",
    "TuiInputModule",
    "NonBlockingInputReader",
    "PastedText",
    "MAX_INPUT_LINES",
    "normalize_paste",
    "visible_line_count",
    "visible_window",
    "wrap_lines",
    "input_text_width",
    "MarkdownView",
    "ProgressView",
    "TelemetryView",
    "TuiApp",
    "build_console",
    "console_environ",
    "log_to_file",
    "resolve_tui_log_config",
    "discover_all_tools",
    "render_categories_markdown",
    "render_loaded_tools_markdown",
    "render_tool_list_markdown",
    "select_tools_interactive_tui",
    "is_tool_selection_command",
    "render_chat_sessions_markdown",
    "render_session_picker_markdown",
    "render_chat_info_markdown",
    "handle_chat_command_markdown",
    "is_project_command",
    "handle_project_command_markdown",
]
