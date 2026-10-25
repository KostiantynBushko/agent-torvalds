"""
Tests for the MikroTik RouterOS agent adapter (``agent_mikrotik_toolkit.py``).

The tests exercise the **tool layer** with a mocked transport: the real
:class:`RouterOSSession` is replaced by a fake that replays canned RouterOS
output. No network access and no router is required.

What is covered:

* the uniform result shape (MODULE_SPECIFICATION.md section 6.2);
* the safety gate: the classification, the confirmation requirement and the
  human-in-the-loop approval;
* the multi-line guard, which must reject a chained command outright;
* the error-code mapping;
* the redaction of secrets;
* the tool registration (eight tools, ``Category: Network``).

Authoritative spec: ``investigate/MikroTik-RouterOS/MODULE_SPECIFICATION.md``
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from toolkits.mikrotik_routeros import agent_mikrotik_toolkit as mikrotik


# ---------------------------------------------------------------------------
# Fixtures and fakes
# ---------------------------------------------------------------------------

#: The canned output of ``/system/resource/print`` on a real device.
IDENTITY_OUTPUT = """                   uptime: 3d4h5m6s
                  version: 7.19.4 (stable)
               build-time: Aug/01/2025 09:12:33
         factory-software: 7.19.4
              free-hdd-space: 21.9MiB
         total-hdd-space: 64.0MiB
                cpu-load: 3%
             cpu-count: 4
           cpu-frequency: 1600MHz
               free-memory: 32.9MiB
              total-memory: 64.0MiB
                 board-name: RB5009UG+S+
                   model: RB5009UG+S+
             serial-number: HEX0123456789
       architecture-name: arm64
"""

#: The canned output of ``/interface/print``.
INTERFACE_OUTPUT = """Flags: R - RUNNING; S - SLAVE; X - DISABLED
Columns: NAME, TYPE, ACTUAL-MTU, L2MTU, MAC-ADDRESS
  0  R ether1      ether        1500    1598  48:A9:8A:11:22:33
  1  R ether2      ether        1500    1598  48:A9:8A:11:22:34
  2  RS ether3     ether        1500    1598  48:A9:8A:11:22:35
  3  X  ether4     ether        1500    1598  48:A9:8A:11:22:36
"""

#: The canned output of ``/ip/address/print``.
ADDRESS_OUTPUT = """Flags: X - DISABLED; I - INVALID, D - DYNAMIC
Columns: ADDRESS, NETWORK, INTERFACE
  0   10.0.0.1/24  10.0.0.0  ether1
  1   192.168.88.1/24  192.168.88.0  ether2
