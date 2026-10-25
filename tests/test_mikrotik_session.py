"""
Tests for the MikroTik RouterOS session layer as seen from the adapter.

The package-local suite (``toolkits/MikroTik-RouterOS/tests/test_session.py``)
covers the session in depth. This file covers the parts the **adapter**
relies on: the transport selection, the timeout handling and the way the
session's errors are turned into the machine-readable error codes.

No network access is required.

Authoritative spec: ``investigate/MikroTik-RouterOS/MODULE_SPECIFICATION.md``
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from toolkits.mikrotik_routeros import agent_mikrotik_toolkit as mikrotik

from toolkits.mikrotik_routeros import (
    AuthError,
    CommandRejectedError,
    CommandTimeoutError,
    ConnectionError_,
    HostKeyError,
    InteractiveInputRequiredError,
    MikroTikError,
    MultilineUnsupportedError,
    NotAuthorizedError,
    PagingError,
    SafeModeError,
    TargetRegistry,
)


@pytest.fixture
def registry(monkeypatch):
    """Install a registry with one target."""
    from toolkits.mikrotik_routeros import MikroTikTarget

    target = MikroTikTarget(
        id="core-rtr-01", host="10.0.0.1", username="agent", password="s3cret"
    )
    monkeypatch.setattr(mikrotik, "_REGISTRY", TargetRegistry([target]))
    return target


class RaisingSession:
    """A session that raises the given error on connect."""

    def __init__(self, target):
        self.target = target

    async def __aenter__(self):
        raise self.error

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.parametrize(
    "error,expected_code",
    [
        (AuthError("bad credentials"), "AUTH_FAILED"),
        (HostKeyError("key changed"), "HOST_KEY_MISMATCH"),
        (ConnectionError_("no route"), "UNREACHABLE"),
        (CommandTimeoutError("too slow"), "TIMEOUT"),
        (CommandRejectedError("bad syntax"), "COMMAND_REJECTED"),
        (MultilineUnsupportedError("multi-line"), "MULTILINE_UNSUPPORTED"),
        (InteractiveInputRequiredError("needs input"), "INTERACTIVE_INPUT_REQUIRED"),
        (SafeModeError("in safe mode"), "SAFE_MODE_ACTIVE"),
        (PagingError("paged"), "PAGING_DETECTED"),
        (NotAuthorizedError("policy"), "NOT_AUTHORIZED"),
    ],
)
@pytest.mark.asyncio
async def test_every_error_maps_to_its_code(monkeypatch, registry, error, expected_code):
    """The error taxonomy survives the trip through the adapter."""

    class Session(RaisingSession):
        pass

    Session.error = error
    monkeypatch.setattr(mikrotik, "RouterOSSession", Session)

    result = await mikrotik.run_mikrotik_command(
        "core-rtr-01", "/system/resource/print"
    )

    assert result["ok"] is False
    assert result["error"] == expected_code


@pytest.mark.asyncio
async def test_an_unknown_error_falls_back_to_unreachable(monkeypatch, registry):
    """An unexpected error still produces a structured result."""

    class Session(RaisingSession):
        pass

    Session.error = RuntimeError("something odd")
    monkeypatch.setattr(mikrotik, "RouterOSSession", Session)

    result = await mikrotik.run_mikrotik_command(
        "core-rtr-01", "/system/resource/print"
    )

    assert result["ok"] is False
    assert result["error"] == "UNREACHABLE"
    assert result["message"]


@pytest.mark.asyncio
async def test_the_timeout_is_passed_to_the_session(monkeypatch, registry):
    """The ``timeout`` argument reaches the transport."""
    seen = {}

    class RecordingSession:
        def __init__(self, target):
            self.target = target

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def run_exec(self, command, timeout=None):
            seen["command"] = command
            seen["timeout"] = timeout
            return _Result()

        async def run(self, command, timeout=None):
            seen["command"] = command
            seen["timeout"] = timeout
            return _Result()

    class _Result:
        stdout = ""
        stderr = ""
        ok = True
        error = None
        rows = None
        exit_status = 0
        duration_ms = 5
        transport = "exec"
        safe_mode = False
        prompt_path = None

    monkeypatch.setattr(mikrotik, "RouterOSSession", RecordingSession)

    await mikrotik.run_mikrotik_command(
        "core-rtr-01", "/system/resource/print", timeout=77
    )

    assert seen["timeout"] == 77


@pytest.mark.asyncio
async def test_a_safe_mode_result_is_reported(monkeypatch, registry):
    """The safe-mode flag of the router is passed through."""

    class _Result:
        stdout = ""
        stderr = ""
        ok = True
        error = None
        rows = None
        exit_status = 0
        duration_ms = 5
        transport = "session"
        safe_mode = True
        prompt_path = "/"

    class Session:
        def __init__(self, target):
            self.target = target

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def run(self, command, timeout=None):
            return _Result()

        async def run_exec(self, command, timeout=None):
            return _Result()

    monkeypatch.setattr(mikrotik, "RouterOSSession", Session)

    result = await mikrotik.run_mikrotik_command(
        "core-rtr-01", "/system/resource/print"
    )

    assert result["safe_mode"] is True


@pytest.mark.asyncio
async def test_a_prompt_not_detected_error_is_reported(monkeypatch, registry):
    """``PROMPT_NOT_DETECTED`` is a documented code of the taxonomy."""

    class _Result:
        stdout = ""
        stderr = ""
        ok = False
        error = "PROMPT_NOT_DETECTED"
        rows = None
        exit_status = None
        duration_ms = 30000
        transport = "session"
        safe_mode = False
        prompt_path = None

    class Session:
        def __init__(self, target):
            self.target = target

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def run(self, command, timeout=None):
            return _Result()

        async def run_exec(self, command, timeout=None):
            return _Result()

    monkeypatch.setattr(mikrotik, "RouterOSSession", Session)

    result = await mikrotik.run_mikrotik_command(
        "core-rtr-01", "/system/resource/print"
    )

    assert result["ok"] is False
    assert result["error"] == "PROMPT_NOT_DETECTED"


def test_the_error_codes_of_the_taxonomy_are_all_known():
    """Every code the adapter can emit is part of the documented set."""
    from toolkits.mikrotik_routeros import ERROR_CODES

    assert "UNKNOWN_TARGET" in ERROR_CODES
    assert "PROMPT_NOT_DETECTED" in ERROR_CODES
    assert "NOT_AUTHORIZED" in ERROR_CODES
    assert "MULTILINE_UNSUPPORTED" in ERROR_CODES
