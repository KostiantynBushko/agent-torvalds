"""
Unit tests for the configuration file — ``~/.config/torvalds/config.toml``.

The operator asked for it on 2026-10-29: a configuration file under
``~/.config/torvalds/``.  What is pinned here:

- the **location** — the XDG directory, and ``TORVALDS_CONFIG`` for the
  file that is somewhere else;
- the **precedence** — flag, environment variable, config file, default,
  and the file must not change the behaviour of an operator who already
  has environment variables;
- the **degradation** — a missing file is not an error, a broken file is
  a warning, an unknown key is a warning, and a value of the wrong type
  is a warning;
- the **template** — what ``--write-default-config`` writes;
- the **wiring** — the orchestrators read the file, and the ``\\config``
  command tells the operator where every value came from.

Run with:
    pytest tests/test_config.py -v
"""
import argparse
import logging
import os
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

# Ensure the repository root is on the path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from components.config import (  # noqa: E402
    APP_DIR_NAME,
    CONFIG_FILENAME,
    CONFIG_HOME_ENV,
    CONFIG_PATH_ENV,
    Config,
    MACOS_APP_SUPPORT_DIR,
    WINDOWS_APP_DATA_ENV,
    WINDOWS_APP_DATA_FALLBACK,
    default_config_dir,
    default_config_path,
    Effective,
    Setting,
    SETTINGS,
    Source,
    default_config_dir,
    default_config_path,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TempDirCase(unittest.TestCase):
    """A test case with a temporary directory that is cleaned up."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="torvalds-config-")
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def write(self, text: str, name: str = "config.toml") -> Path:
        """Write a configuration file and return its path."""
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return path

    def config(self, text: str, environ=None, **kwargs) -> Config:
        """A configuration that reads the given file."""
        return Config(
            path=self.write(text),
            environ={} if environ is None else environ,
            **kwargs,
        )


# ---------------------------------------------------------------------------
# The location
# ---------------------------------------------------------------------------

class TestTheLocation(TempDirCase):
    """The XDG directory, and the override."""

    def test_the_default_directory_follows_xdg(self):
        path = default_config_dir({"XDG_CONFIG_HOME": "/tmp/xdg"})
        self.assertEqual(path, Path("/tmp/xdg") / APP_DIR_NAME)

    def test_the_default_directory_is_dot_config(self):
        path = default_config_dir({})
        self.assertEqual(path, Path.home() / ".config" / APP_DIR_NAME)

    def test_the_default_path_is_the_file_in_that_directory(self):
        path = default_config_path({"XDG_CONFIG_HOME": "/tmp/xdg"})
        self.assertEqual(path, Path("/tmp/xdg") / APP_DIR_NAME / CONFIG_FILENAME)

    def test_the_environment_variable_points_at_another_file(self):
        path = default_config_path({CONFIG_PATH_ENV: "/tmp/other.toml"})
        self.assertEqual(path, Path("/tmp/other.toml"))

    def test_the_home_is_expanded(self):
        path = default_config_path({CONFIG_PATH_ENV: "~/other.toml"})
        self.assertEqual(path, Path.home() / "other.toml")

    def test_the_xdg_home_is_expanded(self):
        path = default_config_dir({"XDG_CONFIG_HOME": "~/xdg"})
        self.assertEqual(path, Path.home() / "xdg" / APP_DIR_NAME)


# ---------------------------------------------------------------------------
# The location on every platform
# ---------------------------------------------------------------------------

class TestTheLocationOnEveryPlatform(TempDirCase):
    """Where the file is on Windows, on macOS and on Linux.

    The platform is a property of the interpreter, not of the
    environment, so it is patched — the tests must say the same thing on
    every system they run on.
    """

    def the_dir(self, platform: str, environ=None) -> Path:
        """The configuration directory, as it would be on that platform."""
        with mock.patch.object(sys, "platform", platform):
            return default_config_dir({} if environ is None else environ)

    def test_on_windows_the_application_data_wins_over_the_fallback(self):
        """The path is absolute **on the platform the test runs on**: the
        Windows shape cannot be written on POSIX and the other way
        round, and ``is_absolute()`` is the platform's."""
        app_data = str(self.tmp / "AppData" / "Roaming")
        directory = self.the_dir("win32", {"APPDATA": app_data})
        self.assertEqual(
            directory, self.tmp / "AppData" / "Roaming" / APP_DIR_NAME
        )

    def test_the_windows_directories_are_the_ones_windows_uses(self):
        """The shape of the path, pinned as the constants they are."""
        self.assertEqual(WINDOWS_APP_DATA_ENV, "APPDATA")
        self.assertEqual(WINDOWS_APP_DATA_FALLBACK, "~/AppData/Roaming")

    def test_the_macos_directory_is_the_application_support(self):
        """The shape of the path, pinned as the constant it is."""
        self.assertEqual(MACOS_APP_SUPPORT_DIR, "~/Library/Application Support")

    def test_on_windows_without_the_variable_the_home_is_used(self):
        directory = self.the_dir("win32", {})
        self.assertEqual(
            directory,
            Path.home() / "AppData" / "Roaming" / APP_DIR_NAME,
        )

    def test_on_macos_the_file_is_under_the_application_support(self):
        directory = self.the_dir("darwin", {})
        self.assertEqual(
            directory,
            Path.home() / "Library" / "Application Support" / APP_DIR_NAME,
        )

    def test_on_linux_the_xdg_standard_is_used(self):
        directory = self.the_dir("linux", {})
        self.assertEqual(directory, Path.home() / ".config" / APP_DIR_NAME)

    def test_the_xdg_variable_is_honoured_on_every_platform(self):
        """An explicit choice by the operator beats the convention."""
        for platform in ("linux", "darwin", "win32"):
            directory = self.the_dir(
                platform, {CONFIG_HOME_ENV: str(self.tmp)}
            )
            self.assertEqual(directory, self.tmp / APP_DIR_NAME, platform)

    def test_the_file_is_named_the_same_on_every_platform(self):
        for platform in ("linux", "darwin", "win32"):
            with mock.patch.object(sys, "platform", platform):
                path = default_config_path({})
            self.assertEqual(path.name, CONFIG_FILENAME, platform)

    def test_a_relative_xdg_path_is_ignored(self):
        """A relative path would make the configuration depend on the
        directory the agent was started in."""
        directory = self.the_dir("linux", {CONFIG_HOME_ENV: "relative/path"})
        self.assertEqual(directory, Path.home() / ".config" / APP_DIR_NAME)

    def test_a_relative_application_data_is_ignored_on_windows(self):
        directory = self.the_dir("win32", {"APPDATA": "relative/path"})
        self.assertEqual(
            directory,
            Path.home() / "AppData" / "Roaming" / APP_DIR_NAME,
        )

    def test_the_directory_carries_the_name_of_the_application(self):
        for platform in ("linux", "darwin", "win32"):
            with mock.patch.object(sys, "platform", platform):
                directory = default_config_dir({})
            self.assertEqual(directory.name, APP_DIR_NAME, platform)


