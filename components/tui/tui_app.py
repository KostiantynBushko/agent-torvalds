"""
Main TUI Orchestrator Application for Torvalds AI Agent.

Coordinates:
- Rich Live(screen=True) render loop at target FPS
- Cross-platform non-blocking keyboard input
- Background async query execution while keeping UI responsive
- Seamless Human-in-the-Loop (HITL) prompt dialogs
- Terminal screen restoration on shutdown or signal interruption
"""
import asyncio
import logging
import os
import sys
import time
from contextlib import contextmanager
from typing import Any, Callable, Coroutine, Dict, List, Optional

from rich.console import Console
from rich.live import Live

from components.command_registry import HelpOptions, build_help_markdown, is_help_command
from components.tui.layout_manager import (
    build_torvalds_layout,
    render_header,
    render_footer,
    check_terminal_size,
)
from components.tui.state_bridge import TuiState, TuiEventAdapter, TuiInputModule
from components.tui.input_reader import NonBlockingInputReader
from components.tui.markdown_view import MarkdownView
from components.tui.progress_view import ProgressView
from components.tui.telemetry_view import TelemetryView

logger = logging.getLogger(__name__)


#: The default TUI help screen, generated from the central command registry.
#: Kept as a module-level constant for existing importers and tests; the
#: running application uses :meth:`TuiApp._build_help_markdown` instead, which
#: takes the session's feature flags into account.
HELP_TEXT = build_help_markdown(
    HelpOptions(
        hitl=True,
        chat_history=True,
        project_manager=True,
        tui=True,
        keyboard_shortcuts=True,
    )
)


