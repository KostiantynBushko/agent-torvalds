"""
Event Consumer Component

Consumes workflow events from the LlamaIndex agent in real-time. Routes
events to appropriate handlers, manages spinner state, updates UI with
progress, and tracks tool calls and results.

Now includes HITL (Human-in-the-Loop) support:
- Handles InputRequiredEvent from LlamaIndex workflows
- Handles AgentQuestionEvent raised by components.hitl_agent.HITLFunctionAgent
- Pauses/resumes spinner during human prompts
- Sends AgentAnswerEvent (a HumanResponseEvent) back to the workflow, which
  resumes the step that is waiting for the human
- Integrates with runtime toggle for dynamic HITL enable/disable

This consumer is the *single* place where the user is prompted.  The
question reaches it through the workflow event stream (the framework writes
an InputRequiredEvent to the stream when a step waits for human input) and
the answer travels back through ctx.send_event(), which dispatches it to the
waiting step.

Usage:
    consumer = EventConsumer(
        spinner_controller=spinner_controller,
        state_handler=state_handler,
        console=console,
        hitl_timeout=-1,   # -1 means "no timeout": wait for the human
        hitl_default_answer="",
    )
    
    handler = agent.run(cmd, ...)
    result = await consumer.consume_events(handler, cmd, hitl_toggle=hitl_toggle)
"""
import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional, Set

from rich.console import Console
from rich.markup import escape

from components.spinner_controller import SpinnerController
from components.state_handler import StateHandler
from components.console_input_module import ConsoleInputModule
from components.hitl_timeout import NO_TIMEOUT, describe_timeout

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
    from llama_index.core.agent.workflow.workflow_events import AgentWorkflowStartEvent
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


# Import custom HITL events.  They subclass the framework events
# (InputRequiredEvent / HumanResponseEvent) so the workflows runtime
# publishes the question to the event stream and routes the answer back to
# the step that is waiting for it.
try:
    from components.hitl_events import AgentQuestionEvent, AgentAnswerEvent
    CUSTOM_HITL_EVENTS_AVAILABLE = True
except ImportError:
    CUSTOM_HITL_EVENTS_AVAILABLE = False
    # Fallback dummy classes for custom HITL events
    class AgentQuestionEvent(InputRequiredEvent):
        def __init__(self, question="", question_id="", timeout=30, default_answer="", input_type="text", options=None, context=None, prefix=""):
            super().__init__(prefix=prefix)
            self.question = question
            self.question_id = question_id
            self.timeout = timeout
            self.default_answer = default_answer
            self.input_type = input_type
            self.options = options or []
            self.context = context

    class AgentAnswerEvent(HumanResponseEvent):
        def __init__(self, question_id="", answer="", was_timeout=False, response=None):
            super().__init__(response=answer if response is None else response)
            self.question_id = question_id
            self.answer = answer
            self.was_timeout = was_timeout


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


