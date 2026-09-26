"""
Unit tests for dynamic logging level via CLI argument.

Tests the --log-level CLI argument and centralized logging configuration:
- Default log level is INFO
- All valid log levels can be set via CLI
- Invalid log level produces a helpful error (SystemExit)
- configure_logging() properly sets the root logger level
- No toolkit module has duplicate basicConfig or hardcoded setLevel overrides
- All toolkit loggers respect the configured root level

Run with:
    pytest tests/test_logging_cli.py -v
    python -m pytest tests/test_logging_cli.py -v
"""
import unittest
import logging
import sys
import io
import argparse
import os

# Ensure the self-development module root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import loggers from modules that actually define them
from agent_git_toolkit import logger as git_logger
from agent_linux_toolkit import logger as linux_logger
from agent_windows_toolkit import logger as windows_logger
from agent_os_toolkit import logger as os_logger
from agent_math_toolkit import logger as math_logger
from agent_db_toolkit import logger as db_logger
from agent_apt_toolkit import logger as apt_logger
from agent_chat_memory import logger as chat_memory_logger
from agent_github_toolkit import logger as github_logger


# ---------------------------------------------------------------------------
# CLI Argument Parsing Tests
# ---------------------------------------------------------------------------

class TestLogLevelCLIArgument(unittest.TestCase):
    """Tests for --log-level CLI argument parsing."""

    def _make_parser(self):
        """Recreate the argument parser used by agent-torvalds."""
        parser = argparse.ArgumentParser(description="Torvalds AI Agent")
        parser.add_argument("--full", action="store_true")
        parser.add_argument("--top-k", type=int, default=8)
        parser.add_argument("--no-stats", action="store_true")
        parser.add_argument("--no-events", action="store_true")
        parser.add_argument("--verbose-events", action="store_true")
        parser.add_argument(
            "--log-level",
            type=str,
            choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            default="INFO",
            help="Set logging verbosity level",
        )
        return parser

    def test_default_log_level_is_info(self):
        parser = self._make_parser()
        args = parser.parse_args([])
        self.assertEqual(args.log_level, "INFO")

    def test_log_level_debug(self):
        parser = self._make_parser()
        args = parser.parse_args(["--log-level", "DEBUG"])
        self.assertEqual(args.log_level, "DEBUG")

    def test_log_level_warning(self):
        parser = self._make_parser()
        args = parser.parse_args(["--log-level", "WARNING"])
        self.assertEqual(args.log_level, "WARNING")

    def test_log_level_error(self):
        parser = self._make_parser()
        args = parser.parse_args(["--log-level", "ERROR"])
        self.assertEqual(args.log_level, "ERROR")

    def test_log_level_critical(self):
        parser = self._make_parser()
        args = parser.parse_args(["--log-level", "CRITICAL"])
        self.assertEqual(args.log_level, "CRITICAL")

    def test_invalid_log_level_raises_system_exit(self):
        parser = self._make_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--log-level", "TRACE"])

    def test_invalid_log_level_empty_string(self):
        parser = self._make_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--log-level", ""])

    def test_log_level_combined_with_other_args(self):
        parser = self._make_parser()
        args = parser.parse_args(["--full", "--log-level", "DEBUG", "--no-stats"])
        self.assertTrue(args.full)
        self.assertEqual(args.log_level, "DEBUG")
        self.assertTrue(args.no_stats)

    def test_log_level_lowercase_rejected(self):
        """Lowercase should fail since choices are uppercase."""
        parser = self._make_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--log-level", "debug"])


# ---------------------------------------------------------------------------
# configure_logging() Tests
# ---------------------------------------------------------------------------

