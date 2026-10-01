"""
Event Consumer Component

Consumes workflow events from the LlamaIndex agent in real-time. Routes
events to appropriate handlers, manages spinner state, updates UI with
progress, and tracks tool calls and results.

Now includes HITL (Human-in-the-Loop) support:
- Handles InputRequiredEvent from LlamaIndex workflows
- Handles custom AgentQuestionEvent from HITL handler
- Pauses/resumes spinner during human prompts
- Sends HumanResponseEvent back to the workflow
- Integrates with runtime toggle for dynamic HITL enable/disable

Usage:
    consumer = EventConsumer(
        spinner_controller=spinner_controller,
        state_handler=state_handler,
        console=console,
        hitl_timeout=30,
        hitl_default_answer="",
    )
    
    handler = agent.run(cmd, ...)
    result = await consumer.consume_events(handler, cmd, hitl_toggle=hitl_toggle)
"""
import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Set

from rich.console import Console

from components.spinner_controller import SpinnerController
from components.state_handler import StateHandler
from components.console_input_module import ConsoleInputModule

logger = logging.getLogger(__name__)

# Import LlamaIndex event types
try:
    from llama_index.core.workflow import Event, StopEvent, InputRequiredEvent, HumanResponseEvent
    from llama_index.core.agent.workflow import (
        AgentInput,
        AgentSetup,
        AgentOutput,
        AgentStream,
        ToolCall,
        ToolCallResult,
    )
    WORKFLOW_EVENTS_AVAILABLE = True
except ImportError:
    WORKFLOW_EVENTS_AVAILABLE = False
    # Fallback: create dummy classes
    class Event:
        pass
    class StopEvent(Event):
        def __init__(self, result=None):
            self.result = result
    class InputRequiredEvent(Event):
        def __init__(self, prefix="", user_name=None):
            self.prefix = prefix
            self.user_name = user_name
    class HumanResponseEvent(Event):
        def __init__(self, response="", user_name=None):
            self.response = response
            self.user_name = user_name
    class AgentWorkflowStartEvent(Event):
        pass
    class AgentInput(Event):
        def __init__(self, input=None):
            self.input = input
    class AgentSetup(Event):
        pass
    class AgentOutput(Event):
        def __init__(self, output=None):
            self.output = output
    class AgentStream(Event):
        def __init__(self, delta="", prefix=False, suffix=False):
            self.delta = delta
            self.prefix = prefix
            self.suffix = suffix
    class ToolCall(Event):
        def __init__(self, tool_name="", tool_kwargs=None, tool_id=""):
            self.tool_name = tool_name
            self.tool_kwargs = tool_kwargs or {}
            self.tool_id = tool_id
    class ToolCallResult(Event):
        def __init__(self, tool_name="", tool_output=None, tool_id=""):
            self.tool_name = tool_name
            self.tool_output = tool_output
            self.tool_id = tool_id


# Default set of tools that should pause the spinner
# These tools perform interactive operations (password prompts, whiptail dialogs,
# long-running installs) that conflict with the rich console spinner.
DEFAULT_INTERACTIVE_TOOLS: Set[str] = {
    "prompt_sudo_password_whiptail",
    "prompt_sudo_password_console",
    "prompt_sudo_password",
    "test_sudo_password",
    "install_package",
    "install_multiple_packages",
    "interactive_install_missing_command",
}

# Events to ignore in verbose logging (these are high-frequency/internal)
VERBOSE_IGNORE_EVENTS: Set[str] = {
    "AgentStream",          # Fires for every token - too noisy
    "AgentSetup",           # Internal setup
    "AgentInput",           # Internal input handling
    "AgentWorkflowStartEvent",  # Internal workflow start
}


