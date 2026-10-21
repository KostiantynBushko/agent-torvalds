"""
Integration tests for the MikroTik RouterOS toolkit.

These tests talk to a **real** MikroTik router over SSH. They are opt-in:
without ``MIKROTIK_TEST_HOST`` in the environment they are skipped, so the
default test run never touches the network.

Enable them with::

    export MIKROTIK_TEST_HOST=10.0.0.1
    export MIKROTIK_TEST_USER=agent
    export MIKROTIK_TEST_KEY=~/.ssh/mikrotik_agent_ed25519
    # or: export MIKROTIK_TEST_PASSWORD=...

    pytest tests/test_mikrotik_integration.py -m integration

Every test in this file is marked ``integration``, so ``pytest -m
"not integration"`` skips the whole module.

Authoritative spec: ``investigate/MikroTik-RouterOS/MODULE_SPECIFICATION.md``
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent_mikrotik_toolkit as mikrotik

from toolkits.mikrotik_routeros import MikroTikTarget


#: The host of the router under test. Without it, everything is skipped.
TEST_HOST = os.environ.get("MIKROTIK_TEST_HOST", "")

#: The SSH user.
TEST_USER = os.environ.get("MIKROTIK_TEST_USER", "admin")

#: The private key used for the login.
TEST_KEY = os.environ.get("MIKROTIK_TEST_KEY", "")

#: The password used for the login, when no key is configured.
TEST_PASSWORD = os.environ.get("MIKROTIK_TEST_PASSWORD", "")

#: Whether the host key of the router is accepted without verification.
#: Only for a lab router whose key changes on every reboot.
TEST_INSECURE = os.environ.get("MIKROTIK_TEST_INSECURE", "").lower() in (
    "1",
    "true",
    "yes",
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not TEST_HOST, reason="no router configured (set MIKROTIK_TEST_HOST)"
    ),
]


@pytest.fixture
def live_target(monkeypatch):
    """Register the router under test as the only target."""
    kwargs = {
        "id": "integration-rtr",
        "host": TEST_HOST,
        "username": TEST_USER,
        "allow_unknown_host_key": TEST_INSECURE,
    }
    if TEST_KEY:
        kwargs["key_path"] = TEST_KEY
    if TEST_PASSWORD:
        kwargs["password"] = TEST_PASSWORD

    target = MikroTikTarget(**kwargs)

    from toolkits.mikrotik_routeros import TargetRegistry

    monkeypatch.setattr(mikrotik, "_REGISTRY", TargetRegistry([target]))
    return target


@pytest.mark.asyncio
async def test_a_read_only_command_against_the_real_router(live_target):
    """The agent can connect and read the router identity."""
    result = await mikrotik.get_routeros_identity("integration-rtr")

    assert result["ok"] is True, result.get("message")
    assert result["identity"]["routeros_version"]
    assert result["identity"]["model"]


@pytest.mark.asyncio
async def test_the_connection_test_against_the_real_router(live_target):
    """The reachability check reports the version."""
    result = await mikrotik.test_mikrotik_connection("integration-rtr")

    assert result["ok"] is True, result.get("message")
    assert result["version"]


@pytest.mark.asyncio
async def test_reading_a_config_section_against_the_real_router(live_target):
    """A configuration section comes back as structured rows."""
    result = await mikrotik.get_routeros_config("integration-rtr", "/ip/address")

    assert result["ok"] is True, result.get("message")
    assert isinstance(result["rows"], list)


@pytest.mark.asyncio
async def test_listing_the_interfaces_against_the_real_router(live_target):
    """The interface list is decoded into the running/disabled flags."""
    result = await mikrotik.get_routeros_interfaces("integration-rtr")

    assert result["ok"] is True, result.get("message")
    assert isinstance(result["interfaces"], list)
    for interface in result["interfaces"]:
        assert "running" in interface
        assert "disabled" in interface


@pytest.mark.asyncio
async def test_a_multiline_command_is_refused_by_the_real_router(live_target):
    """The multi-line guard refuses before anything reaches the router."""
    result = await mikrotik.run_mikrotik_command(
        "integration-rtr", "/system/resource/print\n/system/reboot"
    )

    assert result["ok"] is False
    assert result["error"] == "MULTILINE_UNSUPPORTED"


@pytest.mark.asyncio
async def test_an_unknown_command_is_reported_as_rejected(live_target):
    """The router's own error comes back as COMMAND_REJECTED."""
    result = await mikrotik.run_mikrotik_command(
        "integration-rtr", "/this/path/does/not/exist"
    )

    assert result["ok"] is False
    assert result["error"] == "COMMAND_REJECTED"
    assert result["stderr"]


@pytest.mark.asyncio
async def test_the_export_against_the_real_router(live_target):
    """The configuration export returns the RouterOS text."""
    result = await mikrotik.backup_routeros_config("integration-rtr")

    assert result["ok"] is True, result.get("message")
    assert result["bytes"] > 0