# ---------------------------------------------------------------------------
# The precedence
# ---------------------------------------------------------------------------

class TestThePrecedence(TempDirCase):
    """The environment variable wins over the file; the file wins over the default."""

    def test_the_default_is_used_when_nothing_carries_the_value(self):
        config = self.config("")
        self.assertEqual(config.get("llm.model"), "richardyoung/qwen3.6-27b-abliterated:Q4_K_M")
        self.assertEqual(config.source("llm.model"), Source.DEFAULT)

    def test_the_file_wins_over_the_default(self):
        config = self.config('[llm]\nmodel = "from-the-file"\n')
        self.assertEqual(config.get("llm.model"), "from-the-file")
        self.assertIn("config file", config.source("llm.model"))

    def test_the_environment_wins_over_the_file(self):
        config = self.config(
            '[llm]\nmodel = "from-the-file"\n',
            environ={"TORVALDS_MODEL": "from-the-environment"},
        )
        self.assertEqual(config.get("llm.model"), "from-the-environment")
        self.assertEqual(config.source("llm.model"), "environment variable TORVALDS_MODEL")

    def test_the_flag_wins_over_everything(self):
        config = self.config(
            '[llm]\nmodel = "from-the-file"\n',
            environ={"TORVALDS_MODEL": "from-the-environment"},
        )
        value = config.flag("llm.model", "from-the-flag")
        self.assertEqual(value, "from-the-flag")
        self.assertEqual(config.source("llm.model"), Source.FLAG)

    def test_an_empty_environment_variable_does_not_win(self):
        """An unset variable and an empty one mean the same thing."""
        config = self.config(
            '[llm]\nmodel = "from-the-file"\n',
            environ={"TORVALDS_MODEL": "   "},
        )
        self.assertEqual(config.get("llm.model"), "from-the-file")

    def test_a_default_may_be_overridden_by_the_caller(self):
        config = self.config("")
        self.assertEqual(config.get("llm.max_iterations", default=500), 500)

    def test_no_default_means_none(self):
        """The caller asks whether the file carries a value at all."""
        config = self.config("")
        self.assertIsNone(config.get("llm.host", default=None))