"""


class FakeCommandResult:
    """A stand-in for :class:`CommandResult`."""

    def __init__(self, stdout="", stderr="", ok=True, error=None, rows=None,
                 exit_status=0, duration_ms=12, transport="exec", safe_mode=False,
                 prompt_path=None):
        self.stdout = stdout
        self.stderr = stderr
        self.ok = ok
        self.error = error
        self.rows = rows
        self.exit_status = exit_status
        self.duration_ms = duration_ms
        self.transport = transport
        self.safe_mode = safe_mode
        self.prompt_path = prompt_path

    def to_dict(self):
        return {
            "command": "",
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_status": self.exit_status,
            "duration_ms": self.duration_ms,
            "transport": self.transport,
            "ok": self.ok,
            "error": self.error,
            "rows": self.rows,
            "safe_mode": self.safe_mode,
            "prompt_path": self.prompt_path,
        }


class FakeSession:
    """A fake :class:`RouterOSSession`.

    It records every command it was asked to run and replies with the
    canned output registered for that command.
    """

    #: The commands that were run, in order.
    calls: list[str] = []

    #: command -> (stdout, stderr, ok)
    responses: dict[str, tuple[str, str, bool]] = {}

    #: The exception the fake session raises on connect, if any.
    connect_error: Exception | None = None

    def __init__(self, target):
        self.target = target

    async def __aenter__(self):
        if type(self).connect_error is not None:
            raise type(self).connect_error
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def run_exec(self, command, timeout=None):
        type(self).calls.append(command)
        stdout, stderr, ok = type(self).responses.get(
            command, ("", "", True)
        )
        return FakeCommandResult(
            stdout=stdout,
            stderr=stderr,
            ok=ok,
            error=None if ok else "COMMAND_REJECTED",
            exit_status=0 if ok else 1,
            transport="exec",
        )

    async def run(self, command, timeout=None):
        type(self).calls.append(command)
        stdout, stderr, ok = type(self).responses.get(
            command, ("", "", True)
        )
        return FakeCommandResult(
            stdout=stdout,
            stderr=stderr,
            ok=ok,
            error=None if ok else "COMMAND_REJECTED",
            exit_status=0 if ok else 1,
            transport="session",
        )


@pytest.fixture
def fake_session(monkeypatch):
    """Replace the real session with the fake one and reset its state."""
    FakeSession.calls = []
    FakeSession.responses = {}
    FakeSession.connect_error = None
    monkeypatch.setattr(mikrotik, "RouterOSSession", FakeSession)
    return FakeSession


@pytest.fixture
def registry(monkeypatch):
    """Install a registry with one target and point the adapter at it."""
    from toolkits.mikrotik_routeros import MikroTikTarget, TargetRegistry

    target = MikroTikTarget(
        id="core-rtr-01",
        host="10.0.0.1",
        username="agent",
        password="sup3rs3cr3t",
    )
    reg = TargetRegistry([target])
    monkeypatch.setattr(mikrotik, "_REGISTRY", reg)
    return reg


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Remove the approval-related environment variables by default."""
    monkeypatch.delenv(mikrotik.ENV_SKIP_APPROVAL, raising=False)
    monkeypatch.delenv(mikrotik.ENV_APPROVAL_ANSWER, raising=False)


# ---------------------------------------------------------------------------
# The tool registration
# ---------------------------------------------------------------------------

class TestToolRegistration:
    """The adapter must expose exactly the eight documented tools."""

    def test_exactly_eight_tools(self):
        tools = mikrotik.get_all_tools()
        assert len(tools) == 8

    def test_every_description_ends_with_the_network_category(self):
        for tool in mikrotik.get_all_tools():
            assert tool.metadata.description.rstrip().endswith("Category: Network")

    def test_the_tool_names_are_the_documented_ones(self):
        names = {tool.metadata.name for tool in mikrotik.get_all_tools()}
        assert names == {
            "list_mikrotik_targets",
            "test_mikrotik_connection",
            "run_mikrotik_command",
            "get_routeros_config",
            "backup_routeros_config",
            "get_routeros_identity",
            "get_routeros_interfaces",
            "get_routeros_health",
        }

    def test_the_tools_are_async_aware(self):
        """LlamaIndex must be able to await the tools.

        The transport is asynchronous, so the tool functions are coroutine
        functions. ``FunctionTool`` detects that and awaits them in
        ``acall()``, which is the path the agent uses.
        """
        for tool in mikrotik.get_all_tools():
            assert tool._async_fn is not None, tool.metadata.name

    def test_the_tools_expose_a_json_schema(self):
        for tool in mikrotik.get_all_tools():
            schema = tool.metadata.fn_schema.model_json_schema()
            assert "properties" in schema, tool.metadata.name


# ---------------------------------------------------------------------------
# list_mikrotik_targets
# ---------------------------------------------------------------------------