class TuiApp:
    """
    Main TUI orchestrator managing the Live screen loop and input dispatcher.
    """

    def __init__(
        self,
        agent: Any,
        prompt_handler_fn: Callable[..., Coroutine],
        state: Optional[TuiState] = None,
        console: Optional[Console] = None,
        target_fps: int = 15,
        hitl_toggle: Optional[Any] = None,
        event_consumer: Optional[Any] = None,
        stats_enabled: bool = True,
        chat_history_enabled: bool = True,
        project_manager_enabled: bool = True,
    ):
        self.console = console or Console()
        self.state = state or TuiState()
        self.agent = agent
        self.prompt_handler_fn = prompt_handler_fn
        self.target_fps = max(5, min(30, target_fps))
        self.hitl_toggle = hitl_toggle
        self.event_consumer = event_consumer
        self.stats_enabled = stats_enabled
        self.chat_history_enabled = chat_history_enabled
        self.project_manager_enabled = project_manager_enabled

        self.layout = build_torvalds_layout()
        self.input_reader = NonBlockingInputReader()
        self.markdown_view = MarkdownView(self.console)
        self.progress_view = ProgressView()
        self.telemetry_view = TelemetryView()

        self._active_query_task: Optional[asyncio.Task] = None
        self._is_paused: bool = False
        self._live: Optional[Live] = None

    @contextmanager
    def pause_screen(self):
        """
        Temporarily pause the Live TUI screen.
        Used for external full-screen tools like Whiptail dialogs.
        """
        if self._live and self._live.is_started:
            self._live.stop()
            self.input_reader.stop()
            self._is_paused = True
        try:
            yield
        finally:
            if self._live and self._is_paused:
                self.input_reader.start()
                self._live.start()
                self._is_paused = False

    async def run(self) -> None:
        """
        Start and run the main interactive TUI event loop.
        """
        # Minimum size check
        sufficient, w, h = check_terminal_size(self.console)
        if not sufficient:
            self.console.print(
                f"[yellow]Warning: Terminal size ({w}x{h}) is smaller than recommended (80x24). "
                f"TUI will adapt but may appear crowded.[/yellow]"
            )
            await asyncio.sleep(1.0)

        # Initialize input reader
        self.input_reader.start()

        # Create Live display with screen=True (full terminal takeover)
        with Live(
            self.layout,
            console=self.console,
            screen=True,
            auto_refresh=False,
            redirect_stdout=False,
            redirect_stderr=False,
        ) as live:
            self._live = live
            tick_interval = 1.0 / self.target_fps

            try:
                while not self.state.exit_requested:
                    start_tick = time.monotonic()

                    # 1. Process keyboard inputs
                    self._process_keyboard_input()

                    # 2. Render frame components
                    self._update_layout_panes()

                    # 3. Refresh display
                    if not self._is_paused:
                        live.update(self.layout, refresh=True)

                    # 4. Sleep remainder of frame tick
                    elapsed = time.monotonic() - start_tick
                    sleep_time = max(0.005, tick_interval - elapsed)
                    await asyncio.sleep(sleep_time)

            except (KeyboardInterrupt, asyncio.CancelledError):
                logger.info("TUI loop interrupted")
            finally:
                self.input_reader.stop()
                if self._active_query_task and not self._active_query_task.done():
                    self._active_query_task.cancel()

    def _process_keyboard_input(self) -> None:
        """Read and handle pending keys from the non-blocking input reader."""
        # Read all available keys this tick
        while self.input_reader.is_available():
            key = self.input_reader.poll_key()
            if not key:
                break
            self._handle_key(key)

    def _handle_key(self, key: str) -> None:
        """Process a single normalized keystroke."""
        with self.state._lock:
            buf = self.state.input_buffer
            pos = self.state.cursor_pos

            # Enter Key: Submit command or HITL response
            if key == "ENTER":
                self._handle_enter_pressed()
                return

            # Backspace Key
            if key == "BACKSPACE":
                if pos > 0:
                    self.state.input_buffer = buf[:pos - 1] + buf[pos:]
                    self.state.cursor_pos = pos - 1
                return

            # Delete Key
            if key == "DELETE":
                if pos < len(buf):
                    self.state.input_buffer = buf[:pos] + buf[pos + 1:]
                return

            # Arrow Navigation
            if key == "LEFT":
                self.state.cursor_pos = max(0, pos - 1)
                return
            if key == "RIGHT":
                self.state.cursor_pos = min(len(buf), pos + 1)
                return
            if key == "HOME":
                self.state.cursor_pos = 0
                return
            if key == "END":
                self.state.cursor_pos = len(buf)
                return

            # History Navigation
            if key == "UP":
                if self.state.command_history:
                    if self.state.history_index == -1:
                        self.state._saved_input = buf
                        self.state.history_index = len(self.state.command_history) - 1
                    elif self.state.history_index > 0:
                        self.state.history_index -= 1
                    
                    hist_cmd = self.state.command_history[self.state.history_index]
                    self.state.input_buffer = hist_cmd
                    self.state.cursor_pos = len(hist_cmd)
                return

            if key == "DOWN":
                if self.state.history_index != -1:
                    if self.state.history_index < len(self.state.command_history) - 1:
                        self.state.history_index += 1
                        hist_cmd = self.state.command_history[self.state.history_index]
                        self.state.input_buffer = hist_cmd
                        self.state.cursor_pos = len(hist_cmd)
                    else:
                        self.state.history_index = -1
                        self.state.input_buffer = self.state._saved_input
                        self.state.cursor_pos = len(self.state.input_buffer)
                return

            # Page Up / Page Down (Document Viewer Scrolling)
            if key == "PGUP":
                self.state.scroll_up(lines=6)
                return
            if key == "PGDN":
                self.state.scroll_down(lines=6)
                return

            # Exit / Interrupt shortcuts
            if key in ("CTRL_C", "CTRL_D"):
                if buf:
                    # Clear current buffer
                    self.state.input_buffer = ""
                    self.state.cursor_pos = 0
                else:
                    self.state.exit_requested = True
                return

            # Printable Character
            if len(key) == 1 and key.isprintable():
                self.state.input_buffer = buf[:pos] + key + buf[pos:]
                self.state.cursor_pos = pos + 1

    def _handle_enter_pressed(self) -> None:
        """Handle Enter key press (submission)."""
        cmd = self.state.input_buffer.strip()

        # If HITL mode is active, submit input to waiting future
        if self.state.hitl_active:
            if self.state.hitl_future and not self.state.hitl_future.done():
                self.state.hitl_future.set_result(cmd)
            self.state.input_buffer = ""
            self.state.cursor_pos = 0
            return

        # Empty command
        if not cmd:
            return

        # Record in history
        self.state.command_history.append(cmd)
        self.state.history_index = -1
        self.state.input_buffer = ""
        self.state.cursor_pos = 0

        # Handle built-in slash commands
        cmd_lower = cmd.lower()
        if cmd_lower in ("\\exit", "\\quit"):
            self.state.exit_requested = True
            return

        if cmd_lower == "\\clear":
            self.state.clear_markdown()
            self.state.show_notification("Document pane cleared.")
            return

        if is_help_command(cmd):
            self.state.set_markdown_content(self._build_help_markdown())
            return

        if cmd_lower == "\\stats":
            self._render_stats_to_markdown()
            return

        if cmd_lower == "\\toggle-hitl" and self.hitl_toggle:
            asyncio.create_task(self._toggle_hitl_action())
            return

        if cmd_lower == "\\hitl-status":
            self._render_hitl_status_to_markdown()
            return

        # The remaining HITL commands (\hitl-on, \hitl-off, \hitl-help) are
        # handled by the runtime toggle itself.
        if self.hitl_toggle and self.hitl_toggle.is_hitl_command(cmd):
            asyncio.create_task(self._run_hitl_command(cmd))
            return

        # ---- Tool selection commands ----
        if cmd_lower == "\\tools":
            self._render_tool_selection_menu()
            return

        if cmd_lower == "\\tool-list":
            self._render_tool_list()
            return

        if cmd_lower.startswith("\\tool-select"):
            self._handle_tool_select_command(cmd)
            return

        # ---- Project management commands ----
        if self.project_manager_enabled:
            from components.tui.project_manager_view import handle_project_command_markdown

            if cmd_lower.startswith("\\project") or cmd_lower.startswith("\\projects"):
                try:
                    project_md = handle_project_command_markdown(cmd)
                except Exception as e:
                    project_md = f"# Project Command\n\n**Error:** {e}"
                if project_md:
                    self.state.set_markdown_content(project_md)
                return

        # ---- Chat history commands ----
        if self.chat_history_enabled:
            from components.tui.chat_history_view import handle_chat_command_markdown

            try:
                chat_md = handle_chat_command_markdown(cmd)
            except Exception as e:
                chat_md = f"# Chat Command\n\n**Error:** {e}"
            if chat_md:
                self.state.set_markdown_content(chat_md)
                self._refresh_chat_session_state()
                return

        # Standard agent query: Launch async task
        if self.state.is_busy:
            self.state.show_notification("Agent is busy processing. Please wait.", duration=2.5)
            return

        self._active_query_task = asyncio.create_task(self._execute_agent_query(cmd))

    async def _execute_agent_query(self, query: str) -> None:
        """Execute agent workflow in background without freezing UI loop."""
        self.state.set_busy(True, query)
        self.state.markdown_content = ""

        try:
            response, stats = await self.prompt_handler_fn(
                cmd=query,
                agent=self.agent,
                enable_stats=self.stats_enabled,
                event_consumer=self.event_consumer,
            )

            # If response is None or empty, provide fallback
            if not response:
                response = "*No output returned from agent.*"

            self.state.set_markdown_content(response)

            if stats:
                self.state.update_telemetry_stats(stats)
                # Persist stats to cache if configured
                from components.stats_handler import STATS_PERSIST
                if STATS_PERSIST:
                    from agent_cache_system import save_request_stats
                    save_request_stats(stats.to_dict())

        except Exception as e:
            import traceback
            error_str = f"# Error during execution\n\n```text\n{e}\n{traceback.format_exc()}\n```"
            self.state.set_markdown_content(error_str)
            logger.error("Agent execution failed: %s", e)
        finally:
            self.state.set_busy(False)
            self._refresh_cache_metrics()

    def _build_help_markdown(self) -> str:
        """
        Build the help screen for the current session.

        The command list comes from the central registry, filtered by the
        feature flags that are actually enabled in this TUI session, so the
        help screen never advertises a command that would fail.

        Returns:
            str: Markdown document describing every available command.
        """
        options = HelpOptions(
            hitl=True,
            chat_history=self.chat_history_enabled,
            project_manager=self.project_manager_enabled,
            tui=True,
            keyboard_shortcuts=True,
        )
        return build_help_markdown(options)

    def _render_stats_to_markdown(self) -> None:
        """Format request statistics summary into Markdown view."""
        from agent_cache_system import get_stats_summary
        summary = get_stats_summary()

        if "message" in summary:
            content = f"# Request Statistics\n\n{summary['message']}"
        else:
            content = f"""# 📊 Request Statistics Summary

| Metric | Value |
| :--- | :--- |
| **Total Requests** | {summary.get('total_requests', 0)} |
| **Total Tokens** | {summary.get('total_tokens', 0):,} |
| **Total LLM Calls** | {summary.get('total_llm_calls', 0):,} |
| **Total Tool Calls** | {summary.get('total_tool_calls', 0):,} |
| **Avg Tokens/Request** | {summary.get('avg_tokens_per_request', 0):,.1f} |
| **Avg Duration** | {summary.get('avg_duration_ms', 0):,.1f}ms |
| **Avg LLM Calls/Request** | {summary.get('avg_llm_calls_per_request', 0):,.1f} |
| **Total Errors** | {summary.get('total_errors', 0)} |
"""
        self.state.set_markdown_content(content)

    def _render_hitl_status_to_markdown(self) -> None:
        """Display HITL status in Markdown view."""
        if not self.hitl_toggle:
            self.state.set_markdown_content("# HITL Status\n\nHITL is not configured.")
            return

        status_info = self.hitl_toggle.status_sync()
        hitl_stats = self.event_consumer.get_hitl_stats() if self.event_consumer else {}

        content = f"""# 🤖 Human-in-the-Loop (HITL) Status

| Setting | Current Value |
| :--- | :--- |
| **HITL Enabled** | {'🟢 YES' if status_info.get('enabled') else '🔴 NO'} |
| **Method** | {hitl_stats.get('method', 'TUI Command Bar')} |
| **Timeout** | {hitl_stats.get('timeout', 30)}s |
| **Default Answer** | '{hitl_stats.get('default_answer', '')}' |
| **Questions Asked** | {hitl_stats.get('question_count', 0)} |
| **Timeouts** | {hitl_stats.get('timeout_count', 0)} |
| **Runtime Toggles** | {status_info.get('toggle_count', 0)} |
"""
        self.state.set_markdown_content(content)

    # ------------------------------------------------------------------
    # Tool selection
    # ------------------------------------------------------------------

    def _render_tool_selection_menu(self) -> None:
        """Render the interactive tool category selection menu."""
        from components.tui.tool_selection_view import (
            discover_all_tools,
            render_categories_markdown,
        )

        try:
            tools = discover_all_tools()
        except Exception as e:
            self.state.set_markdown_content(
                f"# 🧰 Startup Tool Selection\n\n**Error:** {e}"
            )
            return

        from agent_tool_selection import group_tools_by_category

        groups = group_tools_by_category(tools)
        self.state.set_markdown_content(
            render_categories_markdown(groups, len(tools))
        )
        self.state.show_notification(
            "Type your selection in the command bar (e.g. 1,3,5 or 1-4) and press Enter.",
            duration=6.0,
        )

    def _render_tool_list(self) -> None:
        """Render the flat list of every available tool."""
        from components.tui.tool_selection_view import (
            discover_all_tools,
            render_tool_list_markdown,
        )

        try:
            tools = discover_all_tools()
        except Exception as e:
            self.state.set_markdown_content(
                f"# 🧰 Available Tools\n\n**Error:** {e}"
            )
            return

        self.state.set_markdown_content(render_tool_list_markdown(tools))

    def _handle_tool_select_command(self, cmd: str) -> None:
        """
        Handle the non-interactive ``\tool-select <spec>`` command.

        Args:
            cmd: The full command string.
        """
        from agent_tool_selection import (
            _extract_category,
            group_tools_by_category,
            parse_tool_selection,
        )
        from components.tui.tool_selection_view import discover_all_tools

        parts = cmd.strip().split(maxsplit=1)
        spec = parts[1].strip() if len(parts) > 1 else ""

        if not spec:
            self.state.set_markdown_content(
                "# 🧰 Tool Selection\n\n"
                "**Usage:** `\\tool-select <spec>`  "
                "(e.g. `\\tool-select 1-3,7`)"
            )
            return

        try:
            tools = discover_all_tools()
        except Exception as e:
            self.state.set_markdown_content(
                f"# 🧰 Tool Selection\n\n**Error:** {e}"
            )
            return

        groups = group_tools_by_category(tools)
        category_list = list(groups.keys())

        try:
            indexes = parse_tool_selection(spec, maximum=len(category_list))
        except ValueError as e:
            self.state.set_markdown_content(
                f"# 🧰 Tool Selection\n\n**Error:** {e}"
            )
            return

        selected_categories = {category_list[i - 1] for i in indexes}
        selected_tools = [
            t for t in tools
            if _extract_category(t.metadata.description) in selected_categories
        ]

        lines = [
            "# 🧰 Tool Selection Result",
            "",
            f"Selected **{len(selected_categories)}** categories "
            f"({len(selected_tools)} of {len(tools)} tools):",
            "",
        ]
        for cat in selected_categories:
            lines.append(f"- ✓ **{cat}** ({len(groups[cat])} tools)")

        self.state.set_markdown_content("\n".join(lines))
        self.state.show_notification(
            f"Selected {len(selected_tools)} tools. Restart with --select to apply.",
            duration=5.0,
        )

    # ------------------------------------------------------------------
    # Chat session state
    # ------------------------------------------------------------------

    def _refresh_chat_session_state(self) -> None:
        """Refresh the active chat session information in the TUI state."""
        try:
            from chat_manager.startup import get_chat_manager

            manager = get_chat_manager()
            if manager is None or not manager.is_initialized:
                return

            session = manager.get_active_session()
            if session is None:
                return

            self.state.update_chat_session(
                session_name=session.session_name,
                session_type=session.session_type.value,
                session_id=session.session_id,
            )

            # Refresh the message count for the (possibly new) session
            try:
                msgs = manager.get_messages()
                self.state.memory_msg_count = len(msgs)
            except Exception:
                pass
        except Exception:
            pass

    async def _run_hitl_command(self, cmd: str) -> None:
        r"""
        Run a HITL runtime-toggle command and show its output.

        Args:
            cmd: The HITL command to execute (e.g. ``\hitl-on``).
        """
        if not self.hitl_toggle:
            return

        try:
            result = await self.hitl_toggle.process_command(cmd)
        except Exception as e:  # pragma: no cover - defensive
            self.state.set_markdown_content(f"# HITL Command\n\n**Error:** {e}")
            return

        if result:
            self.state.set_markdown_content(
                "# HITL Command\n\n```text\n" + result + "\n```"
            )

        self.state.hitl_enabled = self.hitl_toggle.is_enabled

    async def _toggle_hitl_action(self) -> None:
        """Toggle HITL runtime state and notify."""
        if self.hitl_toggle:
            result = await self.hitl_toggle.process_command("\\toggle-hitl")
            self.state.hitl_enabled = self.hitl_toggle.is_enabled
            self.state.show_notification(f"HITL {'Enabled' if self.state.hitl_enabled else 'Disabled'}")

    def _refresh_cache_metrics(self) -> None:
        """Update cache hits from cache system summary."""
        try:
            from agent_cache_system import get_stats_summary
            summary = get_stats_summary()
            total_req = summary.get("total_requests", 0)
            self.state.update_cache_metrics(self.state.cache_hits, total_req)
        except Exception:
            pass

    def _update_layout_panes(self) -> None:
        """Render and attach panels to the layout partitions."""
        # 1. Header
        header_panel = render_header(
            model_name=self.state.model_name,
            memory_count=self.state.memory_msg_count,
            hitl_enabled=self.state.hitl_enabled,
            session_start_time=self.state.session_start_time,
            is_busy=self.state.is_busy,
        )
        self.layout["header"].update(header_panel)

        # 2. Markdown View (Main Body Left)
        markdown_panel = self.markdown_view.render(self.state)
        self.layout["markdown_pane"].update(markdown_panel)

        # 3. Progress View (Sidebar Top)
        progress_panel = self.progress_view.render(self.state)
        self.layout["progress_pane"].update(progress_panel)

        # 4. Telemetry View (Sidebar Bottom)
        telemetry_panel = self.telemetry_view.render(self.state)
        self.layout["telemetry_pane"].update(telemetry_panel)

        # 5. Footer Input Bar / HITL Modal
        remaining = self.state.get_hitl_time_remaining()
        footer_panel = render_footer(
            input_buffer=self.state.input_buffer,
            cursor_pos=self.state.cursor_pos,
            hitl_active=self.state.hitl_active,
            hitl_prompt=self.state.hitl_prompt,
            hitl_time_remaining=remaining,
            hitl_default_answer=self.state.hitl_default_answer,
            is_busy=self.state.is_busy,
        )
        self.layout["footer"].update(footer_panel)
