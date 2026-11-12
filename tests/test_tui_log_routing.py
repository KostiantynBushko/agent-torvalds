"""
While the TUI is up, the log goes into the file — never onto the screen.

The multi-window TUI owns the terminal while it runs.  A log line
written to ``stderr`` in that moment lands on top of the layout and
scrolls the screen, and the scroll is visible as a blink.

The operator decided on 2026-11-13: *"the log must go into file, not
painted over"*.

The investigation is in ``investigate/tui-selection-and-flicker/``.

Run with:
    pytest tests/test_tui_log_routing.py -v
"""
from __future__ import annotations

import io
import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from components.file_logging import LogFileConfig  # noqa: E402
from components.tui.log_routing import (  # noqa: E402
    DEFAULT_TUI_LOG_FILE,
    log_to_file,
    resolve_tui_log_config,
    terminal_handlers,
)


@pytest.fixture
def isolated_logger():
    """A logger of its own, so the root of the test session is untouched."""
    logger = logging.Logger("torvalds.test.log_routing")
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    return logger


@pytest.fixture
def log_config(tmp_path) -> LogFileConfig:
    """The configuration of a log file in a temporary directory."""
    return LogFileConfig(
        log_file=tmp_path / "agent.log",
        max_bytes=1024 * 1024,
        backup_count=2,
        symlink=tmp_path / "agent-current.log",
    )


class TestTerminalHandlers:
    """Which handlers write to the terminal."""

    def test_the_stderr_handler_is_a_terminal_handler(self, isolated_logger):
        handler = logging.StreamHandler(sys.stderr)
        isolated_logger.addHandler(handler)
        assert handler in terminal_handlers(isolated_logger)

    def test_the_stdout_handler_is_a_terminal_handler(self, isolated_logger):
        handler = logging.StreamHandler(sys.stdout)
        isolated_logger.addHandler(handler)
        assert handler in terminal_handlers(isolated_logger)

    def test_a_file_handler_is_not(self, isolated_logger, tmp_path):
        handler = logging.FileHandler(tmp_path / "agent.log")
        isolated_logger.addHandler(handler)
        assert handler not in terminal_handlers(isolated_logger)


class TestLogToFile:
    """The log goes into the file while the TUI is up."""

    def test_the_terminal_handler_is_gone_inside(self, isolated_logger, log_config):
        terminal = logging.StreamHandler(sys.stderr)
        isolated_logger.addHandler(terminal)

        with log_to_file(log_config, root=isolated_logger):
            assert terminal not in isolated_logger.handlers

    def test_the_terminal_handler_is_back_afterwards(self, isolated_logger, log_config):
        terminal = logging.StreamHandler(sys.stderr)
        isolated_logger.addHandler(terminal)

        with log_to_file(log_config, root=isolated_logger):
            pass

        assert terminal in isolated_logger.handlers

    def test_the_log_reaches_the_file(self, isolated_logger, log_config):
        with log_to_file(log_config, root=isolated_logger):
            isolated_logger.info("a line of the agent")

        assert "a line of the agent" in log_config.log_file.read_text()

    def test_the_log_does_not_reach_the_terminal(self, isolated_logger, log_config):
        """The whole point: the line goes to the file, not to the screen."""
        stream = io.StringIO()
        terminal = logging.StreamHandler(stream)
        isolated_logger.addHandler(terminal)

        with log_to_file(log_config, root=isolated_logger):
            isolated_logger.info("a line of the agent")

        assert "a line of the agent" not in stream.getvalue()

    def test_the_file_handler_is_removed_afterwards(self, isolated_logger, log_config):
        with log_to_file(log_config, root=isolated_logger) as handler:
            assert handler in isolated_logger.handlers

        assert handler not in isolated_logger.handlers

    def test_the_own_file_handler_of_the_operator_stays(self, isolated_logger, log_config):
        """The handler the operator configured is not taken away."""
        own = logging.FileHandler(log_config.log_file)
        isolated_logger.addHandler(own)

        with log_to_file(log_config, root=isolated_logger):
            pass

        assert own in isolated_logger.handlers

    def test_the_file_is_private(self, isolated_logger, log_config):
        """The log carries the prompts, so it is not world-readable."""
        with log_to_file(log_config, root=isolated_logger):
            isolated_logger.info("a line of the agent")

        mode = log_config.log_file.stat().st_mode & 0o777
        assert mode == 0o600, f"the log file is {mode:o}, not 600"

    def test_a_file_that_cannot_be_opened_keeps_the_terminal(self, isolated_logger, tmp_path):
        """A log that cannot be written degrades - it never stops the TUI."""
        terminal = logging.StreamHandler(sys.stderr)
        isolated_logger.addHandler(terminal)

        broken = LogFileConfig(
            log_file=tmp_path / "missing-directory" / "agent.log",
            max_bytes=1024,
            backup_count=1,
            symlink=None,
        )
        # The directory cannot be created: make its parent a file.
        blocker = tmp_path / "blocker"
        blocker.write_text("not a directory")
        broken = LogFileConfig(
            log_file=blocker / "agent.log",
            max_bytes=1024,
            backup_count=1,
            symlink=None,
        )

        with log_to_file(broken, root=isolated_logger):
            assert terminal not in isolated_logger.handlers

        assert terminal in isolated_logger.handlers


class TestResolveTuiLogConfig:
    """Where the log file of the TUI is."""

    def test_the_configuration_of_the_operator_wins(self, log_config):
        assert resolve_tui_log_config(log_config) is log_config

    def test_there_is_always_a_file(self, tmp_path, monkeypatch):
        """The TUI always has a file to write into."""
        monkeypatch.setenv("TORVALDS_LOG_DIR", str(tmp_path))
        monkeypatch.delenv("TORVALDS_LOG_FILE", raising=False)

        resolved = resolve_tui_log_config()
        assert resolved.log_file.name == DEFAULT_TUI_LOG_FILE
        assert resolved.log_file.parent == tmp_path

    def test_the_environment_wins_over_the_default(self, tmp_path, monkeypatch):
        """TORVALDS_LOG_FILE and TORVALDS_LOG_DIR are honoured."""
        monkeypatch.setenv("TORVALDS_LOG_DIR", str(tmp_path))
        monkeypatch.setenv("TORVALDS_LOG_FILE", "other.log")

        resolved = resolve_tui_log_config()
        assert resolved.log_file.name == "other.log"
        assert resolved.log_file.parent == tmp_path
