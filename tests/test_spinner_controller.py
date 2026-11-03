"""
Unit tests for the spinner controller.

The spinner is the one component that had **no** tests at all: the two
implementations it grew out of were covered only by the tests of the
components that use them.  These cover the class on its own — its state
transitions, and the lifecycle callbacks that came over from the
``spinner_manager.py`` that was merged into it.

The console is faked, so the tests neither animate nor need a terminal.
"""
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from components.spinner_controller import SpinnerController  # noqa: E402


class FakeStatus:
    """Stands in for ``rich.console.Status``."""

    def __init__(self, console, text, spinner):
        self.console = console
        self.text = text
        self.spinner = spinner
        self.started = 0
        self.stopped = 0

    def start(self) -> None:
        self.started += 1

    def stop(self) -> None:
        self.stopped += 1


class FakeConsole:
    """A console that hands out FakeStatus objects and records them."""

    def __init__(self, fail_on_start: bool = False):
        self.fail_on_start = fail_on_start
        self.statuses = []

    def status(self, text, spinner=None):
        if self.fail_on_start:
            raise RuntimeError("the console is already in use")
        st = FakeStatus(self, text, spinner)
        self.statuses.append(st)
        return st


def make_spinner(**kwargs):
    console = kwargs.pop("console", None) or FakeConsole()
    spinner = SpinnerController(console=console, **kwargs)
    return spinner, console


class TestSpinnerState(unittest.TestCase):
    """The state transitions the rest of the code relies on."""

    def test_a_new_spinner_is_not_running(self):
        spinner, _ = make_spinner()
        self.assertFalse(spinner.is_running)
        self.assertFalse(spinner.is_paused)

    def test_start_makes_the_spinner_running(self):
        spinner, console = make_spinner()
        spinner.start()
        self.assertTrue(spinner.is_running)
        self.assertFalse(spinner.is_paused)
        self.assertEqual(len(console.statuses), 1)
        self.assertEqual(console.statuses[0].started, 1)

    def test_start_is_idempotent(self):
        """Starting twice must not start two spinners."""
        spinner, console = make_spinner()
        spinner.start()
        spinner.start()
        self.assertEqual(len(console.statuses), 1)
        self.assertEqual(console.statuses[0].started, 1)

    def test_stop_makes_the_spinner_not_running(self):
        spinner, console = make_spinner()
        spinner.start()
        spinner.stop()
        self.assertFalse(spinner.is_running)
        self.assertFalse(spinner.is_paused)
        self.assertEqual(console.statuses[0].stopped, 1)

    def test_stop_on_a_spinner_that_never_started_does_nothing(self):
        spinner, console = make_spinner()
        spinner.stop()
        self.assertFalse(spinner.is_running)
        self.assertEqual(console.statuses, [])

    def test_pause_and_resume(self):
        spinner, console = make_spinner()
        spinner.start()
        spinner.pause()
        self.assertTrue(spinner.is_running)
        self.assertTrue(spinner.is_paused)
        self.assertEqual(console.statuses[0].stopped, 1)

        spinner.resume()
        self.assertFalse(spinner.is_paused)
        self.assertTrue(spinner.is_running)
        # The resume builds a fresh status object.
        self.assertEqual(len(console.statuses), 2)
        self.assertEqual(console.statuses[1].started, 1)

    def test_pause_on_a_spinner_that_is_not_running_does_nothing(self):
        """The pause must be safe to call when there is no spinner."""
        spinner, console = make_spinner()
        spinner.pause()
        self.assertFalse(spinner.is_paused)
        self.assertEqual(console.statuses, [])

    def test_resume_on_a_spinner_that_is_not_paused_does_nothing(self):
        spinner, console = make_spinner()
        spinner.start()
        spinner.resume()
        self.assertFalse(spinner.is_paused)
        self.assertEqual(len(console.statuses), 1)

    def test_pause_context_hides_the_spinner_for_the_block(self):
        spinner, _ = make_spinner()
        spinner.start()
        with spinner.pause_context():
            self.assertTrue(spinner.is_paused)
        self.assertFalse(spinner.is_paused)
        self.assertTrue(spinner.is_running)

    def test_pause_context_resumes_even_when_the_block_raises(self):
        """An exception inside the block must not leave the spinner down."""
        spinner, _ = make_spinner()
        spinner.start()
        with self.assertRaises(ValueError):
            with spinner.pause_context():
                raise ValueError("the dialog failed")
        self.assertFalse(spinner.is_paused)
        self.assertTrue(spinner.is_running)


