"""
Tests for the configuration layer: targets, the registry and the loader.

These tests live inside the hyphenated package directory, so they use
**relative** imports (``from ..config import ...``).

This directory must **not** contain an ``__init__.py`` - see
MODULE_SPECIFICATION.md section 3.4. The suite runs under
``--import-mode=importlib``, which ``pytest.ini`` sets through ``addopts``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ..config import (
    DEFAULT_TARGETS_PATH,
    ENV_KEY,
    ENV_PASSWORD,
    MikroTikTarget,
    TargetRegistry,
    load_targets,
)


# ---------------------------------------------------------------------------
# MikroTikTarget
# ---------------------------------------------------------------------------

def test_minimal_target_uses_documented_defaults():
    target = MikroTikTarget(id="core-rtr-01", host="10.0.0.1")

    assert target.port == 22
    assert target.username == "admin"
    assert target.password is None
    assert target.key_path is None
    assert target.group is None
    assert target.known_hosts is None
    assert target.allow_unknown_host_key is False
    assert target.connect_timeout == 10
    assert target.command_timeout == 30
    assert target.console_login_params == "c"


def test_console_login_params_disable_colour():
    """The default 'c' parameter removes ANSI escapes from the output."""
    target = MikroTikTarget(id="r1", host="h", console_login_params="c")
    assert target.login_username == "admin+c"

    target = MikroTikTarget(id="r1", host="h", console_login_params="")
    assert target.login_username == "admin"

    target = MikroTikTarget(id="r1", host="h", username="netops", console_login_params="ce")
    assert target.login_username == "netops+ce"


@pytest.mark.parametrize(
    "bad_id",
    [
        "",
        "has space",
        "has/slash",
        "semi;colon",
        "quote'd",
        "$(command)",
        "..dots",
        "-leading-hyphen",
        ".leading-dot",
    ],
)
def test_rejects_unsafe_id(bad_id):
    with pytest.raises(ValueError):
        MikroTikTarget(id=bad_id, host="10.0.0.1")


@pytest.mark.parametrize(
    "good_id",
    ["core-rtr-01", "router1", "a1", "router.lab", "rtr_01"],
)
def test_accepts_safe_id(good_id):
    """The documented example id 'core-rtr-01' must be accepted."""
    assert MikroTikTarget(id=good_id, host="10.0.0.1").id == good_id


@pytest.mark.parametrize("bad_port", [0, -1, 65536, 99999])
def test_rejects_port_outside_valid_range(bad_port):
    with pytest.raises(ValueError):
        MikroTikTarget(id="r1", host="h", port=bad_port)


@pytest.mark.parametrize("good_port", [1, 22, 2222, 65535])
def test_accepts_valid_port(good_port):
    assert MikroTikTarget(id="r1", host="h", port=good_port).port == good_port


def test_rejects_empty_host():
    with pytest.raises(ValueError):
        MikroTikTarget(id="r1", host="   ")


def test_rejects_non_positive_timeouts():
    with pytest.raises(ValueError):
        MikroTikTarget(id="r1", host="h", connect_timeout=0)
    with pytest.raises(ValueError):
        MikroTikTarget(id="r1", host="h", command_timeout=-5)


# ---------------------------------------------------------------------------
# Secret redaction - MODULE_SPECIFICATION.md R7 / D9
# ---------------------------------------------------------------------------

def test_password_is_redacted_in_repr():
    target = MikroTikTarget(id="r1", host="h", password="super-secret-value")

    assert "super-secret-value" not in repr(target)
    assert "super-secret-value" not in str(target)
    assert "super-secret-value" not in repr(target.password)


def test_key_passphrase_is_redacted_in_repr():
    target = MikroTikTarget(id="r1", host="h", key_passphrase="pass-phrase-value")

    assert "pass-phrase-value" not in repr(target)
    assert "pass-phrase-value" not in repr(target.key_passphrase)


def test_secret_values_returns_clear_text():
    target = MikroTikTarget(
        id="r1", host="h", password="pw-value", key_passphrase="pass-value"
    )

    assert sorted(target.secret_values()) == ["pass-value", "pw-value"]


def test_secret_values_ignores_empty_secrets():
    """An empty secret must not blank out an outgoing message."""
    target = MikroTikTarget(id="r1", host="h", password="")
    assert target.secret_values() == []


def test_public_dict_exposes_no_secret():
    target = MikroTikTarget(
        id="r1", host="h", password="pw-value", key_passphrase="pass-value"
    )

    public = target.public_dict()

    assert "pw-value" not in repr(public)
    assert "pass-value" not in repr(public)
    assert public["id"] == "r1"
    assert public["host"] == "h"


def test_public_dict_reports_auth_method():
    assert MikroTikTarget(id="r1", host="h").public_dict()["auth"] == "none"
    assert (
        MikroTikTarget(id="r1", host="h", password="p").public_dict()["auth"]
        == "password"
    )
    assert (
        MikroTikTarget(id="r1", host="h", key_path="/tmp/k").public_dict()["auth"]
        == "key"
    )


# ---------------------------------------------------------------------------
# TargetRegistry
# ---------------------------------------------------------------------------

def test_registry_register_and_get():
    registry = TargetRegistry()
    target = MikroTikTarget(id="r1", host="10.0.0.1")

    registry.register(target)

    assert registry.get("r1") is target
    assert registry.get("missing") is None
    assert len(registry) == 1
    assert "r1" in registry


def test_registry_rejects_non_target():
    registry = TargetRegistry()
    with pytest.raises(TypeError):
        registry.register({"id": "r1", "host": "h"})


def test_registry_rejects_conflicting_duplicate_id():
    registry = TargetRegistry()
    registry.register(MikroTikTarget(id="r1", host="10.0.0.1"))

    with pytest.raises(ValueError):
        registry.register(MikroTikTarget(id="r1", host="10.0.0.2"))


def test_registry_allows_identical_re_registration():
    registry = TargetRegistry()
    target = MikroTikTarget(id="r1", host="10.0.0.1")
    registry.register(target)
    registry.register(target)
    assert len(registry) == 1


def test_registry_list_targets_sorted_and_filtered():
    registry = TargetRegistry()
    registry.register(MikroTikTarget(id="b", host="h", group="core"))
    registry.register(MikroTikTarget(id="a", host="h", group="core"))
    registry.register(MikroTikTarget(id="c", host="h", group="edge"))

    assert [t.id for t in registry.list_targets()] == ["a", "b", "c"]
    assert [t.id for t in registry.list_targets(group="core")] == ["a", "b"]
    assert registry.groups() == ["core", "edge"]


def test_registry_unregister():
    registry = TargetRegistry()
    registry.register(MikroTikTarget(id="r1", host="h"))

    assert registry.unregister("r1") is True
    assert registry.unregister("r1") is False
    assert len(registry) == 0


# ---------------------------------------------------------------------------
# load_targets
# ---------------------------------------------------------------------------

def test_load_targets_missing_file_returns_empty_registry(tmp_path):
    registry = load_targets(tmp_path / "does-not-exist.yaml")

    assert isinstance(registry, TargetRegistry)
    assert len(registry) == 0


def test_load_targets_default_path_is_not_required():
    """The default path may be absent - the loader must never raise."""
    registry = load_targets()
    assert isinstance(registry, TargetRegistry)


def test_load_targets_reads_a_target(tmp_path):
    config = tmp_path / "targets.yaml"
    config.write_text(
        """