def _normalise_yes_no(response: str) -> str:
    """Normalise a yes/no answer, keeping anything that is not one.

    "y" and "yes" become "yes", "n" and "no" become "no" — and every
    other answer is passed through unchanged, so "yes, go ahead" reaches
    the agent as the operator typed it.
    """
    text = response.strip()
    lowered = text.lower()
    if lowered in ("y", "yes"):
        return "yes"
    if lowered in ("n", "no"):
        return "no"
    return text


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
        hitl_timeout: Timeout in seconds for HITL prompts.  ``-1`` means
            *no timeout*: the agent waits for the human indefinitely.
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
        hitl_timeout: int = NO_TIMEOUT,
        hitl_default_answer: str = "",
        hitl_enabled: bool = True,
        stats_handler: Optional[Any] = None,
        human_loop_handler: Optional[Any] = None,
    ):
        logger.debug(
            "EventConsumer.__init__: spinner=%r, state=%r, verbose=%s, "
            "hitl_timeout=%s, hitl_default_answer=%r, hitl_enabled=%s",
            spinner_controller, state_handler, verbose,
            describe_timeout(hitl_timeout), hitl_default_answer, hitl_enabled,
        )
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
        
        # Per-request stats handler. LlamaIndex never emits
        # CBEventType.FUNCTION_CALL, so tool call counts are sourced from the
        # workflow event stream and fed into the handler from here.
        self.stats_handler = stats_handler

        # Optional HITL handler, used to record the question/answer history.
        self.human_loop_handler = human_loop_handler
        
        # Runtime toggle (set during consume_events or via setter)
        self.runtime_toggle = None
        
        # HITL state tracking
        self._hitl_question_count = 0
        self._hitl_timeout_count = 0
        
        # Current workflow handler reference
        self._current_handler = None
        
        logger.debug("EventConsumer.__init__: initialized successfully")

    def set_runtime_toggle(self, toggle: Any) -> None:
        """Set the runtime toggle for dynamic HITL control.
        
        Args:
            toggle: HITLRuntimeToggle instance or None to disable.
        """
        logger.debug("EventConsumer.set_runtime_toggle: toggle=%r", toggle)
        self.runtime_toggle = toggle

    def set_human_loop_handler(self, human_loop_handler: Optional[Any]) -> None:
        """Attach (or clear) the HITL handler used for question history.

        Args:
            human_loop_handler: HumanLoopHandler instance or None to disable.
        """
        logger.debug(
            "EventConsumer.set_human_loop_handler: human_loop_handler=%r",
            human_loop_handler,
        )
        self.human_loop_handler = human_loop_handler

    def set_stats_handler(self, stats_handler: Optional[Any]) -> None:
        """Attach (or clear) the per-request stats handler.
        
        The event consumer is shared across requests, but the stats handler
        is created per request, so it is re-pointed before every run.
        
        Args:
            stats_handler: RequestStatsHandler instance or None to disable.
        """
        logger.debug("EventConsumer.set_stats_handler: stats_handler=%r", stats_handler)
        self.stats_handler = stats_handler

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
        logger.debug(
            "EventConsumer.consume_events: handler=%r, user_msg=%r, hitl_toggle=%r",
            handler, user_msg, hitl_toggle,
        )
        self._running = True
        self.state.set("current_user_msg", user_msg)
        self.state.set("workflow_running", True)
        self.state.set("start_time", asyncio.get_event_loop().time())
        
        # Store reference to handler for event emission
        self._current_handler = handler
        
        # Set runtime toggle if provided
        if hitl_toggle is not None:
            self.runtime_toggle = hitl_toggle
            logger.debug("EventConsumer.consume_events: runtime_toggle set")
        
        try:
            async for event in handler.stream_events():
                if not self._running:
                    logger.debug("EventConsumer.consume_events: stopped (_running=False)")
                    break
                
                # Route event to appropriate handler
                event_type = type(event).__name__
                logger.debug("EventConsumer.consume_events: received event=%s", event_type)
                await self._handle_event(event)
            
            # Get final result
            logger.debug("EventConsumer.consume_events: getting final result from handler")
            result = await handler
            
            # Mark workflow as completed
            self.state.set("workflow_running", False)
            self.state.set("end_time", asyncio.get_event_loop().time())
            
            logger.debug("EventConsumer.consume_events: workflow completed successfully")
            return result
            
        except asyncio.CancelledError:
            logger.debug("EventConsumer.consume_events: CancelledError caught")
            self.state.set("workflow_running", False)
            self.state.add_error("Workflow was cancelled")
            raise
        except Exception as e:
            logger.error("EventConsumer.consume_events: exception: %s", e, exc_info=True)
            self.state.set("workflow_running", False)
            self.state.add_error(str(e))
            raise
        finally:
            self._running = False
            self._current_handler = None
            # Resume spinner if it was paused by any tool
            if self.spinner.is_paused:
                logger.debug("EventConsumer.consume_events: resuming paused spinner in finally")
                self.spinner.resume()

    async def _handle_event(self, event: Event) -> None:
        """Route event to specific handler."""
        event_type = type(event).__name__
        logger.debug("EventConsumer._handle_event: routing event=%s", event_type)
        
        # Handle custom callbacks if registered
        if event_type in self._event_handlers:
            handler = self._event_handlers[event_type]
            logger.debug("EventConsumer._handle_event: calling custom callback for %s", event_type)
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)
        
        # Route to built-in handlers
        if isinstance(event, AgentWorkflowStartEvent):
            logger.debug("EventConsumer._handle_event: dispatching _on_agent_workflow_start")
            await self._on_agent_workflow_start(event)
        elif isinstance(event, AgentInput):
            logger.debug("EventConsumer._handle_event: dispatching _on_agent_input")
            await self._on_agent_input(event)
        elif isinstance(event, AgentSetup):
            logger.debug("EventConsumer._handle_event: dispatching _on_agent_setup")
            await self._on_agent_setup(event)
        elif isinstance(event, AgentStream):
            logger.debug("EventConsumer._handle_event: dispatching _on_agent_stream")
            await self._on_agent_stream(event)
        elif isinstance(event, ToolCall):
            logger.debug("EventConsumer._handle_event: dispatching _on_tool_call")
            await self._on_tool_call(event)
        elif isinstance(event, ToolCallResult):
            logger.debug("EventConsumer._handle_event: dispatching _on_tool_call_result")
            await self._on_tool_call_result(event)
        elif isinstance(event, AgentOutput):
            logger.debug("EventConsumer._handle_event: dispatching _on_agent_output")
            await self._on_agent_output(event)
        elif isinstance(event, StopEvent):
            logger.debug("EventConsumer._handle_event: dispatching _on_stop_event")
            await self._on_stop_event(event)
        elif isinstance(event, AgentQuestionEvent):
            # AgentQuestionEvent extends InputRequiredEvent, so it must be
            # checked *before* the generic InputRequiredEvent branch.
            logger.debug("EventConsumer._handle_event: dispatching _on_agent_question")
            await self._on_agent_question(event)
        elif isinstance(event, AgentAnswerEvent):
            # AgentAnswerEvent extends HumanResponseEvent, so it must be
            # checked *before* the generic HumanResponseEvent branch.
            logger.debug("EventConsumer._handle_event: dispatching _on_agent_answer")
            await self._on_agent_answer(event)
        elif isinstance(event, InputRequiredEvent):
            logger.debug("EventConsumer._handle_event: dispatching _on_input_required")
            await self._on_input_required(event)
        elif isinstance(event, HumanResponseEvent):
            logger.debug("EventConsumer._handle_event: dispatching _on_human_response")
            await self._on_human_response(event)
        elif self._verbose and event_type not in VERBOSE_IGNORE_EVENTS:
            # Log other events in verbose mode (excluding high-frequency ones)
            logger.debug("EventConsumer._handle_event: verbose log for unhandled event=%s", event_type)
            self.console.print(f"[dim]Event: {event_type}[/dim]")
        else:
            logger.debug("EventConsumer._handle_event: no handler for event=%s (ignored)", event_type)

    def _is_hitl_enabled(self) -> bool:
        """Check if HITL is currently enabled (considering runtime toggle).
        
        Returns:
            True if HITL is enabled, False otherwise.
        """
        if self.runtime_toggle is not None:
            result = self.hitl_enabled and self.runtime_toggle.is_enabled
            logger.debug("EventConsumer._is_hitl_enabled: runtime_toggle active, result=%s", result)
            return result
        logger.debug("EventConsumer._is_hitl_enabled: no runtime_toggle, result=%s", self.hitl_enabled)
        return self.hitl_enabled

    # ------------------------------------------------------------------
    # Built-in Event Handlers
    # ------------------------------------------------------------------

    async def _on_agent_workflow_start(self, event: AgentWorkflowStartEvent) -> None:
        """Handle agent workflow start event."""
        logger.debug("EventConsumer._on_agent_workflow_start: workflow starting")
        self.state.set("workflow_started", True)
        self.state.set("workflow_start_time", asyncio.get_event_loop().time())

    async def _on_agent_input(self, event: AgentInput) -> None:
        """Handle agent input event."""
        logger.debug("EventConsumer._on_agent_input: received agent input")
        input_val = getattr(event, 'input', None)
        logger.debug("EventConsumer._on_agent_input: input=%r", input_val)
        if input_val is not None:
            self.state.set("agent_input", str(input_val))

    async def _on_agent_setup(self, event: AgentSetup) -> None:
        """Handle agent setup event."""
        logger.debug("EventConsumer._on_agent_setup: agent setup received")

    async def _on_agent_stream(self, event: AgentStream) -> None:
        """Handle streaming token event."""
        logger.debug("EventConsumer._on_agent_stream: delta=%r", event.delta)
        if event.delta:
            # Could print streaming tokens here if desired
            # For now, just track in state
            pass

    async def _on_tool_call(self, event: ToolCall) -> None:
        """Handle tool call event."""
        tool_name = event.tool_name
        logger.debug("EventConsumer._on_tool_call: tool_name=%s, tool_id=%s, kwargs=%r",
                     tool_name, event.tool_id, event.tool_kwargs)
        
        # Update state
        self.state.set("current_tool", tool_name)
        self.state.increment("tool_calls")
        
        # Feed the stats handler: LlamaIndex never emits
        # CBEventType.FUNCTION_CALL, so the workflow event stream is the only
        # source of tool-call truth.
        if self.stats_handler is not None:
            try:
                # Pass the tool_id: the workflow runs tool calls concurrently,
                # so the id keeps concurrent calls to the same tool apart.
                self.stats_handler.begin_tool_call(tool_name, tool_id=event.tool_id)
            except Exception as exc:
                logger.warning("EventConsumer._on_tool_call: stats handler error: %s", exc)
        
        # Pause spinner for interactive tools
        if tool_name in self._interactive_tools:
            logger.debug("EventConsumer._on_tool_call: pausing spinner for interactive tool=%s", tool_name)
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
                    logger.debug("EventConsumer._on_tool_call: shell command=%s", cmd)
                    self.console.print(f"   [dim]Command: {cmd}[/dim]")
        else:
            logger.debug("EventConsumer._on_tool_call: non-interactive tool=%s, spinner not paused", tool_name)

    async def _on_tool_call_result(self, event: ToolCallResult) -> None:
        """Handle tool call result event."""
        tool_name = event.tool_name
        logger.debug("EventConsumer._on_tool_call_result: tool_name=%s, tool_id=%s",
                     tool_name, event.tool_id)
        
        # Resume spinner after interactive tool execution
        if tool_name in self._interactive_tools:
            logger.debug("EventConsumer._on_tool_call_result: resuming spinner after interactive tool=%s", tool_name)
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
        
        logger.debug("EventConsumer._on_tool_call_result: is_error=%s, result_content_len=%d",
                     is_error, len(result_content))
        self.state.add_tool_call(tool_name, result_content, error=is_error)
        
        # Close out the tool call in the stats handler.
        if self.stats_handler is not None:
            try:
                self.stats_handler.end_tool_call(
                    tool_name,
                    succeeded=not is_error,
                    error_message=(result_content[:200] if is_error else ""),
                    tool_id=event.tool_id,
                )
            except Exception as exc:
                logger.warning("EventConsumer._on_tool_call_result: stats handler error: %s", exc)
        
        # Show result in verbose mode
        if self._verbose and not is_error:
            logger.debug("EventConsumer._on_tool_call_result: verbose success message for %s", tool_name)
            self.console.print(
                f"[green]✅ Tool completed: {tool_name}[/green]"
            )
        elif is_error:
            logger.warning("EventConsumer._on_tool_call_result: error in tool=%s", tool_name)

    async def _on_stop_event(self, event: StopEvent) -> None:
        """Handle workflow completion event."""
        logger.debug("EventConsumer._on_stop_event: workflow stopping, result=%r", event.result)
        self.state.set("workflow_running", False)

    async def _on_agent_output(self, event: AgentOutput) -> None:
        """Handle agent output event."""
        logger.debug("EventConsumer._on_agent_output: received agent output")
        output_val = getattr(event, 'output', None)
        logger.debug("EventConsumer._on_agent_output: output=%r", output_val)

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
        logger.debug("EventConsumer._on_input_required: handling InputRequiredEvent")
        
        if not self._is_hitl_enabled():
            logger.debug("EventConsumer._on_input_required: HITL disabled, skipping")
            return
        
        self._hitl_question_count += 1
        logger.debug("EventConsumer._on_input_required: question_count=%d", self._hitl_question_count)
        
        # Pause spinner
        self.spinner.pause()
        self.state.set("workflow_paused", True)
        logger.debug("EventConsumer._on_input_required: spinner paused, workflow paused")
        
        # Extract question text
        question = getattr(event, 'prefix', 'Please respond: ')
        logger.debug("EventConsumer._on_input_required: question=%r", question)
        
        # Display question
        self.console.print(
            f"\n[magenta]🤖 Agent asks: {question}[/magenta]"
        )
        
        try:
            # Get user input with timeout
            logger.debug(
                "EventConsumer._on_input_required: waiting for user input (timeout=%s)",
                describe_timeout(self.hitl_timeout),
            )
            response = await self.console_input.prompt(
                message="Your response: ",
                default=self.hitl_default_answer,
                timeout=self.hitl_timeout,
            )
            logger.debug("EventConsumer._on_input_required: received response=%r", response)
            
            # Check if it was a timeout (empty response when default is empty)
            if response == self.hitl_default_answer and not response.strip():
                self._hitl_timeout_count += 1
                logger.debug("EventConsumer._on_input_required: timeout detected, timeout_count=%d", self._hitl_timeout_count)
                self.console.print(
                    f"[yellow]⏱️  Timeout — using default answer[/yellow]"
                )
            else:
                logger.debug("EventConsumer._on_input_required: valid response received")
                self.console.print("[green]✅ Response sent to agent[/green]")
            
            # Send response back to workflow
            # Note: We emit the event back into the workflow via the handler
            # This requires access to the workflow's event emitter
            if hasattr(self, '_current_handler') and self._current_handler:
                logger.debug("EventConsumer._on_input_required: sending HumanResponseEvent to workflow")
                self._current_handler.ctx.send_event(
                    HumanResponseEvent(
                        response=response,
                        user_name=getattr(event, 'user_name', None),
                    )
                )
            else:
                logger.warning("EventConsumer._on_input_required: no current handler to send response")
            
        except asyncio.TimeoutError:
            self._hitl_timeout_count += 1
            logger.debug("EventConsumer._on_input_required: TimeoutError, timeout_count=%d", self._hitl_timeout_count)
            self.console.print(
                f"[yellow]⏱️  Timeout — using default: '{self.hitl_default_answer}'[/yellow]"
            )
            # Send default response
            if hasattr(self, '_current_handler') and self._current_handler:
                logger.debug("EventConsumer._on_input_required: sending default HumanResponseEvent")
                self._current_handler.ctx.send_event(
                    HumanResponseEvent(
                        response=self.hitl_default_answer,
                        user_name=getattr(event, 'user_name', None),
                    )
                )
        except Exception as e:
            logger.error("EventConsumer._on_input_required: error handling event: %s", e, exc_info=True)
            self.console.print(
                f"[red]⚠️  Error collecting response: {e}[/red]"
            )
        finally:
            # Resume spinner
            logger.debug("EventConsumer._on_input_required: resuming spinner in finally")
            self.spinner.resume()
            self.state.set("workflow_paused", False)

    async def _on_human_response(self, event: HumanResponseEvent) -> None:
        """Handle HumanResponseEvent — human response received.
        
        Args:
            event: HumanResponseEvent containing the response.
        """
        logger.debug("EventConsumer._on_human_response: response=%r, user_name=%r",
                     event.response, getattr(event, 'user_name', None))
        self.state.set("last_human_response", event.response)

    async def _on_agent_question(self, event: AgentQuestionEvent) -> None:
        """Handle AgentQuestionEvent — the agent needs human input.

        This is the *single* place where the user is prompted.  The event
        arrives on the workflow event stream because the agent step used
        ``ctx.wait_for_event(..., waiter_event=AgentQuestionEvent(...))``;
        the framework publishes the waiter event to the stream and suspends
        the step.  The answer is sent back with ``ctx.send_event()``, which
        dispatches it to the waiting step and resumes the agent.

        Args:
            event: AgentQuestionEvent with question details.
        """
        logger.debug(
            "EventConsumer._on_agent_question: question_id=%s, question=%r, "
            "input_type=%s, timeout=%d",
            event.question_id, event.question, event.input_type, event.timeout,
        )

        if not self._is_hitl_enabled():
            logger.debug("EventConsumer._on_agent_question: HITL disabled, skipping")
            return

        self._hitl_question_count += 1
        logger.debug("EventConsumer._on_agent_question: question_count=%d", self._hitl_question_count)

        # Pause spinner
        self.spinner.pause()
        self.state.set("workflow_paused", True)
        logger.debug("EventConsumer._on_agent_question: spinner paused")

        # Display the question — exactly once.  The input module only ever
        # gets a short prompt, so the question cannot reach the terminal a
        # second time (investigation defect D3).
        self._render_question(event)

        answer = ""
        was_timeout = False
        try:
            answer, was_timeout = await self._collect_answer(event)

            if was_timeout:
                self._hitl_timeout_count += 1
                logger.debug(
                    "EventConsumer._on_agent_question: timeout, timeout_count=%d",
                    self._hitl_timeout_count,
                )
                self.console.print(
                    "[yellow]⏱️  Timeout — using default answer[/yellow]"
                )
            else:
                logger.debug("EventConsumer._on_agent_question: valid response")
                self.console.print("[green]✅ Response sent to agent[/green]")

        except Exception as e:
            logger.error("EventConsumer._on_agent_question: error: %s", e, exc_info=True)
            self.console.print(
                f"[red]⚠️  Error collecting response: {e}[/red]"
            )
            answer = event.default_answer
            was_timeout = True

        # Record the answer for the HITL history.
        self._record_answer(
            event.question_id,
            answer,
            was_timeout,
            question=getattr(event, "question", ""),
            timeout=getattr(event, "timeout", None),
            default_answer=getattr(event, "default_answer", ""),
        )

        # Send the answer back into the workflow.  The waiting step accepts
        # AgentAnswerEvent, so the runtime resolves the waiter and replays
        # the step with the answer.
        self._send_answer(event, answer, was_timeout)

        # Resume spinner
        logger.debug("EventConsumer._on_agent_question: resuming spinner in finally")
        self.spinner.resume()
        self.state.set("workflow_paused", False)

    def _render_question(self, event: AgentQuestionEvent) -> None:
        """Render the question and its context — once.

        The report around the question is printed first and the question
        last, so the operator reads the context and then the thing they
        have to answer.  Nothing but whitespace separates the two: the
        message reaches the terminal as the one block the agent wrote.
        """
        question = getattr(event, "question", "") or ""
        context = getattr(event, "context", "") or ""

        self.console.print("\n[magenta]🤖 Agent asks:[/magenta]")
        if context:
            self.console.print(f"[dim]{escape(context)}[/dim]")
        if question:
            self.console.print(f"[magenta]{escape(question)}[/magenta]")

    def _renders_question(self) -> bool:
        """Return ``True`` when the input module renders the question itself.

        The console input module does not: the consumer already printed the
        question, so the module only shows the short prompt.  A widget that
        owns its own layout — the whiptail dialog, the TUI command bar —
        asks for the question with ``renders_question = True``.
        """
        return bool(getattr(self.console_input, "renders_question", False))

    def _prompt_text(self, event: AgentQuestionEvent, short: str) -> str:
        """Return the prompt the input module should show."""
        if self._renders_question():
            question = (getattr(event, "question", "") or "").strip()
            return f"{question} {short}".strip() if question else short
        return short

    async def _confirm(
        self, message: str, default_yes: bool, timeout: int
    ) -> tuple[str, bool]:
        """Ask a yes/no question and return the answer.

        The operator's own words are preserved: "yes, go ahead" reaches the
        agent as it was typed, and only the canonical "y"/"n" are
        normalised.  An empty answer is a timeout, not a "no"
        (investigation defect D6).

        The input module is asked for the raw answer when it can provide
        one; a module that only offers a yes/no widget answers with a
        boolean.

        Returns:
            ``(answer, was_timeout)`` tuple.
        """
        prompt_with_status = getattr(self.console_input, "prompt_with_status", None)
        if prompt_with_status is not None:
            response, was_timeout = await prompt_with_status(
                message=message, default="", timeout=timeout
            )
        else:
            confirm_with_status = getattr(
                self.console_input, "confirm_with_status", None
            )
            if confirm_with_status is not None:
                confirmed, was_timeout = await confirm_with_status(
                    message=message, default_yes=default_yes, timeout=timeout
                )
                return ("yes" if confirmed else "no"), was_timeout
            if hasattr(self.console_input, "prompt"):
                response = await self.console_input.prompt(
                    message=message, default="", timeout=timeout
                )
                was_timeout = not response.strip()
            else:
                confirmed = await self.console_input.confirm(
                    message=message, default_yes=default_yes, timeout=timeout
                )
                return ("yes" if confirmed else "no"), False

        if was_timeout or not response.strip():
            return "", True
        return _normalise_yes_no(response), False

    async def _menu(
        self, message: str, options: List[str], timeout: int
    ) -> tuple[str, bool]:
        """Show a menu and report whether the human answered."""
        menu_with_status = getattr(self.console_input, "menu_with_status", None)
        if menu_with_status is not None:
            return await menu_with_status(
                message=message, options=options, timeout=timeout
            )
        selected = await self.console_input.menu(
            message=message, options=options, timeout=timeout
        )
        return selected, False

    async def _collect_answer(
        self, event: AgentQuestionEvent
    ) -> tuple[str, bool]:
        """Collect the human's answer for *event*.

        The input module never receives the question text — it gets a short
        prompt.  The question itself was rendered by
        :meth:`_render_question`.

        Returns:
            ``(answer, was_timeout)`` tuple.
        """
        input_type = getattr(event, "input_type", "text")
        default_answer = getattr(event, "default_answer", "")
        timeout = getattr(event, "timeout", self.hitl_timeout)

        if input_type == "yesno":
            default_yes = default_answer.strip().lower() in ("yes", "y", "true", "1")
            answer, was_timeout = await self._confirm(
                message=self._prompt_text(
                    event, "[Y/n]" if default_yes else "[y/N]"
                ),
                default_yes=default_yes,
                timeout=timeout,
            )
            if was_timeout:
                return default_answer, True
            return answer, False

        if input_type == "menu":
            options = list(getattr(event, "options", []) or [])
            if options and hasattr(self.console_input, "menu"):
                selected, was_timeout = await self._menu(
                    message=self._prompt_text(event, "Select option [1]: "),
                    options=options,
                    timeout=timeout,
                )
                if was_timeout:
                    return default_answer, True
                return (selected, False)

        if input_type == "password":
            result = await self.console_input.password(
                message=self._prompt_text(event, "Enter password: "),
                timeout=timeout,
            )
            return (result, not result)

        # ``prompt_with_status`` reports a timeout explicitly, so "the user
        # typed the default answer" and "the user did not answer" can be
        # told apart.  Older/custom input modules only offer ``prompt()``;
        # they are used as a fallback.
        prompt_with_status = getattr(self.console_input, "prompt_with_status", None)
        if prompt_with_status is not None:
            response, was_timeout = await prompt_with_status(
                message=self._prompt_text(event, "Your response: "),
                default=default_answer,
                timeout=timeout,
            )
            if was_timeout:
                response = default_answer
            return (response, was_timeout)

        response = await self.console_input.prompt(
            message=self._prompt_text(event, "Your response: "),
            default=default_answer,
            timeout=timeout,
        )
        # An empty answer means the user did not respond.
        was_timeout = not response.strip()
        if was_timeout:
            response = default_answer
        return (response, was_timeout)

    def _send_answer(
        self,
        event: AgentQuestionEvent,
        answer: str,
        was_timeout: bool,
    ) -> None:
        """Send the human's answer back to the waiting workflow step."""
        if not self._current_handler:
            logger.warning("EventConsumer._on_agent_question: no current handler to send answer")
            return

        logger.debug("EventConsumer._on_agent_question: sending AgentAnswerEvent")
        self._current_handler.ctx.send_event(
            AgentAnswerEvent(
                question_id=event.question_id,
                answer=answer,
                was_timeout=was_timeout,
            )
        )

    def _record_answer(
        self,
        question_id: str,
        answer: str,
        was_timeout: bool,
        question: str = "",
        timeout: Optional[int] = None,
        default_answer: str = "",
    ) -> None:
        """Forward the answer to the HITL history handler (if attached)."""
        handler = getattr(self, "human_loop_handler", None)
        if handler is None:
            return
        try:
            handler.record_answer(
                question_id,
                answer,
                was_timeout=was_timeout,
                question=question,
                timeout=timeout,
                default_answer=default_answer,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("EventConsumer._record_answer: handler error: %s", exc)

    async def _on_agent_answer(self, event: AgentAnswerEvent) -> None:
        """Handle AgentAnswerEvent — answer received for a HITL question.
        
        Args:
            event: AgentAnswerEvent with the answer.
        """
        logger.debug(
            "EventConsumer._on_agent_answer: question_id=%s, answer=%r, was_timeout=%s",
            event.question_id, event.answer, event.was_timeout,
        )
        self.state.set("last_agent_answer", event.answer)
        self.state.set("last_answer_question_id", event.question_id)

    async def send_event(self, event: Event) -> None:
        """Send an event to the current workflow handler.
        
        This method allows external handlers (like HumanLoopHandler) to
        emit events into the workflow.
        
        Args:
            event: Event to send.
        """
        event_type = type(event).__name__
        logger.debug("EventConsumer.send_event: event_type=%s", event_type)
        if hasattr(self, '_current_handler') and self._current_handler:
            self._current_handler.ctx.send_event(event)
            logger.debug("EventConsumer.send_event: event sent successfully")
        else:
            logger.warning("EventConsumer.send_event: no active handler to send event to")

    # ------------------------------------------------------------------
    # HITL State Accessors
    # ------------------------------------------------------------------

    def get_hitl_stats(self) -> Dict[str, Any]:
        """Get HITL statistics.
        
        Returns:
            Dict with HITL question and timeout counts.
        """
        logger.debug("EventConsumer.get_hitl_stats: called")
        stats = {
            "enabled": self._is_hitl_enabled(),
            "question_count": self._hitl_question_count,
            "timeout_count": self._hitl_timeout_count,
            "timeout": self.hitl_timeout,
            "default_answer": self.hitl_default_answer,
        }
        logger.debug("EventConsumer.get_hitl_stats: stats=%r", stats)
        return stats

    def reset_hitl_stats(self) -> None:
        """Reset HITL statistics."""
        logger.debug("EventConsumer.reset_hitl_stats: resetting counters")
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
        logger.debug("EventConsumer.register_callback: event_type=%s, callback=%r", event_type, callback)
        self._event_handlers[event_type] = callback

    def add_interactive_tools(self, tool_names: List[str]) -> None:
        """
        Add tools to the interactive set (will pause spinner).
        
        Args:
            tool_names: List of tool names that should pause the spinner
        """
        logger.debug("EventConsumer.add_interactive_tools: adding %s", tool_names)
        self._interactive_tools.update(tool_names)

    def remove_interactive_tools(self, tool_names: List[str]) -> None:
        """
        Remove tools from the interactive set.
        
        Args:
            tool_names: List of tool names to remove
        """
        logger.debug("EventConsumer.remove_interactive_tools: removing %s", tool_names)
        self._interactive_tools -= set(tool_names)

    def cancel(self) -> None:
        """Cancel event consumption."""
        logger.debug("EventConsumer.cancel: stopping event consumption")
        self._running = False

    @property
    def is_running(self) -> bool:
        """Check if event consumer is running."""
        logger.debug("EventConsumer.is_running: %s", self._running)
        return self._running