class TestListTargets:
    """Listing the targets must never leak a secret."""

    @pytest.mark.asyncio
    async def test_lists_the_configured_targets(self, registry):
        result = await mikrotik.list_mikrotik_targets()
        assert result["ok"] is True
        assert result["count"] == 1
        assert result["targets"][0]["id"] == "core-rtr-01"
        assert result["targets"][0]["host"] == "10.0.0.1"

    @pytest.mark.asyncio
    async def test_never_exposes_a_secret(self, registry):
        result = await mikrotik.list_mikrotik_targets()
        assert "sup3rs3cr3t" not in str(result)

    @pytest.mark.asyncio
    async def test_an_empty_registry_is_not_an_error(self, monkeypatch):
        from toolkits.mikrotik_routeros import TargetRegistry

        monkeypatch.setattr(mikrotik, "_REGISTRY", TargetRegistry())
        result = await mikrotik.list_mikrotik_targets()
        assert result["ok"] is True
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_filters_by_group(self, monkeypatch):
        from toolkits.mikrotik_routeros import MikroTikTarget, TargetRegistry

        reg = TargetRegistry([
            MikroTikTarget(id="a-rtr", host="10.0.0.1", group="core"),
            MikroTikTarget(id="b-rtr", host="10.0.0.2", group="edge"),
        ])
        monkeypatch.setattr(mikrotik, "_REGISTRY", reg)

        result = await mikrotik.list_mikrotik_targets(group="core")
        assert result["count"] == 1
        assert result["targets"][0]["id"] == "a-rtr"


# ---------------------------------------------------------------------------
# The uniform result shape
# ---------------------------------------------------------------------------

class TestResultShape:
    """Every tool result must carry the same keys (spec section 6.2)."""

    @pytest.mark.asyncio
    async def test_the_result_has_the_documented_keys(self, registry, fake_session):
        fake_session.responses["/system/resource/print"] = (IDENTITY_OUTPUT, "", True)
        result = await mikrotik.get_routeros_identity("core-rtr-01")

        for key in (
            "ok",
            "stdout",
            "stderr",
            "exit_status",
            "duration_ms",
            "transport",
            "error",
            "rows",
            "safe_mode",
            "prompt_path",
        ):
            assert key in result, key

    @pytest.mark.asyncio
    async def test_a_failed_command_reports_ok_false_and_an_error_code(
        self, registry, fake_session
    ):
        fake_session.responses["/ip/address/print"] = (
            "",
            "invalid command name print",
            False,
        )
        result = await mikrotik.run_mikrotik_command(
            "core-rtr-01", "/ip/address/print"
        )
        assert result["ok"] is False
        assert result["error"] == "COMMAND_REJECTED"
        assert result["stderr"]


# ---------------------------------------------------------------------------
# The safety gate
# ---------------------------------------------------------------------------