# ---------------------------------------------------------------------------
# The degradation
# ---------------------------------------------------------------------------

class TestTheDegradation(TempDirCase):
    """A missing or broken file never stops the agent."""

    def test_a_missing_file_is_not_an_error(self):
        config = Config(path=self.tmp / "nothing.toml", environ={})
        self.assertFalse(config.present)
        self.assertEqual(config.problems, [])
        self.assertEqual(config.get("llm.model"), "richardyoung/qwen3.6-27b-abliterated:Q4_K_M")

    def test_a_broken_file_is_a_warning(self):
        config = self.config("[llm\nmodel = 'x'")
        self.assertTrue(config.present)
        self.assertEqual(len(config.problems), 1)
        self.assertIn("not valid TOML", config.problems[0])
        # The defaults are used.
        self.assertEqual(config.get("llm.model"), "richardyoung/qwen3.6-27b-abliterated:Q4_K_M")

    def test_an_unknown_section_is_a_warning(self):
        config = self.config("[nowhere]\nx = 1\n")
        self.assertEqual(len(config.problems), 1)
        self.assertIn("nowhere", config.problems[0])

    def test_an_unknown_key_is_a_warning(self):
        config = self.config("[llm]\nnot_a_setting = 1\n")
        self.assertEqual(len(config.problems), 1)
        self.assertIn("not_a_setting", config.problems[0])

    def test_a_value_of_the_wrong_type_is_a_warning(self):
        config = self.config('[llm]\nmax_iterations = "not a number"\n')
        self.assertEqual(len(config.problems), 1)
        self.assertIn("max_iterations", config.problems[0])
        # The default is used instead.
        self.assertEqual(config.get("llm.max_iterations"), 50)

    def test_a_boolean_outside_the_two_values_is_a_warning(self):
        config = self.config('[hitl]\nenabled = "perhaps"\n')
        self.assertEqual(len(config.problems), 1)
        self.assertTrue(config.get("hitl.enabled"))

    def test_a_value_outside_the_choices_is_a_warning(self):
        config = self.config('[logging]\nlevel = "TRACE"\n')
        self.assertEqual(len(config.problems), 1)
        self.assertEqual(config.get("logging.level"), "INFO")

    def test_a_table_where_a_value_belongs_is_a_warning(self):
        config = self.config('[llm]\nmodel = {a = 1}\n')
        self.assertEqual(len(config.problems), 1)
        self.assertEqual(config.get("llm.model"), "richardyoung/qwen3.6-27b-abliterated:Q4_K_M")


# ---------------------------------------------------------------------------
# The coercion
# ---------------------------------------------------------------------------

class TestTheCoercion(TempDirCase):
    """The file may hold a number where the setting wants a number."""

    def test_an_integer_in_the_file_is_an_integer(self):
        config = self.config("[llm]\nmax_iterations = 42\n")
        self.assertEqual(config.get("llm.max_iterations"), 42)
        self.assertIsInstance(config.get("llm.max_iterations"), int)

    def test_a_number_written_as_a_string_is_still_a_number(self):
        config = self.config('[llm]\nmax_iterations = "42"\n')
        self.assertEqual(config.get("llm.max_iterations"), 42)

    def test_a_boolean_in_the_file_is_a_boolean(self):
        config = self.config("[hitl]\nenabled = false\n")
        self.assertIs(config.get("hitl.enabled"), False)

    def test_the_words_for_a_boolean_are_understood(self):
        for text, expected in (("true", True), ("yes", True), ("on", True),
                               ("false", False), ("no", False), ("off", False)):
            with self.subTest(text=text):
                config = self.config(f'[hitl]\nenabled = "{text}"\n')
                self.assertIs(config.get("hitl.enabled"), expected)

    def test_a_choice_is_matched_case_insensitively(self):
        config = self.config('[logging]\nlevel = "debug"\n')
        self.assertEqual(config.get("logging.level"), "DEBUG")

    def test_a_raw_setting_is_handed_over_untouched(self):
        """The logging size is validated by the command line parser."""
        config = self.config('[logging]\nmax_size = "10MBB"\n')
        self.assertEqual(config.get("logging.max_size"), "10MBB")
        self.assertEqual(config.problems, [])


# ---------------------------------------------------------------------------
# The template
# ---------------------------------------------------------------------------

