"""
Tests for the session layer: prompt detection, the CLI state machine and the
transport guards.

These tests live inside the hyphenated package directory, so they use
**relative** imports (``from ..session import ...``).

No network access is required: the session is exercised against a fake
reader/writer pair that replays canned RouterOS output.

This directory must **not** contain an ``__init__.py`` - see
MODULE_SPECIFICATION.md section 3.4. The suite runs under
``--import-mode=importlib``, which ``pytest.ini`` sets through ``addopts``.
"""

from __future__ import annotations

import asyncio

import pytest

from ..config import MikroTikTarget
from ..exceptions import (
    InteractiveInputRequiredError,
    MultilineUnsupportedError,
    PagingError,
)
from ..session import (
    CONTINUATION_RE,
    PROMPT_RE,
    VALUE_REQUEST_RE,
    RouterOSSession,
)


# ---------------------------------------------------------------------------
# The 15-case prompt corpus - a permanent regression guard for risk R2
# (INVESTIGATION_REPORT.md section 5.3)
# ---------------------------------------------------------------------------

PROMPT_CORPUS = [
    # (buffer, should_match, description)
    ("[admin@MikroTik] > ", True, "root prompt"),
    ("[admin@MikroTik] >", True, "root prompt no trailing space"),
    ("[admin@MikroTik] /interface> ", True, "submenu prompt"),
    ("[admin@MikroTik] /ip/route> ", True, "deep submenu prompt"),
    ("[admin@MikroTik] <admin@MikroTik> ", True, "bracketed path form"),
    ("[admin@MikroTik] <admin@MikroTik> > ", True, "bracketed path + >"),
    ("[admin@MikroTik] ip route<SAFE> ", True, "safe mode marker"),
    (
        "[admin@MikroTik] > /interface set ether1 mtu=1500",
        False,
        "command typed after prompt",
    ),
    (
        "Flags: R - RUNNING\n  0 R ether1 1500\n[admin@MikroTik] > ",
        True,
        "output + prompt",
    ),
    ("invalid command name foo\n[admin@MikroTik] > ", True, "error + prompt"),
    ("[admin@MikroTik] > ", True, "bare"),
    ("[admin@MikroTik] > some trailing text", False, "prompt not at end"),
    (
        "log line [admin@MikroTik] > was seen\nmore output",
        False,
        "prompt quoted mid-output",
    ),
    ("[netops@core-rtr-01] > ", True, "other user/hostname"),
    ("[admin@MikroTik] /ip/firewall/filter> ", True, "long path"),
]


@pytest.mark.parametrize("buffer,should_match,description", PROMPT_CORPUS)
def test_prompt_corpus(buffer, should_match, description):
    """The prompt regex must match exactly the documented corpus."""
    assert (PROMPT_RE.search(buffer) is not None) is should_match, description


def test_the_prompt_corpus_is_permanently_green():
    """A single test that fails if the corpus ever changes shape."""
    failures = [
        description
        for buffer, should_match, description in PROMPT_CORPUS
        if (PROMPT_RE.search(buffer) is not None) is not should_match
    ]
    assert failures == []


def test_the_corpus_has_fifteen_cases():
    assert len(PROMPT_CORPUS) == 15


def test_continuation_prompt_is_detected():
    assert CONTINUATION_RE.search("line 2 of 3> ") is not None
    assert CONTINUATION_RE.search("line 1 of 1>") is not None
    assert CONTINUATION_RE.search("not a continuation") is None


def test_value_request_prompt_is_detected():
    assert VALUE_REQUEST_RE.search("old password: ") is not None
    assert VALUE_REQUEST_RE.search("new password: ") is not None
    assert VALUE_REQUEST_RE.search("no colon here") is None


# ---------------------------------------------------------------------------
# A fake transport
# ---------------------------------------------------------------------------

class FakeReader:
    """Replays canned output, then blocks until the test ends."""

    def __init__(self, chunks):
        self._chunks = list(chunks)

    async def read(self, _size):
        if self._chunks:
            return self._chunks.pop(0)
        # Nothing left - hang until the caller's timeout fires.
        await asyncio.sleep(3600)
        return ""

    def close(self):
        return None


class FakeWriter:
    """Records what the session wrote."""

    def __init__(self):
        self.written: list[str] = []

    def write(self, data):
        self.written.append(data)

    async def drain(self):
        return None


def make_target(**kwargs) -> MikroTikTarget:
    """Build a target for the tests."""
    defaults = {"id": "r1", "host": "10.0.0.1"}
    defaults.update(kwargs)
    return MikroTikTarget(**defaults)


def make_session(chunks, **kwargs) -> RouterOSSession:
    """Build a session wired to a fake transport."""
    session = RouterOSSession(make_target(**kwargs))
    session._reader = FakeReader(chunks)
    session._writer = FakeWriter()
    session._closed = False
    return session


