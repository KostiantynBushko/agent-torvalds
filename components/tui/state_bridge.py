"""
TUI State Bridge for Torvalds Multi-Window Console.

Provides thread-safe state synchronization between the LlamaIndex workflow,
EventConsumer, HumanLoopHandler, and the Rich Live rendering loop.
"""
import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolExecutionRecord:
    """Record of a tool execution for progress monitoring."""
    id: str
    name: str
    status: str  # "running", "completed", "error"
    start_time: float
    end_time: float = 0.0
    duration_ms: float = 0.0
    details: str = ""
    error_message: str = ""


class TuiState:
    """
    Thread-safe state container for Torvalds Multi-Window TUI.
    
    Coordinates UI variables across rendering frames and async tasks.
    """

    def __init__(self):
        self._lock = threading.RLock()

        # Agent activity state
        self.is_busy: bool = False
        self.current_query: str = ""
        self.status_message: str = "Ready"
        self.active_tool: Optional[str] = None
        self.active_tool_args: Dict[str, Any] = {}

        # Markdown Document Viewer state
        self.markdown_content: str = ""
        self.scroll_offset: int = 0
        self.total_rendered_lines: int = 0
        self.spinner_frame: int = 0

        # Background workflow & progress state
        self.workflow_iteration: int = 0
        self.max_iterations: int = 10
        self.tool_tasks: List[ToolExecutionRecord] = []
        self._tool_counter: int = 0

        # Telemetry & metrics state
        self.session_start_time: float = time.time()
        self.total_requests: int = 0
        self.total_tokens: int = 0
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.llm_call_count: int = 0
        self.total_tool_calls: int = 0
        self.cache_hits: int = 0
        self.cache_total: int = 0
        self.model_name: str = ""
        self.mode: str = "On-Demand Retriever"
        self.active_toolkits: List[str] = []
        self.memory_msg_count: int = 0
        self.last_stats: Optional[Any] = None

        # Interactive input bar state
        self.input_buffer: str = ""
        self.cursor_pos: int = 0
        self.command_history: List[str] = []
        self.history_index: int = -1
        self._saved_input: str = ""

        # Human-In-The-Loop (HITL) prompt state
        self.hitl_active: bool = False
        self.hitl_prompt: str = ""
        self.hitl_input_type: str = "text"  # "text", "yesno", "password"
        self.hitl_timeout: int = 30
        self.hitl_start_time: float = 0.0
        self.hitl_default_answer: str = ""
        self.hitl_enabled: bool = True
        self.hitl_future: Optional[asyncio.Future] = None

        # Session lifecycle
        self.exit_requested: bool = False
        self.notification_message: Optional[str] = None
        self.notification_expire: float = 0.0

    # ----------------------------------------------------------------------
    # Thread-Safe State Mutators
    # ----------------------------------------------------------------------

    def set_busy(self, busy: bool, query: str = "") -> None:
        """Update busy status and current query."""
        with self._lock:
            self.is_busy = busy
            if busy:
                self.current_query = query
                self.status_message = "Analyzing request..."
                self.scroll_offset = 0
            else:
                self.status_message = "Ready"
                self.active_tool = None

    def update_tool_start(self, tool_name: str, tool_kwargs: Dict[str, Any]) -> None:
        """Record the start of a tool execution."""
        with self._lock:
            self.status_message = f"Calling tool `{tool_name}`..."
            self.active_tool = tool_name
            self.active_tool_args = tool_kwargs
            self._tool_counter += 1

            details = ""
            if tool_name == "execute_shell_command":
                details = tool_kwargs.get("command", "")[:40]
            elif "file_path" in tool_kwargs:
                details = tool_kwargs.get("file_path", "")[:40]

            record = ToolExecutionRecord(
                id=f"tool-{self._tool_counter}",
                name=tool_name,
                status="running",
                start_time=time.time(),
                details=details,
            )
            self.tool_tasks.append(record)
            # Keep history bounded to last 15 tool executions
            if len(self.tool_tasks) > 15:
                self.tool_tasks.pop(0)

    def update_tool_end(self, tool_name: str, result: str, is_error: bool = False) -> None:
        """Record the completion of a tool execution."""
        with self._lock:
            self.status_message = f"Tool `{tool_name}` completed"
            if self.active_tool == tool_name:
                self.active_tool = None

            now = time.time()
            for record in reversed(self.tool_tasks):
                if record.name == tool_name and record.status == "running":
                    record.status = "error" if is_error else "completed"
                    record.end_time = now
                    record.duration_ms = (now - record.start_time) * 1000
                    if is_error:
                        record.error_message = result[:60]
                    break

            self.total_tool_calls += 1

    def append_stream_token(self, token: str) -> None:
        """Append streaming LLM token to markdown content."""
        with self._lock:
            self.markdown_content += token

    def set_markdown_content(self, content: str) -> None:
        """Set the complete markdown content."""
        with self._lock:
            self.markdown_content = content
            self.scroll_offset = 0

    def clear_markdown(self) -> None:
        """Clear document pane content."""
        with self._lock:
            self.markdown_content = ""
            self.scroll_offset = 0

    def scroll_up(self, lines: int = 5) -> None:
        """Scroll document viewer upwards."""
        with self._lock:
            self.scroll_offset = max(0, self.scroll_offset - lines)

    def scroll_down(self, lines: int = 5) -> None:
        """Scroll document viewer downwards."""
        with self._lock:
            max_scroll = max(0, self.total_rendered_lines - 10)
            self.scroll_offset = min(max_scroll, self.scroll_offset + lines)

    def update_workflow_iteration(self, iteration: int, max_iterations: int) -> None:
        """Update workflow iteration progress."""
        with self._lock:
            self.workflow_iteration = iteration
            self.max_iterations = max_iterations

    def update_telemetry_stats(self, stats: Any) -> None:
        """Update telemetry counts from finalized RequestStats."""
        with self._lock:
            self.last_stats = stats
            self.total_requests += 1
            if hasattr(stats, "total_prompt_tokens"):
                self.prompt_tokens += stats.total_prompt_tokens
                self.completion_tokens += stats.total_completion_tokens
                self.total_tokens += stats.total_tokens
            if hasattr(stats, "llm_call_count"):
                self.llm_call_count += stats.llm_call_count

    def update_cache_metrics(self, hits: int, total: int) -> None:
        """Update cache hits and total queries."""
        with self._lock:
            self.cache_hits = hits
            self.cache_total = total

    def show_notification(self, message: str, duration: float = 3.0) -> None:
        """Display a temporary notification in the status bar."""
        with self._lock:
            self.notification_message = message
            self.notification_expire = time.time() + duration

    def get_notification(self) -> Optional[str]:
        """Get active notification message if not expired."""
        with self._lock:
            if self.notification_message and time.time() < self.notification_expire:
                return self.notification_message
            self.notification_message = None
            return None

    def get_hitl_time_remaining(self) -> Optional[float]:
        """Calculate remaining time for active HITL prompt."""
        with self._lock:
            if not self.hitl_active:
                return None
            elapsed = time.time() - self.hitl_start_time
            remaining = max(0.0, self.hitl_timeout - elapsed)
            return remaining