class TestTheTemplate(TempDirCase):
    """What ``--write-default-config`` writes."""

    def test_the_template_is_valid_toml(self):
        config = Config(path=self.tmp / "config.toml", environ={})
        path = config.write_default()
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        self.assertIsInstance(data, dict)

    def test_the_template_carries_every_setting(self):
        config = Config(path=self.tmp / "config.toml", environ={})
        text = config.default_template()
        for setting in SETTINGS:
            self.assertIn(f"# {setting.option} =", text, setting.key)

    def test_the_template_is_private(self):
        config = Config(path=self.tmp / "config.toml", environ={})
        path = config.write_default()
        mode = stat.S_IMODE(path.stat().st_mode)
        self.assertEqual(mode, 0o600)

    def test_the_template_explains_the_precedence(self):
        config = Config(path=self.tmp / "config.toml", environ={})
        text = config.default_template()
        self.assertIn("flag", text)
        self.assertIn("environment variable", text)
        self.assertIn("default", text)

    def test_an_existing_file_is_not_overwritten(self):
        """The settings the operator wrote are worth more than a fresh copy."""
        target = self.tmp / "config.toml"
        target.write_text("[llm]\nmodel = 'mine'\n", encoding="utf-8")
        config = Config(path=target, environ={})

        with self.assertRaises(FileExistsError):
            config.write_default()

        self.assertEqual(
            target.read_text(encoding="utf-8"), "[llm]\nmodel = 'mine'\n"
        )

    def test_an_existing_file_is_overwritten_when_it_is_asked_for(self):
        target = self.tmp / "config.toml"
        target.write_text("[llm]\nmodel = 'mine'\n", encoding="utf-8")
        config = Config(path=target, environ={})

        config.write_default(overwrite=True)

        self.assertIn("# model =", target.read_text(encoding="utf-8"))

    def test_a_symbolic_link_is_never_written_through(self):
        """The link and the file it points at are two different things."""
        elsewhere = self.tmp / "elsewhere.toml"
        elsewhere.write_text("do not touch me\n", encoding="utf-8")
        link = self.tmp / "config.toml"
        link.symlink_to(elsewhere)

        config = Config(path=link, environ={})
        with self.assertRaises(FileExistsError):
            config.write_default()

        self.assertEqual(
            elsewhere.read_text(encoding="utf-8"), "do not touch me\n"
        )

    def test_a_broken_symbolic_link_is_not_written_through(self):
        link = self.tmp / "config.toml"
        link.symlink_to(self.tmp / "nothing.toml")

        config = Config(path=link, environ={})
        with self.assertRaises(FileExistsError):
            config.write_default()

        self.assertFalse((self.tmp / "nothing.toml").exists())

    def test_the_file_is_private_from_the_moment_it_exists(self):
        """Not 'private after a moment' — private."""
        target = self.tmp / "config.toml"
        config = Config(path=target, environ={})
        config.write_default()
        mode = stat.S_IMODE(target.stat().st_mode)
        self.assertEqual(mode, 0o600)

    def test_the_directory_is_created_when_it_is_missing(self):
        target = self.tmp / "deep" / "deeper" / "config.toml"
        config = Config(path=target, environ={})
        written = config.write_default()
        self.assertTrue(written.is_file())


# ---------------------------------------------------------------------------
# The file the agent creates for itself
# ---------------------------------------------------------------------------

