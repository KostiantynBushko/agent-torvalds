"""
Agent State Handler

Manages agent state during workflow execution. Tracks workflow status,
tool call history, errors, and interactive prompts. Provides state
snapshots and persistence capabilities.

Usage:
    state = StateHandler()
    state.set("current_tool", "execute_shell_command")
    state.increment("tool_calls")
    snapshot = state.get_state_snapshot()
"""
from typing import Any, Dict, List, Optional
from datetime import datetime


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
        self._state: Dict[str, Any] = self._default_state()

    @staticmethod
    def _default_state() -> Dict[str, Any]:
        return {
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

    def add_tool_call(self, tool_name: str, result: Any, error: bool = False) -> None:
        """Record tool call in history."""
        self._state["tool_history"].append({
            "tool": tool_name,
            "result": str(result)[:500] if result else None,  # Truncate long results
            "error": error,
            "timestamp": datetime.now().isoformat(),
        })

    def add_error(self, error: str) -> None:
        """Record error."""
        self._state["errors"].append({
            "error": error,
            "timestamp": datetime.now().isoformat(),
        })

    def add_interactive_prompt(self, prompt_type: str, message: str) -> None:
        """Record interactive prompt."""
        self._state["interactive_prompts"].append({
            "type": prompt_type,
            "message": message,
            "timestamp": datetime.now().isoformat(),
        })

    def get_state_snapshot(self) -> Dict[str, Any]:
        """Get current state snapshot."""
        return self._state.copy()

    def reset(self) -> None:
        """Reset state for new workflow."""
        self._state = self._default_state()

    def get_tool_summary(self) -> Dict[str, Any]:
        """Get summary of tool calls."""
        total = len(self._state["tool_history"])
        errors = sum(1 for t in self._state["tool_history"] if t.get("error"))
        return {
            "total_tool_calls": total,
            "errors": errors,
            "success": total - errors,
        }

    def get_errors(self) -> List[Dict[str, Any]]:
        """Get all recorded errors."""
        return self._state["errors"].copy()

    def get_tool_history(self) -> List[Dict[str, Any]]:
        """Get tool call history."""
        return self._state["tool_history"].copy()

    @property
    def is_running(self) -> bool:
        """Check if workflow is running."""
        return self._state.get("workflow_running", False)

    @property
    def is_paused(self) -> bool:
        """Check if workflow is paused."""
        return self._state.get("workflow_paused", False)
