"""
Unit tests for the file logging — the rotating log file and the symlink.

The operator asked for it on 2026-10-27: the logging must be redirectable
into a file, the file must be rotated when it reaches a predefined size,
and the directory must hold a symlink to the current log file.

What is pinned here:

- the size parser — ``10MB`` works, ``10MBB`` is reported;
- the resolution — the flags win over the environment, and the file
  logging is **off** until it is asked for;
- the handler — the records reach the file, the file is private (0600),
  the rotation is real and bounded, and the symlink follows the live file;
- the degradation — a directory that cannot be created, a file that
  cannot be opened and a symlink that cannot be created degrade the
  feature, they never take the agent down;
- the tee — the stderr handler stays.

Run with:
    pytest tests/test_file_logging.py -v
"""
import logging
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure the self-development module root is on the path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from components.file_logging import (  # noqa: E402
    DEFAULT_LOG_DIR,
    DEFAULT_MAX_FILES,
    DEFAULT_MAX_SIZE,
    ENV_LOG_DIR,
    ENV_LOG_FILE,
    ENV_LOG_MAX_FILES,
    ENV_LOG_MAX_SIZE,
    ENV_LOG_SYMLINK,
    LogFileConfig,
    SymlinkedRotatingFileHandler,
    add_logging_arguments,
    build_file_handler,
    parse_size,
    positive_int,
    resolve_config,
    size_argument,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _isolated_logger(name: str) -> logging.Logger:
    """A logger that writes nowhere but into the handler under test."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    return logger


def _write(logger: logging.Logger, count: int, text: str = "x" * 100) -> None:
    for i in range(count):
        logger.info("record %04d %s", i, text)


class TempDirCase(unittest.TestCase):
    """A test case with a temporary directory that is cleaned up."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="torvalds-file-logging-")
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)


# ---------------------------------------------------------------------------
# The size parser
# ---------------------------------------------------------------------------

