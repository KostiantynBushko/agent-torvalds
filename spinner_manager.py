"""
Spinner Manager - Shared console spinner with pause/resume and callback hooks.

This module provides a global spinner controller that can be imported by any
toolkit module to pause/resume the console spinner during interactive operations
(whiptail dialogs, password prompts, etc.).

Architecture:
    agent-torvalds.py  ──imports──>  spinner_manager.py  <──imports──  agent_apt_toolkit.py
                                     (shared singleton)

Key Features:
    - Global singleton accessible from any module via `get_spinner()`
    - pause() / resume() methods for temporary hiding during dialogs
    - Context manager `pause_context()` for automatic pause/resume
    - Callback hooks: `on_start`, `on_stop`, `on_pause`, `on_resume`
    - Lifecycle callbacks for whiptail integration

Usage:
    from spinner_manager import get_spinner

    spinner = get_spinner()
    spinner.start()

    # Manual pause/resume
    spinner.pause()
    # ... show whiptail dialog ...
    spinner.resume()

    # Context manager (preferred)
    with spinner.pause_context():
        # ... show whiptail dialog (spinner hidden) ...

    spinner.stop()

    # Callback hooks
    spinner.on_pause.append(lambda: print("Spinner paused!"))
    spinner.on_resume.append(lambda: print("Spinner resumed!"))
"""

import logging
from typing import Callable, List, Optional
from contextlib import contextmanager
from rich.console import Console

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Global console instance (shared across modules)
# ---------------------------------------------------------------------------
_console: Optional[Console] = None


def get_console() -> Console:
    """Get or create the global console instance."""
    global _console
    if _console is None:
        _console = Console()
    return _console


# ---------------------------------------------------------------------------
# Callback types
# ---------------------------------------------------------------------------
Callback = Callable[[], None]


# ---------------------------------------------------------------------------
# Spinner Manager
# ---------------------------------------------------------------------------
class SpinnerManager:
    """
    Manages the console spinner with pause/resume and callback hooks.

    This class wraps the rich console.status spinner and provides
    pause() and resume() methods so that toolkit modules can temporarily
    hide the spinner during interactive dialogs (e.g., whiptail password prompts).

    Callback hooks:
        - on_start: Called when spinner starts
        - on_stop: Called when spinner stops
        - on_pause: Called when spinner is paused (before dialog)
        - on_resume: Called when spinner is resumed (after dialog)

    Usage:
        spinner = get_spinner()
        spinner.start()
        try:
            spinner.pause()       # Hide spinner before whiptail dialog
            # ... show whiptail dialog ...
            spinner.resume()      # Show spinner again after dialog
        finally:
            spinner.stop()

    Can also be used as a context manager:
        with spinner.pause_context():
            # ... show whiptail dialog (spinner hidden) ...
    """

    def __init__(
        self,
        console: Optional[Console] = None,
        status_text: str = "[yellow]Processing...[/yellow]",
        spinner_style: str = "dots",
    ):
        self.console = console or get_console()
        self.status_text = status_text
        self.spinner_style = spinner_style
        self._status: Optional[object] = None  # The rich.Status object
        self._running: bool = False
        self._paused: bool = False

        # Callback hooks (lists of callable)
        self.on_start: List[Callback] = []
        self.on_stop: List[Callback] = []
        self.on_pause: List[Callback] = []
        self.on_resume: List[Callback] = []

    def _fire_callbacks(self, callbacks: List[Callback]) -> None:
        """Fire all callbacks in a list, logging errors."""
        for cb in callbacks:
            try:
                cb()
            except Exception as e:
                logger.warning(f"Spinner callback error: {e}")

    def start(self) -> None:
        """Start the spinner if not already running."""
        if not self._running:
            self._status = self.console.status(
                self.status_text, spinner=self.spinner_style
            )
            self._status.start()
            self._running = True
            self._paused = False
            self._fire_callbacks(self.on_start)
            logger.info("Spinner started")

    def stop(self) -> None:
        """Stop the spinner."""
        if self._running and self._status is not None:
            self._status.stop()
            self._status = None
            self._running = False
            self._paused = False
            self._fire_callbacks(self.on_stop)
            logger.info("Spinner stopped")

    def pause(self) -> None:
        """Pause (hide) the spinner temporarily."""
        if self._running and self._status is not None and not self._paused:
            self._status.stop()
            self._paused = True
            self._fire_callbacks(self.on_pause)
            logger.info("Spinner paused")

    def resume(self) -> None:
        """Resume (show) the spinner after pause."""
        if self._running and self._paused:
            self._status = self.console.status(
                self.status_text, spinner=self.spinner_style
            )
            self._status.start()
            self._paused = False
            self._fire_callbacks(self.on_resume)
            logger.info("Spinner resumed")

    @contextmanager
    def pause_context(self):
        """
        Context manager to pause the spinner for a block of code.

        Usage:
            with spinner.pause_context():
                # ... interactive dialog here ...
        """
        self.pause()
        try:
            yield
        finally:
            self.resume()

    @property
    def is_running(self) -> bool:
        """Check if the spinner is currently running."""
        return self._running

    @property
    def is_paused(self) -> bool:
        """Check if the spinner is currently paused."""
        return self._paused


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------
_global_spinner: Optional[SpinnerManager] = None


def get_spinner() -> SpinnerManager:
    """
    Get the global spinner manager instance.

    Returns the singleton SpinnerManager. Creates it if it doesn't exist yet.

    Returns:
        SpinnerManager instance
    """
    global _global_spinner
    if _global_spinner is None:
        _global_spinner = SpinnerManager()
    return _global_spinner


def reset_spinner() -> None:
    """Reset the global spinner (for testing)."""
    global _global_spinner
    if _global_spinner is not None:
        _global_spinner.stop()
    _global_spinner = None


# ---------------------------------------------------------------------------
# Convenience functions for toolkit modules
# ---------------------------------------------------------------------------

def pause_spinner() -> None:
    """Pause the global spinner. Safe to call even if spinner isn't running."""
    try:
        get_spinner().pause()
    except Exception as e:
        logger.warning(f"Failed to pause spinner: {e}")


def resume_spinner() -> None:
    """Resume the global spinner. Safe to call even if spinner isn't paused."""
    try:
        get_spinner().resume()
    except Exception as e:
        logger.warning(f"Failed to resume spinner: {e}")


def spinner_pause_context():
    """
    Context manager to pause the global spinner.

    Usage:
        with spinner_pause_context():
            # ... interactive dialog here ...
    """
    return get_spinner().pause_context()