class TestSafetyGate:
    """The classifier, the confirmation and the human-in-the-loop."""

    @pytest.mark.asyncio
    async def test_a_read_only_command_runs_without_confirmation(
        self, registry, fake_session
    ):
        fake_session.responses["/system/resource/print"] = (IDENTITY_OUTPUT, "", True)
        result = await mikrotik.run_mikrotik_command(
            "core-rtr-01", "/system/resource/print"
        )
        assert result["ok"] is True
        assert result["category"] == "READ_ONLY"

    @pytest.mark.asyncio
    async def test_a_change_without_confirm_is_refused(self, registry, fake_session):
        result = await mikrotik.run_mikrotik_command(
            "core-rtr-01", "/ip/address/set/1/address=10.0.0.5/24"
        )
        assert result["ok"] is False
        assert result["error"] == "NOT_AUTHORIZED"
        assert result["category"] in ("MEDIUM", "HIGH", "CRITICAL")
        # Nothing was sent to the router.
        assert fake_session.calls == []

    @pytest.mark.asyncio
    async def test_a_change_with_confirm_runs(self, registry, fake_session):
        result = await mikrotik.run_mikrotik_command(
            "core-rtr-01",
            "/ip/address/set/1/address=10.0.0.5/24",
            confirm=True,
        )
        assert result["ok"] is True
        assert fake_session.calls == ["/ip/address/set/1/address=10.0.0.5/24"]

    @pytest.mark.asyncio
    async def test_a_critical_command_takes_a_backup_first(
        self, registry, fake_session, monkeypatch
    ):
        """A critical change exports the configuration before it runs."""
        monkeypatch.setenv(mikrotik.ENV_APPROVAL_ANSWER, "yes")
        fake_session.responses["/export"] = ("# the previous config\n", "", True)

        result = await mikrotik.run_mikrotik_command(
            "core-rtr-01", "/system/reset-configuration", confirm=True
        )

        assert result["ok"] is True
        assert result["backup"] == "# the previous config\n"
        # The export ran before the change.
        assert fake_session.calls == ["/export", "/system/reset-configuration"]

    @pytest.mark.asyncio
    async def test_a_critical_command_is_refused_when_the_backup_fails(
        self, registry, fake_session, monkeypatch
    ):
        """A change that cannot be backed up is not applied."""
        monkeypatch.setenv(mikrotik.ENV_APPROVAL_ANSWER, "yes")
        fake_session.responses["/export"] = ("", "failure: out of memory", False)

        result = await mikrotik.run_mikrotik_command(
            "core-rtr-01", "/system/reset-configuration", confirm=True
        )

        assert result["ok"] is False
        assert "/system/reset-configuration" not in fake_session.calls

    @pytest.mark.asyncio
    async def test_a_high_risk_command_needs_a_human(self, registry, fake_session):
        """``confirm=True`` alone must not be enough for a HIGH command."""
        result = await mikrotik.run_mikrotik_command(
            "core-rtr-01",
            "/system/reboot",
            confirm=True,
        )
        assert result["ok"] is False
        assert result["error"] == "NOT_AUTHORIZED"
        assert "approve" in result["message"].lower()
        assert fake_session.calls == []

    @pytest.mark.asyncio
    async def test_a_high_risk_command_runs_after_the_human_approved(
        self, registry, fake_session, monkeypatch
    ):
        monkeypatch.setenv(mikrotik.ENV_APPROVAL_ANSWER, "yes")
        result = await mikrotik.run_mikrotik_command(
            "core-rtr-01", "/system/reboot", confirm=True
        )
        assert result["ok"] is True
        assert fake_session.calls == ["/system/reboot"]

    @pytest.mark.asyncio
    async def test_a_high_risk_command_is_refused_when_the_human_declines(
        self, registry, fake_session, monkeypatch
    ):
        monkeypatch.setenv(mikrotik.ENV_APPROVAL_ANSWER, "no")
        result = await mikrotik.run_mikrotik_command(
            "core-rtr-01", "/system/reboot", confirm=True
        )
        assert result["ok"] is False
        assert result["error"] == "NOT_AUTHORIZED"
        assert fake_session.calls == []

    @pytest.mark.asyncio
    async def test_the_approval_can_be_disabled_for_unattended_runs(
        self, registry, fake_session, monkeypatch
    ):
        monkeypatch.setenv(mikrotik.ENV_SKIP_APPROVAL, "1")
        result = await mikrotik.run_mikrotik_command(
            "core-rtr-01", "/system/reboot", confirm=True
        )
        assert result["ok"] is True
        assert fake_session.calls == ["/system/reboot"]

    @pytest.mark.asyncio
    async def test_a_management_path_change_is_escalated_to_critical(
        self, registry, fake_session
    ):
        """Disabling the management interface must be CRITICAL."""
        result = await mikrotik.run_mikrotik_command(
            "core-rtr-01",
            "/interface/ether1/set/disabled=yes",
            confirm=True,
        )
        assert result["category"] == "CRITICAL"

    @pytest.mark.asyncio
    async def test_the_critical_command_still_needs_a_human(
        self, registry, fake_session, monkeypatch
    ):
        monkeypatch.setenv(mikrotik.ENV_APPROVAL_ANSWER, "no")
        result = await mikrotik.run_mikrotik_command(
            "core-rtr-01",
            "/interface/ether1/set/disabled=yes",
            confirm=True,
        )
        assert result["ok"] is False
        assert result["error"] == "NOT_AUTHORIZED"
        assert fake_session.calls == []


# ---------------------------------------------------------------------------
# The multi-line guard
# ---------------------------------------------------------------------------

