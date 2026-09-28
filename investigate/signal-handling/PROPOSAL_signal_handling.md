# Signal Handling for Torvalds AI Agent

## Proposal: Graceful Shutdown with Signal Handling

**Status:** Proposal  
**Date:** 2026-09-13  
**Author:** Torvalds AI Agent  
**Location:** `self-development/investigate/signal-handling/`  

---

## 1. Executive Summary

This proposal outlines the implementation of signal handling for the Torvalds AI Agent to enable graceful shutdown on `SIGINT`, `SIGKILL`, and `SIGQUIT`. The goal is to ensure the agent saves the current session state, cleans up resources, and exits cleanly when interrupted by the user or system.

---

## 2. Problem Statement

Currently, when the Torvalds agent is running in interactive mode and receives an interrupt signal:
- **No graceful shutdown** occurs — the session is not properly ended
- **Session data is lost** — the active session in the cache is not marked as ended
- **Resources are not cleaned up** — spinner, event consumers, and state handlers may leave dangling state
- **User experience is degraded** — no farewell message or summary is shown

This is problematic for:
- Long-running sessions where users want to preserve session metadata
- Automation scripts that rely on clean exit codes
- Debugging and error tracking (abrupt exits don't log properly)

---

## 3. Signal Definitions & Capabilities

| Signal | Source | Catchable? | Typical Trigger | Action Required |
|--------|--------|------------|-----------------|-----------------|
| `SIGINT` | User | ✅ Yes | `Ctrl+C` | Save session, stop spinner, print goodbye |
| `SIGQUIT` | User | ✅ Yes | `Ctrl+\` | Save session, dump state (optional), exit |
| `SIGKILL` | User/System | ❌ No | `kill -9 <pid>` | Cannot be caught; see §5.3 for mitigation |

### 3.1 Important Note on SIGKILL

`SIGKILL` (signal 9) **cannot be caught, blocked, or ignored** by any process. It is a hard kill issued by the kernel. We cannot register a handler for it. However, we can:

1. **Document this limitation** to users
2. **Provide a SIGTERM handler** as the "graceful kill" alternative (`kill <pid>`)
3. **Use `atexit` registration** as a fallback for normal exits
4. **Consider `SIGUSR1`/`SIGUSR2`** for custom shutdown hooks if needed

---

## 4. Current Architecture Analysis

### 4.1 Main Loop (`agent-torvalds.py`)

```python
async def main():
    # ... setup ...
    start_session()  # ← Session started here
    agent = create_agent(...)
    
    while True:
        cmd = console.input(">>> ").strip()
        # ... process command ...
    
    # Manual exit: \exit or \quit
    end_session()
    console.print("Goodbye!")
```

**Issues:**
- No signal handlers registered
- `end_session()` is only called on manual `\exit`/`\quit`
- No cleanup of `spinner_controller`, `EventConsumer`, or `StateHandler`

### 4.2 Session Management (`agent_cache_system.py`)

```python
def start_session() -> str:
    cache["sessions"].append({
        "started_at": datetime.now(timezone.utc).isoformat(),
        "commands_run": 0,
    })
    _save_cache(cache)

def end_session() -> str:
    sessions = cache.get("sessions", [])
    if sessions:
        sessions[-1]["ended_at"] = datetime.now(timezone.utc).isoformat()
        _save_cache(cache)
```

**Capabilities:**
- Sessions track `started_at`, `commands_run`, and `ended_at`
- `_save_cache()` uses atomic writes (write to `.tmp`, then `os.replace`)
- Session data persists to `~/.cache/torvalds/agent_cache.json`

### 4.3 Components Architecture

| Component | Role | Cleanup Needed? |
|-----------|------|-----------------|
| `SpinnerController` | Console spinner | ✅ `stop()` method exists |
| `StateHandler` | Workflow state | ✅ `reset()` method exists |
| `EventConsumer` | Event streaming | ✅ `cancel()` method exists |
| `agent_chat_memory` | PostgreSQL memory | ✅ Connection cleanup needed |

---

## 5. Proposed Solution

### 5.1 Architecture: Signal Handler Component

Create a new component `components/signal_handler.py` that:
1. Registers signal handlers for `SIGINT`, `SIGQUIT`, `SIGTERM`
2. Integrates with asyncio event loop
3. Coordinates cleanup across all subsystems
4. Saves session state before exit

### 5.2 Signal Flow Diagram

```
User presses Ctrl+C (SIGINT)
        │
        ▼
┌─────────────────────┐
│ Signal Handler      │
│ (signal_handler.py) │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ 1. Stop Spinner     │
│    spinner.stop()   │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ 2. Cancel Events    │
│    consumer.cancel()│
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ 3. End Session      │
│    end_session()    │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ 4. Print Summary    │
│    console.print()  │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│ 5. Exit Cleanly     │
│    sys.exit(0)      │
└─────────────────────┘
```

### 5.3 SIGKILL Mitigation Strategy

Since `SIGKILL` cannot be caught:

1. **Recommend `SIGTERM`** as the graceful alternative:
   - `kill <pid>` sends `SIGTERM` (default)
   - Our handler catches `SIGTERM` and does graceful shutdown
   
2. **Use `atexit` module** as a safety net:
   - Registers cleanup to run on normal interpreter exit
   - Covers cases where signals are not caught

3. **Document the limitation** in README and help text

---

## 6. Implementation Plan

### 6.1 New Files

| File | Purpose |
|------|---------|
| `components/signal_handler.py` | Signal handler component with cleanup orchestration |
| `investigate/signal-handling/PROPOSAL_signal_handling.md` | This document |

### 6.2 Modified Files

| File | Changes |
|------|---------|
| `agent-torvalds.py` | Import and initialize signal handler in `main()` |
| `components/__init__.py` | Export `SignalHandler` class |
| `agent_cache_system.py` | Add optional `exit_code` field to session end |

### 6.3 Component Design: `SignalHandler`

```python
class SignalHandler:
    """
    Manages OS signals for graceful shutdown of the Torvalds agent.
    
    Handles SIGINT (Ctrl+C), SIGQUIT (Ctrl+\), and SIGTERM (kill <pid>).
    Note: SIGKILL cannot be caught — use SIGTERM for graceful shutdown.
    """
    
    def __init__(
        self,
        console: Console,
        spinner: SpinnerController,
        event_consumer: EventConsumer,
        state_handler: StateHandler,
    ):
        self.console = console
        self.spinner = spinner
        self.event_consumer = event_consumer
        self.state_handler = state_handler
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._shutdown_initiated = False
        
    def register(self, loop: asyncio.AbstractEventLoop) -> None:
        """Register signal handlers with the asyncio event loop."""
        self._loop = loop
        for sig in (signal.SIGINT, signal.SIGQUIT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._handle_signal, sig)
            
    async def _handle_signal(self, sig: int) -> None:
        """Handle incoming signal — perform graceful shutdown."""
        if self._shutdown_initiated:
            return  # Prevent double shutdown
        self._shutdown_initiated = True
        
        sig_name = signal.Signals(sig).name
        self.console.print(f"\n[yellow]Received {sig_name}, shutting down...[/yellow]")
        
        try:
            await self._shutdown(sig)
        except Exception as e:
            self.console.print(f"[red]Error during shutdown: {e}[/red]")
            sys.exit(1)
            
    async def _shutdown(self, sig: int) -> None:
        """Execute shutdown sequence."""
        # 1. Stop spinner
        self.spinner.stop()
        
        # 2. Cancel event consumer
        self.event_consumer.cancel()
        
        # 3. End session in cache
        from agent_cache_system import end_session
        end_session()
        
        # 4. Print goodbye
        self.console.print("[yellow]Goodbye![/yellow]")
        
        # 5. Exit
        sys.exit(0)
```

### 6.4 Integration in `agent-torvalds.py`

```python
async def main():
    # ... existing setup ...
    
    # Initialize signal handler
    signal_handler = SignalHandler(
        console=console,
        spinner=spinner_controller,
        event_consumer=None,  # Will be set per-request
        state_handler=StateHandler(),
    )
    
    # Register signals with the event loop
    loop = asyncio.get_event_loop()
    signal_handler.register(loop)
    
    # ... rest of main loop ...
```

---

## 7. Testing Strategy

### 7.1 Manual Testing

| Test | Command | Expected Result |
|------|---------|-----------------|
| SIGINT | `Ctrl+C` | Session saved, goodbye message, exit code 0 |
| SIGQUIT | `Ctrl+\` | Session saved, goodbye message, exit code 0 |
| SIGTERM | `kill <pid>` | Session saved, goodbye message, exit code 0 |
| SIGKILL | `kill -9 <pid>` | Hard exit (session may not save — documented) |
| Double signal | `Ctrl+C` twice rapidly | No crash, idempotent shutdown |
| During tool call | `Ctrl+C` while spinner active | Spinner stops, session saves |

### 7.2 Automated Testing

```python
# tests/test_signal_handler.py
import signal
import asyncio
import pytest

class TestSignalHandler:
    async def test_sigint_handling(self):
        """Test that SIGINT triggers graceful shutdown."""
        handler = SignalHandler(...)
        loop = asyncio.get_event_loop()
        handler.register(loop)
        
        # Simulate signal
        os.kill(os.getpid(), signal.SIGINT)
        # Verify session was ended
        
    async def test_sigquit_handling(self):
        """Test that SIGQUIT triggers graceful shutdown."""
        handler = SignalHandler(...)
        loop = asyncio.get_event_loop()
        handler.register(loop)
        
        os.kill(os.getpid(), signal.SIGQUIT)
        # Verify session was ended
        
    async def test_double_signal_idempotency(self):
        """Test that sending signal twice doesn't crash."""
        handler = SignalHandler(...)
        loop = asyncio.get_event_loop()
        handler.register(loop)
        
        os.kill(os.getpid(), signal.SIGINT)
        os.kill(os.getpid(), signal.SIGINT)
        # Should not raise exception
```

---

## 8. Configuration Options

### 8.1 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TORVALDS_GRACEFUL_SHUTDOWN` | `true` | Enable/disable signal handling |
| `TORVALDS_SHUTDOWN_TIMEOUT` | `5` | Seconds to wait before forced exit |
| `TORVALDS_DUMP_STATE_ON_SIGQUIT` | `false` | Dump full state on SIGQUIT (debug) |

### 8.2 CLI Arguments

```bash
python agent-torvalds.py --no-signal-handling  # Disable signal handlers
```

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Signal during async operation | Deadlock | Use `loop.call_soon_threadsafe()` |
| Double signal before first completes | Crash | Idempotent `_shutdown_initiated` flag |
| SIGKILL loses session data | Data loss | Document limitation; recommend `SIGTERM` |
| Spinner stop fails | Console corruption | Wrap in try/except; always proceed |
| Cache write fails during shutdown | Session not saved | Log error but still exit cleanly |

---

## 10. Alternative Approaches Considered

### 10.1 Option A: Global Signal Handlers (Non-asyncio)

```python
signal.signal(signal.SIGINT, handler)
```
**Pros:** Simple, works outside asyncio  
**Cons:** Doesn't integrate well with async event loop; can cause race conditions  

### 10.2 Option B: Context Manager for Main Loop

```python
with GracefulShutdown() as ctx:
    while True:
        # ...
```
**Pros:** Clean Pythonic API  
**Cons:** Doesn't handle signals during tool execution  

### 10.3 Option C: Background Watcher Thread

```python
threading.Thread(target=watch_signals).start()
```
**Pros:** Decoupled from main loop  
**Cons:** Complex threading; race conditions; overkill  

**Selected Approach:** Option 1 (asyncio signal handlers) — best integration with existing async architecture.

---

## 11. Dependencies

- Python `signal` module (stdlib)
- Python `atexit` module (stdlib)
- Existing: `agent_cache_system.end_session()`
- Existing: `SpinnerController.stop()`
- Existing: `EventConsumer.cancel()`
- Existing: `StateHandler.reset()`

**No new external dependencies required.**

---

## 12. Rollout Plan

### Phase 1: Core Implementation
- [ ] Create `components/signal_handler.py`
- [ ] Integrate into `agent-torvalds.py`
- [ ] Add `atexit` fallback

### Phase 2: Testing & Hardening
- [ ] Manual testing of all signal types
- [ ] Add unit tests
- [ ] Test idempotency (double signals)
- [ ] Test during active tool execution

### Phase 3: Documentation
- [ ] Update README with signal handling info
- [ ] Add help text in agent console
- [ ] Document SIGKILL limitation

---

## 13. Acceptance Criteria

- [ ] `Ctrl+C` (SIGINT) saves session and exits cleanly
- [ ] `Ctrl+\` (SIGQUIT) saves session and exits cleanly
- [ ] `kill <pid>` (SIGTERM) saves session and exits cleanly
- [ ] Spinner is always stopped before exit
- [ ] Session `ended_at` timestamp is recorded in cache
- [ ] No crashes on double signal
- [ ] User sees goodbye message before exit
- [ ] Exit code is 0 on graceful shutdown
- [ ] SIGKILL limitation is documented

---

## 14. Appendix

### A. Linux Signal Reference

```bash
# Send SIGINT (graceful, catchable)
kill -INT <pid>

# Send SIGQUIT (graceful, catchable)
kill -QUIT <pid>

# Send SIGTERM (graceful, catchable) — RECOMMENDED
kill <pid>

# Send SIGKILL (hard, NOT catchable) — AVOID
kill -9 <pid>
kill -KILL <pid>
```

### B. Session Cache Structure

```json
{
  "sessions": [
    {
      "started_at": "2026-09-13T10:00:00Z",
      "commands_run": 42,
      "ended_at": "2026-09-13T10:30:00Z",
      "exit_signal": "SIGINT"
    }
  ]
}
```

### C. Existing Session Functions

| Function | Module | Purpose |
|----------|--------|---------|
| `start_session()` | `agent_cache_system` | Creates new session entry |
| `end_session()` | `agent_cache_system` | Marks session as ended |
| `increment_session_commands()` | `agent_cache_system` | Increments command counter |
| `log_error()` | `agent_cache_system` | Logs errors to cache |

---

*End of Proposal*