class TestTheFileTheAgentCreatesForItself(TempDirCase):
    """What the agent writes into its home directory when it starts."""

    def the_default(self, home: Path) -> Config:
        """A configuration that reads the default location of a home.

        ``XDG_CONFIG_HOME`` and not ``HOME``: the ``~`` of
        ``~/.config`` is expanded by :meth:`Path.expanduser`, which reads
        the environment of the **process**, not the mapping that was
        handed over.
        """
        return Config(environ={CONFIG_HOME_ENV: str(home / ".config")})

    def test_the_file_is_created_when_it_is_not_there(self):
        home = self.tmp / "home"
        config = self.the_default(home)

        created = config.ensure_default()

        self.assertIsNotNone(created)
        self.assertTrue(created.is_file())
        self.assertEqual(
            created, home / ".config" / APP_DIR_NAME / CONFIG_FILENAME
        )

    def test_the_file_it_creates_is_private(self):
        home = self.tmp / "home"
        config = self.the_default(home)

        created = config.ensure_default()

        self.assertEqual(stat.S_IMODE(created.stat().st_mode), 0o600)

    def test_the_file_it_creates_carries_no_settings(self):
        """It must not change the way the agent runs."""
        home = self.tmp / "home"
        config = self.the_default(home)

        created = config.ensure_default()

        with created.open("rb") as handle:
            data = tomllib.load(handle)
        for section in data.values():
            self.assertEqual(section, {}, "the template carries a setting")

    def test_an_existing_file_is_not_overwritten(self):
        home = self.tmp / "home"
        target = home / ".config" / APP_DIR_NAME / CONFIG_FILENAME
        target.parent.mkdir(parents=True)
        target.write_text("[llm]\nmodel = 'mine'\n", encoding="utf-8")
        config = self.the_default(home)

        created = config.ensure_default()

        self.assertIsNone(created)
        self.assertEqual(
            target.read_text(encoding="utf-8"), "[llm]\nmodel = 'mine'\n"
        )

    def test_a_file_the_operator_named_is_not_created(self):
        """They pointed at it on purpose."""
        home = self.tmp / "home"
        named = self.tmp / "named.toml"
        config = Config(
            environ={
                CONFIG_HOME_ENV: str(home / ".config"),
                CONFIG_PATH_ENV: str(named),
            },
        )

        created = config.ensure_default()

        self.assertIsNone(created)
        self.assertFalse(named.exists())

    def test_a_file_that_is_not_the_default_one_is_not_created(self):
        other = self.tmp / "somewhere" / "config.toml"
        config = Config(
            path=other,
            environ={CONFIG_HOME_ENV: str(self.tmp / "home" / ".config")},
        )

        created = config.ensure_default()

        self.assertIsNone(created)
        self.assertFalse(other.exists())

    def test_a_symbolic_link_is_not_created_through(self):
        home = self.tmp / "home"
        target = home / ".config" / APP_DIR_NAME / CONFIG_FILENAME
        target.parent.mkdir(parents=True)
        elsewhere = self.tmp / "elsewhere.toml"
        elsewhere.write_text("do not touch me\n", encoding="utf-8")
        target.symlink_to(elsewhere)
        config = self.the_default(home)

        created = config.ensure_default()

        self.assertIsNone(created)
        self.assertEqual(
            elsewhere.read_text(encoding="utf-8"), "do not touch me\n"
        )

    def test_importing_the_agent_writes_nothing(self):
        """The creation belongs to the **startup**, not to the import.

        A module that writes into the home directory when it is imported
        litters every process that imports it — the tests, the tools, a
        library that uses the agent.
        """
        home = self.tmp / "home"
        script = (
            "import importlib.util, sys\n"
            f"spec = importlib.util.spec_from_file_location('agent', {str(ROOT / 'agent-torvalds.py')!r})\n"
            "module = importlib.util.module_from_spec(spec)\n"
            "sys.modules['agent'] = module\n"
            "spec.loader.exec_module(module)\n"
        )
        env = dict(os.environ)
        env["HOME"] = str(home)
        env.pop("XDG_CONFIG_HOME", None)
        env.pop(CONFIG_PATH_ENV, None)
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
            timeout=180,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertFalse(
            (home / ".config" / APP_DIR_NAME / CONFIG_FILENAME).exists()
        )

    def test_both_orchestrators_create_the_file_at_the_startup(self):
        """The wiring, pinned on the source — the way the repo pins it."""
        for filename in ("agent-torvalds.py", "agent-torvalds-mw.py"):
            source = (ROOT / filename).read_text(encoding="utf-8")
            self.assertIn("config.ensure_default()", source, filename)

    def test_a_home_that_cannot_be_written_to_is_not_fatal(self):
        """The agent boots anyway."""
        home = self.tmp / "home"
        (home / ".config").mkdir(parents=True)
        (home / ".config" / APP_DIR_NAME).write_text("not a directory")
        config = self.the_default(home)

        created = config.ensure_default()

        self.assertIsNone(created)
        self.assertTrue(config.problems)
        self.assertIn("could not be created", config.problems[0])


# ---------------------------------------------------------------------------
# Writing into the file
# ---------------------------------------------------------------------------