class TuiEventAdapter:
    """
    Adapter between workflow events and TuiState.
    
    Can be registered with EventConsumer to listen to workflow events.
    """

    def __init__(self, state: TuiState):
        self.state = state

    def on_tool_call_start(self, tool_name: str, tool_kwargs: Dict[str, Any]) -> None:
        self.state.update_tool_start(tool_name, tool_kwargs)

    def on_tool_call_end(self, tool_name: str, result: str, is_error: bool = False) -> None:
        self.state.update_tool_end(tool_name, result, is_error)

    def on_stream_token(self, token: str) -> None:
        self.state.append_stream_token(token)

    def on_agent_output(self, output: str) -> None:
        self.state.set_markdown_content(output)

    def on_workflow_iteration(self, iteration: int, max_iter: int) -> None:
        self.state.update_workflow_iteration(iteration, max_iter)

    def register_with_event_consumer(self, consumer: Any) -> None:
        """Hook into EventConsumer callbacks."""
        if hasattr(consumer, "register_callback"):
            consumer.register_callback("ToolCall", self._handle_tool_call)
            consumer.register_callback("ToolCallResult", self._handle_tool_call_result)
            consumer.register_callback("AgentStream", self._handle_stream)

    async def _handle_tool_call(self, event: Any) -> None:
        tool_name = getattr(event, "tool_name", "")
        tool_kwargs = getattr(event, "tool_kwargs", {}) or {}
        self.on_tool_call_start(tool_name, tool_kwargs)

    async def _handle_tool_call_result(self, event: Any) -> None:
        tool_name = getattr(event, "tool_name", "")
        output = getattr(event, "tool_output", "")
        is_error = False
        if hasattr(output, "is_error"):
            is_error = output.is_error
        elif hasattr(output, "content"):
            content = str(output.content)
            is_error = content.startswith("Error:") or content.startswith("Traceback")
        self.on_tool_call_end(tool_name, str(output), is_error)

    async def _handle_stream(self, event: Any) -> None:
        delta = getattr(event, "delta", "")
        if delta:
            self.on_stream_token(delta)