# ---------------------------------------------------------------------------
# The multi-line guard
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "command",
    [
        "/ip/print\n/system/shutdown",
        "/ip/print; reboot",
        "/ip/print && reboot",
        "/ip/print | grep x",
        "{ /ip/print }",
    ],
)
def test_multiline_commands_are_rejected(command):
    session = make_session([])

    with pytest.raises(MultilineUnsupportedError):
        asyncio.run(session.run(command))

    with pytest.raises(MultilineUnsupportedError):
        asyncio.run(session.run_exec(command))


def test_an_empty_command_is_rejected():
    session = make_session([])

    with pytest.raises(MultilineUnsupportedError):
        asyncio.run(session.run(""))


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------

def test_run_returns_the_output_without_the_echo_or_the_prompt():
    session = make_session(
        [
            "/system/resource/print\n"
            "                   uptime: 3d4h5m6s\n"
            "[admin@MikroTik] > "
        ]
    )

    result = asyncio.run(session.run("/system/resource/print"))

    assert result.ok is True
    assert result.error is None
    assert "uptime: 3d4h5m6s" in result.stdout
    assert "[admin@MikroTik]" not in result.stdout
    assert result.transport == "session"
    assert result.exit_status == 0


def test_run_reports_a_rejected_command():
    session = make_session(["invalid command name bogus\n[admin@MikroTik] > "])

    result = asyncio.run(session.run("/bogus/command"))

    assert result.ok is False
    assert result.error == "COMMAND_REJECTED"
    assert "invalid command name bogus" in result.stdout


def test_run_appends_without_paging_to_a_print_command():
    session = make_session(["[admin@MikroTik] > "])

    asyncio.run(session.run("/interface/print"))

    assert session._writer.written[0].strip() == "/interface/print without-paging"


def test_run_does_not_append_without_paging_twice():
    session = make_session(["[admin@MikroTik] > "])

    asyncio.run(session.run("/interface/print without-paging"))

    assert session._writer.written[0].strip() == "/interface/print without-paging"


def test_run_does_not_append_without_paging_to_a_non_print_command():
    session = make_session(["[admin@MikroTik] > "])

    asyncio.run(session.run("/system/reboot"))

    assert session._writer.written[0].strip() == "/system/reboot"


def test_run_reports_the_prompt_path():
    session = make_session(["[admin@MikroTik] /ip/route> "])

    result = asyncio.run(session.run("/ip/route/print"))

    assert result.prompt_path == "/ip/route"


def test_run_parses_a_print_table_into_rows():
    session = make_session(
        [
            "Flags: R - RUNNING\n"
            "Columns: NAME, TYPE\n"
            "  0  R ether1  ether\n"
            "[admin@MikroTik] > "
        ]
    )

    result = asyncio.run(session.run("/interface/print"))

    assert result.rows is not None
    assert len(result.rows) == 1
    assert result.rows[0]["NAME"] == "ether1"


def test_run_times_out_when_no_prompt_arrives():
    session = make_session([])

    result = asyncio.run(session.run("/system/resource/print", timeout=0.2))

    assert result.ok is False
    assert result.error == "PROMPT_NOT_DETECTED"


def test_run_raises_on_a_paging_prompt():
    session = make_session(["--[Q | more]--"])

    with pytest.raises(PagingError):
        asyncio.run(session.run("/interface/print", timeout=1))


def test_run_raises_on_a_continuation_prompt():
    session = make_session(["line 2 of 3> "])

    with pytest.raises(MultilineUnsupportedError):
        asyncio.run(session.run("/ip/address/print", timeout=1))


def test_run_raises_on_a_value_request_prompt():
    session = make_session(["old password: "])

    with pytest.raises(InteractiveInputRequiredError):
        asyncio.run(session.run("/password", timeout=1))


# ---------------------------------------------------------------------------
# Safe mode
# ---------------------------------------------------------------------------

def test_safe_mode_is_detected_from_the_prompt():
    session = make_session(["[admin@MikroTik] ip route<SAFE> "])

    result = asyncio.run(session.run("/ip/route/print"))

    assert result.safe_mode is True


def test_enter_safe_mode_sends_ctrl_x():
    session = make_session(["[admin@MikroTik] <SAFE> "])

    result = asyncio.run(session.enter_safe_mode())

    assert session._writer.written[0] == "\x18"
    assert result.safe_mode is True


def test_exit_safe_mode_sends_ctrl_d():
    session = make_session(["[admin@MikroTik] > "])

    result = asyncio.run(session.exit_safe_mode())

    assert session._writer.written[0] == "\x04"
    assert result.safe_mode is False


# ---------------------------------------------------------------------------
# Transport selection
# ---------------------------------------------------------------------------

def test_the_session_is_not_connected_before_connect():
    session = RouterOSSession(make_target())
    assert session.is_connected is False


def test_close_is_safe_to_call_twice():
    session = make_session([])
    asyncio.run(session.close())
    asyncio.run(session.close())
    assert session.is_connected is False


def test_run_without_a_connection_raises():
    session = RouterOSSession(make_target())

    with pytest.raises(Exception):
        asyncio.run(session.run("/system/resource/print"))
