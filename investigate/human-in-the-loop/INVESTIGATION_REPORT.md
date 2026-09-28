# INVESTIGATION REPORT: Human-in-the-Loop Agent Implementation

**Date:** 2025-01-15  
**Author:** Torvalds AI Agent  
**Repository:** agent-torvalds  
**Branch:** feature/human-in-the-loop  
**Target:** Interactive Agent with Human-in-the-Loop (HITL) capabilities, timeout support, and console/whiptail input modules

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current Architecture Analysis](#current-architecture-analysis)
   - [2.1 Event Streaming System](#21-event-streaming-system)
   - [2.2 Callback Manager & Handlers](#22-callback-manager--handlers)
   - [2.3 Spinner Controller](#23-spinner-controller)
   - [2.4 Whiptail Password Module](#24-whiptail-password-module)
3. [LlamaIndex Workflow HITL Patterns](#llamaindex-workflow-hitl-patterns)
   - [3.1 InputRequiredEvent & HumanResponseEvent](#31-inputrequiredevent--humanresponseevent)
   - [3.2 wait_for_event Mechanism](#32-wait_for_event-mechanism)
   - [3.3 Custom Event Definitions](#33-custom-event-definitions)
   - [3.4 Event Injection via send_event](#34-event-injection-via-send_event)
4. [Gap Analysis](#gap-analysis)
5. [Proposed Architecture](#proposed-architecture)
   - [5.1 HumanLoopHandler Callback](#51-humanloophandler-callback)
   - [5.2 Console Input Module](#52-console-input-module)
   - [5.3 Whiptail Input Module](#53-whiptail-input-module)
   - [5.4 Timeout Logic](#54-timeout-logic)
   - [5.5 Agent Integration](#55-agent-integration)
6. [Implementation Plan](#implementation-plan)
7. [Key Findings](#key-findings)
8. [Recommendations](#recommendations)
9. [References](#references)

---

## Executive Summary

This investigation examines how to implement **Human-in-the-Loop (HITL)** capabilities in the Torvalds AI Agent. The goal is to enable the agent to:

1. **Pause execution** when it needs clarification from the user
2. **Ask questions** via console or whiptail dialog UI
3. **Handle timeouts** with fallback answers if the user doesn't respond
4. **Resume execution** after receiving user input

The current architecture already has:
- ✅ Event streaming via `EventConsumer`
- ✅ Spinner pause/resume via `SpinnerController`
- ✅ State management via `StateHandler`
- ✅ Whiptail password module for dialogs
- ✅ Callback manager infrastructure

**Key Finding**: The LlamaIndex workflow system natively supports HITL patterns via `InputRequiredEvent`/`HumanResponseEvent` and `ctx.wait_for_event()`. We can leverage this without modifying the core agent.

---

## Current Architecture Analysis

### 2.1 Event Streaming System

**Location:** `components/event_consumer.py`

The `EventConsumer` class already provides real-time event consumption from the workflow:

```python
class EventConsumer:
    async def consume_events(self, handler: WorkflowHandler, user_msg: str) -> Any:
        async for event in handler.stream_events():
            await self._handle_event(event)
        result = await handler
        return result
```

**Current Capabilities:**
- Streams events from `handler.stream_events()`
- Routes events to specific handlers (`_on_tool_call`, `_on_tool_call_result`, etc.)
- Pauses/resumes spinner for interactive tools
- Supports custom callbacks via `register_callback()`

**Current Event Handlers:**

| Event Type | Handler | Purpose |
|------------|---------|---------|
| `AgentStream` | `_on_agent_stream` | Streaming tokens |
| `ToolCall` | `_on_tool_call` | Tool invocation |
| `ToolCallResult` | `_on_tool_call_result` | Tool results |
| `StopEvent` | `_on_stop_event` | Workflow completion |
| `AgentOutput` | `_on_agent_output` | Agent output |

**Gap**: No handler for `InputRequiredEvent` (HITL trigger).

### 2.2 Callback Manager & Handlers

**Location:** `llama_index.core.callbacks.base.CallbackManager`

The callback manager provides a way to register handlers for LlamaIndex events:

```python
class CallbackManager(BaseCallbackHandler, ABC):
    """Handles callbacks for events within LlamaIndex."""
    - handlers: List[BaseCallbackHandler]
    - trace_stack: Current stack of events
    - trace_map: Event id to children mapping
    - on_event_start/end: Lifecycle hooks
```

**Current Usage in agent-torvalds.py:**
```python
if enable_stats:
    handler = RequestStatsHandler(request_id=request_id, user_query=cmd)
    callback_manager = CallbackManager([handler])
else:
    callback_manager = CallbackManager([])

workflow_handler = agent.run(
    cmd,
    memory=chat_memory,
    max_iterations=MAX_ITERATIONS,
    callback_manager=callback_manager,
)
```

**Opportunity**: Add a `HumanLoopHandler` to the callback manager to intercept HITL events.

### 2.3 Spinner Controller

**Location:** `components/spinner_controller.py`

Provides pause/resume for the console spinner:

```python
class SpinnerController:
    def start() -> None       # Start spinner
    def stop() -> None        # Stop spinner
    def pause() -> None       # Pause (hide) spinner
    def resume() -> None      # Resume (show) spinner
    @property
    def is_paused -> bool     # Check pause state
```

**Current Usage**: Paused during interactive tool calls (password prompts, package installs).

**Extension Needed**: Pause during HITL prompts.

### 2.4 Whiptail Password Module

**Location:** `components/whiptail_password.py`

Provides whiptail-based terminal dialogs:

```python
class WhiptailPasswordPrompter:
    def prompt_password(message, max_attempts, test_callback) -> Dict[str, Any]
    def show_message(message, title) -> bool
    def confirm(message, title, default_yes) -> bool
    @staticmethod
    def is_available() -> Dict[str, Any]
```

**Existing Functionality:**
- Password dialogs with validation
- Message boxes
- Yes/No confirmations
- Availability checking (binary + Python package)

**Extension Needed**: General input prompt (not just password).

---

## LlamaIndex Workflow HITL Patterns

### 3.1 InputRequiredEvent & HumanResponseEvent

**Location:** `workflows.events`

These are the core HITL event types provided by the workflows library:

#### InputRequiredEvent

```python
class InputRequiredEvent(Event):
    """Emitted when human input is required to proceed.
    
    Automatically written to the event stream if returned from a step.
    If returned from a step, it does not need to be consumed by other steps.
    It's expected that the caller will respond with HumanResponseEvent.
    """
```

**Usage Pattern:**
```python
# A step returns InputRequiredEvent to signal it needs input
@step
async def my_step(self, ev: StartEvent) -> InputRequiredEvent:
    return InputRequiredEvent(prefix="What's your name? ")
```

#### HumanResponseEvent

```python
class HumanResponseEvent(Event):
    """Carries a human's response for a prior input request.
    
    If consumed by a step and not returned by another, it passes validation.
    """
```

**Usage Pattern:**
```python
# Another step consumes HumanResponseEvent to get the answer
@step
async def my_step(self, ev: HumanResponseEvent) -> StopEvent:
    return StopEvent(result=ev.response)
```

**Key Insight**: Both events accept `**params`, so we can add custom fields like `timeout`, `default_value`, `input_type`, etc.

### 3.2 wait_for_event Mechanism

**Location:** `workflows.context.Context.wait_for_event()`

This is the primary mechanism for pausing workflow execution and waiting for external input:

```python
async def wait_for_event(
    self,
    event_type: type[T],
    waiter_event: Event | None = None,      # Event to emit when waiting starts
    waiter_id: str | None = None,           # Unique ID to prevent duplicates
    requirements: dict[str, Any] | None = None,  # Key/value filters
    timeout: float | None = 2000,           # Max seconds to wait (default: 2000)
) -> T:
    """Wait for the next matching event of type event_type."""
```

**Usage Example:**
```python
@step
async def ask_human(self, ctx: Context, ev: StartEvent) -> StopEvent:
    # Wait for human response with 60-second timeout
    response = await ctx.wait_for_event(
        HumanResponseEvent,
        waiter_event=InputRequiredEvent(msg="What's your name?"),
        waiter_id="user_name",
        timeout=60,
    )
    return StopEvent(result=response.response)
```

**How it works:**
1. The step calls `ctx.wait_for_event()`
2. An internal control-flow exception is thrown
3. The workflow pauses and emits the `waiter_event` (e.g., `InputRequiredEvent`)
4. The caller receives the event via the event stream
5. The caller sends back a `HumanResponseEvent` via `ctx.send_event()`
6. The step resumes with the response

**Limitation**: The `FunctionAgent` uses internal steps that we don't control. We can't modify those steps to call `wait_for_event()`.

### 3.3 Custom Event Definitions

We can define custom events for our HITL system:

```python
from workflows.events import Event

class AgentQuestionEvent(Event):
    """Custom event: Agent is asking a question."""
    def __init__(self, question: str, question_id: str, 
                 timeout: int = 30, default_answer: str = "", 
                 input_type: str = "text"):
        super().__init__()
        self.question = question
        self.question_id = question_id
        self.timeout = timeout
        self.default_answer = default_answer
        self.input_type = input_type  # "text", "yesno", "menu"

class AgentAnswerEvent(Event):
    """Custom event: Human answered the agent's question."""
    def __init__(self, question_id: str, answer: str, 
                 was_timeout: bool = False):
        super().__init__()
        self.question_id = question_id
        self.answer = answer
        self.was_timeout = was_timeout
```

### 3.4 Event Injection via send_event

**Location:** `workflows.context.Context.send_event()`

We can inject events into the running workflow from outside:

```python
def send_event(self, message: Event, step: str | None = None) -> None:
    """Dispatch an event to one or all workflow steps.
    
    If step is omitted, the event is broadcast to all step queues.
    When step is provided, the target step must accept the event type.
    """
```

**Usage:**
```python
# From outside the workflow (e.g., in event consumer):
workflow_handler.send_event(HumanResponseEvent(response="yes"))
```

**Key Insight**: The `WorkflowHandler` (returned by `agent.run()`) supports `send_event()` to inject events into the running workflow.

---

## Gap Analysis

### Current vs. Target Capabilities

| Capability | Current | Target | Gap |
|------------|---------|--------|-----|
| Event Streaming | ✅ Implemented | ✅ Real-time feedback | None |
| Spinner Control | ✅ Pause/resume | ✅ Pause during HITL | Medium |
| Whiptail Dialogs | ✅ Password only | ✅ General input | Medium |
| HITL Events | ❌ Not handled | ✅ InputRequiredEvent handler | High |
| Timeout Logic | ❌ Not available | ✅ Auto-fallback | High |
| Custom HITL Events | ❌ Not defined | ✅ AgentQuestion/Answer | High |
| Event Injection | ❌ Not used | ✅ Send HumanResponseEvent | High |
| Callback Handler | ❌ Stats only | ✅ HumanLoopHandler | High |

---

## Proposed Architecture

### 5.1 HumanLoopHandler Callback

A custom callback handler that intercepts when the agent needs human input:

```python
class HumanLoopHandler(BaseCallbackHandler):
    """
    Callback handler for Human-in-the-Loop interactions.
    
    Responsibilities:
    - Detect when agent needs clarification
    - Pause workflow and prompt user
    - Handle timeout with fallback answer
    - Inject response back into workflow
    """
    
    def __init__(
        self,
        input_method: str = "console",  # "console" or "whiptail"
        default_timeout: int = 30,
        console: Console = None,
        spinner: SpinnerController = None,
    ):
        self.input_method = input_method
        self.default_timeout = default_timeout
        self.console = console
        self.spinner = spinner
        self._pending_questions: Dict[str, asyncio.Future] = {}
    
    def on_event_start(self, event: Event, **kwargs):
        """Called when an event starts."""
        if isinstance(event, InputRequiredEvent):
            # Agent needs human input
            asyncio.create_task(self._handle_question(event))
    
    async def _handle_question(self, event: InputRequiredEvent):
        """Handle a question from the agent."""
        question_id = str(uuid.uuid4())[:8]
        
        # Pause spinner
        if self.spinner:
            self.spinner.pause()
        
        # Create future to hold the answer
        future = asyncio.get_event_loop().create_future()
        self._pending_questions[question_id] = future
        
        # Get user input with timeout
        try:
            answer = await asyncio.wait_for(
                self._get_user_input(event),
                timeout=self.default_timeout
            )
            future.set_result(answer)
        except asyncio.TimeoutError:
            future.set_result(self.default_answer)
            self.console.print("[yellow]⏱️ Timeout - using default answer[/yellow]")
        
        # Resume spinner
        if self.spinner:
            self.spinner.resume()
        
        # Inject answer back into workflow
        self._inject_answer(event, answer)
    
    async def _get_user_input(self, event: InputRequiredEvent) -> str:
        """Get user input via console or whiptail."""
        if self.input_method == "whiptail":
            return await WhiptailInputModule.prompt(event.msg)
        else:
            return await ConsoleInputModule.prompt(event.msg)
    
    def _inject_answer(self, event: InputRequiredEvent, answer: str):
        """Inject the answer back into the workflow."""
        # Use HumanResponseEvent
        response = HumanResponseEvent(response=answer)
        # Send to workflow via handler
```

### 5.2 Console Input Module

A module for text-based terminal input with timeout support:

```python
class ConsoleInputModule:
    """Console-based input module for HITL."""
    
    @staticmethod
    async def prompt(message: str, default: str = "", timeout: int = 30) -> str:
        """
        Prompt user for input via console with timeout.
        
        Args:
            message: Question to ask
            default: Default answer if timeout
            timeout: Seconds to wait
            
        Returns:
            User's response or default on timeout
        """
        loop = asyncio.get_event_loop()
        
        # Use asyncio.to_thread for blocking input()
        def ask():
            try:
                return input(message)
            except (EOFError, KeyboardInterrupt):
                return default
        
        try:
            response = await asyncio.wait_for(
                loop.run_in_executor(None, ask),
                timeout=timeout
            )
            return response if response.strip() else default
        except asyncio.TimeoutError:
            return default
    
    @staticmethod
    async def confirm(message: str, default_yes: bool = True, timeout: int = 30) -> bool:
        """
        Ask for yes/no confirmation via console.
        
        Args:
            message: Question to ask
            default_yes: Default answer if timeout
            timeout: Seconds to wait
            
        Returns:
            True if yes, False otherwise
        """
        suffix = " [Y/n]" if default_yes else " [y/N]"
        full_message = f"{message}{suffix}"
        response = await ConsoleInputModule.prompt(full_message, timeout=timeout)
        
        if not response:
            return default_yes
        
        return response.lower() in ("y", "yes")
    
    @staticmethod
    async def menu(message: str, options: List[str], timeout: int = 30) -> str:
        """
        Display a menu and get user selection.
        
        Args:
            message: Menu title
            options: List of option strings
            timeout: Seconds to wait
            
        Returns:
            Selected option or first option on timeout
        """
        print(f"\n{message}")
        for i, opt in enumerate(options, 1):
            print(f"  {i}. {opt}")
        
        default = "1"
        response = await ConsoleInputModule.prompt(
            "Select option [1]: ", default=default, timeout=timeout
        )
        
        try:
            idx = int(response) - 1
            if 0 <= idx < len(options):
                return options[idx]
        except ValueError:
            pass
        
        return options[0]  # Default to first option
```

### 5.3 Whiptail Input Module

A module for whiptail-based terminal dialogs with timeout support:

```python
class WhiptailInputModule:
    """Whiptail-based input module for HITL."""
    
    @staticmethod
    def is_available() -> bool:
        """Check if whiptail is available."""
        return WhiptailPasswordPrompter.is_available()["available"]
    
    @staticmethod
    async def prompt(
        message: str, 
        default: str = "", 
        timeout: int = 30,
        title: str = "Agent Question"
    ) -> str:
        """
        Prompt user for input via whiptail dialog with timeout.
        
        Args:
            message: Question to ask
            default: Default answer if timeout
            timeout: Seconds to wait
            title: Dialog title
            
        Returns:
            User's response or default on timeout
        """
        try:
            from whiptail import Whiptail
            
            wt = Whiptail(
                title=title,
                backtitle="AI Agent requires your input",
                height=10,
                width=60,
                auto_exit=False,
            )
            
            # Use subprocess with timeout
            def ask():
                return wt.prompt(msg=message, default=default, password=False)
            
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                loop.run_in_executor(None, ask),
                timeout=timeout
            )
            return response if response.strip() else default
            
        except asyncio.TimeoutError:
            return default
        except Exception as e:
            print(f"Whiptail error: {e}")
            return default
    
    @staticmethod
    async def confirm(
        message: str,
        default_yes: bool = True,
        timeout: int = 30,
        title: str = "Confirmation"
    ) -> bool:
        """
        Ask for yes/no confirmation via whiptail dialog.
        
        Args:
            message: Question to ask
            default_yes: Default if timeout
            timeout: Seconds to wait
            title: Dialog title
            
        Returns:
            True if yes, False otherwise
        """
        try:
            from whiptail import Whiptail
            
            wt = Whiptail(
                title=title,
                backtitle="AI Agent requires your input",
                height=10,
                width=60,
                auto_exit=False,
            )
            
            def ask():
                extra = ['--defaultno'] if not default_yes else []
                return wt.run(
                    control='yesno',
                    msg=message,
                    extra=extra,
                    exit_on=(1, 255)
                )
            
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(None, ask),
                timeout=timeout
            )
            return result.returncode == 0
            
        except asyncio.TimeoutError:
            return default_yes
        except Exception as e:
            print(f"Whiptail error: {e}")
            return default_yes
    
    @staticmethod
    async def menu(
        message: str,
        options: List[str],
        timeout: int = 30,
        title: str = "Select Option"
    ) -> str:
        """
        Display a menu via whiptail dialog.
        
        Args:
            message: Menu title
            options: List of option descriptions
            timeout: Seconds to wait
            title: Dialog title
            
        Returns:
            Selected option or first option on timeout
        """
        try:
            from whiptail import Whiptail
            
            wt = Whiptail(
                title=title,
                backtitle="AI Agent requires your input",
                height=15,
                width=60,
                auto_exit=False,
            )
            
            # Format items as (tag, description) tuples
            items = [(str(i), opt) for i, opt in enumerate(options, 1)]
            
            def ask():
                return wt.menu(msg=message, items=items)
            
            loop = asyncio.get_event_loop()
            tag = await asyncio.wait_for(
                loop.run_in_executor(None, ask),
                timeout=timeout
            )
            
            try:
                idx = int(tag) - 1
                if 0 <= idx < len(options):
                    return options[idx]
            except ValueError:
                pass
            
            return options[0]  # Default
            
        except asyncio.TimeoutError:
            return options[0]
        except Exception as e:
            print(f"Whiptail error: {e}")
            return options[0]
```

### 5.4 Timeout Logic

The timeout mechanism is critical for ensuring the agent doesn't hang indefinitely:

```python
class TimeoutManager:
    """Manages timeout logic for HITL prompts."""
    
    def __init__(self, default_timeout: int = 30):
        self.default_timeout = default_timeout
        self._timed_out_questions: List[Dict] = []
    
    async def prompt_with_timeout(
        self,
        prompt_fn: Callable,  # Async function to prompt user
        timeout: int = None,
        default_answer: str = "",
        question_id: str = None
    ) -> Tuple[str, bool]:
        """
        Prompt with timeout handling.
        
        Args:
            prompt_fn: Async function that prompts the user
            timeout: Seconds to wait (uses default if None)
            default_answer: Fallback answer on timeout
            question_id: ID for tracking
            
        Returns:
            Tuple of (answer, was_timeout)
        """
        timeout = timeout or self.default_timeout
        
        try:
            answer = await asyncio.wait_for(
                prompt_fn(),
                timeout=timeout
            )
            return answer, False
        except asyncio.TimeoutError:
            # Log the timeout
            self._timed_out_questions.append({
                "question_id": question_id,
                "timeout": timeout,
                "default_answer": default_answer,
                "timestamp": datetime.now().isoformat(),
            })
            return default_answer, True
    
    def get_timeout_log(self) -> List[Dict]:
        """Get log of all timed-out questions."""
        return self._timed_out_questions.copy()
```

### 5.5 Agent Integration

Wire everything into the agent workflow:

```python
# In agent-torvalds.py

# Create HumanLoopHandler
human_loop_handler = HumanLoopHandler(
    input_method=os.environ.get("TORVALDS_HITL_METHOD", "console"),
    default_timeout=int(os.environ.get("TORVALDS_HITL_TIMEOUT", "30")),
    console=console,
    spinner=spinner_controller,
)

# Add to callback manager
callback_manager = CallbackManager([
    RequestStatsHandler(...),  # Existing stats handler
    human_loop_handler,        # New HITL handler
])

# Pass to agent
workflow_handler = agent.run(
    cmd,
    memory=chat_memory,
    max_iterations=MAX_ITERATIONS,
    callback_manager=callback_manager,
)
```

---

## Implementation Plan

### Phase 1: Foundation (Priority: High)

1. **Create Custom HITL Events**
   - Define `AgentQuestionEvent` and `AgentAnswerEvent`
   - Extend `InputRequiredEvent` with custom fields

2. **Create Console Input Module**
   - Implement `ConsoleInputModule` with `prompt()`, `confirm()`, `menu()`
   - Add async timeout support

3. **Create Whiptail Input Module**
   - Implement `WhiptailInputModule` with same interface
   - Reuse existing `WhiptailPasswordPrompter` patterns

### Phase 2: Core HITL Logic (Priority: High)

4. **Implement HumanLoopHandler**
   - Extend `BaseCallbackHandler`
   - Intercept `InputRequiredEvent`
   - Pause spinner during prompts
   - Handle timeout with fallback

5. **Integrate Timeout Manager**
   - Track timed-out questions
   - Log unanswered questions for review

### Phase 3: Agent Integration (Priority: Medium)

6. **Wire into Agent**
   - Add `HumanLoopHandler` to callback manager
   - Configure via environment variables
   - Add CLI flags for HITL settings

7. **Update EventConsumer**
   - Handle `InputRequiredEvent` and `AgentQuestionEvent`
   - Route to appropriate input module

### Phase 4: Testing & Polish (Priority: Medium)

8. **Test HITL Flows**
   - Console input with timeout
   - Whiptail input with timeout
   - Fallback on timeout
   - Resume after input

9. **Documentation**
   - Update README with HITL usage
   - Add examples

---

## Key Findings

### 1. LlamaIndex Native HITL Support
The workflows library provides `InputRequiredEvent` and `HumanResponseEvent` specifically for HITL patterns. These are designed to be used with `ctx.wait_for_event()` for pausing workflow execution.

### 2. Event Stream is Already Available
The current `EventConsumer` already streams events from the workflow. We just need to add handlers for HITL events.

### 3. Callback Manager Can Extend
The `CallbackManager` accepts a list of `BaseCallbackHandler` instances. We can add a `HumanLoopHandler` without modifying existing handlers.

### 4. Timeout Requires Async
Since `input()` is blocking, we need to use `asyncio.wait_for()` with `run_in_executor()` to implement timeout for console input.

### 5. Whiptail Module Exists
The `WhiptailPasswordPrompter` already provides whiptail dialogs. We just need to extend it for general input (not just passwords).

### 6. Spinner Control is Ready
The `SpinnerController` already supports pause/resume. We just need to trigger it during HITL prompts.

### 7. Limitation: FunctionAgent Internal Steps
The `FunctionAgent` uses internal workflow steps that we don't control. We cannot modify those steps to emit `InputRequiredEvent`. **Workaround**: Use callback handlers to intercept LLM responses and inject HITL logic when needed.

---

## Recommendations

### Immediate Actions

1. **Implement HumanLoopHandler** as a callback handler that:
   - Listens for specific event patterns indicating need for human input
   - Pauses the spinner
   - Prompts user via console or whiptail
   - Handles timeout with configurable fallback
   - Resumes spinner after input

2. **Create Input Modules** (`ConsoleInputModule`, `WhiptailInputModule`) with:
   - Async timeout support
   - Common interface (`prompt()`, `confirm()`, `menu()`)
   - Configuration via environment variables

3. **Add Configuration Options**:
   ```bash
   TORVALDS_HITL_ENABLED=true        # Enable/disable HITL
   TORVALDS_HITL_METHOD=console      # "console" or "whiptail"
   TORVALDS_HITL_TIMEOUT=30          # Default timeout in seconds
   TORVALDS_HITL_DEFAULT_ANSWER=""   # Default fallback answer
   ```

### Short-term Enhancements

4. **Smart HITL Triggers**: Detect when the agent is asking a question (via LLM response pattern matching) and automatically trigger HITL flow.

5. **Confirmation Prompts**: For destructive operations (delete, drop, overwrite), automatically prompt for confirmation.

6. **Interactive Menus**: When the agent suggests multiple options, present them as a menu.

### Long-term Vision

7. **Custom Workflow Steps**: Define custom workflow steps that explicitly use `ctx.wait_for_event()` for HITL.

8. **State Persistence**: Save HITL questions and answers to enable resumption across sessions.

9. **Multiple Input Methods**: Support for web UI, chat interfaces, etc.

---

## References

- [LlamaIndex Human in the Loop](https://developers.llamaindex.ai/python/framework/understanding/agent/human_in_the_loop/)
- [LlamaIndex Workflows](https://developers.llamaindex.ai/python/llamaagents/workflows/)
- [Workflows Library Events](.venv/lib/python3.12/site-packages/workflows/events.py)
- [Workflows Context API](.venv/lib/python3.12/site-packages/workflows/context/context.py)
- [Base Agent Source](.venv/lib/python3.12/site-packages/llama_index/core/agent/workflow/base_agent.py)
- [Current Investigation Report](./llama-index-workflow/INVESTIGATION_REPORT.md)
- [Whiptail Investigation Report](./whiptail/INVESTIGATION_REPORT.md)

---

*Generated by Torvalds AI Agent*  
*Date: 2025-01-15*  
*Branch: feature/human-in-the-loop*
