# STEP-BY-STEP PROPOSAL: Human-in-the-Loop Implementation for Torvalds AI Agent

**Date:** 2025-01-15  
**Author:** Torvalds AI Agent  
**Repository:** agent-torvalds  
**Branch:** feature/human-in-the-loop  
**Status:** Proposed  
**Priority:** High  
**Estimated Effort:** 3-4 weeks

---

## Table of Contents

1. [Overview](#overview)
2. [Related Investigations & References](#related-investigations--references)
3. [LlamaIndex HITL Architecture Summary](#llamaindex-hitl-architecture-summary)
4. [Step-by-Step Implementation Plan](#step-by-step-implementation-plan)
   - [Step 1: Foundation - Custom HITL Events](#step-1-foundation---custom-hitl-events)
   - [Step 2: Console Input Module](#step-2-console-input-module)
   - [Step 3: Whiptail Input Module](#step-3-whiptail-input-module)
   - [Step 4: HumanLoopHandler Callback](#step-4-humanloophandler-callback)
   - [Step 5: EventConsumer Integration](#step-5-eventconsumer-integration)
   - [Step 6: Timeout Manager](#step-6-timeout-manager)
   - [Step 7: Runtime Toggle](#step-7-runtime-toggle)
   - [Step 8: Agent Integration](#step-8-agent-integration)
   - [Step 9: Configuration & CLI](#step-9-configuration--cli)
5. [Testing Strategy](#testing-strategy)
6. [Risk Assessment](#risk-assessment)
7. [Success Criteria](#success-criteria)

---

## Overview

This proposal provides a **detailed step-by-step implementation plan** for adding Human-in-the-Loop (HITL) capabilities to the Torvalds AI Agent. The agent will be able to:

1. **Pause execution** when it needs clarification from the user
2. **Ask questions** via console or whiptail dialog UI
3. **Handle timeouts** with fallback answers if the user doesn't respond
4. **Resume execution** after receiving user input

This builds upon the existing infrastructure:
- ✅ Event streaming via `EventConsumer`
- ✅ Spinner pause/resume via `SpinnerController`
- ✅ State management via `StateHandler`
- ✅ Whiptail password module for dialogs
- ✅ Callback manager infrastructure

---

## Related Investigations & References

### Local Investigation Documents

| Document | Location | Description |
|----------|----------|-------------|
| **HITL Investigation Report** | [`investigate/human-in-the-loop/INVESTIGATION_REPORT.md`](./INVESTIGATION_REPORT.md) | Comprehensive gap analysis and architecture proposal |
| **HITL Task Description** | [`investigate/human-in-the-loop/llama-human-in-loop-task.md`](./llama-human-in-loop-task.md) | Original task requirements |
| **Whiptail Investigation** | [`investigate/whiptail/INVESTIGATION_REPORT.md`](../whiptail/INVESTIGATION_REPORT.md) | Whiptail bash vs Python package analysis |
| **LlamaIndex Workflow Investigation** | [`investigate/llama-index-workflow/INVESTIGATION_REPORT.md`](../llama-index-workflow/INVESTIGATION_REPORT.md) | Workflow architecture and event system |
| **Workflow Implementation Proposal** | [`investigate/llama-index-workflow/PROPOSAL_implementation.md`](../llama-index-workflow/PROPOSAL_implementation.md) | EventConsumer, StateHandler, InteractivePromptManager design |

### External References

| Resource | URL | Description |
|----------|-----|-------------|
| **LlamaIndex HITL Docs** | [developers.llamaindex.ai](https://developers.llamaindex.ai/python/framework/understanding/agent/human_in_the_loop/) | Official HITL documentation |
| **LlamaIndex Workflows** | [developers.llamaindex.ai](https://developers.llamaindex.ai/python/llamaagents/workflows/) | Workflow system documentation |
| **Full HITL Example** | [GitHub Example](https://github.com/run-llama/python-agents-tutorial/blob/main/5_human_in_the_loop.py) | Complete working example |

---

## LlamaIndex HITL Architecture Summary

### Core Concepts from LlamaIndex Documentation

The LlamaIndex workflow system natively supports HITL patterns via three key mechanisms:

#### 1. `InputRequiredEvent` - Signals Need for Human Input

```python
from llama_index.core.workflow import InputRequiredEvent, HumanResponseEvent

# Emitted when human input is required
# Automatically written to the event stream if returned from a step
InputRequiredEvent(
    prefix="Are you sure you want to proceed? ",
    user_name="Laurie",  # Custom field for routing
)
```

**Key Properties:**
- Accepts `**params` for custom fields (timeout, default_value, input_type, etc.)
- Automatically written to event stream
- Does NOT need to be consumed by other steps
- Expected that caller will respond with `HumanResponseEvent`

#### 2. `HumanResponseEvent` - Carries Human's Response

```python
# Carries a human's response for a prior input request
HumanResponseEvent(
    response="yes",
    user_name="Laurie",  # Must match requirements filter
)
```

**Key Properties:**
- If consumed by a step and not returned by another, it passes validation
- Used to inject answers back into the workflow

#### 3. `ctx.wait_for_event()` - Pauses Workflow Execution

```python
from llama_index.core.workflow import Context

@step
async def ask_human(self, ctx: Context, ev: StartEvent) -> StopEvent:
    # Wait for human response with 60-second timeout
    response = await ctx.wait_for_event(
        HumanResponseEvent,                    # Event type to wait for
        waiter_event=InputRequiredEvent(       # Event to emit when waiting starts
            msg="What's your name?",
            user_name="Laurie",
        ),
        waiter_id="user_name",                 # Unique ID to prevent duplicates
        requirements={"user_name": "Laurie"},  # Key/value filters
        timeout=60,                            # Max seconds to wait
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

#### 4. `handler.ctx.send_event()` - Inject Events from Outside

```python
# From outside the workflow (e.g., in event consumer):
handler.ctx.send_event(
    HumanResponseEvent(
        response="yes",
        user_name="Laurie",
    )
)
```

**Key Insight:** The `WorkflowHandler` (returned by `agent.run()`) supports `send_event()` to inject events into the running workflow.

### Important Limitation

> **The `FunctionAgent` uses internal workflow steps that we don't control. We cannot modify those steps to emit `InputRequiredEvent` or call `wait_for_event()`.**

**Workaround:** Use callback handlers to intercept LLM responses and inject HITL logic when the agent asks a question or needs clarification.

---

## Step-by-Step Implementation Plan

### Step 1: Foundation - Custom HITL Events

**Goal:** Define custom event classes for our HITL system.

**Files to Create:**
- `components/hitl_events.py`

**Implementation:**

```python
# components/hitl_events.py

from workflows.events import Event
from typing import Optional


class AgentQuestionEvent(Event):
    """Custom event: Agent is asking a question that requires human input.
    
    Fields:
        question: The question to ask the user
        question_id: Unique identifier for this question
        timeout: Seconds to wait for response (default: 30)
        default_answer: Fallback answer if timeout (default: "")
        input_type: Type of input expected ("text", "yesno", "menu", "password")
        options: List of options for menu-type questions
        context: Additional context about why the question is being asked
    """
    def __init__(
        self,
        question: str,
        question_id: str,
        timeout: int = 30,
        default_answer: str = "",
        input_type: str = "text",
        options: Optional[list[str]] = None,
        context: Optional[str] = None,
    ):
        super().__init__()
        self.question = question
        self.question_id = question_id
        self.timeout = timeout
        self.default_answer = default_answer
        self.input_type = input_type
        self.options = options or []
        self.context = context


class AgentAnswerEvent(Event):
    """Custom event: Human answered the agent's question.
    
    Fields:
        question_id: ID of the question being answered
        answer: The user's response
        was_timeout: Whether this was a timeout fallback
    """
    def __init__(
        self,
        question_id: str,
        answer: str,
        was_timeout: bool = False,
    ):
        super().__init__()
        self.question_id = question_id
        self.answer = answer
        self.was_timeout = was_timeout
```

**Deliverables:**
- [ ] Create `AgentQuestionEvent` class
- [ ] Create `AgentAnswerEvent` class
- [ ] Add comprehensive docstrings
- [ ] Add unit tests for event serialization

---

### Step 2: Console Input Module

**Goal:** Provide text-based terminal input with timeout support.

**Files to Create:**
- `components/console_input_module.py`

**Implementation:**

```python
# components/console_input_module.py

import asyncio
from typing import List, Optional
from rich.console import Console


class ConsoleInputModule:
    """Console-based input module for HITL interactions.
    
    Provides async input methods with timeout support.
    All methods return default values on timeout.
    """
    
    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
    
    @staticmethod
    async def prompt(
        message: str,
        default: str = "",
        timeout: int = 30,
    ) -> str:
        """
        Prompt user for text input via console with timeout.
        
        Args:
            message: Question to ask
            default: Default answer if timeout or empty response
            timeout: Seconds to wait for input
            
        Returns:
            User's response or default on timeout/empty
        """
        loop = asyncio.get_event_loop()
        
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
    
    async def confirm(
        self,
        message: str,
        default_yes: bool = True,
        timeout: int = 30,
    ) -> bool:
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
    
    async def menu(
        self,
        message: str,
        options: List[str],
        timeout: int = 30,
    ) -> str:
        """
        Display a menu and get user selection.
        
        Args:
            message: Menu title
            options: List of option strings
            timeout: Seconds to wait
            
        Returns:
            Selected option or first option on timeout
        """
        self.console.print(f"\n{message}")
        for i, opt in enumerate(options, 1):
            self.console.print(f"  [bold]{i}[/bold]. {opt}")
        
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
    
    async def password(
        self,
        message: str = "Enter password: ",
        timeout: int = 60,
    ) -> str:
        """
        Prompt for password input (hidden).
        
        Args:
            message: Prompt message
            timeout: Seconds to wait
            
        Returns:
            Entered password or empty string on timeout
        """
        import getpass
        
        loop = asyncio.get_event_loop()
        
        def ask():
            try:
                return getpass.getpass(message)
            except (EOFError, KeyboardInterrupt):
                return ""
        
        try:
            response = await asyncio.wait_for(
                loop.run_in_executor(None, ask),
                timeout=timeout
            )
            return response
        except asyncio.TimeoutError:
            return ""
```

**Deliverables:**
- [ ] Create `ConsoleInputModule` class
- [ ] Implement `prompt()`, `confirm()`, `menu()`, `password()` methods
- [ ] Add timeout handling with `asyncio.wait_for()`
- [ ] Add unit tests with mocked input

---

### Step 3: Whiptail Input Module

**Goal:** Extend existing Whiptail functionality for general HITL input.

**Files to Create:**
- `components/whiptail_input_module.py`

**Implementation:**

```python
# components/whiptail_input_module.py

import asyncio
from typing import List, Optional
from components.whiptail_password import WhiptailPasswordPrompter


class WhiptailInputModule:
    """Whiptail-based input module for HITL interactions.
    
    Extends the existing WhiptailPasswordPrompter for general input.
    Provides dialog-based interaction with timeout support.
    
    See: investigate/whiptail/INVESTIGATION_REPORT.md for details
    """
    
    def __init__(self):
        self._prompter = WhiptailPasswordPrompter()
    
    @staticmethod
    def is_available() -> bool:
        """Check if whiptail is available on the system."""
        info = WhiptailPasswordPrompter.is_available()
        return info.get("available", False)
    
    async def prompt(
        self,
        message: str,
        default: str = "",
        timeout: int = 30,
        title: str = "Agent Question",
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
        if not self.is_available():
            return default
        
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
            print(f"Whiptail prompt error: {e}")
            return default
    
    async def confirm(
        self,
        message: str,
        default_yes: bool = True,
        timeout: int = 30,
        title: str = "Confirmation",
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
        if not self.is_available():
            return default_yes
        
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
            print(f"Whiptail confirm error: {e}")
            return default_yes
    
    async def menu(
        self,
        message: str,
        options: List[str],
        timeout: int = 30,
        title: str = "Select Option",
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
        if not self.is_available():
            return options[0] if options else ""
        
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
            print(f"Whiptail menu error: {e}")
            return options[0]
```

**Deliverables:**
- [ ] Create `WhiptailInputModule` class
- [ ] Implement `prompt()`, `confirm()`, `menu()` methods
- [ ] Reuse existing `WhiptailPasswordPrompter` patterns
- [ ] Add availability checking
- [ ] Add unit tests

---

### Step 4: HumanLoopHandler Callback

**Goal:** Create a callback handler that intercepts when the agent needs human input.

**Files to Create:**
- `components/human_loop_handler.py`

**Implementation:**

```python
# components/human_loop_handler.py

import asyncio
import uuid
from typing import Dict, Optional, Any
from rich.console import Console
from llama_index.core.callbacks.base import BaseCallbackHandler
from components.hitl_events import AgentQuestionEvent, AgentAnswerEvent
from components.console_input_module import ConsoleInputModule
from components.whiptail_input_module import WhiptailInputModule
from components.spinner_controller import SpinnerController


class HumanLoopHandler(BaseCallbackHandler):
    """
    Callback handler for Human-in-the-Loop interactions.
    
    Responsibilities:
    - Detect when agent needs clarification (via LLM response patterns)
    - Pause workflow and prompt user via console or whiptail
    - Handle timeout with fallback answer
    - Inject response back into workflow
    - Track pending questions and timeouts
    
    Events Emitted:
    - AgentQuestionEvent: When a question is posed to the user
    - AgentAnswerEvent: When the user responds (or times out)
    """
    
    def __init__(
        self,
        input_method: str = "console",  # "console" or "whiptail"
        default_timeout: int = 30,
        default_answer: str = "",
        console: Optional[Console] = None,
        spinner: Optional[SpinnerController] = None,
        enable_hitl: bool = True,
    ):
        """
        Initialize HumanLoopHandler.
        
        Args:
            input_method: Input method ("console" or "whiptail")
            default_timeout: Default timeout in seconds
            default_answer: Default fallback answer on timeout
            console: Rich Console instance
            spinner: SpinnerController for pause/resume
            enable_hitl: Whether HITL is enabled
        """
        self.input_method = input_method
        self.default_timeout = default_timeout
        self.default_answer = default_answer
        self.console = console
        self.spinner = spinner
        self.enable_hitl = enable_hitl
        
        # Input modules
        self.console_input = ConsoleInputModule(console)
        self.whiptail_input = WhiptailInputModule() if input_method == "whiptail" else None
        
        # State tracking
        self._pending_questions: Dict[str, asyncio.Future] = {}
        self._timeout_log: list[Dict[str, Any]] = []
        self._question_history: list[Dict[str, Any]] = []
        
        # Question detection patterns
        self._question_patterns = [
            r'\?$',           # Ends with question mark
            r'confirm',       # Contains "confirm"
            r'proceed',       # Contains "proceed"
            r'yes/no',        # Contains "yes/no"
            r'continue',      # Contains "continue"
            r'destructive',   # Contains "destructive"
            r'delete',        # Contains "delete"
            r'drop',          # Contains "drop"
            r'overwrite',     # Contains "overwrite"
        ]
    
    def on_event_start(self, event: Any, **kwargs):
        """Called when an event starts."""
        # Check for InputRequiredEvent from LlamaIndex
        if hasattr(event, '__class__'):
            event_name = event.__class__.__name__
            if event_name == "InputRequiredEvent":
                asyncio.create_task(self._handle_input_required(event))
    
    def on_event_end(self, event: Any, **kwargs):
        """Called when an event ends."""
        # Check for agent output that might contain a question
        if hasattr(event, '__class__'):
            event_name = event.__class__.__name__
            if event_name == "AgentOutput":
                self._check_for_question(event)
    
    async def _handle_input_required(self, event):
        """Handle an InputRequiredEvent from the workflow."""
        if not self.enable_hitl:
            return
        
        question_id = str(uuid.uuid4())[:8]
        
        # Pause spinner
        if self.spinner:
            self.spinner.pause()
        
        try:
            # Get user input with timeout
            answer = await self._get_user_input(
                message=getattr(event, 'prefix', 'Please respond: '),
                timeout=self.default_timeout,
                default_answer=self.default_answer,
            )
            
            # Record in history
            self._question_history.append({
                "question_id": question_id,
                "question": getattr(event, 'prefix', ''),
                "answer": answer,
                "was_timeout": False,
                "timestamp": asyncio.get_event_loop().time(),
            })
            
        except asyncio.TimeoutError:
            answer = self.default_answer
            self._log_timeout(question_id, getattr(event, 'prefix', ''))
            
            if self.console:
                self.console.print(
                    "[yellow]⏱️ Timeout - using default answer[/yellow]"
                )
        
        finally:
            # Resume spinner
            if self.spinner:
                self.spinner.resume()
    
    async def _get_user_input(
        self,
        message: str,
        timeout: int = 30,
        default_answer: str = "",
        input_type: str = "text",
    ) -> str:
        """
        Get user input via configured input method.
        
        Args:
            message: Question to ask
            timeout: Seconds to wait
            default_answer: Fallback on timeout
            input_type: Type of input ("text", "yesno", "menu", "password")
            
        Returns:
            User's response or default on timeout
        """
        if self.input_method == "whiptail" and self.whiptail_input:
            return await self._whiptail_input.get_user_input(
                message, timeout, default_answer, input_type
            )
        else:
            return await self._console_input.get_user_input(
                message, timeout, default_answer, input_type
            )
    
    def _check_for_question(self, event):
        """Check if agent output contains a question requiring human input."""
        # Parse agent output for question patterns
        output = str(getattr(event, 'output', ''))
        
        for pattern in self._question_patterns:
            if pattern in output.lower():
                # Trigger HITL flow
                asyncio.create_task(self._handle_detected_question(output))
                break
    
    def _log_timeout(self, question_id: str, question: str):
        """Log a timed-out question."""
        self._timeout_log.append({
            "question_id": question_id,
            "question": question,
            "timeout": self.default_timeout,
            "default_answer": self.default_answer,
            "timestamp": asyncio.get_event_loop().time(),
        })
    
    def get_timeout_log(self) -> list[Dict[str, Any]]:
        """Get log of all timed-out questions."""
        return self._timeout_log.copy()
    
    def get_question_history(self) -> list[Dict[str, Any]]:
        """Get history of all questions asked."""
        return self._question_history.copy()
    
    def reset(self):
        """Reset handler state."""
        self._pending_questions.clear()
        self._timeout_log.clear()
        self._question_history.clear()
```

**Deliverables:**
- [ ] Create `HumanLoopHandler` extending `BaseCallbackHandler`
- [ ] Implement `on_event_start()` and `on_event_end()` hooks
- [ ] Add question detection via LLM response pattern matching
- [ ] Add timeout logging and question history
- [ ] Add unit tests

---

### Step 5: EventConsumer Integration

**Goal:** Integrate HITL handling into the existing EventConsumer.

**Files to Modify:**
- `components/event_consumer.py`

**Changes:**

```python
# Add to EventConsumer class

async def _handle_event(self, event: Event) -> None:
    """Route event to specific handler."""
    event_type = type(event).__name__
    
    if event_type == "AgentStream":
        await self._on_agent_stream(event)
    elif event_type == "ToolCall":
        await self._on_tool_call(event)
    elif event_type == "ToolCallResult":
        await self._on_tool_call_result(event)
    elif event_type == "StopEvent":
        await self._on_stop_event(event)
    elif event_type == "AgentOutput":
        await self._on_agent_output(event)
    elif event_type == "InputRequiredEvent":
        await self._on_input_required(event)  # NEW
    elif event_type == "AgentQuestionEvent":
        await self._on_agent_question(event)  # NEW

async def _on_input_required(self, event: Event) -> None:
    """Handle InputRequiredEvent - agent needs human input."""
    # Pause spinner
    self.spinner.pause()
    
    # Display question
    self.console.print(
        f"\n[magenta]🤖 Agent asks: {event.prefix}[/magenta]"
    )
    
    try:
        # Get user input
        response = await self.console_input.prompt(
            message=event.prefix,
            timeout=self.hitl_timeout,
        )
        
        # Send response back to workflow
        self.handler.ctx.send_event(
            HumanResponseEvent(
                response=response,
                user_name=getattr(event, 'user_name', None),
            )
        )
        
        self.console.print("[green]✅ Response sent to agent[/green]")
        
    except asyncio.TimeoutError:
        self.console.print(
            f"[yellow]⏱️ Timeout - using default: {self.hitl_default_answer}[/yellow]"
        )
        self.handler.ctx.send_event(
            HumanResponseEvent(
                response=self.hitl_default_answer,
                user_name=getattr(event, 'user_name', None),
            )
        )
    
    finally:
        # Resume spinner
        self.spinner.resume()
```

**Deliverables:**
- [ ] Add `_on_input_required()` handler
- [ ] Add `_on_agent_question()` handler
- [ ] Integrate with spinner pause/resume
- [ ] Add HITL configuration parameters

---

### Step 6: Timeout Manager

**Goal:** Centralized timeout management for HITL prompts.

**Files to Create:**
- `components/timeout_manager.py`

**Implementation:**

```python
# components/timeout_manager.py

import asyncio
from datetime import datetime
from typing import Callable, Tuple, Optional, Dict, Any


class TimeoutManager:
    """
    Manages timeout logic for HITL prompts.
    
    Responsibilities:
    - Wrap async prompt functions with timeout
    - Track timed-out questions
    - Provide fallback answers
    - Log timeout events for review
    """
    
    def __init__(self, default_timeout: int = 30):
        self.default_timeout = default_timeout
        self._timed_out_questions: list[Dict[str, Any]] = []
    
    async def prompt_with_timeout(
        self,
        prompt_fn: Callable,
        timeout: Optional[int] = None,
        default_answer: str = "",
        question_id: Optional[str] = None,
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
    
    def get_timeout_log(self) -> list[Dict[str, Any]]:
        """Get log of all timed-out questions."""
        return self._timed_out_questions.copy()
    
    def reset(self):
        """Clear timeout log."""
        self._timed_out_questions.clear()
```

**Deliverables:**
- [ ] Create `TimeoutManager` class
- [ ] Implement `prompt_with_timeout()` method
- [ ] Add timeout logging
- [ ] Add unit tests

---

### Step 7: Runtime Toggle

**Goal:** Allow users to dynamically enable/disable HITL during agent execution without restarting.

**Files to Create:**
- `components/hitl_runtime_toggle.py`

**Implementation:**

```python
# components/hitl_runtime_toggle.py

import asyncio
from typing import Optional
from rich.console import Console


class HITLRuntimeToggle:
    """
    Runtime toggle for Human-in-the-Loop mode.
    
    Allows enabling/disabling HITL during agent execution via:
    1. Interactive command (e.g., typing 'toggle-hitl' during execution)
    2. Environment variable change detection
    3. API endpoint (for headless/server mode)
    
    Thread-safe state management with atomic toggle operations.
    """
    
    def __init__(
        self,
        initial_state: bool = True,
        console: Optional[Console] = None,
    ):
        """
        Initialize runtime toggle.
        
        Args:
            initial_state: Whether HITL is enabled at start
            console: Rich Console for status messages
        """
        self._enabled = initial_state
        self._console = console or Console()
        self._lock = asyncio.Lock()
        self._toggle_count = 0
        self._last_toggled_by: str = "init"
    
    @property
    def is_enabled(self) -> bool:
        """Current HITL enabled state."""
        return self._enabled
    
    @property
    def toggle_count(self) -> int:
        """Number of times toggle has been invoked."""
        return self._toggle_count
    
    async def toggle(self, source: str = "user") -> bool:
        """
        Toggle HITL on/off.
        
        Args:
            source: Who/what triggered the toggle ("user", "env", "api", "init")
        
        Returns:
            New state after toggle
        """
        async with self._lock:
            self._enabled = not self._enabled
            self._toggle_count += 1
            self._last_toggled_by = source
            
            status = "🟢 ENABLED" if self._enabled else "🔴 DISABLED"
            self._console.print(
                f"\n[bold cyan]HITL Toggle[/bold cyan]: {status} "
                f"(by {source}, toggle #{self._toggle_count})"
            )
            return self._enabled
    
    async def set_state(self, enabled: bool, source: str = "user") -> None:
        """
        Set HITL state explicitly.
        
        Args:
            enabled: True to enable, False to disable
            source: Who/what triggered the change
        """
        async with self._lock:
            if self._enabled != enabled:
                self._enabled = enabled
                self._toggle_count += 1
                self._last_toggled_by = source
                
                status = "🟢 ENABLED" if enabled else "🔴 DISABLED"
                self._console.print(
                    f"\n[bold cyan]HITL Set[/bold cyan]: {status} "
                    f"(by {source}, toggle #{self._toggle_count})"
                )
    
    async def status(self) -> dict:
        """
        Get current toggle status.
        
        Returns:
            Dict with current state info
        """
        async with self._lock:
            return {
                "enabled": self._enabled,
                "toggle_count": self._toggle_count,
                "last_toggled_by": self._last_toggled_by,
            }
    
    def status_sync(self) -> dict:
        """Synchronous version of status() for non-async contexts."""
        return {
            "enabled": self._enabled,
            "toggle_count": self._toggle_count,
            "last_toggled_by": self._last_toggled_by,
        }
```

**Integration into HumanLoopHandler:**

```python
# In HumanLoopHandler.__init__, add:
from components.hitl_runtime_toggle import HITLRuntimeToggle

self.runtime_toggle = HITLRuntimeToggle(
    initial_state=enable_hitl,
    console=console,
)

# Replace all `self.enable_hitl` checks with:
if not self.runtime_toggle.is_enabled:
    return  # Skip HITL flow

# Add a command listener for interactive toggle
async def _listen_for_toggle_command(self):
    """Background task that listens for toggle commands during execution."""
    try:
        while True:
            # Check for inline command during agent execution
            cmd = await self._get_background_input()  # Non-blocking
            if cmd.lower().strip() == "toggle-hitl":
                await self.runtime_toggle.toggle(source="interactive")
            elif cmd.lower().strip() == "hitl-status":
                status = await self.runtime_toggle.status()
                self.console.print(f"[dim]HITL Status: {status}[/dim]")
    except asyncio.CancelledError:
        pass
```

**Integration into EventConsumer:**

```python
# In EventConsumer, add toggle command handling:

async def _handle_inline_commands(self) -> None:
    """Process inline commands typed during agent execution."""
    commands = {
        "toggle-hitl": self._toggle_hitl,
        "hitl-status": self._show_hitl_status,
        "hitl-on": self._enable_hitl,
        "hitl-off": self._disable_hitl,
    }
    
    try:
        cmd = await self._get_background_input()
        if cmd.strip().lower() in commands:
            await commands[cmd.strip().lower()]()
    except asyncio.TimeoutError:
        pass  # No command typed, continue normal flow

async def _toggle_hitl(self) -> None:
    """Toggle HITL on/off."""
    await self.runtime_toggle.toggle(source="inline-command")

async def _enable_hitl(self) -> None:
    """Enable HITL."""
    await self.runtime_toggle.set_state(True, source="inline-command")

async def _disable_hitl(self) -> None:
    """Disable HITL."""
    await self.runtime_toggle.set_state(False, source="inline-command")

async def _show_hitl_status(self) -> None:
    """Show current HITL status."""
    status = await self.runtime_toggle.status()
    self.console.print(
        f"[dim]HITL: {'ON' if status['enabled'] else 'OFF'}, "
        f"toggles: {status['toggle_count']}[/dim]"
    )
```

**Environment Variable Hot-Reload:**

```python
# Optional: Watch for env var changes
import os

class EnvVarWatcher:
    """Watches TORVALDS_HITL_ENABLED env var for changes."""
    
    def __init__(self, toggle: HITLRuntimeToggle):
        self.toggle = toggle
        self._last_value = os.environ.get("TORVALDS_HITL_ENABLED", "true")
    
    async def check(self) -> None:
        """Check if env var changed and update toggle accordingly."""
        current = os.environ.get("TORVALDS_HITL_ENABLED", "true")
        if current.lower() != self._last_value.lower():
            enabled = current.lower() == "true"
            await self.toggle.set_state(enabled, source="env-var")
            self._last_value = current
```

**Deliverables:**
- [ ] Create `HITLRuntimeToggle` class with async-safe state management
- [ ] Add inline command parsing (`toggle-hitl`, `hitl-status`, etc.)
- [ ] Integrate with `HumanLoopHandler` and `EventConsumer`
- [ ] Add environment variable hot-reload support
- [ ] Add unit tests for toggle state transitions
- [ ] Add visual status indicator in agent output

---

### Step 8: Agent Integration

**Goal:** Wire HITL components into the agent workflow.

**Files to Modify:**
- `agent-torvalds.py`

**Changes:**

```python
# In agent-torvalds.py

# Import new components
from components.human_loop_handler import HumanLoopHandler
from components.timeout_manager import TimeoutManager
from components.runtime_toggle import HITLRuntimeToggle
from components.console_input_module import ConsoleInputModule
from components.whiptail_input_module import WhiptailInputModule

# Configuration via environment variables
HITL_ENABLED = os.environ.get("TORVALDS_HITL_ENABLED", "true").lower() == "true"
HITL_METHOD = os.environ.get("TORVALDS_HITL_METHOD", "console")  # "console" or "whiptail"
HITL_TIMEOUT = int(os.environ.get("TORVALDS_HITL_TIMEOUT", "30"))
HITL_DEFAULT_ANSWER = os.environ.get("TORVALDS_HITL_DEFAULT_ANSWER", "")

# Create runtime toggle
hitl_toggle = HITLRuntimeToggle(
    initial_state=HITL_ENABLED,
    console=console,
)

# Create HITL handler with toggle
human_loop_handler = HumanLoopHandler(
    input_method=HITL_METHOD,
    default_timeout=HITL_TIMEOUT,
    default_answer=HITL_DEFAULT_ANSWER,
    console=console,
    spinner=spinner_controller,
    runtime_toggle=hitl_toggle,
)

# Add to callback manager
if enable_stats:
    callback_handlers = [
        RequestStatsHandler(request_id=request_id, user_query=cmd),
        human_loop_handler,
    ]
    callback_manager = CallbackManager(callback_handlers)
else:
    callback_manager = CallbackManager([])
    callback_manager.add_handler(human_loop_handler)

# Pass to agent
workflow_handler = agent.run(
    cmd,
    memory=chat_memory,
    max_iterations=MAX_ITERATIONS,
    callback_manager=callback_manager,
)

# Consume events with HITL support and runtime toggle
result = await event_consumer.consume_events(
    workflow_handler,
    cmd,
    hitl_toggle=hitl_toggle,
    hitl_timeout=HITL_TIMEOUT,
    hitl_default_answer=HITL_DEFAULT_ANSWER,
)
```

**Deliverables:**
- [ ] Add environment variable configuration
- [ ] Create `HumanLoopHandler` instance with runtime toggle
- [ ] Add to callback manager
- [ ] Pass to agent workflow
- [ ] Update EventConsumer to handle HITL events and toggle commands

---

### Step 9: Configuration & CLI

**Goal:** Add CLI flags and configuration for HITL settings.

**Files to Modify:**
- `agent-torvalds.py` (CLI argument parser)

**Changes:**

```python
# Add CLI arguments
parser.add_argument(
    "--hitl-enabled",
    action="store_true",
    default=True,
    help="Enable Human-in-the-Loop interactions (default: True)",
)

parser.add_argument(
    "--hitl-disabled",
    action="store_true",
    help="Disable Human-in-the-Loop interactions at startup",
)

parser.add_argument(
    "--hitl-method",
    choices=["console", "whiptail"],
    default="console",
    help="Input method for HITL prompts (default: console)",
)

parser.add_argument(
    "--hitl-timeout",
    type=int,
    default=30,
    help="Timeout in seconds for HITL prompts (default: 30)",
)

parser.add_argument(
    "--hitl-default-answer",
    type=str,
    default="",
    help="Default fallback answer on timeout (default: empty)",
)

parser.add_argument(
    "--hitl-no-runtime-toggle",
    action="store_true",
    help="Disable runtime toggle commands (toggle-hitl, hitl-status, etc.)",
)
```

**Deliverables:**
- [ ] Add CLI arguments for HITL configuration
- [ ] Add `--hitl-disabled` flag for initial disable
- [ ] Add `--hitl-no-runtime-toggle` to disable inline commands
- [ ] Update help text
- [ ] Add environment variable overrides
- [ ] Update README with HITL usage and runtime toggle commands

---

## Testing Strategy

### Unit Tests

```python
# tests/test_hitl_events.py
# tests/test_console_input_module.py
# tests/test_whiptail_input_module.py
# tests/test_human_loop_handler.py
# tests/test_timeout_manager.py
# tests/test_hitl_runtime_toggle.py  # NEW
```

### Integration Tests

```python
# tests/test_hitl_integration.py
# Test full HITL flow with mocked agent
# Test timeout handling
# Test whiptail fallback to console
# Test runtime toggle during execution  # NEW
```

### Manual Tests

1. Test console input with timeout
2. Test whiptail input (if available)
3. Test confirmation prompts
4. Test menu selection
5. Test timeout fallback
6. Test spinner pause/resume during prompts
7. Test runtime toggle via `toggle-hitl` command  # NEW
8. Test `hitl-status` command  # NEW
9. Test env var hot-reload  # NEW

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Terminal conflicts** | Whiptail conflicts with rich output | Proper spinner pause/resume |
| **Timeout hangs** | Agent hangs if timeout fails | Use `asyncio.wait_for()` with executor |
| **Question detection false positives** | Unnecessary prompts | Refine regex patterns |
| **Performance overhead** | Event processing latency | Async processing, batch handling |
| **Breaking changes** | Affects existing functionality | Feature flags, gradual rollout |
| **Toggle race conditions** | State inconsistency | Async lock in `HITLRuntimeToggle` |

---

## Success Criteria

### Quantitative

| Metric | Target | Measurement |
|--------|--------|-------------|
| HITL prompt response time | < 2s | Profiling |
| Timeout accuracy | 100% | Testing |
| Question detection rate | > 90% | Manual testing |
| False positive rate | < 5% | Manual testing |
| Toggle response time | < 100ms | Unit tests |

### Qualitative

- ✅ Users can interact with agent during execution
- ✅ Spinner doesn't conflict with dialogs
- ✅ Timeout handling works reliably
- ✅ Whiptail and console input both work
- ✅ No performance degradation
- ✅ Configuration is flexible
- ✅ HITL can be toggled on/off during execution without restart
- ✅ Inline commands are properly parsed and handled

---

## Next Steps

1. **Week 1:** Steps 1-3 (Foundation, Console Input, Whiptail Input)
2. **Week 2:** Steps 4-5 (HumanLoopHandler, EventConsumer Integration)
3. **Week 3:** Steps 6-7 (Timeout Manager, Runtime Toggle)
4. **Week 4:** Steps 8-9 (Agent Integration, CLI, Testing, Documentation)

---

*Generated by Torvalds AI Agent*  
*Date: 2025-01-15*  
*Branch: feature/human-in-the-loop*
