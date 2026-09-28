"""
Signal Handler Component

Manages OS signals for graceful shutdown of the Torvalds agent.

Handles SIGINT (Ctrl+C), SIGQUIT (Ctrl+\), and SIGTERM (kill <pid>).
Note: SIGKILL cannot be caught — use SIGTERM for graceful shutdown.

This component coordinates cleanup across all subsystems:
- Stops the spinner
- Cancels event consumers
- Ends the session in cache
- Resets state handlers
- Prints a goodbye message

Usage:
    signal_handler = SignalHandler(
        console=console,
        spinner=spinner_controller,
        state_handler=state_handler,
    )
    
    # Register with asyncio event loop
    loop = asyncio.get_event_loop()
    signal_handler.register(loop)
"""
import asyncio
import atexit
import os
import signal
import sys
from typing import Optional

from rich.console import Console

from components.spinner_controller import SpinnerController
from components.state_handler import StateHandler
from components.event_consumer import EventConsumer

# ---------------------------------------------------------------------------
# Configuration via environment variables
# ---------------------------------------------------------------------------
GRACEFUL_SHUTDOWN_ENABLED = os.environ.get("TORVALDS_GRACEFUL_SHUTDOWN", "true").lower() in ("true", "1", "yes")
SHUTDOWN_TIMEOUT = int(os.environ.get("TORVALDS_SHUTDOWN_TIMEOUT", "5"))
DUMP_STATE_ON_SIGQUIT = os.environ.get("TORVALDS_DUMP_STATE_ON_SIGQUIT", "false").lower() in ("true", "1", "yes")


