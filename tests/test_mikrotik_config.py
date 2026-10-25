"""
Tests for the MikroTik RouterOS target configuration.

The package-local suite (``toolkits/MikroTik-RouterOS/tests/test_config.py``)
covers the configuration layer in depth. This file verifies the parts the
**adapter** depends on:

* the YAML loader is tolerant - a missing or broken file never raises;
* the environment variable fallbacks work;
* the secrets are redacted in every representation;
* the target list of the adapter never exposes a secret.

No network access is required.

Authoritative spec: ``investigate/MikroTik-RouterOS/MODULE_SPECIFICATION.md``
"""

from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from toolkits.mikrotik_routeros import agent_mikrotik_toolkit as mikrotik

from toolkits.mikrotik_routeros import (
    DEFAULT_TARGETS_PATH,
    ENV_KEY,
    ENV_PASSWORD,
    MikroTikTarget,
    TargetRegistry,
    load_targets,
)


#: A valid configuration document.
VALID_YAML = textwrap.dedent(
    """
    targets:
      - id: core-rtr-01
        host: 10.0.0.1
        port: 22
        username: agent
        password: sup3rs3cr3t
        group: core
        connect_timeout: 5
        command_timeout: 15
      - id: edge-rtr-02
        host: 10.0.1.1
        username: agent
        key_path: ~/.ssh/mikrotik_ed25519
        group: edge
    """
).strip()


@pytest.fixture
def config_file(tmp_path):
    """Write the valid configuration to a temporary file."""
    path = tmp_path / "mikrotik_targets.yaml"
    path.write_text(VALID_YAML, encoding="utf-8")
    return path


class TestLoader:
    """The tolerant YAML loader."""

    def test_a_valid_file_is_loaded(self, config_file):
        registry = load_targets(config_file)
        assert len(registry) == 2
        assert registry.get("core-rtr-01").host == "10.0.0.1"
        assert registry.get("edge-rtr-02").group == "edge"

    def test_a_missing_file_yields_an_empty_registry(self, tmp_path):
        registry = load_targets(tmp_path / "does-not-exist.yaml")
        assert len(registry) == 0

    def test_a_broken_file_yields_an_empty_registry(self, tmp_path):
        path = tmp_path / "broken.yaml"
        path.write_text("targets: [this is: not: valid: yaml", encoding="utf-8")
        registry = load_targets(path)
        assert len(registry) == 0

    def test_a_malformed_entry_is_skipped(self, tmp_path):
        path = tmp_path / "partial.yaml"
        path.write_text(
            textwrap.dedent(
                """
                targets:
                  - id: good-rtr
                    host: 10.0.0.1
                  - id: "bad id with spaces"
                    host: 10.0.0.2
                """
            ).strip(),
            encoding="utf-8",
        )
        registry = load_targets(path)
        assert len(registry) == 1
        assert registry.get("good-rtr") is not None

    def test_the_environment_supplies_a_missing_password(
        self, tmp_path, monkeypatch
    ):
        """The environment fills in a credential the file does not carry."""
        path = tmp_path / "no-credentials.yaml"
        path.write_text(
            textwrap.dedent(
                """
                targets:
                  - id: edge-rtr-02
                    host: 10.0.1.1
                """
            ).strip(),
            encoding="utf-8",
        )
        monkeypatch.setenv(ENV_PASSWORD, "from-the-environment")

        registry = load_targets(path)
        target = registry.get("edge-rtr-02")
        assert target.password.get_secret_value() == "from-the-environment"

    def test_the_environment_supplies_a_missing_key(self, tmp_path, monkeypatch):
        """The environment fills in a key the file does not carry."""
        path = tmp_path / "no-credentials.yaml"
        path.write_text(
            textwrap.dedent(
                """
                targets:
                  - id: edge-rtr-02
                    host: 10.0.1.1
                """
            ).strip(),
            encoding="utf-8",
        )
        monkeypatch.setenv(ENV_KEY, "/tmp/some_key")

        registry = load_targets(path)
        target = registry.get("edge-rtr-02")
        assert str(target.key_path) == "/tmp/some_key"

    def test_the_file_wins_over_the_environment(self, config_file, monkeypatch):
        """A credential in the file is never replaced by the environment."""
        monkeypatch.setenv(ENV_PASSWORD, "from-the-environment")
        monkeypatch.setenv(ENV_KEY, "/tmp/some_key")

        registry = load_targets(config_file)
        target = registry.get("core-rtr-01")
        assert target.password.get_secret_value() == "sup3rs3cr3t"

        other = registry.get("edge-rtr-02")
        assert str(other.key_path) == "~/.ssh/mikrotik_ed25519"

    def test_the_default_path_is_the_documented_one(self):
        assert DEFAULT_TARGETS_PATH == "mikrotik_targets.yaml"