class TuiInputModule:
    """
    Non-blocking replacement for ConsoleInputModule in TUI mode.
    
    Routes HITL prompts through the TUI footer command bar.
    """

    def __init__(self, state: TuiState):
        self.state = state

    async def prompt(
        self,
        message: str = "Please respond: ",
        default: str = "",
        timeout: Optional[int] = None,
    ) -> str:
        """
        Prompt the user for input via the TUI command bar.
        
        Args:
            message: The question or confirmation prompt.
            default: Fallback answer on timeout.
            timeout: Timeout in seconds (defaults to state.hitl_timeout).
            
        Returns:
            The user's input string, or default on timeout.
        """
        timeout_val = timeout if timeout is not None else self.state.hitl_timeout
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        # Activate HITL mode in TuiState
        with self.state._lock:
            self.state.hitl_active = True
            self.state.hitl_prompt = message
            self.state.hitl_input_type = "text"
            self.state.hitl_timeout = timeout_val
            self.state.hitl_start_time = time.time()
            self.state.hitl_default_answer = default
            self.state.hitl_future = future
            # Reset input buffer for HITL answer
            self.state.input_buffer = ""
            self.state.cursor_pos = 0

        try:
            if timeout_val and timeout_val > 0:
                answer = await asyncio.wait_for(future, timeout=float(timeout_val))
            else:
                answer = await future

            return answer.strip() if answer.strip() else default

        except asyncio.TimeoutError:
            logger.info("TUI HITL prompt timed out, using default: %s", default)
            return default
        finally:
            with self.state._lock:
                self.state.hitl_active = False
                self.state.hitl_future = None
                self.state.input_buffer = ""
                self.state.cursor_pos = 0

    async def confirm(
        self,
        message: str = "Confirm?",
        default_yes: bool = True,
        timeout: Optional[int] = None,
    ) -> bool:
        """Prompt for confirmation (yes/no)."""
        default_str = "yes" if default_yes else "no"
        answer = await self.prompt(
            message=f"{message} [y/n]",
            default=default_str,
            timeout=timeout,
        )
        return answer.strip().lower() in ("y", "yes", "true", "1")

    async def password(
        self,
        message: str = "Password: ",
        timeout: Optional[int] = None,
    ) -> str:
        """Prompt for sensitive text / password."""
        return await self.prompt(
            message=message,
            default="",
            timeout=timeout,
        )