class TestWritingIntoTheFile(TempDirCase):
    """What ``\\config <setting> <value>`` writes."""

    def a_config(self, text: str = "") -> Config:
        """A configuration that reads a file with the given text."""
        path = self.tmp / "config.toml"
        if text:
            path.write_text(text, encoding="utf-8")
        return Config(path=path, environ={})

    def the_file(self, config: Config) -> str:
        """The text of the file the configuration reads."""
        return config.path.read_text(encoding="utf-8")

    def test_the_value_is_written_into_the_file(self):
        config = self.a_config('[logging]\nfile = "old.log"\n')
        value, problem = config.set_value("logging.file", "agent.output.log")
        self.assertIsNone(problem)
        self.assertEqual(value, "agent.output.log")
        self.assertIn('file = "agent.output.log"', self.the_file(config))

    def test_a_commented_setting_is_uncommented(self):
        """That is where the template leaves every setting."""
        config = self.a_config(
            "[logging]\n# The log file.\n# file = \"\"\n# dir = \"x\"\n"
        )
        config.set_value("logging.file", "agent.output.log")
        text = self.the_file(config)
        self.assertIn('file = "agent.output.log"', text)
        self.assertNotIn('# file = ', text)

    def test_the_comments_of_the_operator_survive(self):
        config = self.a_config(
            "[logging]\n# my own note\nfile = \"old.log\"\n# another note\n"
        )
        config.set_value("logging.file", "new.log")
        text = self.the_file(config)
        self.assertIn("# my own note", text)
        self.assertIn("# another note", text)
        self.assertIn('file = "new.log"', text)

    def test_the_order_of_the_settings_survives(self):
        config = self.a_config(
            '[llm]\nmodel = "a"\nhost = "b"\n[logging]\nfile = "c"\n'
        )
        config.set_value("logging.file", "d")
        text = self.the_file(config)
        self.assertLess(text.index('model = "a"'), text.index('host = "b"'))
        self.assertLess(text.index('host = "b"'), text.index('file = "d"'))

    def test_a_setting_that_is_not_in_the_file_is_added(self):
        config = self.a_config('[llm]\nmodel = "a"\n')
        config.set_value("logging.file", "agent.output.log")
        text = self.the_file(config)
        self.assertIn("[logging]", text)
        self.assertIn('file = "agent.output.log"', text)

    def test_a_section_that_is_not_in_the_file_is_created(self):
        config = self.a_config('[llm]\nmodel = "a"\n')
        config.set_value("logging.file", "agent.output.log")
        text = self.the_file(config)
        self.assertIn("[logging]", text)
        self.assertIn('file = "agent.output.log"', text)
        # the section of the setting is the one it went into
        self.assertLess(text.index("[logging]"), text.index('file = "'))

    def test_the_value_is_escaped(self):
        """A path with a backslash in it has to survive the trip."""
        config = self.a_config('[logging]\nfile = ""\n')
        config.set_value("logging.file", r"C:\Users\<user>\agent.log")
        import tomllib
        with config.path.open("rb") as handle:
            data = tomllib.load(handle)
        self.assertEqual(
            data["logging"]["file"], r"C:\Users\<user>\agent.log"
        )

    def test_an_unknown_setting_is_a_problem(self):
        config = self.a_config("")
        value, problem = config.set_value("logging.nonsense", "x")
        self.assertIsNone(value)
        self.assertIn("no setting called", problem)

    def test_a_value_that_is_not_usable_is_a_problem(self):
        """The file can never carry a value the agent would refuse."""
        config = self.a_config('[hitl]\ntimeout = 60\n')
        before = self.the_file(config)
        value, problem = config.set_value("hitl.timeout", "soon")
        self.assertIsNone(value)
        self.assertIsNotNone(problem)
        self.assertEqual(self.the_file(config), before)

    def test_a_number_is_written_as_a_number(self):
        config = self.a_config('[hitl]\ntimeout = -1\n')
        config.set_value("hitl.timeout", "120")
        import tomllib
        with config.path.open("rb") as handle:
            data = tomllib.load(handle)
        self.assertEqual(data["hitl"]["timeout"], 120)
        self.assertNotEqual(data["hitl"]["timeout"], "120")

    def test_a_boolean_is_written_as_a_boolean(self):
        config = self.a_config('[agent]\nverbose_events = false\n')
        config.set_value("agent.verbose_events", "yes")
        import tomllib
        with config.path.open("rb") as handle:
            data = tomllib.load(handle)
        self.assertIs(data["agent"]["verbose_events"], True)

    def test_the_file_stays_private(self):
        config = self.a_config("")
        config.set_value("logging.file", "agent.output.log")
        mode = stat.S_IMODE(config.path.stat().st_mode)
        self.assertEqual(mode, 0o600)

    def test_no_temporary_file_is_left_behind(self):
        config = self.a_config("")
        config.set_value("logging.file", "agent.output.log")
        leftovers = [p.name for p in config.path.parent.iterdir() if p != config.path]
        self.assertEqual(leftovers, [])

    def test_the_value_is_read_back_at_once(self):
        config = self.a_config("")
        config.set_value("logging.file", "agent.output.log")
        self.assertEqual(config.get("logging.file"), "agent.output.log")
        self.assertIn("config file", config.source("logging.file"))

    def test_a_file_that_is_not_there_is_created(self):
        config = self.a_config("")
        self.assertFalse(config.path.exists())
        value, problem = config.set_value("logging.file", "agent.output.log")
        self.assertIsNone(problem)
        self.assertTrue(config.path.is_file())
        self.assertIn('file = "agent.output.log"', self.the_file(config))


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------