targets:
  - id: core-rtr-01
    host: 10.0.0.1
    port: 2222
    username: agent
    group: core
""",
        encoding="utf-8",
    )

    registry = load_targets(config)
    target = registry.get("core-rtr-01")

    assert target is not None
    assert target.host == "10.0.0.1"
    assert target.port == 2222
    assert target.username == "agent"
    assert target.group == "core"


def test_load_targets_skips_a_malformed_entry(tmp_path):
    config = tmp_path / "targets.yaml"
    config.write_text(
        """
targets:
  - id: good
    host: 10.0.0.1
  - id: "1 bad id"
    host: 10.0.0.2
""",
        encoding="utf-8",
    )

    registry = load_targets(config)

    assert registry.get("good") is not None
    assert registry.get("1 bad id") is None
    assert len(registry) == 1


def test_load_targets_env_password_fallback(tmp_path, monkeypatch):
    config = tmp_path / "targets.yaml"
    config.write_text(
        """
targets:
  - id: r1
    host: 10.0.0.1
""",
        encoding="utf-8",
    )
    monkeypatch.setenv(ENV_PASSWORD, "env-password")

    registry = load_targets(config)
    target = registry.get("r1")

    assert target is not None
    assert target.password is not None
    assert target.password.get_secret_value() == "env-password"


def test_load_targets_env_key_fallback(tmp_path, monkeypatch):
    config = tmp_path / "targets.yaml"
    config.write_text(
        """
targets:
  - id: r1
    host: 10.0.0.1
""",
        encoding="utf-8",
    )
    monkeypatch.setenv(ENV_KEY, "/tmp/some-key")

    registry = load_targets(config)
    target = registry.get("r1")

    assert target is not None
    assert target.key_path == Path("/tmp/some-key")


def test_load_targets_does_not_override_an_explicit_password(tmp_path, monkeypatch):
    config = tmp_path / "targets.yaml"
    config.write_text(
        """
targets:
  - id: r1
    host: 10.0.0.1
    password: file-password
""",
        encoding="utf-8",
    )
    monkeypatch.setenv(ENV_PASSWORD, "env-password")

    target = load_targets(config).get("r1")

    assert target is not None
    assert target.password.get_secret_value() == "file-password"


def test_load_targets_tolerates_a_malformed_file(tmp_path):
    config = tmp_path / "targets.yaml"
    config.write_text("this: is: not: valid: yaml:\n  - [\n", encoding="utf-8")

    registry = load_targets(config)

    assert isinstance(registry, TargetRegistry)


def test_load_targets_tolerates_a_non_list_document(tmp_path):
    config = tmp_path / "targets.yaml"
    config.write_text("just: a mapping\n", encoding="utf-8")

    registry = load_targets(config)

    assert isinstance(registry, TargetRegistry)


def test_default_targets_path_is_the_documented_name():
    assert DEFAULT_TARGETS_PATH == "mikrotik_targets.yaml"