class TestParseSize(unittest.TestCase):
    """L7 — the size limit is written the way an operator writes it."""

    def test_the_units(self):
        cases = {
            "10MB": 10 * 1024 * 1024,
            "512K": 512 * 1024,
            "1G": 1024 ** 3,
            "2048": 2048,
            "10MB ": 10 * 1024 * 1024,
            "10 MB": 10 * 1024 * 1024,
            "1.5MB": int(1.5 * 1024 * 1024),
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(parse_size(text), expected)

    def test_the_units_are_case_insensitive(self):
        self.assertEqual(parse_size("10mb"), 10 * 1024 * 1024)
        self.assertEqual(parse_size("10Mb"), 10 * 1024 * 1024)

    def test_an_unknown_unit_is_reported(self):
        with self.assertRaises(ValueError) as ctx:
            parse_size("10MBB")
        self.assertIn("MBB", str(ctx.exception))

    def test_an_empty_size_is_reported(self):
        with self.assertRaises(ValueError):
            parse_size("")

    def test_a_size_without_a_number_is_reported(self):
        with self.assertRaises(ValueError):
            parse_size("MB")

    def test_a_zero_size_is_reported(self):
        with self.assertRaises(ValueError):
            parse_size("0")
        with self.assertRaises(ValueError):
            parse_size(0)

    def test_a_negative_size_is_reported(self):
        with self.assertRaises(ValueError):
            parse_size(-1)

    def test_the_argparse_type_turns_the_error_into_a_usage_error(self):
        import argparse

        with self.assertRaises(argparse.ArgumentTypeError):
            size_argument("10MBB")

    def test_the_argparse_type_accepts_a_good_size(self):
        self.assertEqual(size_argument("10MB"), 10 * 1024 * 1024)


class TestPositiveInt(unittest.TestCase):
    """The number of generations must be at least one."""

    def test_zero_is_refused(self):
        with self.assertRaises(ValueError):
            positive_int(0)
        with self.assertRaises(ValueError):
            positive_int("0")

    def test_a_negative_number_is_refused(self):
        with self.assertRaises(ValueError):
            positive_int(-3)

    def test_a_number_is_accepted(self):
        self.assertEqual(positive_int("5"), 5)
        self.assertEqual(positive_int(1), 1)

    def test_a_non_number_is_refused(self):
        with self.assertRaises(ValueError):
            positive_int("five")


# ---------------------------------------------------------------------------
# The resolution
# ---------------------------------------------------------------------------

class TestResolveConfig(TempDirCase):
    """The flags win over the environment; the environment wins over the default."""

    def test_the_file_logging_is_off_by_default(self):
        self.assertIsNone(resolve_config(environ={}))

    def test_the_environment_turns_it_on(self):
        config = resolve_config(environ={ENV_LOG_FILE: "agent.log"})
        self.assertIsNotNone(config)
        self.assertEqual(config.log_file.name, "agent.log")

    def test_the_flag_turns_it_on(self):
        config = resolve_config(log_file="agent.log", environ={})
        self.assertIsNotNone(config)

    def test_the_flag_wins_over_the_environment(self):
        config = resolve_config(
            log_file="from-flag.log",
            environ={ENV_LOG_FILE: "from-env.log"},
        )
        self.assertEqual(config.log_file.name, "from-flag.log")

    def test_a_bare_name_goes_into_the_log_directory(self):
        config = resolve_config(
            log_file="agent.log", log_dir=str(self.tmp), environ={}
        )
        self.assertEqual(config.log_file, self.tmp / "agent.log")

    def test_the_log_directory_comes_from_the_environment(self):
        config = resolve_config(
            log_file="agent.log",
            environ={ENV_LOG_DIR: str(self.tmp)},
        )
        self.assertEqual(config.log_file, self.tmp / "agent.log")

    def test_the_flag_wins_over_the_environment_for_the_directory(self):
        config = resolve_config(
            log_file="agent.log",
            log_dir=str(self.tmp),
            environ={ENV_LOG_DIR: "/somewhere/else"},
        )
        self.assertEqual(config.log_file, self.tmp / "agent.log")

    def test_a_path_with_a_directory_is_used_as_given(self):
        target = self.tmp / "elsewhere" / "agent.log"
        config = resolve_config(log_file=str(target), environ={})
        self.assertEqual(config.log_file, target)

    def test_the_default_symlink_sits_next_to_the_log_file(self):
        config = resolve_config(
            log_file="agent.log", log_dir=str(self.tmp), environ={}
        )
        self.assertEqual(config.symlink, self.tmp / "agent-current.log")

    def test_a_named_symlink_sits_next_to_the_log_file(self):
        config = resolve_config(
            log_file="agent.log",
            log_dir=str(self.tmp),
            symlink="current.log",
            environ={},
        )
        self.assertEqual(config.symlink, self.tmp / "current.log")

    def test_the_symlink_comes_from_the_environment(self):
        config = resolve_config(
            log_file="agent.log",
            log_dir=str(self.tmp),
            environ={ENV_LOG_SYMLINK: "pointer.log"},
        )
        self.assertEqual(config.symlink, self.tmp / "pointer.log")

    def test_the_flag_wins_over_the_environment_for_the_symlink(self):
        config = resolve_config(
            log_file="agent.log",
            log_dir=str(self.tmp),
            symlink="from-flag.log",
            environ={ENV_LOG_SYMLINK: "from-env.log"},
        )
        self.assertEqual(config.symlink, self.tmp / "from-flag.log")

    def test_the_default_size_and_the_default_number_of_generations(self):
        config = resolve_config(log_file="agent.log", environ={})
        self.assertEqual(config.max_bytes, parse_size(DEFAULT_MAX_SIZE))
        self.assertEqual(config.backup_count, DEFAULT_MAX_FILES)

    def test_the_environment_sets_the_size(self):
        config = resolve_config(
            log_file="agent.log", environ={ENV_LOG_MAX_SIZE: "2MB"}
        )
        self.assertEqual(config.max_bytes, 2 * 1024 * 1024)

    def test_the_environment_sets_the_number_of_generations(self):
        config = resolve_config(
            log_file="agent.log", environ={ENV_LOG_MAX_FILES: "3"}
        )
        self.assertEqual(config.backup_count, 3)

    def test_a_bad_size_in_the_environment_is_reported(self):
        with self.assertRaises(ValueError):
            resolve_config(
                log_file="agent.log", environ={ENV_LOG_MAX_SIZE: "10MBB"}
            )

    def test_zero_generations_are_refused(self):
        with self.assertRaises(ValueError):
            resolve_config(
                log_file="agent.log", environ={ENV_LOG_MAX_FILES: "0"}
            )

    def test_the_symlink_can_be_turned_off(self):
        """The word "none" is the explicit way to ask for no pointer."""
        config = resolve_config(
            log_file="agent.log",
            log_dir=str(self.tmp),
            symlink="none",
            environ={},
        )
        self.assertIsNone(config.symlink)

    def test_an_empty_symlink_is_not_an_untouched_one(self):
        """An empty variable is an unset variable — the default stands."""
        config = resolve_config(
            log_file="agent.log",
            log_dir=str(self.tmp),
            environ={ENV_LOG_SYMLINK: ""},
        )
        self.assertEqual(config.symlink, self.tmp / "agent-current.log")

    def test_the_default_log_directory_is_the_convention_of_the_project(self):
        self.assertEqual(DEFAULT_LOG_DIR, "~/.torvalds/logs")


# ---------------------------------------------------------------------------
# The handler
# ---------------------------------------------------------------------------

class TestTheHandler(TempDirCase):
    """The invariants of the design, against the public behaviour."""

    def _handler(self, name: str = "agent.log", **kwargs) -> SymlinkedRotatingFileHandler:
        config = LogFileConfig(
            log_file=self.tmp / name,
            max_bytes=kwargs.pop("max_bytes", 10 * 1024 * 1024),
            backup_count=kwargs.pop("backup_count", 5),
            symlink=self.tmp / kwargs.pop("symlink", "agent-current.log"),
        )
        handler = build_file_handler(config, logging.INFO)
        self.assertIsNotNone(handler)
        return handler

    def test_the_file_is_created_and_receives_the_records(self):
        handler = self._handler()
        logger = _isolated_logger("t1")
        logger.addHandler(handler)

        _write(logger, 25)
        handler.flush()

        content = (self.tmp / "agent.log").read_text(encoding="utf-8")
        missing = [i for i in range(25) if f"record {i:04d}" not in content]
        self.assertEqual(missing, [])

    def test_the_file_is_private(self):
        handler = self._handler()
        handler.close()
        mode = stat.S_IMODE((self.tmp / "agent.log").stat().st_mode)
        self.assertEqual(mode, 0o600)

    def test_the_rotation_happens_at_the_size_limit(self):
        handler = self._handler(max_bytes=4096, backup_count=3)
        logger = _isolated_logger("t2")
        logger.addHandler(handler)

        _write(logger, 200)
        handler.flush()

        rotated = list(self.tmp.glob("agent.log.*"))
        self.assertTrue(rotated, "the file was not rotated")
        live = (self.tmp / "agent.log").stat().st_size
        # The limit is soft: the file may exceed it by the record that
        # crossed it, but not by a whole file's worth.
        self.assertLessEqual(live, 4096 * 2)

    def test_no_more_than_the_limit_of_generations_are_kept(self):
        handler = self._handler(max_bytes=2048, backup_count=3)
        logger = _isolated_logger("t3")
        logger.addHandler(handler)

        _write(logger, 500)
        handler.flush()

        self.assertLessEqual(len(list(self.tmp.glob("agent.log.*"))), 3)

    def test_the_symlink_exists_and_resolves_to_the_live_file(self):
        handler = self._handler()
        link = self.tmp / "agent-current.log"
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.path.realpath(link), os.path.realpath(self.tmp / "agent.log"))

    def test_the_symlink_survives_a_rotation(self):
        handler = self._handler(max_bytes=4096, backup_count=3)
        logger = _isolated_logger("t4")
        logger.addHandler(handler)
        link = self.tmp / "agent-current.log"

        inode_before = os.stat(self.tmp / "agent.log").st_ino
        _write(logger, 200)
        handler.flush()
        inode_after = os.stat(self.tmp / "agent.log").st_ino

        self.assertNotEqual(inode_before, inode_after, "the file was not rotated")
        self.assertEqual(os.path.realpath(link), os.path.realpath(self.tmp / "agent.log"))

    def test_the_symlink_comes_back_after_it_was_deleted(self):
        handler = self._handler(max_bytes=4096, backup_count=3)
        logger = _isolated_logger("t5")
        logger.addHandler(handler)
        link = self.tmp / "agent-current.log"

        os.remove(link)
        _write(logger, 200)
        handler.flush()

        self.assertTrue(link.is_symlink())
        self.assertEqual(os.path.realpath(link), os.path.realpath(self.tmp / "agent.log"))

    def test_a_symlink_that_cannot_be_created_does_not_stop_the_logging(self):
        config = LogFileConfig(
            log_file=self.tmp / "agent.log",
            max_bytes=4096,
            backup_count=3,
            symlink=self.tmp / "no-such-dir" / "current.log",
        )
        handler = build_file_handler(config, logging.INFO)
        self.assertIsNotNone(handler, "the handler must still be installed")

        logger = _isolated_logger("t6")
        logger.addHandler(handler)
        _write(logger, 10)
        handler.flush()

        content = (self.tmp / "agent.log").read_text(encoding="utf-8")
        self.assertIn("record 0000", content)

    def test_a_log_file_that_cannot_be_opened_degrades(self):
        # A directory where the log file should be: opening it fails.
        blocker = self.tmp / "blocked.log"
        blocker.mkdir()
        config = LogFileConfig(
            log_file=blocker,
            max_bytes=4096,
            backup_count=3,
            symlink=self.tmp / "blocked-current.log",
        )
        self.assertIsNone(build_file_handler(config, logging.INFO))

    def test_the_file_is_appended_to_when_the_logging_is_reconfigured(self):
        handler = self._handler()
        logger = _isolated_logger("t7")
        logger.addHandler(handler)

        _write(logger, 5)
        handler.flush()
        size_after_first = (self.tmp / "agent.log").stat().st_size

        # A second handler on the same file — the reconfiguration must
        # not truncate what the first run wrote.
        handler2 = self._handler()
        logger.removeHandler(handler)
        logger.addHandler(handler2)
        _write(logger, 5)
        handler2.flush()

        size_after_second = (self.tmp / "agent.log").stat().st_size
        self.assertGreater(size_after_second, size_after_first)
        content = (self.tmp / "agent.log").read_text(encoding="utf-8")
        self.assertIn("record 0000", content)


