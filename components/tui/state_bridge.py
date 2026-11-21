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
from typing import Any, Dict, List, Optional, Set

from components.hitl_timeout import NO_TIMEOUT, is_no_timeout, normalize_timeout
from components.tui.hotkeys import (
    FOCUS_INPUT,
    FOCUS_PROGRESS,
    FOCUS_TELEMETRY,
    PANE_OF_FOCUS,
    PANES,
)
from components.tui.pane_scroll import PaneScroll

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
        #: The number of lines the document pane shows.  The
        #: application sets it from the layout: the number is the one
        #: the layout really uses, and not the one the source guesses.
        self.document_height: int = 10

        # Background workflow & progress state
        self.workflow_iteration: int = 0
        #: The budget of the run — how many iterations the agent may take.
        #: Zero means "not known yet": the console tells the state the
        #: budget when the agent is built, and it tells it again with
        #: every iteration of the run.
        self.max_iterations: int = 0
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
        # The tools the agent really has, by name, and how it got them:
        # "selected" - the operator picked them with ``--select``;
        # "loaded" - every tool of every toolkit, loaded upfront;
        # "indexed" - every tool of every toolkit, indexed by the
        # retriever.  The telemetry panel shows them - and an empty list
        # means "not known", not "no tools".
        self.active_tools: List[str] = []
        self.active_tool_scope: str = ""
        # The groups the operator picked with ``--select``: the
        # categories of the menu - "Operating System", "System",
        # "Security".  The panel names the groups and not the tools:
        # the operator picked a category, and the name of one tool out
        # of its eleven says nothing about the other ten.
        self.active_tool_groups: List[str] = []
        self.memory_msg_count: int = 0
        self.last_stats: Optional[Any] = None

        # The size of the prompt that goes to the model — the context.
        # The agent measures it before every request and hands the
        # measurement over; the telemetry panel renders it.
        self.context_measured: bool = False
        self.context_tokens: int = 0
        self.context_messages: int = 0
        self.context_bytes: int = 0
        self.context_window: int = 0
        self.context_estimated: bool = False

        # Project management state (active project / workspace)
        self.active_project: str = ""
        self.project_type: str = ""
        self.project_path: str = ""
        self.registered_projects: List[str] = []

        # Chat history state (active chat session)
        self.chat_session_name: str = ""
        self.chat_session_type: str = ""
        self.chat_session_id: str = ""

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
        # ``-1`` means "no timeout": the TUI waits for the human
        # indefinitely and shows no countdown.
        self.hitl_timeout: int = NO_TIMEOUT
        self.hitl_start_time: float = 0.0
        self.hitl_default_answer: str = ""
        self.hitl_enabled: bool = True
        self.hitl_future: Optional[asyncio.Future] = None

        # Session lifecycle
        self.exit_requested: bool = False
        self.notification_message: Optional[str] = None
        self.notification_expire: float = 0.0

        # -- the hot-keys ------------------------------------------------
        #
        # The focus is the command bar by default: **nothing changes for
        # the operator who uses no hot-key at all**.  The pager keys
        # still scroll the document, and the cursor still moves in the
        # input.
        self.focus: str = FOCUS_INPUT
        # The panes that are hidden.  A hidden pane is not in the focus
        # cycle, and the space it took goes to its sibling.
        self.hidden_panes: Set[str] = set()
        # The scroll of every pane of the sidebar that can be scrolled.
        # Every pane carries its own: the operator reads the progress
        # pane and the telemetry pane at the same time, and one window
        # does not move the other.  The document pane scrolls on
        # ``scroll_offset`` -- it has carried its own scroll since the
        # beginning.
        self.pane_scrolls: Dict[str, PaneScroll] = {
            FOCUS_PROGRESS: PaneScroll(),
            FOCUS_TELEMETRY: PaneScroll(),
        }

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
                # A new request is a new run: the iteration starts at
                # zero again, so the panel counts the run that is
                # running and not the one that ran before it.
                self.workflow_iteration = 0
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

            # The detail is the **whole** path or command, not a cut
            # of it: the view decides how much of it fits on the
            # screen, and the screen hides the home of the operator
            # before it cuts.  A cut here would leave half a home on
            # the screen.
            details = ""
            if tool_name == "execute_shell_command":
                details = tool_kwargs.get("command", "")
            elif "file_path" in tool_kwargs:
                details = tool_kwargs.get("file_path", "")

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
            max_scroll = self.max_scroll()
            self.scroll_offset = min(max_scroll, self.scroll_offset + lines)

    def scroll_home(self) -> None:
        """Go to the top of the document."""
        with self._lock:
            self.scroll_offset = 0

    def scroll_end(self) -> None:
        """Go to the bottom of the document."""
        with self._lock:
            self.scroll_offset = self.max_scroll()

    def max_scroll(self) -> int:
        """The largest offset the document may have.

        The number of lines the pane shows is the one the layout really
        uses: the scroll stops where the last line of the content is on
        the screen.
        """
        return max(0, self.total_rendered_lines - max(1, self.document_height))

    def update_workflow_iteration(self, iteration: int, max_iterations: int) -> None:
        """Update the progress of the workflow.

        The agent tells the panel which iteration of the run this is, and
        the budget the run was started with.

        A budget of zero is the *absence* of a budget, not a budget of
        zero: it does not replace a budget that is already known.

        Args:
            iteration: The number of the iteration of the run.
            max_iterations: The budget of the run.
        """
        with self._lock:
            self.workflow_iteration = max(0, int(iteration))
            if int(max_iterations) > 0:
                self.max_iterations = int(max_iterations)

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

    def update_context_size(
        self,
        tokens: int = 0,
        messages: int = 0,
        total_bytes: int = 0,
        window: int = 0,
        estimated: bool = False,
    ) -> None:
        """Update the size of the prompt that goes to the model.

        The agent measures the prompt in the workflow thread and the
        panel is painted in the render loop: the numbers are written
        under the lock, so the panel never sees half of a measurement.

        Args:
            tokens: The tokens of the prompt.
            messages: The messages of the prompt.
            total_bytes: The size of the prompt, in bytes.
            window: The context window of the model, in tokens.
            estimated: True when the tokens were estimated instead of
                counted with the tokenizer of the agent.
        """
        with self._lock:
            self.context_measured = True
            self.context_tokens = max(0, int(tokens))
            self.context_messages = max(0, int(messages))
            self.context_bytes = max(0, int(total_bytes))
            self.context_window = max(0, int(window))
            self.context_estimated = bool(estimated)

    def update_tools(
        self,
        tools: Optional[List[str]] = None,
        scope: str = "",
        groups: Optional[List[str]] = None,
    ) -> None:
        """Update the tools the agent really has.

        The orchestrator measures them: the names of the tools the agent
        was given, how it got them, and - when the operator picked the
        tools by hand - the groups the tools belong to.  The panel
        renders the measurement - it never guesses.

        Args:
            tools: The names of the tools.
            scope: How the agent got them: "selected" (the operator
                picked them), "loaded" (every tool, loaded upfront) or
                "indexed" (every tool, indexed by the retriever).
            groups: The groups the operator picked - the categories of
                the menu.  The panel names them; the tools are the
                detail behind them.
        """
        with self._lock:
            self.active_tools = list(tools or [])
            self.active_tool_scope = str(scope or "")
            self.active_tool_groups = list(groups or [])

    def update_project_context(
        self,
        project_name: str = "",
        project_type: str = "",
        project_path: str = "",
        registered_projects: Optional[List[str]] = None,
    ) -> None:
        """Update the active project / workspace context."""
        with self._lock:
            self.active_project = project_name
            self.project_type = project_type
            self.project_path = project_path
            self.registered_projects = list(registered_projects or [])

    def update_chat_session(
        self,
        session_name: str = "",
        session_type: str = "",
        session_id: str = "",
    ) -> None:
        """Update the active chat session information."""
        with self._lock:
            self.chat_session_name = session_name
            self.chat_session_type = session_type
            self.chat_session_id = session_id

    # ----------------------------------------------------------------------
    # The hot-keys
    # ----------------------------------------------------------------------

    def set_focus(self, focus: str) -> None:
        """Give the focus to a pane.

        Args:
            focus: The focus — "input", "document", "progress" or
                "telemetry".
        """
        with self._lock:
            self.focus = focus or FOCUS_INPUT

    def is_pane_visible(self, focus: str) -> bool:
        """Whether the pane of a focus is on the screen.

        Args:
            focus: The focus of the pane.

        Returns:
            True when the pane is visible.
        """
        with self._lock:
            pane = PANE_OF_FOCUS.get(focus, focus)
            return pane not in self.hidden_panes

    def focus_cycle(self) -> List[str]:
        """The focus cycle, in the order the operator walks through it.

        A hidden pane is not in the cycle: the operator cannot focus
        what is not on the screen.
        """
        with self._lock:
            cycle = [FOCUS_INPUT]
            for pane in PANES:
                layout_pane = PANE_OF_FOCUS.get(pane, pane)
                if layout_pane not in self.hidden_panes:
                    cycle.append(pane)
            return cycle

    def move_focus(self, step: int = 1) -> str:
        """Move the focus by a number of panes, and wrap around.

        Args:
            step: How many panes to move — one forward, one backward.

        Returns:
            The new focus.
        """
        with self._lock:
            cycle = self.focus_cycle()
            if not cycle:
                return self.focus
            try:
                index = cycle.index(self.focus)
            except ValueError:
                index = 0
            self.focus = cycle[(index + int(step)) % len(cycle)]
            return self.focus

    def toggle_pane(self, pane: str) -> bool:
        """Show or hide a pane.

        The space of a hidden pane goes to its sibling: the sidebar
        carries one pane instead of two, and the pane that is left
        takes the whole of it.

        Args:
            pane: The name of the pane in the layout — "progress_pane"
                or "telemetry_pane".

        Returns:
            True when the pane is visible after the change.
        """
        with self._lock:
            if pane in self.hidden_panes:
                self.hidden_panes.discard(pane)
            else:
                self.hidden_panes.add(pane)
            return pane not in self.hidden_panes

    def scroll_of(self, focus: str) -> PaneScroll:
        """The scroll of a pane.

        Args:
            focus: The focus of the pane.

        Returns:
            The scroll of the pane — a new one when the pane is not
            known, so that the caller never gets None.
        """
        with self._lock:
            scroll = self.pane_scrolls.get(focus)
            if scroll is None:
                scroll = PaneScroll()
                self.pane_scrolls[focus] = scroll
            return scroll

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
        """Calculate remaining time for active HITL prompt.

        Returns ``None`` when there is no countdown to show — either no
        prompt is active, or the prompt has no timeout (``-1``), in which
        case the agent waits for the human indefinitely.
        """
        with self._lock:
            if not self.hitl_active:
                return None
            if is_no_timeout(self.hitl_timeout):
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
        # The type of the pending question ("text", "yesno", "menu",
        # "password").  The consumer tells us through set_input_type().
        self._input_type = "text"

    def set_input_type(self, input_type: str) -> None:
        """Tell the TUI what kind of answer the pending question wants."""
        if input_type:
            self._input_type = input_type

    def on_tool_call_start(self, tool_name: str, tool_kwargs: Dict[str, Any]) -> None:
        self.state.update_tool_start(tool_name, tool_kwargs)

    def on_tool_call_end(self, tool_name: str, result: str, is_error: bool = False) -> None:
        self.state.update_tool_end(tool_name, result, is_error)

    def on_stream_token(self, token: str) -> None:
        self.state.append_stream_token(token)

    def on_agent_output(self, output: str) -> None:
        self.state.set_markdown_content(output)

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

    #: The TUI command bar owns its own layout, so it shows the question
    #: itself — the consumer prints into a silent console in TUI mode.
    renders_question = True

    def __init__(self, state: TuiState):
        self.state = state
        # The kind of answer the pending question wants ("text",
        # "yesno", "menu", "password").  The consumer tells us through
        # set_input_type(); without it the footer would label every
        # question "Answer:".
        self._input_type = "text"

    def set_input_type(self, input_type: str) -> None:
        """Tell the module what kind of answer the pending question wants."""
        if input_type:
            self._input_type = input_type

    async def prompt_with_status(
        self,
        message: str = "Please respond: ",
        default: str = "",
        timeout: Optional[int] = None,
    ) -> tuple[str, bool]:
        """
        Prompt the user for input and report whether the human answered.

        Args:
            message: The question or confirmation prompt.
            default: Fallback answer on timeout.
            timeout: Timeout in seconds (defaults to state.hitl_timeout).
                ``-1`` means *no timeout*: wait for the human
                indefinitely.

        Returns:
            ``(answer, was_timeout)`` tuple.  ``was_timeout`` is ``True``
            when the human did not answer at all.
        """
        timeout_val = timeout if timeout is not None else self.state.hitl_timeout
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        # Activate HITL mode in TuiState
        with self.state._lock:
            self.state.hitl_active = True
            self.state.hitl_prompt = message
            self.state.hitl_input_type = self._input_type
            self.state.hitl_timeout = timeout_val
            self.state.hitl_start_time = time.time()
            self.state.hitl_default_answer = default
            self.state.hitl_future = future
            # Reset input buffer for HITL answer
            self.state.input_buffer = ""
            self.state.cursor_pos = 0

        try:
            # ``None`` means "wait forever" — that is what the no-timeout
            # convention (-1) translates to.
            wait_timeout = normalize_timeout(timeout_val)
            if wait_timeout is not None:
                answer = await asyncio.wait_for(future, timeout=wait_timeout)
            else:
                answer = await future

            text = answer.strip() if isinstance(answer, str) else ""
            if not text:
                return default, True
            return text, False

        except asyncio.TimeoutError:
            logger.info("TUI HITL prompt timed out, using default: %s", default)
            return default, True
        finally:
            with self.state._lock:
                self.state.hitl_active = False
                self.state.hitl_future = None
                self.state.input_buffer = ""
                self.state.cursor_pos = 0

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
                ``-1`` means *no timeout*: wait for the human
                indefinitely.
            
        Returns:
            The user's input string, or default on timeout.
        """
        response, _ = await self.prompt_with_status(
            message=message, default=default, timeout=timeout
        )
        return response

    async def confirm_with_status(
        self,
        message: str = "",
        default_yes: bool = True,
        timeout: Optional[int] = None,
    ) -> tuple[bool, bool]:
        """Prompt for confirmation and report whether the human answered.

        Returns:
            ``(confirmed, was_timeout)`` tuple.
        """
        default_str = "yes" if default_yes else "no"
        response, was_timeout = await self.prompt_with_status(
            message=message,
            default=default_str,
            timeout=timeout,
        )
        if was_timeout:
            return default_yes, True
        return response.strip().lower() in ("y", "yes", "true", "1"), False

    async def confirm(
        self,
        message: str = "Confirm?",
        default_yes: bool = True,
        timeout: Optional[int] = None,
    ) -> bool:
        """Prompt for confirmation (yes/no)."""
        confirmed, _ = await self.confirm_with_status(
            message=f"{message} [y/n]",
            default_yes=default_yes,
            timeout=timeout,
        )
        return confirmed

    async def menu_with_status(
        self,
        message: str = "",
        options: List[str] = None,
        timeout: Optional[int] = None,
    ) -> tuple[str, bool]:
        """Ask the operator to pick one of *options* in the command bar.

        The choices travel beside the question, not inside it, so the
        footer has to show both: the operator has to see what the numbers
        stand for before typing one.

        Returns:
            ``(selected_option, was_timeout)`` tuple.
        """
        choices = list(options or [])
        if not choices:
            return "", True

        hint = f"[1-{len(choices)}]"
        numbered = "\n".join(
            f"{index}. {choice}" for index, choice in enumerate(choices, 1)
        )
        if message:
            prompt = f"{message}\n{numbered} {hint}"
        else:
            prompt = f"{numbered} {hint}"
        response, was_timeout = await self.prompt_with_status(
            message=prompt, default="", timeout=timeout
        )
        if was_timeout or not response.strip():
            return choices[0], True

        try:
            index = int(response.strip()) - 1
            if 0 <= index < len(choices):
                return choices[index], False
        except ValueError:
            pass

        return choices[0], False

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
