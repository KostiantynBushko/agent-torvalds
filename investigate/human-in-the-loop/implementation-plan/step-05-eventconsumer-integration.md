# Step 5: EventConsumer Integration

**Step:** 5 of 9  
**Goal:** Integrate HITL handling into the existing EventConsumer  
**Estimated Effort:** 4-5 days  
**Dependencies:** Step 4 (HumanLoopHandler Callback)

---

## Overview

This step integrates HITL handling into the existing EventConsumer. The EventConsumer will now handle HITL-specific events like `InputRequiredEvent` and `AgentQuestionEvent`, managing the flow of questions to users and responses back to the agent.

## Files to Modify

- `components/event_consumer.py`

## Implementation Details

### EventConsumer Enhancements

1. **Add HITL event handlers** - Handle `InputRequiredEvent` and `AgentQuestionEvent`
2. **Integrate with spinner** - Pause/resume spinner during prompts
3. **Add HITL configuration** - Support timeout and default answer parameters

## Changes to EventConsumer

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

## Deliverables

- [ ] Add `_on_input_required()` handler
- [ ] Add `_on_agent_question()` handler
- [ ] Integrate with spinner pause/resume
- [ ] Add HITL configuration parameters (timeout, default_answer)
- [ ] Update event routing logic
- [ ] Add unit tests for new handlers

## Success Criteria

- [ ] `InputRequiredEvent` is handled correctly
- [ ] `AgentQuestionEvent` is handled correctly
- [ ] Spinner is paused during prompts
- [ ] Spinner is resumed after responses
- [ ] Responses are sent back to the workflow
- [ ] Timeout handling works correctly
- [ ] Unit tests pass

## Next Step

Step 6: Timeout Manager