class TestTheConfigCommand(TempDirCase):
    """The ``\\config`` command — show it, and change it."""

    def a_config(self, text: str = "") -> Config:
        """A configuration that reads a file with the given text."""
        path = self.tmp / "config.toml"
        if text:
            path.write_text(text, encoding="utf-8")
        return Config(path=path, environ={})

    def the_output(self, config: Config, argument: str) -> str:
        """What the command prints."""
        import io

        from rich.console import Console

        from components.config_view import handle_config

        stream = io.StringIO()
        console = Console(file=stream, width=100, force_terminal=False)
        handle_config(config, argument, console)
        return stream.getvalue()

    def test_without_an_argument_the_table_is_shown(self):
        config = self.a_config("")
        config.get("llm.model")
        output = self.the_output(config, "")
        self.assertIn("llm.model", output)

    def test_one_setting_is_shown_in_detail(self):
        config = self.a_config('[logging]\nfile = "agent.output.log"\n')
        output = self.the_output(config, "logging.file")
        self.assertIn("logging.file", output)
        self.assertIn("agent.output.log", output)
        self.assertIn("config file", output)

    def test_a_value_is_written_into_the_file(self):
        config = self.a_config('[logging]\nfile = ""\n')
        output = self.the_output(config, "logging.file agent.output.log")
        self.assertIn("agent.output.log", output)
        self.assertIn(
            'file = "agent.output.log"',
            config.path.read_text(encoding="utf-8"),
        )

    def test_a_value_with_a_space_is_written(self):
        config = self.a_config('[logging]\nfile = ""\n')
        self.the_output(config, "logging.file my agent.log")
        self.assertIn(
            'file = "my agent.log"',
            config.path.read_text(encoding="utf-8"),
        )

    def test_an_unknown_setting_says_so(self):
        config = self.a_config("")
        output = self.the_output(config, "logging.nonsense")
        self.assertIn("no setting called", output)

    def test_a_value_that_is_not_usable_says_so(self):
        config = self.a_config('[hitl]\ntimeout = 60\n')
        output = self.the_output(config, "hitl.timeout soon")
        self.assertIn("must be a number", output)

    def test_the_wiring_is_in_both_orchestrators(self):
        """The argument has to reach the command."""
        for filename in ("agent-torvalds.py", "agent-torvalds-mw.py"):
            source = (ROOT / filename).read_text(encoding="utf-8")
            self.assertIn("handle_config(config, argument", source, filename)


# ---------------------------------------------------------------------------
# The effective configuration
# ---------------------------------------------------------------------------

class TestTheEffectiveConfiguration(TempDirCase):
    """The table the ``\\config`` command prints."""

    def test_only_the_resolved_settings_are_listed(self):
        config = self.config('[llm]\nmodel = "x"\n')
        config.get("llm.model")
        rows = config.effective()
        self.assertEqual([row.key for row in rows], ["llm.model"])

    def test_the_table_has_a_stable_order(self):
        config = self.config("")
        config.get("stats.enabled")
        config.get("llm.model")
        rows = config.effective()
        self.assertEqual([row.key for row in rows], ["llm.model", "stats.enabled"])

    def test_a_row_carries_the_value_and_the_source(self):
        config = self.config('[llm]\nmodel = "x"\n')
        config.get("llm.model")
        row = config.effective()[0]
        self.assertIsInstance(row, Effective)
        self.assertEqual(row.value, "x")
        self.assertIn("config file", row.source)


# ---------------------------------------------------------------------------
# The wiring
# ---------------------------------------------------------------------------