class TestSpinnerErrors(unittest.TestCase):
    """A failure in the console must not leave the spinner lying."""

    def test_a_console_that_refuses_the_status_leaves_the_spinner_stopped(self):
        spinner, _ = make_spinner(console=FakeConsole(fail_on_start=True))
        spinner.start()
        self.assertFalse(spinner.is_running)
        self.assertFalse(spinner.is_paused)

    def test_a_console_that_refuses_the_status_on_resume_stops_the_spinner(self):
        console = FakeConsole()
        spinner = SpinnerController(console=console)
        spinner.start()
        spinner.pause()
        # The console now refuses to build a new status.
        console.fail_on_start = True
        spinner.resume()
        self.assertFalse(spinner.is_running)
        self.assertFalse(spinner.is_paused)


class TestSpinnerCallbacks(unittest.TestCase):
    """The lifecycle hooks, merged in from spinner_manager.py."""

    def test_on_start_fires_when_the_spinner_starts(self):
        spinner, _ = make_spinner()
        calls = []
        spinner.on_start.append(lambda: calls.append("start"))
        spinner.start()
        self.assertEqual(calls, ["start"])

    def test_on_stop_fires_when_the_spinner_stops(self):
        spinner, _ = make_spinner()
        calls = []
        spinner.on_stop.append(lambda: calls.append("stop"))
        spinner.start()
        spinner.stop()
        self.assertEqual(calls, ["stop"])

    def test_on_pause_and_on_resume_fire(self):
        spinner, _ = make_spinner()
        calls = []
        spinner.on_pause.append(lambda: calls.append("pause"))
        spinner.on_resume.append(lambda: calls.append("resume"))
        spinner.start()
        spinner.pause()
        spinner.resume()
        self.assertEqual(calls, ["pause", "resume"])

    def test_a_callback_that_raises_does_not_break_the_spinner(self):
        """A listener that fails must not take the spinner with it."""
        spinner, _ = make_spinner()

        def broken():
            raise RuntimeError("the listener is broken")

        spinner.on_start.append(broken)
        spinner.start()
        self.assertTrue(spinner.is_running)

        spinner.on_pause.append(broken)
        spinner.pause()
        self.assertTrue(spinner.is_paused)

    def test_a_failing_callback_does_not_stop_the_other_callbacks(self):
        spinner, _ = make_spinner()
        calls = []

        def broken():
            raise RuntimeError("the listener is broken")

        spinner.on_start.append(broken)
        spinner.on_start.append(lambda: calls.append("second"))
        spinner.start()
        self.assertEqual(calls, ["second"])

    def test_more_than_one_callback_can_subscribe(self):
        spinner, _ = make_spinner()
        calls = []
        spinner.on_start.append(lambda: calls.append("a"))
        spinner.on_start.append(lambda: calls.append("b"))
        spinner.start()
        self.assertEqual(calls, ["a", "b"])

    def test_a_callback_does_not_fire_when_the_transition_did_not_happen(self):
        """A pause that does nothing must not report that it did."""
        spinner, _ = make_spinner()
        calls = []
        spinner.on_pause.append(lambda: calls.append("pause"))
        spinner.pause()  # the spinner was never started
        self.assertEqual(calls, [])


class TestSpinnerThreadSafety(unittest.TestCase):
    """The lock is the reason the class survived the merge."""

    def test_concurrent_starts_produce_one_spinner(self):
        console = FakeConsole()
        spinner = SpinnerController(console=console)
        threads = [threading.Thread(target=spinner.start) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(console.statuses), 1)
        self.assertTrue(spinner.is_running)

    def test_concurrent_pauses_leave_one_consistent_state(self):
        console = FakeConsole()
        spinner = SpinnerController(console=console)
        spinner.start()
        threads = [threading.Thread(target=spinner.pause) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertTrue(spinner.is_paused)
        self.assertEqual(console.statuses[0].stopped, 1)


if __name__ == "__main__":
    unittest.main()
