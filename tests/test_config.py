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

# Ensure the repository root is on the path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from components.config import (  # noqa: E402
    APP_DIR_NAME,
    CONFIG_FILENAME,
    CONFIG_PATH_ENV,
    Config,
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
