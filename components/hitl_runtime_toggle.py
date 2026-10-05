"""
Runtime Toggle for HITL (Human-in-the-Loop)

Provides a mechanism to dynamically enable/disable HITL during agent
execution without restarting. Supports interactive commands, environment
variable monitoring, and async-safe state management.

Usage:
    from components.hitl_runtime_toggle import HITLRuntimeToggle

    toggle = HITLRuntimeToggle(initial_state=True)

    # Toggle via API
    new_state = await toggle.toggle(source="user")

    # Check status
    status = await toggle.status()
"""

from __future__ import annotations

import asyncio
import os
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from rich.console import Console

logger = logging.getLogger(__name__)

# Recognized inline commands
HITL_COMMANDS: frozenset = frozenset({
    "toggle-hitl",
    "hitl-status",
    "hitl-on",
    "hitl-off",
    "hitl-help",
})


class HITLRuntimeToggle:
    """Runtime toggle for Human-in-the-Loop mode.

    Allows enabling/disabling HITL during agent execution via:
    1. Interactive command (e.g., typing 'toggle-hitl' during execution)
    2. Environment variable change detection
    3. API calls

    Thread-safe state management with atomic toggle operations.

    Attributes:
        is_enabled: Current HITL enabled state.
        toggle_count: Number of times toggle has been invoked.
    """

    def __init__(
        self,
        initial_state: bool = True,
        console: Optional[Console] = None,
        env_var: str = "HITL_ENABLED",
    ) -> None:
        """Initialise the runtime toggle.

        Args:
            initial_state: Whether HITL is enabled at start.
            console: Rich Console for status messages.
            env_var: Environment variable name to monitor for changes.
        """
        self._enabled = initial_state
        self._console = console or Console()
        self._lock = asyncio.Lock()
        self._toggle_count = 0
        self._last_toggled_by: str = "init"
        self._last_toggle_time: Optional[datetime] = None
        self._env_var = env_var
        self._toggle_history: List[Dict[str, Any]] = []

        # Log initial state
        logger.info("HITLRuntimeToggle initialised — initial_state=%s", initial_state)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_enabled(self) -> bool:
        """Current HITL enabled state."""
        return self._enabled

    @property
    def toggle_count(self) -> int:
        """Number of times toggle has been invoked."""
        return self._toggle_count

    # ------------------------------------------------------------------
    # Core Toggle Operations
    # ------------------------------------------------------------------

    async def toggle(self, source: str = "user") -> bool:
        """Toggle HITL on/off.

        Args:
            source: Who/what triggered the toggle ("user", "env", "api", "init",
                    "interactive").

        Returns:
            New state after toggle.
        """
        async with self._lock:
            self._enabled = not self._enabled
            self._toggle_count += 1
            self._last_toggled_by = source
            self._last_toggle_time = datetime.now()

            # Record history
            self._toggle_history.append({
                "action": "toggle",
                "new_state": self._enabled,
                "source": source,
                "timestamp": self._last_toggle_time.isoformat(),
            })

            self._print_status(source)
            return self._enabled

    async def set_state(self, enabled: bool, source: str = "user") -> None:
        """Set HITL state explicitly.

        Args:
            enabled: True to enable, False to disable.
            source: Who/what triggered the change.
        """
        async with self._lock:
            if self._enabled != enabled:
                self._enabled = enabled
                self._toggle_count += 1
                self._last_toggled_by = source
                self._last_toggle_time = datetime.now()

                # Record history
                self._toggle_history.append({
                    "action": "set",
                    "new_state": enabled,
                    "source": source,
                    "timestamp": self._last_toggle_time.isoformat(),
                })

                self._print_status(source)

    async def status(self) -> Dict[str, Any]:
        """Get current toggle status.

        Returns:
            Dict with current state info.
        """
        async with self._lock:
            return {
                "enabled": self._enabled,
                "toggle_count": self._toggle_count,
                "last_toggled_by": self._last_toggled_by,
                "last_toggle_time": self._last_toggle_time.isoformat() if self._last_toggle_time else None,
            }

    def status_sync(self) -> Dict[str, Any]:
        """Synchronous version of status() for non-async contexts."""
        return {
            "enabled": self._enabled,
            "toggle_count": self._toggle_count,
            "last_toggled_by": self._last_toggled_by,
            "last_toggle_time": self._last_toggle_time.isoformat() if self._last_toggle_time else None,
        }

    # ------------------------------------------------------------------
    # Command Parsing
    # ------------------------------------------------------------------

    async def process_command(self, command: str) -> Optional[str]:
        """Process an inline command string.

        Recognised commands:
        - ``toggle-hitl`` — Toggle HITL on/off
        - ``hitl-status`` — Show current status
        - ``hitl-on`` — Enable HITL
        - ``hitl-off`` — Disable HITL
        - ``hitl-help`` — Show available commands

        Args:
            command: Raw command string (case-insensitive).

        Returns:
            Response message or ``None`` if command not recognised.
        """
        cmd = command.lower().strip()

        if cmd == "toggle-hitl":
            await self.toggle(source="interactive")
            return f"HITL {'enabled' if self._enabled else 'disabled'}"

        elif cmd == "hitl-status":
            st = await self.status()
            return (
                f"HITL Status: {'🟢 ENABLED' if st['enabled'] else '🔴 DISABLED'}\n"
                f"  Toggles: {st['toggle_count']}\n"
                f"  Last by: {st['last_toggled_by']}"
            )

        elif cmd == "hitl-on":
            await self.set_state(True, source="interactive")
            return "HITL enabled"

        elif cmd == "hitl-off":
            await self.set_state(False, source="interactive")
            return "HITL disabled"

        elif cmd == "hitl-help":
            return (
                "Available HITL commands:\n"
                "  toggle-hitl  — Toggle HITL on/off\n"
                "  hitl-status  — Show current status\n"
                "  hitl-on      — Enable HITL\n"
                "  hitl-off     — Disable HITL\n"
                "  hitl-help    — Show this help"
            )

        return None

    def is_hitl_command(self, text: str) -> bool:
        """Check if text is a recognised HITL command.

        Args:
            text: Text to check.

        Returns:
            True if text matches a known command.
        """
        return text.lower().strip() in HITL_COMMANDS

    # ------------------------------------------------------------------
    # Environment Variable Monitoring
    # ------------------------------------------------------------------

    async def check_env_var(self) -> bool:
        """Check if environment variable has changed and update state.

        Returns:
            True if state was updated.
        """
        env_value = os.environ.get(self._env_var, "").lower()

        if not env_value:
            return False

        # Parse environment value
        new_state = env_value in ("1", "true", "yes", "on", "enabled")

        if self._enabled != new_state:
            await self.set_state(new_state, source="env")
            return True

        return False

    # ------------------------------------------------------------------
    # History & Stats
    # ------------------------------------------------------------------

    def get_toggle_history(self) -> List[Dict[str, Any]]:
        """Return a copy of the toggle history."""
        return list(self._toggle_history)

    def get_stats(self) -> Dict[str, Any]:
        """Return summary statistics about toggle usage.

        Returns:
            Dictionary with keys:
            - ``current_state``: Whether HITL is currently enabled.
            - ``total_toggles``: Number of toggle operations.
            - ``sources``: Set of unique sources that triggered toggles.
            - ``first_toggle``: Timestamp of first toggle (or ``None``).
            - ``last_toggle``: Timestamp of most recent toggle (or ``None``).
        """
        if not self._toggle_history:
            return {
                "current_state": self._enabled,
                "total_toggles": 0,
                "sources": set(),
                "first_toggle": None,
                "last_toggle": None,
            }

        sources = {entry["source"] for entry in self._toggle_history}

        return {
            "current_state": self._enabled,
            "total_toggles": len(self._toggle_history),
            "sources": sources,
            "first_toggle": self._toggle_history[0]["timestamp"],
            "last_toggle": self._toggle_history[-1]["timestamp"],
        }

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _print_status(self, source: str) -> None:
        """Print status message to console."""
        status = "🟢 ENABLED" if self._enabled else "🔴 DISABLED"
        self._console.print(
            f"\n[bold cyan]HITL Toggle[/bold cyan]: {status} "
            f"(by {source}, toggle #{self._toggle_count})"
        )

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"HITLRuntimeToggle(enabled={self._enabled}, "
            f"toggle_count={self._toggle_count})"
        )

    def reset(self) -> None:
        """Clear toggle history."""
        self._toggle_history.clear()
        logger.info("HITLRuntimeToggle history cleared")