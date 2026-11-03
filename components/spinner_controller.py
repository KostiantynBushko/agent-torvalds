"""
Spinner Controller Component

Manages the console spinner with pause/resume capabilities. This component
wraps the rich console.status spinner and provides pause() and resume()
methods so that toolkit modules can temporarily hide the spinner during
interactive dialogs (e.g., whiptail password prompts).

This is the **single** spinner feature of the project.  It was
``components/spinner_controller.py`` and ``spinner_manager.py``, two
implementations of the same idea, and the second one was dead: nothing
imported it, no test reached it, and no toolkit used it.  They were
merged into this file, and the investigation is in
``investigate/spinner-consolidation/``.

What each of them had, and where it went:

    * ``components/spinner_controller.py`` had the thread safety and the
      error handling.  It is used by both orchestrators, by
      ``EventConsumer``, ``SignalHandler`` and ``HumanLoopHandler``, and by
      ten test files.  It is what survived.

    * ``spinner_manager.py`` had the lifecycle callback hooks, and a
      global singleton.  The hooks came here.  The singleton did not:
      nothing called it, and a module-level global is the opposite of how
      this codebase passes a dependency.  The spinner is handed to the
      three components that need it, and ``EventConsumer`` — the single
      place where the user is prompted — pauses and resumes it.

Key improvements:
    - Proper cleanup with error handling
    - Thread-safe state management
    - Console write protection to prevent race conditions
    - Lifecycle callback hooks (on_start, on_stop, on_pause, on_resume)
"""
import logging
import threading
import time
from contextlib import contextmanager
from typing import Callable, List, Optional
from rich.console import Console

logger = logging.getLogger(__name__)

# A lifecycle callback takes no arguments and returns nothing.
Callback = Callable[[], None]


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

    The lifecycle callbacks fire on each transition, so a caller can react
    to the spinner being hidden or shown:
        spinner.on_pause.append(lambda: print("the spinner is down"))
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
        self._lock = threading.Lock()  # Thread-safe state management

        # Lifecycle callbacks.  Each is a list of callables, so more than
        # one listener can subscribe.
        self.on_start: List[Callback] = []
        self.on_stop: List[Callback] = []
        self.on_pause: List[Callback] = []
        self.on_resume: List[Callback] = []

    def _fire_callbacks(self, callbacks: List[Callback]) -> None:
        """Fire every callback in a list.

        A callback that raises must not take the spinner down with it, so
        each one is called in its own guard and the failure is logged.
        """
        for cb in callbacks:
            try:
                cb()
            except Exception as e:
                logger.warning("Spinner callback error: %s", e)

    def start(self) -> None:
        """Start the spinner if not already running."""
        with self._lock:
            if not self._running:
                try:
                    self._status = self.console.status(
                        self.status_text, spinner=self.spinner_style
                    )
                    self._status.start()
                    self._running = True
                    self._paused = False
                except Exception:
                    # If start fails (e.g., console already in use), reset state
                    self._running = False
                    self._paused = False
                    self._status = None
                else:
                    self._fire_callbacks(self.on_start)

    def stop(self) -> None:
        """Stop the spinner with proper cleanup."""
        with self._lock:
            if self._running and self._status is not None:
                try:
                    self._status.stop()
                except Exception:
                    pass  # Ignore errors during stop
                finally:
                    # Small delay to ensure thread cleanup
                    time.sleep(0.01)
                    self._status = None
                    self._running = False
                    self._paused = False
                    self._fire_callbacks(self.on_stop)

    def pause(self) -> None:
        """Pause (hide) the spinner temporarily."""
        with self._lock:
            if self._running and self._status is not None and not self._paused:
                try:
                    self._status.stop()
                except Exception:
                    pass
                self._paused = True
                self._fire_callbacks(self.on_pause)

    def resume(self) -> None:
        """Resume (show) the spinner after pause."""
        with self._lock:
            if self._running and self._paused:
                try:
                    self._status = self.console.status(
                        self.status_text, spinner=self.spinner_style
                    )
                    self._status.start()
                    self._paused = False
                except Exception:
                    # If resume fails, mark as not running
                    self._running = False
                    self._paused = False
                    self._status = None
                else:
                    self._fire_callbacks(self.on_resume)

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
