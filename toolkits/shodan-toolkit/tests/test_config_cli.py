"""Tests for the configuration layer and the CLI entry point."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ..cli import main
from ..config import ShodanConfig, load_config


class TestConfig:
    def test_defaults(self) -> None:
        config = ShodanConfig()
        assert config.executable == "shodan"
        assert config.max_results == 100
        assert config.timeout > 0

    def test_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SHODAN_TOOLKIT_EXECUTABLE", "/opt/shodan")
        monkeypatch.setenv("SHODAN_TOOLKIT_TIMEOUT", "42")
        monkeypatch.setenv("SHODAN_TOOLKIT_MAX_RESULTS", "7")
        monkeypatch.setenv("SHODAN_TOOLKIT_API_KEY", "env-key")

        config = load_config()

        assert config.executable == "/opt/shodan"
        assert config.timeout == 42.0
        assert config.max_results == 7
        assert config.api_key == "env-key"

    def test_shodan_api_key_env_is_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SHODAN_API_KEY", "plain-key")
        config = load_config()
        assert config.api_key == "plain-key"

    def test_invalid_env_values_are_ignored(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SHODAN_TOOLKIT_TIMEOUT", "not-a-number")
        monkeypatch.setenv("SHODAN_TOOLKIT_MAX_RESULTS", "also-not-a-number")

        config = load_config()
        assert config.timeout == ShodanConfig().timeout
        assert config.max_results == ShodanConfig().max_results

    def test_from_file(self, tmp_path: Path) -> None:
        path = tmp_path / "config.json"
        path.write_text(json.dumps({"executable": "shodan-custom", "max_results": 3}))

        config = ShodanConfig.from_file(str(path))
        assert config.executable == "shodan-custom"
        assert config.max_results == 3

    def test_missing_file_yields_defaults(self, tmp_path: Path) -> None:
        config = ShodanConfig.from_file(str(tmp_path / "nope.json"))
        assert config.executable == "shodan"

    def test_malformed_file_yields_defaults(self, tmp_path: Path) -> None:
        path = tmp_path / "config.json"
        path.write_text("{not valid json")

        config = ShodanConfig.from_file(str(path))
        assert config.executable == "shodan"

    def test_unknown_keys_are_ignored(self) -> None:
        config = ShodanConfig.from_dict({"executable": "x", "bogus": 1})
        assert config.executable == "x"

    def test_to_dict_redacts_api_key(self) -> None:
        config = ShodanConfig(api_key="secret")
        assert config.to_dict()["api_key"] == "***redacted***"

    def test_save_and_reload(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "config.json"
        config = ShodanConfig(executable="saved-shodan")
        config.save(str(path))

        assert path.exists()
        reloaded = ShodanConfig.from_file(str(path))
        assert reloaded.executable == "saved-shodan"


class TestCLI:
    def test_version_command(self, capsys: pytest.CaptureFixture) -> None:
        assert main(["version"]) == 0
        output = capsys.readouterr().out
        assert "toolkit_version" in output

    def test_tools_command(self, capsys: pytest.CaptureFixture) -> None:
        assert main(["tools"]) == 0
        output = capsys.readouterr().out
        assert "shodan_search" in output
        assert "shodan_create_alert" not in output

    def test_tools_command_with_mutating(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        assert main(["tools", "--all"]) == 0
        output = capsys.readouterr().out
        assert "shodan_create_alert" in output

    def test_tools_schemas(self, capsys: pytest.CaptureFixture) -> None:
        assert main(["tools", "--schemas"]) == 0
        output = capsys.readouterr().out
        payload = json.loads(output)
        assert any(entry["name"] == "shodan_search" for entry in payload)

    def test_init_command(
        self, tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(
            "SHODAN_TOOLKIT_SHODAN_CONFIG_DIR", str(tmp_path / "shodan")
        )
        assert main(["init", "my-api-key"]) == 0

        key_file = tmp_path / "shodan" / "api_key"
        assert key_file.read_text() == "my-api-key"

    def test_init_from_env(
        self, tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(
            "SHODAN_TOOLKIT_SHODAN_CONFIG_DIR", str(tmp_path / "shodan")
        )
        monkeypatch.setenv("SHODAN_API_KEY", "env-api-key")

        assert main(["init", "ignored", "--from-env"]) == 0
        key_file = tmp_path / "shodan" / "api_key"
        assert key_file.read_text() == "env-api-key"

    def test_doctor_runs(self, capsys: pytest.CaptureFixture) -> None:
        # The exit code depends on the environment; only the report matters.
        main(["doctor"])
        output = capsys.readouterr().out
        assert "shodan_cli" in output

    def test_unknown_command_exits(self) -> None:
        with pytest.raises(SystemExit):
            main(["not-a-command"])
