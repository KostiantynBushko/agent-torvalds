"""
Spinner Controller Component

Manages the console spinner with pause/resume capabilities. This component
wraps the rich console.status spinner and provides pause() and resume()
methods so that toolkit modules can temporarily hide the spinner during
interactive dialogs (e.g., whiptail password prompts).
"""
from contextlib import contextmanager
from typing import Optional
from rich.console import Console


class SpinnerController:
    """
    Manages the console spinner with pause/resume capabilities.

    This class wraps the rich console.status spinner and provides
    pause() and resume() methods so that toolkit modules can temporarily
    hide the spinner during interactive dialogs (e.g., whiptail password prompts).

    Usage:
        spinner = SpinnerController(console, "[yellow]Processing...[/yellow]", spinner="dots")
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
        console: Console,
        status_text: str = "[yellow]Processing...[/yellow]",
        spinner_style: str = "dots",
    ):
        self.console = console
        self.status_text = status_text
        self.spinner_style = spinner_style
        self._status: Optional[object] = None  # The rich.Status object
        self._running: bool = False
        self._paused: bool = False

    def start(self) -> None:
        """Start the spinner if not already running."""
        if not self._running:
            self._status = self.console.status(
                self.status_text, spinner=self.spinner_style
            )
            self._status.start()
            self._running = True
            self._paused = False

    def stop(self) -> None:
        """Stop the spinner."""
        if self._running and self._status is not None:
            self._status.stop()
            self._status = None
            self._running = False
            self._paused = False

    def pause(self) -> None:
        """Pause (hide) the spinner temporarily."""
        if self._running and self._status is not None and not self._paused:
            self._status.stop()
            self._paused = True

    def resume(self) -> None:
        """Resume (show) the spinner after pause."""
        if self._running and self._paused:
            self._status = self.console.status(
                self.status_text, spinner=self.spinner_style
            )
            self._status.start()
            self._paused = False

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
