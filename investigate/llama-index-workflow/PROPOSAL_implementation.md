# PROPOSAL: Interactive Agent Workflow Implementation

**Date:** 2025-01-12  
**Author:** Torvalds AI Agent  
**Repository:** agent-torvalds  
**Status:** Proposed  
**Priority:** High  
**Estimated Effort:** 2-3 weeks

---

## Table of Contents

1. [Overview](#overview)
2. [Problem Statement](#problem-statement)
3. [Proposed Solution](#proposed-solution)
   - 3.1 [Architecture Diagram](#31-architecture-diagram)
   - 3.2 [Component Design](#32-component-design)
4. [Implementation Plan](#implementation-plan)
   - Phase 1: Event Streaming & Spinner Control
   - Phase 2: State Handler & Interactive Prompts
   - Phase 3: Advanced Features
5. [API Design](#api-design)
6. [Code Examples](#code-examples)
7. [Testing Strategy](#testing-strategy)
8. [Migration Path](#migration-path)
9. [Risks & Mitigations](#risks--mitigations)
10. [Success Metrics](#success-metrics)

---

## Overview

This proposal outlines the implementation of an interactive agent workflow system with:
1. **Real-time event streaming** for user feedback
2. **Spinner pause/resume** during interactive operations
3. **Agent state handler** for context management
4. **Human-in-the-loop** capabilities for interactive prompts

**Primary Use Case:** Pause/resume console spinner when the agent invokes sudo password using Whiptail.

---

## Problem Statement

### Current Limitations

1. **No Real-Time Feedback**
   - Users see only a spinner during agent execution
   - No visibility into tool calls, progress, or intermediate results
   - Long-running operations appear frozen

2. **No Interactive Capability**
   - Cannot pause for user input during workflow
   - Whiptail dialogs conflict with spinner output
   - No way to inject events or modify state mid-execution

3. **Limited State Management**
   - Only default state tracking (memory, iterations)
   - No custom state for agent context
   - No persistence across sessions

4. **No Recovery Mechanism**
   - Failures require full restart
   - No partial state preservation
   - No graceful degradation

---

## Proposed Solution

### 3.1 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    agent-torvalds.py                         │
│                                                              │
│  ┌─────────────┐    ┌──────────────┐    ┌───────────────┐   │
│  │  CLI Input  │───▶│  Event Loop  │───▶│  Response     │   │
│  │  Handler    │    │  Manager     │    │  Renderer     │   │
│  └─────────────┘    └──────────────┘    └───────────────┘   │
│                              │                       │      │
│                              ▼                       ▼      │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              Workflow Event Consumer                     │
│  │                                                          │
│  │  ┌────────────┐  ┌────────────┐  ┌──────────────────┐  │
│  │  │ Spinner    │  │ State      │  │ Interactive      │  │
│  │  │ Controller │  │ Handler    │  │ Prompt Manager   │  │
│  │  └────────────┘  └────────────┘  └──────────────────┘  │
│  └────────────────────────────────────────────────────────┘ │
│                              │                              │
│                              ▼                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              LlamaIndex FunctionAgent                    │
│  │                                                          │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │  │ Tool     │  │ Memory   │  │ Context Store         │  │
│  │  │ Executor │  │ Manager  │  │ (state, iterations)   │  │
│  │  └──────────┘  └──────────┘  └──────────────────────┘  │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Component Design

#### Component 1: EventConsumer

**Purpose:** Consume and process workflow events in real-time.

```python
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
    ):
        self.spinner = spinner_controller
        self.state = state_handler
        self.console = console
        self._event_handlers = {}
        self._running = False
    
    async def consume_events(
        self,
        handler: WorkflowHandler,
        user_msg: str,
    ) -> AgentOutput:
        """
        Consume events from workflow handler.
        
        Args:
            handler: WorkflowHandler from agent.run()
            user_msg: Original user message
            
        Returns:
            Final AgentOutput result
        """
        self._running = True
        self.state.set("current_user_msg", user_msg)
        
        try:
            async for event in handler.stream_events():
                if not self._running:
                    break
                
                # Route event to appropriate handler
                await self._handle_event(event)
            
            # Get final result
            result = await handler
            return result
            
        finally:
            self._running = False
            self.state.set("workflow_running", False)
    
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
        # ... more event types
    
    async def _on_tool_call(self, event: ToolCall) -> None:
        """Handle tool call event."""
        # Pause spinner for interactive tools
        if self._is_interactive_tool(event.tool_name):
            self.spinner.pause()
            self.console.print(
                f"\n[yellow]🔧 Calling tool: {event.tool_name}[/yellow]"
            )
        
        # Update state
        self.state.set("current_tool", event.tool_name)
        self.state.increment("tool_calls")
    
    async def _on_tool_call_result(self, event: ToolCallResult) -> None:
        """Handle tool call result."""
        # Resume spinner after tool execution
        if self._is_interactive_tool(event.tool_name):
            self.spinner.resume()
        
        # Log result
        self.state.set(f"tool_result_{event.tool_name}", event.tool_output.content)
    
    def _is_interactive_tool(self, tool_name: str) -> bool:
        """Check if tool requires interactive handling."""
        interactive_tools = {
            "prompt_sudo_password_whiptail",
            "execute_shell_command",  # Long-running
            "run_postgres_query",     # Database operations
            # ... more tools
        }
        return tool_name in interactive_tools
```

#### Component 2: StateHandler

**Purpose:** Manage agent state across workflow execution.

```python
class StateHandler:
    """
    Manages agent state during workflow execution.
    
    Responsibilities:
    - Track workflow state (running, paused, completed)
    - Store tool call history
    - Manage interactive prompts
    - Persist state across sessions (optional)
    """
    
    def __init__(self):
        self._state: Dict[str, Any] = {
            "workflow_running": False,
            "workflow_paused": False,
            "current_tool": None,
            "current_user_msg": None,
            "tool_calls": 0,
            "tool_history": [],
            "errors": [],
            "interactive_prompts": [],
            "start_time": None,
            "end_time": None,
        }
    
    def set(self, key: str, value: Any) -> None:
        """Set state value."""
        self._state[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get state value."""
        return self._state.get(key, default)
    
    def increment(self, key: str, amount: int = 1) -> None:
        """Increment counter."""
        self._state[key] = self._state.get(key, 0) + amount
    
    def add_tool_call(self, tool_name: str, result: Any) -> None:
        """Record tool call in history."""
        self._state["tool_history"].append({
            "tool": tool_name,
            "result": result,
            "timestamp": datetime.now(),
        })
    
    def add_error(self, error: str) -> None:
        """Record error."""
        self._state["errors"].append({
            "error": error,
            "timestamp": datetime.now(),
        })
    
    def get_state_snapshot(self) -> Dict[str, Any]:
        """Get current state snapshot."""
        return self._state.copy()
    
    def reset(self) -> None:
        """Reset state for new workflow."""
        self._state = {
            "workflow_running": False,
            "workflow_paused": False,
            "current_tool": None,
            "current_user_msg": None,
            "tool_calls": 0,
            "tool_history": [],
            "errors": [],
            "interactive_prompts": [],
            "start_time": None,
            "end_time": None,
        }
```

#### Component 3: InteractivePromptManager

**Purpose:** Manage human-in-the-loop interactions.

```python
class InteractivePromptManager:
    """
    Manages interactive prompts during workflow execution.
    
    Responsibilities:
    - Handle user prompts (yes/no, text input, selection)
    - Integrate with Whiptail dialogs
    - Manage prompt timeouts
    - Send responses back to workflow
    """
    
    def __init__(
        self,
        spinner_controller: SpinnerController,
        console: Console,
    ):
        self.spinner = spinner_controller
        self.console = console
        self._whiptail_prompter = WhiptailPasswordPrompter()
    
    async def prompt_password(
        self,
        message: str = "Enter sudo password",
        timeout: int = 60,
    ) -> str:
        """
        Prompt for password with spinner pause.
        
        Args:
            message: Prompt message
            timeout: Timeout in seconds
            
        Returns:
            Entered password or empty string on timeout
        """
        # Pause spinner
        self.spinner.pause()
        
        try:
            # Show whiptail dialog
            result = self._whiptail_prompter.prompt_password(
                message=message,
                max_attempts=3,
            )
            
            if result["success"]:
                return result["password"]
            else:
                self.console.print(
                    f"[red]Password prompt failed: {result.get('error')}[/red]"
                )
                return ""
        
        finally:
            # Resume spinner
            self.spinner.resume()
    
    async def prompt_confirmation(
        self,
        message: str,
        default: bool = True,
    ) -> bool:
        """Prompt for yes/no confirmation."""
        self.spinner.pause()
        
        try:
            response = self.console.input(
                f"\n[cyan]{message} (y/n)[default={'y' if default else 'n'}]: [/cyan]"
            ).strip().lower()
            
            if not response:
                return default
            return response in ('y', 'yes')
        
        finally:
            self.spinner.resume()
    
    async def prompt_text(
        self,
        message: str,
        default: str = "",
    ) -> str:
        """Prompt for text input."""
        self.spinner.pause()
        
        try:
            response = self.console.input(
                f"\n[cyan]{message}: [/cyan]"
            ).strip()
            
            return response if response else default
        
        finally:
            self.spinner.resume()
```

---

## Implementation Plan

### Phase 1: Event Streaming & Spinner Control (Week 1)

**Deliverables:**
- [ ] Create `EventConsumer` class
- [ ] Integrate with `agent.run()` call
- [ ] Implement spinner pause/resume for interactive tools
- [ ] Add tool call logging to console
- [ ] Basic error handling

**Files to Create/Modify:**
- `components/event_consumer.py` (new)
- `components/state_handler.py` (new)
- `agent-torvalds.py` (modify)

**Key Changes:**
```python
# Before
result = await agent.run(cmd, memory=chat_memory, ...)

# After
handler = agent.run(cmd, memory=chat_memory, ...)
event_consumer = EventConsumer(spinner_controller, state_handler, console)
result = await event_consumer.consume_events(handler, cmd)
```

### Phase 2: State Handler & Interactive Prompts (Week 2)

**Deliverables:**
- [ ] Create `StateHandler` class
- [ ] Create `InteractivePromptManager` class
- [ ] Integrate Whiptail with spinner control
- [ ] Add custom state tracking
- [ ] Implement prompt timeout handling

**Files to Create/Modify:**
- `components/interactive_prompt_manager.py` (new)
- `agent_torvalds.py` (modify)
- `agent_apt_toolkit.py` (modify for Whiptail integration)

### Phase 3: Advanced Features (Week 3)

**Deliverables:**
- [ ] Context persistence (optional)
- [ ] Recovery mechanism
- [ ] Enhanced observability
- [ ] Performance optimization
- [ ] Documentation & examples

**Files to Create/Modify:**
- `components/context_manager.py` (new)
- `docs/workflow_events.md` (new)
- Tests for all new components

---

## API Design

### EventConsumer API

```python
class EventConsumer:
    async def consume_events(
        self,
        handler: WorkflowHandler,
        user_msg: str,
        on_tool_call: Callable[[ToolCall], None] = None,
        on_tool_result: Callable[[ToolCallResult], None] = None,
        on_stream: Callable[[AgentStream], None] = None,
        on_error: Callable[[Exception], None] = None,
    ) -> AgentOutput:
        """Consume events with custom callbacks."""
        ...
    
    def pause_spinner_for_tools(self, tool_names: List[str]) -> None:
        """Configure which tools should pause the spinner."""
        ...
    
    def cancel(self) -> None:
        """Cancel event consumption."""
        ...
```

### StateHandler API

```python
class StateHandler:
    def set(self, key: str, value: Any) -> None:
        ...
    
    def get(self, key: str, default: Any = None) -> Any:
        ...
    
    def get_state_snapshot(self) -> Dict[str, Any]:
        ...
    
    def reset(self) -> None:
        ...
    
    async def persist_to_file(self, path: str) -> None:
        """Persist state to file."""
        ...
    
    @classmethod
    async def load_from_file(cls, path: str) -> "StateHandler":
        """Load state from file."""
        ...
```

### InteractivePromptManager API

```python
class InteractivePromptManager:
    async def prompt_password(
        self,
        message: str = "Enter password",
        timeout: int = 60,
    ) -> str:
        ...
    
    async def prompt_confirmation(
        self,
        message: str,
        default: bool = True,
    ) -> bool:
        ...
    
    async def prompt_text(
        self,
        message: str,
        default: str = "",
    ) -> str:
        ...
```

---

## Code Examples

### Example 1: Basic Event Streaming

```python
# In agent-torvalds.py

async def prompt_handler(
    cmd: str,
    agent: FunctionAgent,
    enable_stats: bool = True,
):
    handler = agent.run(
        cmd,
        memory=chat_memory,
        max_iterations=MAX_ITERATIONS,
    )
    
    # Create event consumer
    state_handler = StateHandler()
    event_consumer = EventConsumer(
        spinner_controller=spinner_controller,
        state_handler=state_handler,
        console=console,
    )
    
    # Configure spinner pause for interactive tools
    event_consumer.pause_spinner_for_tools([
        "prompt_sudo_password_whiptail",
        "execute_shell_command",
    ])
    
    # Consume events and get result
    result = await event_consumer.consume_events(handler, cmd)
    
    return result, state_handler.get_state_snapshot()
```

### Example 2: Whiptail Password with Spinner Control

```python
# In agent_apt_toolkit.py

@tools_function
def prompt_sudo_password_whiptail() -> Dict[str, Any]:
    """Prompt for sudo password using whiptail dialog."""
    # This will be called during workflow execution
    # The EventConsumer will pause the spinner before this tool runs
    
    prompter = WhiptailPasswordPrompter()
    result = prompter.prompt_password(
        message="Enter your sudo password:",
        max_attempts=3,
    )
    
    return result
```

### Example 3: Custom Event Callbacks

```python
# Advanced usage with custom callbacks

event_consumer = EventConsumer(
    spinner_controller=spinner_controller,
    state_handler=state_handler,
    console=console,
)

# Define custom callbacks
def on_tool_call(event: ToolCall):
    print(f"🔧 Calling: {event.tool_name}")
    if event.tool_name == "execute_shell_command":
        print(f"   Command: {event.tool_kwargs.get('command')}")

def on_tool_result(event: ToolCallResult):
    if event.tool_output.is_error:
        print(f"❌ Error in {event.tool_name}: {event.tool_output.content}")
    else:
        print(f"✅ Success: {event.tool_name}")

# Consume events with callbacks
result = await event_consumer.consume_events(
    handler,
    cmd,
    on_tool_call=on_tool_call,
    on_tool_result=on_tool_result,
)
```

---

## Testing Strategy

### Unit Tests

```python
# tests/test_event_consumer.py

import pytest
from unittest.mock import AsyncMock, MagicMock
from components.event_consumer import EventConsumer

@pytest.mark.asyncio
async def test_event_consumer_basic():
    """Test basic event consumption."""
    spinner = MagicMock()
    state = MagicMock()
    console = MagicMock()
    
    consumer = EventConsumer(spinner, state, console)
    
    # Mock handler
    handler = AsyncMock()
    handler.stream_events = AsyncMock(return_value=iter([]))
    handler.__await__ = AsyncMock(return_value="result")
    
    result = await consumer.consume_events(handler, "test")
    assert result == "result"

@pytest.mark.asyncio
async def test_spinner_pause_on_tool_call():
    """Test spinner pauses for interactive tools."""
    spinner = MagicMock()
    state = MagicMock()
    console = MagicMock()
    
    consumer = EventConsumer(spinner, state, console)
    consumer.pause_spinner_for_tools(["prompt_sudo_password_whiptail"])
    
    # Mock tool call event
    event = ToolCall(
        tool_name="prompt_sudo_password_whiptail",
        tool_kwargs={},
        tool_id="test-id",
    )
    
    await consumer._on_tool_call(event)
    spinner.pause.assert_called_once()
```

### Integration Tests

```python
# tests/test_workflow_integration.py

@pytest.mark.asyncio
async def test_full_workflow_with_events():
    """Test complete workflow with event consumption."""
    agent = create_agent(use_retriever=False)
    
    handler = agent.run("What is 2+2?")
    
    state_handler = StateHandler()
    event_consumer = EventConsumer(
        spinner_controller=spinner_controller,
        state_handler=state_handler,
        console=console,
    )
    
    result = await event_consumer.consume_events(handler, "What is 2+2?")
    
    assert "4" in str(result)
    assert state_handler.get("tool_calls") >= 0
```

---

## Migration Path

### Step 1: Add New Components (Non-Breaking)

```python
# Import new components
from components.event_consumer import EventConsumer
from components.state_handler import StateHandler

# Wrap existing agent.run() call
handler = agent.run(cmd, ...)
event_consumer = EventConsumer(...)
result = await event_consumer.consume_events(handler, cmd)
```

### Step 2: Gradual Feature Enablement

```python
# Feature flags for gradual rollout
ENABLE_EVENT_STREAMING = os.environ.get("TORVALDS_EVENT_STREAMING", "true")
ENABLE_STATE_HANDLER = os.environ.get("TORVALDS_STATE_HANDLER", "true")
ENABLE_INTERACTIVE_PROMPTS = os.environ.get("TORVALDS_INTERACTIVE_PROMPTS", "false")
```

### Step 3: Full Integration

```python
# After testing, make it the default
async def prompt_handler(cmd: str, agent: FunctionAgent, ...):
    handler = agent.run(cmd, ...)
    event_consumer = EventConsumer(...)
    result = await event_consumer.consume_events(handler, cmd)
    return result
```

---

## Risks & Mitigations

### Risk 1: Performance Overhead
**Impact:** Event processing may add latency.
**Mitigation:**
- Use async event processing
- Batch event handling where possible
- Profile and optimize critical paths

### Risk 2: Complexity Increase
**Impact:** More components = more maintenance.
**Mitigation:**
- Clear component boundaries
- Comprehensive documentation
- Thorough testing

### Risk 3: Breaking Changes
**Impact:** May affect existing functionality.
**Mitigation:**
- Feature flags for gradual rollout
- Backward compatibility layer
- Extensive regression testing

### Risk 4: Whiptail Conflicts
**Impact:** Terminal conflicts with rich output.
**Mitigation:**
- Proper spinner pause/resume
- Terminal state management
- Fallback to console input

---

## Success Metrics

### Quantitative

| Metric | Target | Measurement |
|--------|--------|-------------|
| Event processing latency | < 10ms per event | Profiling |
| Tool call visibility | 100% | Logging |
| Spinner pause accuracy | 100% | Testing |
| Error rate | < 1% | Monitoring |

### Qualitative

- ✅ Users can see tool calls in real-time
- ✅ Spinner doesn't conflict with Whiptail dialogs
- ✅ Agent state is tracked and visible
- ✅ Interactive prompts work seamlessly
- ✅ No performance degradation

---

## Appendix

### A. Event Type Reference

| Event Type | Description | Handler Method |
|------------|-------------|----------------|
| `AgentStream` | Streaming tokens | `_on_agent_stream()` |
| `ToolCall` | Tool invocation | `_on_tool_call()` |
| `ToolCallResult` | Tool output | `_on_tool_call_result()` |
| `StopEvent` | Workflow complete | `_on_stop_event()` |
| `AgentOutput` | LLM response | `_on_agent_output()` |
| `AgentInput` | LLM input | `_on_agent_input()` |

### B. Interactive Tool List

```python
INTERACTIVE_TOOLS = {
    "prompt_sudo_password_whiptail": "password_prompt",
    "execute_shell_command": "long_running",
    "run_postgres_query": "database",
    "run_mysql_query": "database",
    "git_commit": "confirmation",
    "git_push": "confirmation",
    "rm": "confirmation",
}
```

### C. State Keys Reference

```python
STATE_KEYS = {
    "workflow_running": "bool - Workflow execution status",
    "workflow_paused": "bool - Workflow pause status",
    "current_tool": "str - Currently executing tool",
    "current_user_msg": "str - Current user message",
    "tool_calls": "int - Total tool call count",
    "tool_history": "list - Tool call history",
    "errors": "list - Error history",
    "start_time": "datetime - Workflow start time",
    "end_time": "datetime - Workflow end time",
}
```

---

*End of Proposal*

**Next Steps:**
1. Review and approve proposal
2. Create implementation tasks
3. Begin Phase 1 development
4. Weekly progress reviews

**Questions?** Contact: Torvalds AI Agent