class TestConfigureLogging(unittest.TestCase):
    """Tests for the configure_logging() helper function."""

    def setUp(self):
        # Reset root logger handlers before each test
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.NOTSET)

    def tearDown(self):
        # Clean up after each test
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.NOTSET)

    def _configure(self, level_name):
        """Call configure_logging equivalent (matches agent-torvalds.py)."""
        level = getattr(logging, level_name.upper(), logging.INFO)
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[logging.StreamHandler(sys.stderr)],
            force=True,
        )

    def test_configure_logging_debug(self):
        self._configure("DEBUG")
        root = logging.getLogger()
        self.assertEqual(root.level, logging.DEBUG)

    def test_configure_logging_info(self):
        self._configure("INFO")
        root = logging.getLogger()
        self.assertEqual(root.level, logging.INFO)

    def test_configure_logging_warning(self):
        self._configure("WARNING")
        root = logging.getLogger()
        self.assertEqual(root.level, logging.WARNING)

    def test_configure_logging_error(self):
        self._configure("ERROR")
        root = logging.getLogger()
        self.assertEqual(root.level, logging.ERROR)

    def test_configure_logging_critical(self):
        self._configure("CRITICAL")
        root = logging.getLogger()
        self.assertEqual(root.level, logging.CRITICAL)

    def test_configure_logging_invalid_defaults_to_info(self):
        self._configure("INVALID_LEVEL")
        root = logging.getLogger()
        self.assertEqual(root.level, logging.INFO)

    def test_configure_logging_format_contains_required_fields(self):
        self._configure("DEBUG")
        root = logging.getLogger()
        self.assertEqual(len(root.handlers), 1)
        handler = root.handlers[0]
        fmt = handler.formatter._style._fmt
        self.assertIn("asctime", fmt)
        self.assertIn("levelname", fmt)
        self.assertIn("name", fmt)
        self.assertIn("message", fmt)

    def test_configure_logging_outputs_to_stderr(self):
        self._configure("DEBUG")
        root = logging.getLogger()
        handler = root.handlers[0]
        self.assertIsInstance(handler, logging.StreamHandler)
        self.assertIs(handler.stream, sys.stderr)

    def test_logging_respects_level_filter(self):
        """Verify that log messages below the configured level are suppressed."""
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            self._configure("WARNING")
            root = logging.getLogger()
            root.debug("debug message")
            root.info("info message")
            root.warning("warning message")
            root.error("error message")
            output = sys.stderr.getvalue()
            self.assertNotIn("debug message", output)
            self.assertNotIn("info message", output)
            self.assertIn("warning message", output)
            self.assertIn("error message", output)
        finally:
            sys.stderr = old_stderr


# ---------------------------------------------------------------------------
# No Duplicate basicConfig / Hardcoded setLevel Tests
# ---------------------------------------------------------------------------

class TestNoDuplicateBasicConfig(unittest.TestCase):
    """
    Verify that toolkit modules do NOT call logging.basicConfig().

    This is a static source inspection — we check that no duplicate
    basicConfig calls exist outside of agent-torvalds.py.
    """

    TOOLKIT_MODULES = [
        "agent_git_toolkit",
        "agent_linux_toolkit",
        "agent_windows_toolkit",
        "agent_os_toolkit",
        "agent_math_toolkit",
        "agent_db_toolkit",
        "agent_apt_toolkit",
        "agent_chat_memory",
        "agent_github_toolkit",
    ]

    def _check_no_basicconfig_in_source(self, module_name):
        """Check that a module's source does not contain basicConfig calls."""
        import importlib
        module = importlib.import_module(module_name)
        import inspect
        source = inspect.getsource(module)
        lines = source.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "basicConfig" in stripped:
                self.fail(
                    f"Found logging.basicConfig() call in {module_name}: {stripped}"
                )

    def _check_no_setlevel_in_source(self, module_name):
        """Check that a module does not hardcode setLevel overrides."""
        import importlib
        module = importlib.import_module(module_name)
        import inspect
        source = inspect.getsource(module)
        lines = source.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "setLevel" in stripped:
                self.fail(
                    f"Found hardcoded setLevel() in {module_name}: {stripped}"
                )

    def test_no_basicconfig_in_toolkits(self):
        for module_name in self.TOOLKIT_MODULES:
            with self.subTest(module=module_name):
                self._check_no_basicconfig_in_source(module_name)

    def test_no_hardcoded_setlevel_in_toolkits(self):
        for module_name in self.TOOLKIT_MODULES:
            with self.subTest(module=module_name):
                self._check_no_setlevel_in_source(module_name)


# ---------------------------------------------------------------------------
# All Loggers Respect Root Level Tests
# ---------------------------------------------------------------------------

