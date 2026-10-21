"""
Tests for the data models.

These tests live inside the hyphenated package directory, so they use
**relative** imports (``from ..models import ...``).

This directory must **not** contain an ``__init__.py`` - see
MODULE_SPECIFICATION.md section 3.4. The suite runs under
``--import-mode=importlib``, which ``pytest.ini`` sets through ``addopts``.
"""

from __future__ import annotations

import json

from ..models import CommandCategory, CommandResult, RouterIdentity


# ---------------------------------------------------------------------------
# CommandResult
# ---------------------------------------------------------------------------

def test_command_result_defaults():
    result = CommandResult(command="/system/resource/print")

    assert result.command == "/system/resource/print"
    assert result.stdout == ""
    assert result.stderr == ""
    assert result.exit_status is None
    assert result.duration_ms == 0
    assert result.transport == "session"
    assert result.ok is True
    assert result.error is None
    assert result.rows is None
    assert result.safe_mode is False
    assert result.prompt_path is None


def test_command_result_carries_every_field():
    result = CommandResult(
        command="/ip/route/print",
        stdout="out",
        stderr="err",
        exit_status=1,
        duration_ms=132,
        transport="exec",
        ok=False,
        error="COMMAND_REJECTED",
        rows=[{"index": 0}],
        safe_mode=True,
        prompt_path="/ip/route",
    )

    assert result.exit_status == 1
    assert result.transport == "exec"
    assert result.ok is False
    assert result.error == "COMMAND_REJECTED"
    assert result.rows == [{"index": 0}]
    assert result.safe_mode is True
    assert result.prompt_path == "/ip/route"


def test_command_result_to_dict_is_json_serialisable():
    result = CommandResult(command="/x", rows=[{"a": 1}])
    payload = result.to_dict()

    assert json.loads(json.dumps(payload))["command"] == "/x"


# ---------------------------------------------------------------------------
# RouterIdentity
# ---------------------------------------------------------------------------

def test_router_identity_defaults_to_none():
    identity = RouterIdentity()

    assert identity.model is None
    assert identity.serial_number is None
    assert identity.routeros_version is None
    assert identity.uptime is None


def test_router_identity_carries_its_values():
    identity = RouterIdentity(
        model="RB5009UG+S+",
        serial_number="HEX123",
        routeros_version="7.19.4",
        uptime="3d4h5m6s",
        cpu_load="3%",
        free_memory="32.9MiB",
        total_memory="64.0MiB",
        free_disk="4.2MiB",
        total_disk="16.0MiB",
    )

    assert identity.model == "RB5009UG+S+"
    assert identity.serial_number == "HEX123"
    assert identity.routeros_version == "7.19.4"
    assert identity.uptime == "3d4h5m6s"
    assert identity.cpu_load == "3%"
    assert identity.free_memory == "32.9MiB"


def test_router_identity_to_dict():
    identity = RouterIdentity(model="RB5009", uptime="1d")

    payload = identity.to_dict()

    assert payload["model"] == "RB5009"
    assert payload["uptime"] == "1d"


# ---------------------------------------------------------------------------
# CommandCategory
# ---------------------------------------------------------------------------

def test_every_category_exists():
    assert CommandCategory.READ_ONLY.value == "READ_ONLY"
    assert CommandCategory.LOW.value == "LOW"
    assert CommandCategory.MEDIUM.value == "MEDIUM"
    assert CommandCategory.HIGH.value == "HIGH"
    assert CommandCategory.CRITICAL.value == "CRITICAL"


def test_categories_compare_by_risk():
    assert CommandCategory.READ_ONLY < CommandCategory.CRITICAL
    assert CommandCategory.HIGH > CommandCategory.MEDIUM
    assert CommandCategory.LOW <= CommandCategory.LOW
    assert CommandCategory.CRITICAL >= CommandCategory.CRITICAL


def test_a_category_is_a_string():
    """The enum is a str subclass, so it serialises cleanly."""
    assert CommandCategory.HIGH == "HIGH"
    assert str(CommandCategory.HIGH.value) == "HIGH"
