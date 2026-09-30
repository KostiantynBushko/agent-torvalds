# Step 7: Runtime Toggle

**Step:** 7 of 9  
**Goal:** Allow users to dynamically enable/disable HITL during agent execution  
**Estimated Effort:** 3-4 days  
**Dependencies:** Step 4 (HumanLoopHandler Callback), Step 5 (EventConsumer Integration)

---

## Overview

This step implements a runtime toggle mechanism that allows users to enable or disable HITL during agent execution without restarting. This provides flexibility to toggle HITL on/off based on user preferences or system conditions.

## Files to Create

- `components/hitl_runtime_toggle.py`
- `tests/test_hitl_runtime_toggle.py`

## Implementation Details

### HITLRuntimeToggle Class

The toggle provides:

1. **Async-safe state management** - Thread-safe toggle operations
2. **Interactive commands** - `toggle-hitl`, `hitl-status`, etc.
3. **Environment variable monitoring** - Hot-reload from env vars
4. **Status tracking** - Track toggle history and source

## Implementation

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

### Integration with HumanLoopHandler

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

## Deliverables

- [ ] Create `HITLRuntimeToggle` class with async-safe state management
- [ ] Add inline command parsing (`toggle-hitl`, `hitl-status`, etc.)
- [ ] Integrate with `HumanLoopHandler` and `EventConsumer`
- [ ] Add environment variable hot-reload support
- [ ] Add unit tests for toggle state transitions
- [ ] Add visual status indicator in agent output

## Success Criteria

- [ ] Toggle can be enabled/disabled during execution
- [ ] Inline commands are properly parsed and handled
- [ ] State transitions are thread-safe
- [ ] Environment variable changes are detected
- [ ] Visual status indicator works correctly
- [ ] Unit tests pass

## Next Step

Step 8: Agent Integration
