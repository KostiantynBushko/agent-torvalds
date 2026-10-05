# Step 4: HumanLoopHandler Callback

**Step:** 4 of 9  
**Goal:** Create a callback handler that intercepts when the agent needs human input  
**Estimated Effort:** 4-5 days  
**Dependencies:** Step 1 (Custom HITL Events), Step 2 (Console Input Module), Step 3 (Whiptail Input Module)

---

## Overview

This step implements the core HITL callback handler that detects when the agent needs clarification and manages the human input flow. It integrates with LlamaIndex's callback system to intercept events, detect questions, prompt users, and handle timeouts.

## Files to Create

- `components/human_loop_handler.py`
- `tests/test_human_loop_handler.py`

## Implementation Details

### HumanLoopHandler Class

The handler extends `BaseCallbackHandler` from LlamaIndex and provides:

1. **Event Detection** - Monitors `InputRequiredEvent` and `AgentOutput` events
2. **Question Detection** - Uses pattern matching to detect questions in agent output
3. **User Input** - Prompts users via console or whiptail
4. **Timeout Handling** - Provides fallback answers on timeout
5. **History Tracking** - Logs all questions and timeouts

## Implementation

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

## Deliverables

- [ ] Create `HumanLoopHandler` extending `BaseCallbackHandler`
- [ ] Implement `on_event_start()` and `on_event_end()` hooks
- [ ] Add question detection via LLM response pattern matching
- [ ] Add timeout logging and question history
- [ ] Integrate with spinner pause/resume
- [ ] Add unit tests
- [ ] Test with mocked events

## Success Criteria

- [ ] Handler correctly detects `InputRequiredEvent`
- [ ] Question patterns are matched in agent output
- [ ] User input is collected via configured method
- [ ] Timeout handling works correctly
- [ ] Spinner is paused/resumed during prompts
- [ ] Question history is tracked
- [ ] Unit tests pass

## Next Step

Step 5: EventConsumer Integration