class EventConsumer:
    """
    Consumes workflow events and triggers actions.
    
    Responsibilities:
    - Stream events from WorkflowHandler
    - Route events to appropriate handlers
    - Manage spinner state based on events
    - Update UI with progress
    - Handle HITL events (InputRequiredEvent, AgentQuestionEvent)
    - Integrate with runtime toggle for dynamic HITL control
    
    Attributes:
        spinner: SpinnerController for visual feedback.
        state: StateHandler for tracking workflow state.
        console: Rich Console for output.
        hitl_timeout: Timeout in seconds for HITL prompts.
        hitl_default_answer: Default answer when user times out.
        console_input: ConsoleInputModule for collecting user input.
        runtime_toggle: Optional HITLRuntimeToggle for dynamic HITL control.
    """

    def __init__(
        self,
        spinner_controller: SpinnerController,
        state_handler: StateHandler,
        console: Console,
        interactive_tools: Optional[Set[str]] = None,
        verbose: bool = False,
        # HITL configuration
        hitl_timeout: int = 30,
        hitl_default_answer: str = "",
        hitl_enabled: bool = True,
    ):
        self.spinner = spinner_controller
        self.state = state_handler
        self.console = console
        self._interactive_tools = interactive_tools or DEFAULT_INTERACTIVE_TOOLS
        self._verbose = verbose
        self._event_handlers: Dict[str, Callable] = {}
        self._running = False
        self._tool_calls_paused_spinner: Set[str] = set()
        
        # HITL configuration
        self.hitl_timeout = hitl_timeout
        self.hitl_default_answer = hitl_default_answer
        self.hitl_enabled = hitl_enabled
        self.console_input = ConsoleInputModule(console)
        
        # Runtime toggle (set during consume_events or via setter)
        self.runtime_toggle = None
        
        # HITL state tracking
        self._hitl_question_count = 0
        self._hitl_timeout_count = 0

    def set_runtime_toggle(self, toggle: Any) -> None:
        """Set the runtime toggle for dynamic HITL control.
        
        Args:
            toggle: HITLRuntimeToggle instance or None to disable.
        """
        self.runtime_toggle = toggle

    async def consume_events(
        self,
        handler: Any,
        user_msg: str,
        hitl_toggle: Any = None,
    ) -> Any:
        """
        Consume events from workflow handler.
        
        Args:
            handler: WorkflowHandler from agent.run()
            user_msg: Original user message
            hitl_toggle: Optional HITLRuntimeToggle for dynamic HITL control
            
        Returns:
            Final result from the workflow
        """
        self._running = True
        self.state.set("current_user_msg", user_msg)
        self.state.set("workflow_running", True)
        self.state.set("start_time", asyncio.get_event_loop().time())
        
        # Store reference to handler for event emission
        self._current_handler = handler
        
        # Set runtime toggle if provided
        if hitl_toggle is not None:
            self.runtime_toggle = hitl_toggle
        
        try:
            async for event in handler.stream_events():
                if not self._running:
                    break
                
                # Route event to appropriate handler
                await self._handle_event(event)
            
            # Get final result
            result = await handler
            
            # Mark workflow as completed
            self.state.set("workflow_running", False)
            self.state.set("end_time", asyncio.get_event_loop().time())
            
            return result
            
        except asyncio.CancelledError:
            self.state.set("workflow_running", False)
            self.state.add_error("Workflow was cancelled")
            raise
        except Exception as e:
            self.state.set("workflow_running", False)
            self.state.add_error(str(e))
            raise
        finally:
            self._running = False
            self._current_handler = None
            # Resume spinner if it was paused by any tool
            if self.spinner.is_paused:
                self.spinner.resume()

    async def _handle_event(self, event: Event) -> None:
        """Route event to specific handler."""
        event_type = type(event).__name__
        
        # Handle custom callbacks if registered
        if event_type in self._event_handlers:
            handler = self._event_handlers[event_type]
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)
        
        # Route to built-in handlers
        if isinstance(event, AgentStream):
            await self._on_agent_stream(event)
        elif isinstance(event, ToolCall):
            await self._on_tool_call(event)
        elif isinstance(event, ToolCallResult):
            await self._on_tool_call_result(event)
        elif isinstance(event, StopEvent):
            await self._on_stop_event(event)
        elif isinstance(event, AgentOutput):
            await self._on_agent_output(event)
        elif isinstance(event, InputRequiredEvent):
            await self._on_input_required(event)
        elif self._verbose and event_type not in VERBOSE_IGNORE_EVENTS:
            # Log other events in verbose mode (excluding high-frequency ones)
            self.console.print(f"[dim]Event: {event_type}[/dim]")

    def _is_hitl_enabled(self) -> bool:
        """Check if HITL is currently enabled (considering runtime toggle).
        
        Returns:
            True if HITL is enabled, False otherwise.
        """
        if self.runtime_toggle is not None:
            return self.hitl_enabled and self.runtime_toggle.is_enabled
        return self.hitl_enabled

    async def _on_agent_stream(self, event: AgentStream) -> None:
        """Handle streaming token event."""
        if event.delta:
            # Could print streaming tokens here if desired
            # For now, just track in state
            pass

    async def _on_tool_call(self, event: ToolCall) -> None:
        """Handle tool call event."""
        tool_name = event.tool_name
        
        # Update state
        self.state.set("current_tool", tool_name)
        self.state.increment("tool_calls")
        
        # Pause spinner for interactive tools
        if tool_name in self._interactive_tools:
            self.spinner.pause()
            self._tool_calls_paused_spinner.add(tool_name)
            self.state.set("workflow_paused", True)
            
            # Show tool call info
            self.console.print(
                f"\n[yellow]🔧 Calling tool: {tool_name}[/yellow]"
            )
            
            # Show command details for shell commands
            if tool_name == "execute_shell_command":
                cmd = event.tool_kwargs.get("command", "")
                if cmd:
                    self.console.print(f"   [dim]Command: {cmd}[/dim]")

    async def _on_tool_call_result(self, event: ToolCallResult) -> None:
        """Handle tool call result event."""
        tool_name = event.tool_name
        
        # Resume spinner after interactive tool execution
        if tool_name in self._interactive_tools:
            self.spinner.resume()
            self._tool_calls_paused_spinner.discard(tool_name)
            self.state.set("workflow_paused", False)
        
        # Check for errors
        is_error = False
        if hasattr(event.tool_output, 'is_error'):
            is_error = event.tool_output.is_error
        elif hasattr(event.tool_output, 'content'):
            content = event.tool_output.content
            is_error = content.startswith("Error:") or content.startswith("Traceback")
        
        # Record in state
        result_content = ""
        if hasattr(event.tool_output, 'content'):
            result_content = event.tool_output.content
        elif event.tool_output:
            result_content = str(event.tool_output)
        
        self.state.add_tool_call(tool_name, result_content, error=is_error)
        
        # Show result in verbose mode
        if self._verbose and not is_error:
            self.console.print(
                f"[green]✅ Tool completed: {tool_name}[/green]"
            )

    async def _on_stop_event(self, event: StopEvent) -> None:
        """Handle workflow completion event."""
        self.state.set("workflow_running", False)

    async def _on_agent_output(self, event: AgentOutput) -> None:
        """Handle agent output event."""
        pass

    # ------------------------------------------------------------------
    # HITL Event Handlers
    # ------------------------------------------------------------------

    async def _on_input_required(self, event: InputRequiredEvent) -> None:
        """Handle InputRequiredEvent — agent needs human input.
        
        This is the core HITL handler. When the agent emits an
        InputRequiredEvent, we:
        1. Pause the spinner
        2. Display the question to the user
        3. Collect the response (with timeout)
        4. Send the response back via HumanResponseEvent
        5. Resume the spinner
        
        Args:
            event: InputRequiredEvent containing the question/prefix.
        """
        if not self._is_hitl_enabled():
            logger.debug("HITL disabled, skipping InputRequiredEvent")
            return
        
        self._hitl_question_count += 1
        
        # Pause spinner
        self.spinner.pause()
        self.state.set("workflow_paused", True)
        
        # Extract question text
        question = getattr(event, 'prefix', 'Please respond: ')
        
        # Display question
        self.console.print(
            f"\n[magenta]🤖 Agent asks: {question}[/magenta]"
        )
        
        try:
            # Get user input with timeout
            response = await self.console_input.prompt(
                message="Your response: ",
                default=self.hitl_default_answer,
                timeout=self.hitl_timeout,
            )
            
            # Check if it was a timeout (empty response when default is empty)
            if response == self.hitl_default_answer and not response.strip():
                self._hitl_timeout_count += 1
                self.console.print(
                    f"[yellow]⏱️  Timeout — using default answer[/yellow]"
                )
            else:
                self.console.print("[green]✅ Response sent to agent[/green]")
            
            # Send response back to workflow
            # Note: We emit the event back into the workflow via the handler
            # This requires access to the workflow's event emitter
            if hasattr(self, '_current_handler') and self._current_handler:
                self._current_handler.ctx.send_event(
                    HumanResponseEvent(
                        response=response,
                        user_name=getattr(event, 'user_name', None),
                    )
                )
            
        except asyncio.TimeoutError:
            self._hitl_timeout_count += 1
            self.console.print(
                f"[yellow]⏱️  Timeout — using default: '{self.hitl_default_answer}'[/yellow]"
            )
            # Send default response
            if hasattr(self, '_current_handler') and self._current_handler:
                self._current_handler.ctx.send_event(
                    HumanResponseEvent(
                        response=self.hitl_default_answer,
                        user_name=getattr(event, 'user_name', None),
                    )
                )
        except Exception as e:
            logger.error(f"Error handling InputRequiredEvent: {e}")
            self.console.print(
                f"[red]⚠️  Error collecting response: {e}[/red]"
            )
        finally:
            # Resume spinner
            self.spinner.resume()
            self.state.set("workflow_paused", False)

    async def send_event(self, event: Event) -> None:
        """Send an event to the current workflow handler.
        
        This method allows external handlers (like HumanLoopHandler) to
        emit events into the workflow.
        
        Args:
            event: Event to send.
        """
        if hasattr(self, '_current_handler') and self._current_handler:
            self._current_handler.ctx.send_event(event)
        else:
            logger.warning("No active handler to send event to")

    # ------------------------------------------------------------------
    # HITL State Accessors
    # ------------------------------------------------------------------

    def get_hitl_stats(self) -> Dict[str, Any]:
        """Get HITL statistics.
        
        Returns:
            Dict with HITL question and timeout counts.
        """
        return {
            "enabled": self._is_hitl_enabled(),
            "question_count": self._hitl_question_count,
            "timeout_count": self._hitl_timeout_count,
            "timeout": self.hitl_timeout,
            "default_answer": self.hitl_default_answer,
        }

    def reset_hitl_stats(self) -> None:
        """Reset HITL statistics."""
        self._hitl_question_count = 0
        self._hitl_timeout_count = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_callback(self, event_type: str, callback: Callable) -> None:
        """
        Register a custom callback for an event type.
        
        Args:
            event_type: Name of the event type (e.g., "ToolCall", "AgentStream")
            callback: Async or sync callable to handle the event
        """
        self._event_handlers[event_type] = callback

    def add_interactive_tools(self, tool_names: List[str]) -> None:
        """
        Add tools to the interactive set (will pause spinner).
        
        Args:
            tool_names: List of tool names that should pause the spinner
        """
        self._interactive_tools.update(tool_names)

    def remove_interactive_tools(self, tool_names: List[str]) -> None:
        """
        Remove tools from the interactive set.
        
        Args:
            tool_names: List of tool names to remove
        """
        self._interactive_tools -= set(tool_names)

    def cancel(self) -> None:
        """Cancel event consumption."""
        self._running = False

    @property
    def is_running(self) -> bool:
        """Check if event consumer is running."""
        return self._running
