# Step 8: Agent Integration

**Step:** 8 of 9  
**Goal:** Wire HITL components into the agent workflow  
**Estimated Effort:** 4-5 days  
**Dependencies:** Steps 1-7 (All previous components)

---

## Overview

This step integrates all HITL components into the main agent workflow. It involves modifying the agent to use the new HITL handler, integrating with the callback manager, and ensuring proper event handling throughout the agent's execution.

## Files to Modify

- `agent-torvalds.py`

## Implementation Details

### Configuration via Environment Variables

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
```

### Component Initialization

```python
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
```

### Callback Manager Integration

```python
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
```

### Agent Workflow Integration

```python
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

## Deliverables

- [ ] Add environment variable configuration for HITL settings
- [ ] Create `HumanLoopHandler` instance with runtime toggle
- [ ] Add handler to callback manager
- [ ] Pass callback manager to agent workflow
- [ ] Update EventConsumer to handle HITL events and toggle commands
- [ ] Test full integration with agent execution
- [ ] Verify proper error handling

## Success Criteria

- [ ] Agent correctly integrates with HITL handler
- [ ] Callback manager properly handles HITL events
- [ ] Runtime toggle works during agent execution
- [ ] Environment variables are properly read
- [ ] Agent execution doesn't break with HITL enabled
- [ ] Full end-to-end HITL flow works correctly
- [ ] Integration tests pass

## Next Step

Step 9: Configuration & CLI