class TestValidation:
    """The target validation."""

    def test_a_valid_target_is_accepted(self):
        target = MikroTikTarget(id="core-rtr-01", host="10.0.0.1")
        assert target.port == 22
        assert target.username == "admin"

    @pytest.mark.parametrize("bad_id", ["", "has space", "has/slash", "..", "a" * 100])
    def test_an_unsafe_id_is_rejected(self, bad_id):
        with pytest.raises(Exception):
            MikroTikTarget(id=bad_id, host="10.0.0.1")

    def test_a_hyphenated_id_is_accepted(self):
        """The documented example id contains a hyphen and must work."""
        target = MikroTikTarget(id="core-rtr-01", host="10.0.0.1")
        assert target.id == "core-rtr-01"

    @pytest.mark.parametrize("bad_port", [0, -1, 65536, 100000])
    def test_an_invalid_port_is_rejected(self, bad_port):
        with pytest.raises(Exception):
            MikroTikTarget(id="rtr", host="10.0.0.1", port=bad_port)

    def test_an_empty_host_is_rejected(self):
        with pytest.raises(Exception):
            MikroTikTarget(id="rtr", host="   ")


class TestSecrets:
    """A secret must never leak."""

    def test_the_repr_hides_the_password(self):
        target = MikroTikTarget(
            id="rtr", host="10.0.0.1", password="sup3rs3cr3t"
        )
        assert "sup3rs3cr3t" not in repr(target)
        assert "sup3rs3cr3t" not in str(target)

    def test_the_public_dict_hides_the_password(self):
        target = MikroTikTarget(
            id="rtr", host="10.0.0.1", password="sup3rs3cr3t"
        )
        assert "sup3rs3cr3t" not in str(target.public_dict())

    def test_the_secret_values_list_the_password(self):
        """The adapter needs the clear text to redact it."""
        target = MikroTikTarget(
            id="rtr", host="10.0.0.1", password="sup3rs3cr3t"
        )
        assert target.secret_values() == ["sup3rs3cr3t"]


class TestAdapterRegistry:
    """The registry the adapter uses."""

    def test_the_registry_is_loaded_on_first_use(self, config_file, monkeypatch):
        monkeypatch.setattr(mikrotik, "_REGISTRY", None)
        monkeypatch.setenv(mikrotik.ENV_TARGETS_PATH, str(config_file))

        registry = mikrotik.get_registry()
        assert len(registry) == 2

    def test_the_registry_can_be_reloaded(self, config_file, monkeypatch):
        monkeypatch.setattr(mikrotik, "_REGISTRY", None)
        monkeypatch.setenv(mikrotik.ENV_TARGETS_PATH, str(config_file))

        mikrotik.get_registry()
        registry = mikrotik.reload_registry()
        assert len(registry) == 2

    def test_a_missing_file_does_not_raise(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mikrotik, "_REGISTRY", None)
        monkeypatch.setenv(
            mikrotik.ENV_TARGETS_PATH, str(tmp_path / "nope.yaml")
        )
        assert len(mikrotik.get_registry()) == 0

    @pytest.mark.asyncio
    async def test_the_target_list_never_exposes_a_secret(
        self, config_file, monkeypatch
    ):
        monkeypatch.setattr(mikrotik, "_REGISTRY", None)
        monkeypatch.setenv(mikrotik.ENV_TARGETS_PATH, str(config_file))

        result = await mikrotik.list_mikrotik_targets()
        assert "sup3rs3cr3t" not in str(result)

    def test_the_example_configuration_is_valid(self):
        """The shipped example must load without an error."""
        example = Path(__file__).resolve().parents[1] / "mikrotik_targets.yaml.example"
        if not example.is_file():
            pytest.skip("the example configuration is not present")

        registry = load_targets(example)
        assert len(registry) >= 1
