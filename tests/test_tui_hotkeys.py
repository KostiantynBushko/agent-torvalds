"""
Unit tests for the hot-keys of the Torvalds TUI.

The hot-keys are the machinery the two hot-keys the operator asked for
are built on: the table of the bindings, the matcher that finds the
binding of a key, the reading of the file of the configuration, and the
routing in the application.

What the tests hold together:

* **the settings of the file and the actions of the registry agree** --
  one for one.  A setting without an action is a key the operator can
  set and that does nothing; an action without a setting is a hot-key
  the operator cannot change;
* **a chord the operating system takes is refused** -- the kernel, the
  terminal and the desktop have their share of the keyboard, and a
  hot-key that one of them eats is not a hot-key;
* **a refusal is a warning, never a crash**: the default stands, and
  the TUI starts;
* **a printable character always goes into the input**, and it takes
  the focus back: the operator is never trapped in a pane;
* **the \\keys screen names every binding of the table, and only
  those** -- and the \\help screen names none of them.

Run with:
    pytest tests/test_tui_hotkeys.py -v
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from components.config import Config, SETTINGS  # noqa: E402
from components.tui import hotkeys  # noqa: E402
from components.tui.hotkeys import (  # noqa: E402
    ACTION_FOCUS_INPUT,
    ACTION_FOCUS_NEXT,
    ACTION_FOCUS_PREVIOUS,
    ACTION_SCROLL_DOWN,
    ACTION_SCROLL_END,
    ACTION_SCROLL_HOME,
    ACTION_SCROLL_PAGE_DOWN,
    ACTION_SCROLL_PAGE_UP,
    ACTION_SCROLL_UP,
    ACTION_TOGGLE_PROGRESS,
    ACTION_TOGGLE_TELEMETRY,
    FOCUS_INPUT,
    SCOPE_BAR,
    SCOPE_GLOBAL,
    SCOPE_PANE,
)
from components.tui.state_bridge import TuiState  # noqa: E402


def an_app(**kwargs):
    """A TUI application that is not running."""
    from components.tui.tui_app import TuiApp

    return TuiApp(
        agent=MagicMock(),
        prompt_handler_fn=MagicMock(),
        state=TuiState(),
        console=MagicMock(),
        **kwargs,
    )


def a_config_with(hotkeys_section: str, tmp_path: Path) -> Config:
    """A configuration file that carries a [hotkeys] section."""
    path = tmp_path / "config.toml"
    path.write_text(hotkeys_section, encoding="utf-8")
    return Config(path=path, environ={})


# ---------------------------------------------------------------------------
# The table
# ---------------------------------------------------------------------------


class TestTheTable(unittest.TestCase):
    """The table of the keys of the TUI."""

    def test_every_binding_has_a_description(self):
        for binding in hotkeys.ALL_KEYS:
            self.assertTrue(
                binding.description,
                f"{binding.keys} has no description -- the \\keys screen "
                "would show a key without a word",
            )

    def test_the_table_has_no_duplicate_keys(self):
        """Two actions on one key: the second one would never run."""
        seen = {}
        for binding in hotkeys.ALL_KEYS:
            if not binding.action:
                continue
            self.assertNotIn(
                binding.keys,
                seen,
                f"the key {binding.keys} is bound twice -- to "
                f"{seen.get(binding.keys)} and to {binding.action}",
            )
            seen[binding.keys] = binding.action

    def test_every_action_has_a_setting(self):
        """An action without a setting is a hot-key nobody can change."""
        settings = {
            setting.option
            for setting in SETTINGS
            if setting.section == "hotkeys"
        }
        for binding in hotkeys.HOT_KEYS:
            self.assertIn(
                binding.option,
                settings,
                f"the action {binding.action} has no setting in the file",
            )

    def test_every_setting_has_an_action(self):
        """A setting without an action is a key the operator can set."""
        actions = {binding.option for binding in hotkeys.HOT_KEYS}
        for setting in SETTINGS:
            if setting.section != "hotkeys":
                continue
            self.assertIn(
                setting.option,
                actions,
                f"the setting {setting.key} has no action -- it would do "
                "nothing",
            )

    def test_the_defaults_of_the_settings_and_of_the_table_agree(self):
        """The file shows a default, and the table binds another one."""
        defaults = {
            setting.option: setting.default
            for setting in SETTINGS
            if setting.section == "hotkeys"
        }
        for binding in hotkeys.HOT_KEYS:
            self.assertEqual(
                defaults[binding.option],
                binding.label,
                f"the setting {binding.setting} shows {defaults[binding.option]!r} "
                f"and the table binds {binding.label!r}",
            )

    def test_the_default_bindings_are_free_of_the_chords_the_os_takes(self):
        """A hot-key that the operating system would eat is not a hot-key."""
        for binding in hotkeys.HOT_KEYS:
            self.assertEqual(
                "",
                hotkeys.refusal_reason(binding.keys),
                f"the binding {binding.label} is refused: "
                f"{hotkeys.refusal_reason(binding.keys)}",
            )


# ---------------------------------------------------------------------------
# The chords
# ---------------------------------------------------------------------------


class TestTheChords(unittest.TestCase):
    """The way the operator writes a chord, and the way the reader names it."""

    def test_a_chord_is_read_the_way_the_reader_names_it(self):
        cases = {
            "Ctrl+T": "CTRL_T",
            "ctrl+t": "CTRL_T",
            "Ctrl+P": "CTRL_P",
            "Tab": "TAB",
            "Shift+Tab": "SHIFT_TAB",
            "Esc": "ESCAPE",
            "Escape": "ESCAPE",
            "Up": "UP",
            "Down": "DOWN",
            "PgUp": "PGUP",
            "PgDn": "PGDN",
            "PageUp": "PGUP",
            "Home": "HOME",
            "End": "END",
            "F5": "F5",
            "Ctrl+Alt+Y": "CTRL_ALT_Y",
        }
        for text, expected in cases.items():
            self.assertEqual(
                hotkeys.parse_chord(text),
                expected,
                f"the chord {text!r} was not read as {expected!r}",
            )

    def test_a_chord_that_cannot_be_read_is_none(self):
        for text in ("Ctrl+", "Space Bar", "Ctrl+Nonsense", "", "   ", "F99"):
            self.assertIsNone(
                hotkeys.parse_chord(text),
                f"the chord {text!r} was read as a key",
            )

    def test_the_label_is_the_way_the_operator_reads_it(self):
        cases = {
            "CTRL_T": "Ctrl+T",
            "CTRL_SHIFT_UP": "Ctrl+Shift+Up",
            "SHIFT_TAB": "Shift+Tab",
            "ESCAPE": "Esc",
            "PGDN": "PgDn",
            "PGUP": "PgUp",
            "TAB": "Tab",
            "F5": "F5",
        }
        for name, expected in cases.items():
            self.assertEqual(hotkeys.chord_label(name), expected)

    def test_the_round_trip_of_a_chord(self):
        """What the operator reads is what the operator may write."""
        for binding in hotkeys.HOT_KEYS:
            self.assertEqual(
                hotkeys.parse_chord(binding.label),
                binding.keys,
                f"the label {binding.label!r} does not read back as "
                f"{binding.keys!r}",
            )


# ---------------------------------------------------------------------------
# The chords the operating system takes
# ---------------------------------------------------------------------------


class TestTheChordsTheOperatingSystemTakes(unittest.TestCase):
    """A hot-key that the operating system eats is not a hot-key."""

    def test_the_chords_of_the_kernel_are_refused(self):
        for name in ("CTRL_C", "CTRL_Z", "CTRL_BACKSLASH"):
            self.assertTrue(
                hotkeys.is_system_key(name),
                f"the chord {name} was not refused",
            )

    def test_the_chords_of_the_terminal_are_refused(self):
        for name in ("CTRL_S", "CTRL_Q", "CTRL_H", "CTRL_I", "CTRL_J", "CTRL_M"):
            self.assertTrue(
                hotkeys.is_system_key(name),
                f"the chord {name} was not refused",
            )

    def test_the_chords_of_the_desktop_are_refused(self):
        for name in ("ALT_a", "ALT_UP", "ALT_TAB"):
            self.assertTrue(
                hotkeys.is_system_key(name),
                f"the chord {name} was not refused",
            )

    def test_a_printable_character_is_not_bindable(self):
        """A printable character always goes into the input."""
        self.assertTrue(hotkeys.is_system_key("SPACE"))

    def test_the_letters_that_are_left_are_not_refused(self):
        for name in ("CTRL_A", "CTRL_B", "CTRL_E", "CTRL_F", "CTRL_G",
                     "CTRL_K", "CTRL_L", "CTRL_N", "CTRL_O", "CTRL_P",
                     "CTRL_R", "CTRL_T", "CTRL_U", "CTRL_V", "CTRL_X",
                     "CTRL_Y"):
            self.assertFalse(
                hotkeys.is_system_key(name),
                f"the chord {name} was refused -- it is one of the letters "
                "that are left",
            )


# ---------------------------------------------------------------------------
# The file of the configuration
# ---------------------------------------------------------------------------


class TestTheConfigurationFile(unittest.TestCase):
    """The bindings come from the file the operator already has."""

    def setUp(self):
        import tempfile

        self._directory = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._directory.name)

    def tearDown(self):
        self._directory.cleanup()

    def test_the_value_of_the_file_wins_over_the_default(self):
        config = a_config_with(
            '[hotkeys]\ntoggle_telemetry = "Ctrl+Y"\n', self.tmp_path
        )
        resolved = hotkeys.resolve(config)

        self.assertEqual(resolved.chord_of(ACTION_TOGGLE_TELEMETRY), "CTRL_Y")
        self.assertEqual(resolved.problems, ())

    def test_the_old_key_is_freed_by_the_new_one(self):
        """The operator moves one action, and the key it had is free."""
        config = a_config_with(
            '[hotkeys]\ntoggle_telemetry = "Ctrl+Y"\n', self.tmp_path
        )
        resolved = hotkeys.resolve(config)

        self.assertIsNone(hotkeys.match("CTRL_T", resolved))
        self.assertIsNotNone(hotkeys.match("CTRL_Y", resolved))

    def test_an_empty_value_unbinds_the_action(self):
        config = a_config_with(
            '[hotkeys]\nfocus_previous = ""\n', self.tmp_path
        )
        resolved = hotkeys.resolve(config)

        self.assertEqual(resolved.chord_of(ACTION_FOCUS_PREVIOUS), "")
        self.assertIsNone(hotkeys.match("SHIFT_TAB", resolved))
        self.assertEqual(resolved.problems, ())

    def test_a_chord_the_operating_system_takes_is_refused(self):
        config = a_config_with(
            '[hotkeys]\ntoggle_telemetry = "Ctrl+S"\n', self.tmp_path
        )
        resolved = hotkeys.resolve(config)

        self.assertEqual(
            resolved.chord_of(ACTION_TOGGLE_TELEMETRY),
            "CTRL_T",
            "the default does not stand after a refusal",
        )
        self.assertTrue(resolved.problems, "the refusal was not reported")

    def test_a_chord_that_cannot_be_read_is_refused(self):
        config = a_config_with(
            '[hotkeys]\ntoggle_telemetry = "Ctrl+"\n', self.tmp_path
        )
        resolved = hotkeys.resolve(config)

        self.assertEqual(resolved.chord_of(ACTION_TOGGLE_TELEMETRY), "CTRL_T")
        self.assertTrue(resolved.problems, "the refusal was not reported")

    def test_two_actions_that_ask_for_the_same_chord(self):
        """The second one is refused, and the first one keeps the chord."""
        config = a_config_with(
            '[hotkeys]\ntoggle_telemetry = "Ctrl+Y"\n'
            'toggle_progress = "Ctrl+Y"\n',
            self.tmp_path,
        )
        resolved = hotkeys.resolve(config)

        self.assertEqual(resolved.chord_of(ACTION_TOGGLE_TELEMETRY), "CTRL_Y")
        self.assertEqual(resolved.chord_of(ACTION_TOGGLE_PROGRESS), "CTRL_P")
        self.assertTrue(resolved.problems, "the refusal was not reported")

    def test_a_refusal_never_stops_the_tui(self):
        """A broken file is a warning, not a failed boot."""
        config = a_config_with(
            '[hotkeys]\ntoggle_telemetry = "Ctrl+S"\n'
            'focus_next = "Ctrl+"\n',
            self.tmp_path,
        )
        resolved = hotkeys.resolve(config)

        self.assertTrue(resolved.problems)
        self.assertEqual(len(resolved.hot_keys), len(hotkeys.HOT_KEYS))

    def test_the_file_that_says_nothing_leaves_the_defaults(self):
        config = a_config_with("[llm]\nmodel = \"x\"\n", self.tmp_path)
        resolved = hotkeys.resolve(config)

        for binding in hotkeys.HOT_KEYS:
            self.assertEqual(
                resolved.chord_of(binding.action),
                binding.keys,
                f"the default of {binding.action} did not stand",
            )
        self.assertEqual(resolved.problems, ())

    def test_the_template_carries_the_section(self):
        """The file the agent creates is the file it can read back."""
        template = Config(path=self.tmp_path / "none.toml", environ={}).default_template()

        self.assertIn("[hotkeys]", template)
        for binding in hotkeys.HOT_KEYS:
            self.assertIn(
                f"# {binding.option} = ",
                template,
                f"the template does not carry the setting {binding.option}",
            )

    def test_the_sections_of_the_template_are_never_unknown(self):
        """The agent must not report the sections it wrote itself."""
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text(
                Config(path=path, environ={}).default_template(), encoding="utf-8"
            )
            config = Config(path=path, environ={})

            self.assertEqual(
                [p for p in config.problems if "not known" in p],
                [],
                "the agent reported the sections it wrote itself",
            )

    def test_the_template_walks_the_settings_of_the_instance(self):
        """A Config with its own settings writes a template that matches."""
        own = tuple(s for s in SETTINGS if s.section == "hotkeys")
        config = Config(path=self.tmp_path / "none.toml", environ={}, settings=own)

        template = config.default_template()

        self.assertIn("[hotkeys]", template)
        self.assertNotIn("[llm]", template)


# ---------------------------------------------------------------------------
# The routing
# ---------------------------------------------------------------------------


class TestTheRouting(unittest.TestCase):
    """The keys reach the actions, and the input keeps the rest."""

    def setUp(self):
        self.app = an_app()

    def test_a_chord_is_live_while_the_operator_is_typing(self):
        self.app.state.input_buffer = "hello"
        self.app._handle_key("CTRL_T")

        self.assertIn("telemetry_pane", self.app.state.hidden_panes)
        self.assertEqual(
            self.app.state.input_buffer,
            "hello",
            "the chord ate what the operator was writing",
        )

    def test_a_chord_that_is_not_bound_goes_into_the_input(self):
        self.app._handle_key("a")

        self.assertEqual(self.app.state.input_buffer, "a")

    def test_a_printable_character_takes_the_focus_back(self):
        """The operator is never trapped in a pane."""
        self.app.state.set_focus(hotkeys.FOCUS_PROGRESS)
        self.app._handle_key("x")

        self.assertEqual(self.app.state.focus, FOCUS_INPUT)
        self.assertEqual(self.app.state.input_buffer, "x")

    def test_the_telemetry_pane_is_hidden_and_shown(self):
        self.app._handle_key("CTRL_T")

        self.assertIn("telemetry_pane", self.app.state.hidden_panes)

        self.app._handle_key("CTRL_T")

        self.assertNotIn("telemetry_pane", self.app.state.hidden_panes)

    def test_the_progress_pane_is_hidden_and_shown(self):
        self.app._handle_key("CTRL_P")

        self.assertIn("progress_pane", self.app.state.hidden_panes)

        self.app._handle_key("CTRL_P")

        self.assertNotIn("progress_pane", self.app.state.hidden_panes)

    def test_the_focus_moves_to_the_next_pane(self):
        self.app._handle_key("TAB")

        self.assertEqual(self.app.state.focus, hotkeys.FOCUS_DOCUMENT)

    def test_the_focus_moves_to_the_previous_pane(self):
        self.app._handle_key("TAB")
        self.app._handle_key("TAB")
        self.app._handle_key("SHIFT_TAB")

        self.assertEqual(self.app.state.focus, hotkeys.FOCUS_DOCUMENT)

    def test_the_focus_comes_back_to_the_command_bar(self):
        self.app._handle_key("TAB")
        self.app._handle_key("ESCAPE")

        self.assertEqual(self.app.state.focus, FOCUS_INPUT)

    def test_a_pane_key_is_live_only_while_its_pane_has_the_focus(self):
        """The pager keys scroll the document when the bar has the focus."""
        self.app.state.set_markdown_content("line\n" * 50)
        self.app.state.total_rendered_lines = 50

        self.app._handle_key("PGDN")
        self.assertEqual(self.app.state.scroll_offset, 6)

        self.app.state.set_focus(hotkeys.FOCUS_PROGRESS)
        self.app._handle_key("PGDN")

        self.assertEqual(
            self.app.state.scroll_offset,
            6,
            "the pager key of the document moved while the progress pane "
            "had the focus",
        )

    def test_the_answer_of_the_agent_keeps_every_key_that_is_not_a_chord(self):
        """The keys of the answer of the operator are his."""
        self.app.state.hitl_active = True
        self.app.state.set_focus(hotkeys.FOCUS_PROGRESS)

        self.app._handle_key("a")

        self.assertEqual(self.app.state.input_buffer, "a")

    def test_the_chords_are_live_while_the_answer_of_the_agent_is_typed(self):
        """A chord carries no text, and it cannot eat the answer."""
        self.app.state.hitl_active = True

        self.app._handle_key("CTRL_T")

        self.assertIn("telemetry_pane", self.app.state.hidden_panes)

    def test_the_session_picker_keeps_every_key_that_is_not_a_chord(self):
        app = an_app(select_session_at_startup=True)

        app._handle_key("2")

        self.assertEqual(app.state.input_buffer, "2")

    def test_a_paste_is_never_taken_by_a_hot_key(self):
        from components.tui.input_reader import PastedText

        self.app._handle_key(PastedText("\\keys\n"))

        self.assertEqual(self.app.state.input_buffer, "\\keys\n")
        self.assertNotIn("telemetry_pane", self.app.state.hidden_panes)


# ---------------------------------------------------------------------------
# The screen
# ---------------------------------------------------------------------------


class TestTheKeysScreen(unittest.TestCase):
    """The \\keys screen names every binding of the table, and only those."""

    def test_the_screen_names_every_binding(self):
        markdown = hotkeys.keys_markdown()

        for binding in hotkeys.HOT_KEYS:
            self.assertIn(
                binding.label,
                markdown,
                f"the screen does not name {binding.label}",
            )

    def test_the_screen_names_the_keys_of_the_command_bar(self):
        markdown = hotkeys.keys_markdown()

        for binding in hotkeys.BAR_KEYS:
            self.assertIn(
                binding.label,
                markdown,
                f"the screen does not name {binding.label}",
            )

    def test_the_screen_carries_the_lines_to_copy(self):
        markdown = hotkeys.keys_markdown()

        self.assertIn("[hotkeys]", markdown)
        self.assertIn('toggle_telemetry = "Ctrl+T"', markdown)

    def test_the_screen_shows_the_chords_the_operator_has_today(self):
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text(
                '[hotkeys]\ntoggle_telemetry = "Ctrl+Y"\n', encoding="utf-8"
            )
            resolved = hotkeys.resolve(Config(path=path, environ={}))
            markdown = hotkeys.keys_markdown(resolved)

        self.assertIn('toggle_telemetry = "Ctrl+Y"', markdown)
        self.assertNotIn('toggle_telemetry = "Ctrl+T"', markdown)


# ---------------------------------------------------------------------------
# The help screen
# ---------------------------------------------------------------------------


class TestTheHelpScreen(unittest.TestCase):
    """The keys are not in the help screen: they have a command of their own."""

    def test_the_help_screen_names_no_binding(self):
        from components.command_registry import HelpOptions, build_help_markdown

        markdown = build_help_markdown(HelpOptions(tui=True))

        for binding in hotkeys.HOT_KEYS:
            self.assertNotIn(
                binding.label,
                markdown,
                f"the help screen names the binding {binding.label}",
            )


if __name__ == "__main__":
    unittest.main()