class TestTheDegradation(TempDirCase):
    """A missing feature degrades — it never takes the agent down."""

    def test_a_log_directory_that_cannot_be_created_degrades(self):
        # A regular file where the directory should be.
        blocker = self.tmp / "blocker"
        blocker.write_text("not a directory", encoding="utf-8")
        config = LogFileConfig(
            log_file=blocker / "logs" / "agent.log",
            max_bytes=4096,
            backup_count=3,
            symlink=blocker / "logs" / "agent-current.log",
        )
        self.assertIsNone(build_file_handler(config, logging.INFO))

    def test_no_configuration_means_no_handler(self):
        self.assertIsNone(build_file_handler(None, logging.INFO))


# ---------------------------------------------------------------------------
# The wiring
# ---------------------------------------------------------------------------

class TestTheTee(TempDirCase):
    """The file joins the terminal — it does not replace it."""

    def setUp(self):
        super().setUp()
        root = logging.getLogger()
        self._handlers = list(root.handlers)
        self._level = root.level
        root.handlers.clear()
        self.addCleanup(self._restore)

    def _restore(self):
        root = logging.getLogger()
        root.handlers.clear()
        root.handlers.extend(self._handlers)
        root.setLevel(self._level)

    def _configure(self, config):
        """The shape of configure_logging() in the two orchestrators."""
        level = logging.INFO
        handlers = [logging.StreamHandler(sys.stderr)]
        if config is not None:
            handler = build_file_handler(config, level)
            if handler is not None:
                handlers.append(handler)
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=handlers,
            force=True,
        )

    def test_the_stderr_handler_is_still_there(self):
        config = LogFileConfig(
            log_file=self.tmp / "agent.log",
            max_bytes=4096,
            backup_count=3,
            symlink=self.tmp / "agent-current.log",
        )
        self._configure(config)
        root = logging.getLogger()
        self.assertEqual(len(root.handlers), 2)
        self.assertTrue(
            any(
                isinstance(h, logging.StreamHandler) and h.stream is sys.stderr
                for h in root.handlers
            )
        )
        self.assertTrue(
            any(isinstance(h, SymlinkedRotatingFileHandler) for h in root.handlers)
        )

    def test_the_file_logging_is_off_by_default(self):
        self._configure(None)
        root = logging.getLogger()
        self.assertEqual(len(root.handlers), 1)
        self.assertFalse(
            any(isinstance(h, SymlinkedRotatingFileHandler) for h in root.handlers)
        )

    def test_the_records_reach_both_the_terminal_and_the_file(self):
        config = LogFileConfig(
            log_file=self.tmp / "agent.log",
            max_bytes=4096,
            backup_count=3,
            symlink=self.tmp / "agent-current.log",
        )
        self._configure(config)
        logging.getLogger("tee").info("the record that has to be in both places")
        for handler in logging.getLogger().handlers:
            handler.flush()

        content = (self.tmp / "agent.log").read_text(encoding="utf-8")
        self.assertIn("the record that has to be in both places", content)


