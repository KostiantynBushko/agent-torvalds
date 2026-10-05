# Step 1: Foundation - Custom HITL Events

**Step:** 1 of 9  
**Goal:** Define custom event classes for our HITL system  
**Estimated Effort:** 2-3 days

---

## Overview

This step establishes the foundation for Human-in-the-Loop (HITL) communication by creating custom event classes that will be used throughout the implementation. These events will serve as the primary communication mechanism between the agent and the human user.

## Files to Create

- `components/hitl_events.py`

## Implementation Details

### AgentQuestionEvent

This event signals that the agent has a question requiring human input.

**Fields:**
- `question`: The question to ask the user
- `question_id`: Unique identifier for this question
- `timeout`: Seconds to wait for response (default: 30)
- `default_answer`: Fallback answer if timeout (default: "")
- `input_type`: Type of input expected ("text", "yesno", "menu", "password")
- `options`: List of options for menu-type questions
- `context`: Additional context about why the question is being asked

### AgentAnswerEvent

This event carries the human's response back to the agent.

**Fields:**
- `question_id`: ID of the question being answered
- `answer`: The user's response
- `was_timeout`: Whether this was a timeout fallback

## Implementation

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

## Deliverables

- [ ] Create `AgentQuestionEvent` class with all required fields
- [ ] Create `AgentAnswerEvent` class with all required fields
- [ ] Add comprehensive docstrings for both classes
- [ ] Add unit tests for event serialization
- [ ] Verify events work with existing event system

## Success Criteria

- [ ] Events can be instantiated with all parameters
- [ ] Events serialize/deserialize correctly
- [ ] Unit tests pass
- [ ] Events integrate with existing event system

## Next Step

Step 2: Console Input Module