class TestTheWiring(TempDirCase):
    """The orchestrators read the file, and the file changes nothing else.

    The configuration is read **when the module is imported**, so these
    checks run the orchestrators in a **subprocess** with the environment
    they would really have.  A test that changes the environment of the
    running process would read a configuration that was built before the
    change — and would prove nothing.
    """

    #: The settings that would win over the file if they were set.
    THE_ENVIRONMENT = (
        "TORVALDS_MODEL",
        "TORVALDS_MAX_ITERATIONS",
        "TORVALDS_HITL_TIMEOUT",
        "TORVALDS_LOG_FILE",
        "TORVALDS_LOG_DIR",
        "TORVALDS_LOG_MAX_SIZE",
        "TORVALDS_LOG_MAX_FILES",
        "TORVALDS_LOG_SYMLINK",
    )

    def _run(self, filename: str, environ: dict) -> str:
        """Import an orchestrator in a subprocess and return its output."""
        script = (
            "import importlib.util, sys\n"
            f"spec = importlib.util.spec_from_file_location('agent', {str(ROOT / filename)!r})\n"
            "module = importlib.util.module_from_spec(spec)\n"
            "sys.modules['agent'] = module\n"
            "spec.loader.exec_module(module)\n"
            "print('MODEL=' + str(module.MODEL))\n"
            "print('HITL_TIMEOUT=' + str(module.HITL_TIMEOUT))\n"
            "print('LOG_FILE=' + str(module.config.get('logging.file')))\n"
            "print('LOG_DIR=' + str(module.config.get('logging.dir')))\n"
            "print('SOURCE=' + module.config.source('llm.model'))\n"
        )
        env = dict(os.environ)
        for var in self.THE_ENVIRONMENT:
            env.pop(var, None)
        # The home of the test, not the home of the operator: the agent
        # writes its configuration file there when it starts, and the
        # test must not litter the machine it runs on.
        env["HOME"] = str(self.tmp)
        env.pop("XDG_CONFIG_HOME", None)
        env.update(environ)
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(ROOT),
            timeout=180,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        return result.stdout

    def _values(self, output: str) -> dict:
        return dict(
            line.split("=", 1) for line in output.splitlines() if "=" in line
        )

    def test_the_classic_agent_reads_the_file(self):
        path = self.write('[llm]\nmodel = "from-the-file"\n')
        values = self._values(
            self._run("agent-torvalds.py", {CONFIG_PATH_ENV: str(path)})
        )
        self.assertEqual(values["MODEL"], "from-the-file")
        self.assertIn("config file", values["SOURCE"])

    def test_the_multi_window_agent_reads_the_file(self):
        path = self.write('[llm]\nmodel = "from-the-file"\n')
        values = self._values(
            self._run("agent-torvalds-mw.py", {CONFIG_PATH_ENV: str(path)})
        )
        self.assertEqual(values["MODEL"], "from-the-file")

    def test_the_environment_still_wins_over_the_file(self):
        path = self.write('[llm]\nmodel = "from-the-file"\n')
        values = self._values(
            self._run(
                "agent-torvalds.py",
                {
                    CONFIG_PATH_ENV: str(path),
                    "TORVALDS_MODEL": "from-the-environment",
                },
            )
        )
        self.assertEqual(values["MODEL"], "from-the-environment")
        self.assertIn("environment variable", values["SOURCE"])

    def test_the_logging_settings_come_from_the_file(self):
        path = self.write(
            f'[logging]\nfile = "agent.log"\ndir = "{self.tmp}"\n'
        )
        values = self._values(
            self._run("agent-torvalds.py", {CONFIG_PATH_ENV: str(path)})
        )
        self.assertEqual(values["LOG_FILE"], "agent.log")
        self.assertEqual(values["LOG_DIR"], str(self.tmp))

    def test_without_a_file_the_defaults_are_used(self):
        values = self._values(
            self._run(
                "agent-torvalds.py",
                {CONFIG_PATH_ENV: str(self.tmp / "nothing.toml")},
            )
        )
        self.assertEqual(values["MODEL"], "richardyoung/qwen3.6-27b-abliterated:Q4_K_M")
        self.assertEqual(values["SOURCE"], "default")


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

class TestTheRegistry(unittest.TestCase):
    """The settings the file may carry."""

    def test_every_setting_has_a_unique_key(self):
        keys = [s.key for s in SETTINGS]
        self.assertEqual(len(keys), len(set(keys)))

    def test_every_key_has_a_section_and_an_option(self):
        for setting in SETTINGS:
            self.assertIn(".", setting.key, setting.key)
            self.assertTrue(setting.section, setting.key)
            self.assertTrue(setting.option, setting.key)

    def test_every_setting_has_a_description(self):
        for setting in SETTINGS:
            self.assertTrue(setting.description, setting.key)

    def test_the_environment_variables_are_unique(self):
        variables = [s.env_var for s in SETTINGS if s.env_var]
        self.assertEqual(len(variables), len(set(variables)))

    def test_the_setting_is_immutable(self):
        setting = SETTINGS[0]
        with self.assertRaises(Exception):
            setting.default = "something else"


if __name__ == "__main__":
    unittest.main()