# ---------------------------------------------------------------------------
# The command line
# ---------------------------------------------------------------------------

class TestTheCommandLine(unittest.TestCase):
    """The surface: the flags, the defaults, the environment variables."""

    def _parser(self, environ=None):
        import argparse

        parser = argparse.ArgumentParser()
        add_logging_arguments(parser)
        return parser

    def test_the_defaults(self):
        args = self._parser().parse_args([])
        self.assertIsNone(args.log_file)
        self.assertIsNone(args.log_dir)
        self.assertIsNone(args.log_symlink)
        self.assertEqual(args.log_max_size, parse_size(DEFAULT_MAX_SIZE))
        self.assertEqual(args.log_max_files, DEFAULT_MAX_FILES)

    def test_the_flags(self):
        args = self._parser().parse_args(
            [
                "--log-file", "agent.log",
                "--log-dir", "/tmp/logs",
                "--log-max-size", "20MB",
                "--log-max-files", "3",
                "--log-symlink", "current.log",
            ]
        )
        self.assertEqual(args.log_file, "agent.log")
        self.assertEqual(args.log_dir, "/tmp/logs")
        self.assertEqual(args.log_max_size, 20 * 1024 * 1024)
        self.assertEqual(args.log_max_files, 3)
        self.assertEqual(args.log_symlink, "current.log")

    def test_a_bad_size_stops_the_agent(self):
        with self.assertRaises(SystemExit):
            self._parser().parse_args(["--log-max-size", "10MBB"])

    def test_zero_generations_stop_the_agent(self):
        with self.assertRaises(SystemExit):
            self._parser().parse_args(["--log-max-files", "0"])

    def test_the_environment_is_the_default_of_the_flags(self):
        import os

        saved = dict(os.environ)
        os.environ[ENV_LOG_MAX_SIZE] = "5MB"
        os.environ[ENV_LOG_MAX_FILES] = "2"
        try:
            args = self._parser().parse_args([])
            self.assertEqual(args.log_max_size, 5 * 1024 * 1024)
            self.assertEqual(args.log_max_files, 2)
        finally:
            os.environ.clear()
            os.environ.update(saved)

    def test_a_bad_size_in_the_environment_stops_the_agent(self):
        import os

        saved = dict(os.environ)
        os.environ[ENV_LOG_MAX_SIZE] = "10MBB"
        try:
            with self.assertRaises(SystemExit):
                self._parser().parse_args([])
        finally:
            os.environ.clear()
            os.environ.update(saved)


if __name__ == "__main__":
    unittest.main()