class TestMultilineGuard:
    """A multi-line or chained command must be refused outright."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "command",
        [
            "/ip/address/print\n/system/reboot",
            "/ip/address/print; /system/reboot",
            "/ip/address/print && /system/reboot",
            "/ip/address/print | grep foo",
            "{ /ip/address/print }",
        ],
    )
    async def test_a_chained_command_is_rejected(self, registry, command):
        result = await mikrotik.run_mikrotik_command("core-rtr-01", command)
        assert result["ok"] is False
        assert result["error"] == "MULTILINE_UNSUPPORTED"

    @pytest.mark.asyncio
    async def test_the_rejection_happens_before_the_target_is_resolved(self):
        """An unsafe command is refused even when the target is unknown."""
        result = await mikrotik.run_mikrotik_command("no-such-target", "/x\n/y")
        assert result["error"] == "MULTILINE_UNSUPPORTED"

    @pytest.mark.asyncio
    async def test_the_config_section_is_screened_too(self, registry):
        result = await mikrotik.get_routeros_config(
            "core-rtr-01", "/ip/address; /system/reboot"
        )
        assert result["error"] == "MULTILINE_UNSUPPORTED"


# ---------------------------------------------------------------------------
# The error codes
# ---------------------------------------------------------------------------

class TestErrorCodes:
    """The machine-readable error codes of the taxonomy."""

    @pytest.mark.asyncio
    async def test_an_unknown_target_is_reported(self, registry):
        result = await mikrotik.run_mikrotik_command("nope", "/system/resource/print")
        assert result["ok"] is False
        assert result["error"] == "UNKNOWN_TARGET"

    @pytest.mark.asyncio
    async def test_an_unknown_target_lists_the_known_ones(self, registry):
        result = await mikrotik.run_mikrotik_command("nope", "/system/resource/print")
        assert "core-rtr-01" in result["message"]

    @pytest.mark.asyncio
    async def test_a_connection_error_is_mapped_to_unreachable(
        self, registry, fake_session
    ):
        from toolkits.mikrotik_routeros import ConnectionError_

        fake_session.connect_error = ConnectionError_("no route to host")
        result = await mikrotik.run_mikrotik_command(
            "core-rtr-01", "/system/resource/print"
        )
        assert result["ok"] is False
        assert result["error"] == "UNREACHABLE"

    @pytest.mark.asyncio
    async def test_an_auth_error_is_mapped_to_auth_failed(
        self, registry, fake_session
    ):
        from toolkits.mikrotik_routeros import AuthError

        fake_session.connect_error = AuthError("credentials rejected")
        result = await mikrotik.run_mikrotik_command(
            "core-rtr-01", "/system/resource/print"
        )
        assert result["ok"] is False
        assert result["error"] == "AUTH_FAILED"

    @pytest.mark.asyncio
    async def test_a_host_key_mismatch_is_a_hard_stop(self, registry, fake_session):
        from toolkits.mikrotik_routeros import HostKeyError

        fake_session.connect_error = HostKeyError("the key changed")
        result = await mikrotik.run_mikrotik_command(
            "core-rtr-01", "/system/resource/print"
        )
        assert result["ok"] is False
        assert result["error"] == "HOST_KEY_MISMATCH"

    @pytest.mark.asyncio
    async def test_a_tool_never_raises(self, registry, fake_session):
        """Even an unexpected error must come back as a result dictionary."""
        fake_session.connect_error = RuntimeError("something went very wrong")
        result = await mikrotik.run_mikrotik_command(
            "core-rtr-01", "/system/resource/print"
        )
        assert isinstance(result, dict)
        assert result["ok"] is False
        assert result["error"]


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

class TestRedaction:
    """A secret must never appear in a result."""

    @pytest.mark.asyncio
    async def test_a_secret_in_the_output_is_redacted(self, registry, fake_session):
        fake_session.responses["/system/resource/print"] = (
            "the password is sup3rs3cr3t\n",
            "",
            True,
        )
        result = await mikrotik.run_mikrotik_command(
            "core-rtr-01", "/system/resource/print"
        )
        assert "sup3rs3cr3t" not in result["stdout"]
        assert "REDACTED" in result["stdout"]

    def test_the_redaction_helper_leaves_clean_text_alone(self):
        assert mikrotik._redact("nothing to see") == "nothing to see"

    def test_the_redaction_helper_never_blanks_the_text(self):
        assert mikrotik._redact("hello", [""]) == "hello"

    @pytest.mark.asyncio
    async def test_a_secret_in_an_exception_message_is_redacted(
        self, registry, fake_session
    ):
        from toolkits.mikrotik_routeros import AuthError

        fake_session.connect_error = AuthError("the key sup3rs3cr3t was rejected")
        result = await mikrotik.run_mikrotik_command(
            "core-rtr-01", "/system/resource/print"
        )
        assert "sup3rs3cr3t" not in result["message"]


# ---------------------------------------------------------------------------
# The individual tools
# ---------------------------------------------------------------------------

class TestIdentityTool:
    """``get_routeros_identity`` parses the resource output."""

    @pytest.mark.asyncio
    async def test_parses_the_identity(self, registry, fake_session):
        fake_session.responses["/system/resource/print"] = (IDENTITY_OUTPUT, "", True)
        result = await mikrotik.get_routeros_identity("core-rtr-01")

        assert result["ok"] is True
        assert result["identity"]["model"] == "RB5009UG+S+"
        assert result["identity"]["serial_number"] == "HEX0123456789"
        assert result["identity"]["uptime"] == "3d4h5m6s"
        assert result["version"] == "7.19.4 (stable)"

    @pytest.mark.asyncio
    async def test_the_connection_test_reports_the_identity(
        self, registry, fake_session
    ):
        fake_session.responses["/system/resource/print"] = (IDENTITY_OUTPUT, "", True)
        result = await mikrotik.test_mikrotik_connection("core-rtr-01")
        assert result["ok"] is True
        assert result["identity"]["model"] == "RB5009UG+S+"


class TestConfigTool:
    """``get_routeros_config`` returns structured rows."""

    @pytest.mark.asyncio
    async def test_returns_the_parsed_rows(self, registry, fake_session):
        fake_session.responses["/ip/address/print"] = (ADDRESS_OUTPUT, "", True)
        result = await mikrotik.get_routeros_config("core-rtr-01", "/ip/address")

        assert result["ok"] is True
        assert result["section"] == "/ip/address"
        assert result["count"] == 2
        assert result["rows"][0]["ADDRESS"] == "10.0.0.1/24"

    @pytest.mark.asyncio
    async def test_appends_the_verb_itself(self, registry, fake_session):
        fake_session.responses["/ip/address/print"] = (ADDRESS_OUTPUT, "", True)
        await mikrotik.get_routeros_config("core-rtr-01", "/ip/address")
        assert fake_session.calls == ["/ip/address/print"]

    @pytest.mark.asyncio
    async def test_adds_the_leading_slash(self, registry, fake_session):
        fake_session.responses["/ip/address/print"] = (ADDRESS_OUTPUT, "", True)
        result = await mikrotik.get_routeros_config("core-rtr-01", "ip/address")
        assert result["section"] == "/ip/address"
        assert fake_session.calls == ["/ip/address/print"]

    @pytest.mark.asyncio
    async def test_the_detail_format_is_requested(self, registry, fake_session):
        fake_session.responses["/ip/address/print detail"] = (ADDRESS_OUTPUT, "", True)
        await mikrotik.get_routeros_config(
            "core-rtr-01", "/ip/address", detail=True
        )
        assert fake_session.calls == ["/ip/address/print detail"]

    @pytest.mark.asyncio
    async def test_an_empty_section_is_not_an_error(self, registry, fake_session):
        fake_session.responses["/ip/address/print"] = ("", "", True)
        result = await mikrotik.get_routeros_config("core-rtr-01", "/ip/address")
        assert result["ok"] is True
        assert result["rows"] == []
        assert result["count"] == 0


class TestInterfaceTool:
    """``get_routeros_interfaces`` decodes the RouterOS flags."""

    @pytest.mark.asyncio
    async def test_decodes_the_running_and_disabled_flags(
        self, registry, fake_session
    ):
        fake_session.responses["/interface/print"] = (INTERFACE_OUTPUT, "", True)
        result = await mikrotik.get_routeros_interfaces("core-rtr-01")

        assert result["ok"] is True
        assert result["count"] == 4

        by_name = {i["name"]: i for i in result["interfaces"]}
        assert by_name["ether1"]["running"] is True
        assert by_name["ether1"]["disabled"] is False
        assert by_name["ether3"]["slave"] is True
        assert by_name["ether4"]["disabled"] is True
        assert by_name["ether4"]["running"] is False


class TestBackupTool:
    """``backup_routeros_config`` returns the export text."""

    @pytest.mark.asyncio
    async def test_returns_the_export(self, registry, fake_session):
        fake_session.responses["/export"] = (
            "# oct/03/2026 12:00:00 by RouterOS 7.19.4\n/ip address\n",
            "",
            True,
        )
        result = await mikrotik.backup_routeros_config("core-rtr-01")

        assert result["ok"] is True
        assert "by RouterOS 7.19.4" in result["config"]
        assert result["bytes"] == len(result["stdout"])
        assert fake_session.calls == ["/export"]

    @pytest.mark.asyncio
    async def test_the_export_uses_the_stateful_transport(
        self, registry, fake_session
    ):
        fake_session.responses["/export"] = ("# export\n", "", True)
        result = await mikrotik.backup_routeros_config("core-rtr-01")
        assert result["transport"] == "session"


class TestHealthTool:
    """``get_routeros_health`` combines the resources and the log."""

    @pytest.mark.asyncio
    async def test_reports_the_resources_and_the_errors(
        self, registry, fake_session
    ):
        fake_session.responses["/system/resource/print"] = (IDENTITY_OUTPUT, "", True)
        fake_session.responses["/log/print"] = (
            "jan/02 10:00:00 firewall,info input chain accepted\n"
            "jan/02 10:00:01 system,error cpu load too high\n",
            "",
            True,
        )
        result = await mikrotik.get_routeros_health("core-rtr-01")

        assert result["ok"] is True
        assert result["resources"]["cpu_load"] == "3%"
        assert len(result["errors"]) == 1
        assert "cpu load too high" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_an_info_log_line_is_not_an_error(self, registry, fake_session):
        fake_session.responses["/system/resource/print"] = (IDENTITY_OUTPUT, "", True)
        fake_session.responses["/log/print"] = (
            "jan/02 10:00:00 firewall,info input chain accepted\n",
            "",
            True,
        )
        result = await mikrotik.get_routeros_health("core-rtr-01")
        assert result["errors"] == []


# ---------------------------------------------------------------------------
# The transport selection
# ---------------------------------------------------------------------------

class TestTransportSelection:
    """``mode`` decides which transport carries the command."""

    @pytest.mark.asyncio
    async def test_a_read_uses_the_exec_transport(self, registry, fake_session):
        fake_session.responses["/system/resource/print"] = (IDENTITY_OUTPUT, "", True)
        result = await mikrotik.run_mikrotik_command(
            "core-rtr-01", "/system/resource/print"
        )
        assert result["transport"] == "exec"

    @pytest.mark.asyncio
    async def test_a_change_uses_the_session_transport(
        self, registry, fake_session, monkeypatch
    ):
        monkeypatch.setenv(mikrotik.ENV_APPROVAL_ANSWER, "yes")
        result = await mikrotik.run_mikrotik_command(
            "core-rtr-01", "/system/reboot", confirm=True
        )
        assert result["transport"] == "session"

    @pytest.mark.asyncio
    async def test_the_mode_can_be_forced(self, registry, fake_session):
        fake_session.responses["/system/resource/print"] = (IDENTITY_OUTPUT, "", True)
        result = await mikrotik.run_mikrotik_command(
            "core-rtr-01", "/system/resource/print", mode="session"
        )
        assert result["transport"] == "session"

    @pytest.mark.asyncio
    async def test_an_unknown_mode_falls_back_to_auto(self, registry, fake_session):
        fake_session.responses["/system/resource/print"] = (IDENTITY_OUTPUT, "", True)
        result = await mikrotik.run_mikrotik_command(
            "core-rtr-01", "/system/resource/print", mode="nonsense"
        )
        assert result["ok"] is True
        assert result["transport"] == "exec"