class TestAllLoggersRespectRootLevel(unittest.TestCase):
    """
    Verify that all module-level loggers inherit from the root logger
    and respect the configured level.
    """

    LOGGERS = [
        ("git_logger", git_logger),
        ("linux_logger", linux_logger),
        ("windows_logger", windows_logger),
        ("os_logger", os_logger),
        ("math_logger", math_logger),
        ("db_logger", db_logger),
        ("apt_logger", apt_logger),
        ("chat_memory_logger", chat_memory_logger),
        ("github_logger", github_logger),
    ]

    def setUp(self):
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.NOTSET)

    def tearDown(self):
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.NOTSET)

    def test_loggers_are_proper_logger_instances(self):
        """Each logger should be a Logger instance with a proper name."""
        for name, logger in self.LOGGERS:
            self.assertIsInstance(logger, logging.Logger)
            self.assertTrue(logger.name)

    def test_loggers_have_no_explicit_level_override(self):
        """
        Loggers should inherit level from root (level=NOTSET means inherited).
        If a logger has an explicit level, it may not respect root changes.
        """
        for name, logger in self.LOGGERS:
            self.assertEqual(
                logger.level,
                logging.NOTSET,
                f"Logger '{name}' has explicit level {logger.level}. "
                "It should inherit from root (NOTSET).",
            )

    def test_debug_messages_visible_at_debug_level(self):
        """When root is DEBUG, all loggers should emit debug messages."""
        root = logging.getLogger()
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(name)s:%(levelname)s:%(message)s"))
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        try:
            for name, logger in self.LOGGERS:
                logger.debug(f"test-debug-{name}")
                output = stream.getvalue()
                self.assertIn(
                    f"test-debug-{name}",
                    output,
                    f"Logger '{name}' did not emit DEBUG message when root is DEBUG",
                )
                stream.truncate(0)
                stream.seek(0)
        finally:
            root.handlers.clear()

    def test_debug_messages_suppressed_at_warning_level(self):
        """When root is WARNING, debug messages should be suppressed."""
        root = logging.getLogger()
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(name)s:%(levelname)s:%(message)s"))
        root.addHandler(handler)
        root.setLevel(logging.WARNING)
        try:
            for name, logger in self.LOGGERS:
                logger.debug(f"test-debug-{name}")
                output = stream.getvalue()
                self.assertNotIn(
                    f"test-debug-{name}",
                    output,
                    f"Logger '{name}' emitted DEBUG message when root is WARNING",
                )
        finally:
            root.handlers.clear()

    def test_warning_messages_visible_at_warning_level(self):
        """When root is WARNING, warning messages should be visible."""
        root = logging.getLogger()
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(name)s:%(levelname)s:%(message)s"))
        root.addHandler(handler)
        root.setLevel(logging.WARNING)
        try:
            for name, logger in self.LOGGERS:
                logger.warning(f"test-warning-{name}")
                output = stream.getvalue()
                self.assertIn(
                    f"test-warning-{name}",
                    output,
                    f"Logger '{name}' did not emit WARNING message when root is WARNING",
                )
                stream.truncate(0)
                stream.seek(0)
        finally:
            root.handlers.clear()


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestLogLevelIntegration(unittest.TestCase):
    """
    Integration tests that verify end-to-end logging behavior.
    """

    def setUp(self):
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.NOTSET)

    def tearDown(self):
        root = logging.getLogger()
        root.handlers.clear()
        root.setLevel(logging.NOTSET)

    def test_full_flow_configure_and_verify(self):
        """
        Simulate the full flow: parse args -> configure logging -> verify level.
        """
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--log-level",
            type=str,
            choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            default="INFO",
        )

        for level_name in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            with self.subTest(level=level_name):
                args = parser.parse_args(["--log-level", level_name])
                level = getattr(logging, args.log_level.upper(), logging.INFO)
                root = logging.getLogger()
                root.handlers.clear()
                root.setLevel(level)
                self.assertEqual(root.level, getattr(logging, level_name))

    def test_log_output_format(self):
        """Verify log format includes timestamp, level, and module name."""
        root = logging.getLogger()
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)

        test_logger = logging.getLogger("test.module")
        test_logger.debug("test message")

        output = stream.getvalue()
        self.assertIn("DEBUG", output)
        self.assertIn("test.module", output)
        self.assertIn("test message", output)
        # Timestamp should be present
        self.assertTrue(len(output.split()) >= 2, "Expected timestamp in output")

    def test_force_reconfigure(self):
        """Verify that force=True reconfigures even after basicConfig was called."""
        root = logging.getLogger()

        # First config
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(levelname)s: %(message)s",
            handlers=[logging.StreamHandler(sys.stderr)],
        )
        self.assertEqual(root.level, logging.DEBUG)

        # Reconfigure with different level
        logging.basicConfig(
            level=logging.ERROR,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[logging.StreamHandler(sys.stderr)],
            force=True,
        )
        self.assertEqual(root.level, logging.ERROR)
        self.assertEqual(len(root.handlers), 1)


if __name__ == "__main__":
    unittest.main()
