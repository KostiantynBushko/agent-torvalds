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

HELP_TEXT = """# Torvalds AI Agent — Help & Commands

### Interactive Slash Commands:
- `\\stats` : View request statistics summary in this document viewer.
- `\\toggle-hitl` : Toggle Human-In-The-Loop confirmation on/off.
- `\\hitl-status` : Show HITL configuration, question counts, and timeouts.
- `\\clear` : Clear current document view.
- `\\help` : Show this help message.
- `\\exit` or `\\quit` : Exit the Torvalds agent session.

### Keyboard Navigation:
- **Enter** : Submit prompt / confirm HITL answer
- **PgUp / PgDn** : Scroll document viewer up and down
- **Up / Down** : Browse previous input command history
- **Left / Right** : Move cursor horizontally in the input bar
- **Home / End** : Jump to start / end of the input line
- **Ctrl+C** : Cancel current input or exit if buffer is empty
"""


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
    ):
        self.console = console or Console()
        self.state = state or TuiState()
        self.agent = agent
        self.prompt_handler_fn = prompt_handler_fn
        self.target_fps = max(5, min(30, target_fps))
        self.hitl_toggle = hitl_toggle
        self.event_consumer = event_consumer
        self.stats_enabled = stats_enabled

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

        if cmd_lower == "\\help":
            self.state.set_markdown_content(HELP_TEXT)
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
