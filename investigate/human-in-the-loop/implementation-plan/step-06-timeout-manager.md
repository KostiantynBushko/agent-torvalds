# Step 6: Timeout Manager

**Step:** 6 of 9  
**Goal:** Centralized timeout management for HITL prompts  
**Estimated Effort:** 2-3 days  
**Dependencies:** Step 2 (Console Input Module), Step 3 (Whiptail Input Module)

---

## Overview

This step implements a centralized timeout manager for HITL prompts. It provides a clean abstraction for wrapping async prompt functions with timeout handling, tracking timed-out questions, and providing fallback answers.

## Files to Create

- `components/timeout_manager.py`
- `tests/test_timeout_manager.py`

## Implementation Details

### TimeoutManager Class

The manager provides:

1. **`prompt_with_timeout()`** - Wrap any async prompt function with timeout
2. **Timeout logging** - Track all timed-out questions for review
3. **Fallback answers** - Provide default answers on timeout
4. **State management** - Reset and clear timeout logs

## Implementation

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

## Deliverables

- [ ] Create `TimeoutManager` class
- [ ] Implement `prompt_with_timeout()` method
- [ ] Add timeout logging functionality
- [ ] Implement `get_timeout_log()` method
- [ ] Implement `reset()` method
- [ ] Add unit tests
- [ ] Test with various timeout scenarios

## Success Criteria

- [ ] Timeout manager correctly wraps async functions
- [ ] Timeout logging works as expected
- [ ] Fallback answers are returned on timeout
- [ ] `get_timeout_log()` returns correct history
- [ ] `reset()` clears the log
- [ ] Unit tests pass
- [ ] Integration with input modules works correctly

## Next Step

Step 7: Runtime Toggle
