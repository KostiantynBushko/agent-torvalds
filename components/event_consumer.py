"""
Event Consumer Component

Consumes workflow events from the LlamaIndex agent in real-time. Routes
events to appropriate handlers, manages spinner state, updates UI with
progress, and tracks tool calls and results.

Usage:
    consumer = EventConsumer(
        spinner_controller=spinner_controller,
        state_handler=state_handler,
        console=console,
    )
    
    handler = agent.run(cmd, ...)
    result = await consumer.consume_events(handler, cmd)
"""
import asyncio
from typing import Any, Callable, Dict, List, Optional, Set

from rich.console import Console

from components.spinner_controller import SpinnerController
from components.state_handler import StateHandler

# Import LlamaIndex event types
try:
    from llama_index.core.workflow import Event, StopEvent
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
    """

    def __init__(
        self,
        spinner_controller: SpinnerController,
        state_handler: StateHandler,
        console: Console,
        interactive_tools: Optional[Set[str]] = None,
        verbose: bool = False,
    ):
        self.spinner = spinner_controller
        self.state = state_handler
        self.console = console
        self._interactive_tools = interactive_tools or DEFAULT_INTERACTIVE_TOOLS
        self._verbose = verbose
        self._event_handlers: Dict[str, Callable] = {}
        self._running = False
        self._tool_calls_paused_spinner: Set[str] = set()

    async def consume_events(
        self,
        handler: Any,
        user_msg: str,
    ) -> Any:
        """
        Consume events from workflow handler.
        
        Args:
            handler: WorkflowHandler from agent.run()
            user_msg: Original user message
            
        Returns:
            Final result from the workflow
        """
        self._running = True
        self.state.set("current_user_msg", user_msg)
        self.state.set("workflow_running", True)
        self.state.set("start_time", asyncio.get_event_loop().time())
        
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
        elif self._verbose and event_type not in VERBOSE_IGNORE_EVENTS:
            # Log other events in verbose mode (excluding high-frequency ones)
            self.console.print(f"[dim]Event: {event_type}[/dim]")

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