class SignalHandler:
    """
    Manages OS signals for graceful shutdown of the Torvalds agent.

    Handles SIGINT (Ctrl+C), SIGQUIT (Ctrl+\), and SIGTERM (kill <pid>).
    Note: SIGKILL cannot be caught — use SIGTERM for graceful shutdown.

    Attributes:
        console: Rich Console instance for output
        spinner: SpinnerController instance
        state_handler: StateHandler instance
        event_consumer: Optional EventConsumer instance (set per-request)
        _loop: asyncio event loop reference
        _shutdown_initiated: Flag to prevent double shutdown
        _shutdown_lock: Async lock for thread-safe shutdown
    """

    def __init__(
        self,
        console: Console,
        spinner: SpinnerController,
        state_handler: StateHandler,
        event_consumer: Optional[EventConsumer] = None,
    ):
        self.console = console
        self.spinner = spinner
        self.state_handler = state_handler
        self.event_consumer = event_consumer
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._shutdown_initiated = False
        self._shutdown_lock = asyncio.Lock()
        self._registered_signals: list[int] = []

    def register(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        """
        Register signal handlers with the asyncio event loop.

        Args:
            loop: asyncio event loop (defaults to current event loop)
        """
        if not GRACEFUL_SHUTDOWN_ENABLED:
            return

        self._loop = loop or asyncio.get_event_loop()

        # Register handlers for catchable signals
        for sig in (signal.SIGINT, signal.SIGQUIT, signal.SIGTERM):
            self._loop.add_signal_handler(sig, self._handle_signal_sync, sig)
            self._registered_signals.append(sig)

        # Register atexit handler as fallback for normal exits
        atexit.register(self._atexit_handler)

    def unregister(self) -> None:
        """Unregister all signal handlers."""
        if self._loop is None:
            return

        for sig in self._registered_signals:
            try:
                self._loop.remove_signal_handler(sig)
            except Exception:
                pass  # Ignore errors during unregister
        self._registered_signals.clear()

    def _handle_signal_sync(self, sig: int) -> None:
        """
        Synchronous signal handler that schedules async shutdown.

        This is called by the event loop when a signal is received.
        It schedules the async shutdown method to run on the event loop.

        Args:
            sig: Signal number
        """
        if self._shutdown_initiated:
            return  # Prevent double shutdown

        self._shutdown_initiated = True
        sig_name = signal.Signals(sig).name

        # Schedule async shutdown on the event loop
        if self._loop and self._loop.is_running():
            asyncio.ensure_future(self._shutdown(sig, sig_name))
        else:
            # Fallback: run synchronously if loop not running
            self._shutdown_sync(sig, sig_name)

    def _atexit_handler(self) -> None:
        """Fallback handler for normal interpreter exit."""
        if self._shutdown_initiated:
            return

        try:
            self._end_session(exit_signal="EXIT")
            self.spinner.stop()
            self.console.print("[yellow]Goodbye![/yellow]")
        except Exception:
            pass  # Don't raise during atexit

    async def _shutdown(self, sig: int, sig_name: str) -> None:
        """
        Execute async shutdown sequence with lock to prevent race conditions.

        Args:
            sig: Signal number
            sig_name: Signal name for display
        """
        async with self._shutdown_lock:
            await self._shutdown_impl(sig, sig_name)

    async def _shutdown_impl(self, sig: int, sig_name: str) -> None:
        """
        Core shutdown implementation.

        Args:
            sig: Signal number
            sig_name: Signal name for display
        """
        try:
            self.console.print(f"\n[yellow]Received {sig_name}, shutting down...[/yellow]")

            # 1. Stop spinner
            try:
                self.spinner.stop()
            except Exception:
                pass  # Ignore spinner errors during shutdown

            # 2. Cancel event consumer if available
            if self.event_consumer and self.event_consumer.is_running:
                try:
                    self.event_consumer.cancel()
                except Exception:
                    pass  # Ignore cancel errors

            # 3. Handle SIGQUIT state dump if enabled
            if sig == signal.SIGQUIT and DUMP_STATE_ON_SIGQUIT:
                self._dump_state()

            # 4. End session in cache
            self._end_session(exit_signal=sig_name)

            # 5. Reset state handler
            try:
                self.state_handler.reset()
            except Exception:
                pass  # Ignore state reset errors

            # 6. Print goodbye
            self.console.print("[yellow]Goodbye![/yellow]")

        except Exception as e:
            self.console.print(f"[red]Error during shutdown: {e}[/red]")
            sys.exit(1)

        # 7. Exit cleanly
        sys.exit(0)

    def _shutdown_sync(self, sig: int, sig_name: str) -> None:
        """
        Synchronous fallback for shutdown when event loop is not running.

        Args:
            sig: Signal number
            sig_name: Signal name for display
        """
        try:
            self.console.print(f"\n[yellow]Received {sig_name}, shutting down...[/yellow]")

            self.spinner.stop()

            if self.event_consumer and self.event_consumer.is_running:
                self.event_consumer.cancel()

            if sig == signal.SIGQUIT and DUMP_STATE_ON_SIGQUIT:
                self._dump_state()

            self._end_session(exit_signal=sig_name)

            try:
                self.state_handler.reset()
            except Exception:
                pass

            self.console.print("[yellow]Goodbye![/yellow]")

        except Exception as e:
            self.console.print(f"[red]Error during shutdown: {e}[/red]")
            sys.exit(1)

        sys.exit(0)

    def _dump_state(self) -> None:
        """Dump current state for debugging (SIGQUIT only)."""
        try:
            state = self.state_handler.get_state_snapshot()
            self.console.print("\n[dim]=== State Dump ===[/dim]")
            for key, value in state.items():
                # Truncate long values
                val_str = str(value)
                if len(val_str) > 200:
                    val_str = val_str[:200] + "..."
                self.console.print(f"  {key}: {val_str}")
            self.console.print("[dim]=== End State Dump ===[/dim]\n")
        except Exception as e:
            self.console.print(f"[red]Error dumping state: {e}[/red]")

    def _end_session(self, exit_signal: str = "UNKNOWN") -> None:
        """
        End the current session in the cache.

        Args:
            exit_signal: Signal that triggered the shutdown
        """
        try:
            from agent_cache_system import end_session
            end_session(exit_signal=exit_signal)
        except Exception as e:
            self.console.print(f"[red]Error ending session: {e}[/red]")

    @property
    def is_shutdown_initiated(self) -> bool:
        """Check if shutdown has been initiated."""
        return self._shutdown_initiated

    @property
    def is_registered(self) -> bool:
        """Check if signal handlers are registered."""
        return len(self._registered_signals) > 0
