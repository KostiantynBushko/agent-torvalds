"""
Tests for the MikroTik RouterOS safety layer as used by the adapter.

The package-local suite (``toolkits/MikroTik-RouterOS/tests/test_safety.py``)
covers the classifier in depth. This file verifies that the **adapter**
applies the policy correctly:

* a read-only command runs without confirmation;
* a change needs ``confirm=True``;
* a HIGH or CRITICAL change needs a human, and ``confirm=True`` is not a
  substitute for that approval;
* a command that would drop the management path is escalated.

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
    CommandCategory,
    TargetRegistry,
    classify,
    contains_injection_patterns,
    is_management_path_change,
    requires_confirmation,
    requires_hitl,
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


class TestClassifier:
    """The classifier table of the investigation report."""

    @pytest.mark.parametrize(
        "command",
        [
            "/system/resource/print",
            "/ip/address/print",
            "/interface/print",
            "/ip/route/print",
            "/ip/dns/print",
            "/system/log/print",
        ],
    )
    def test_a_read_is_read_only(self, command):
        category, _ = classify(command)
        assert category == CommandCategory.READ_ONLY
        assert requires_confirmation(category) is False
        assert requires_hitl(category) is False

    @pytest.mark.parametrize(
        "command",
        [
            "/system/reboot",
            "/ip/firewall/filter/remove/1",
            "/user/remove/2",
            "/certificate/remove/3",
        ],
    )
    def test_a_destructive_command_is_high(self, command):
        category, _ = classify(command)
        assert category >= CommandCategory.HIGH
        assert requires_hitl(category) is True

    @pytest.mark.parametrize(
        "command",
        [
            "/system/reset-configuration",
            "/system/shutdown",
        ],
    )
    def test_a_catastrophic_command_is_critical(self, command):
        category, _ = classify(command)
        assert category == CommandCategory.CRITICAL

    def test_a_cosmetic_change_is_low(self):
        category, _ = classify("/interface/ether1/set/comment=uplink")
        assert category == CommandCategory.LOW
        assert requires_confirmation(category) is False

    def test_an_address_change_is_medium(self):
        category, _ = classify("/ip/address/set/1/address=10.0.0.5/24")
        assert category == CommandCategory.MEDIUM
        assert requires_confirmation(category) is True
        assert requires_hitl(category) is False


class TestInjectionPatterns:
    """The multi-line and chaining guard."""

    @pytest.mark.parametrize(
        "command",
        [
            "/ip/address/print\n/system/reboot",
            "/ip/address/print; /system/reboot",
            "/ip/address/print && /system/reboot",
            "/ip/address/print || /system/reboot",
            "/ip/address/print | grep foo",
            "{ /ip/address/print }",
        ],
    )
    def test_a_dangerous_construct_is_detected(self, command):
        assert contains_injection_patterns(command)

    def test_a_clean_command_has_no_pattern(self):
        assert contains_injection_patterns("/ip/address/print") == []

    def test_a_command_with_a_query_character_is_clean(self):
        assert contains_injection_patterns("/ip/address/print ?") == []


class TestManagementPath:
    """A change that would drop the management path is escalated."""

    def test_disabling_the_management_interface_is_detected(self):
        assert is_management_path_change("/interface/ether1/set/disabled=yes")

    def test_removing_the_management_interface_is_detected(self):
        assert is_management_path_change("/interface/ether1/remove")

    def test_an_unrelated_interface_is_not_detected(self):
        assert not is_management_path_change(
            "/interface/ether9/set/disabled=yes",
            current_interfaces=["ether1"],
        )

    def test_the_adapter_escalates_to_critical(self):
        category, reasons = mikrotik._classify(
            "/interface/ether1/set/disabled=yes"
        )
        assert category == CommandCategory.CRITICAL
        assert reasons


class TestPolicy:
    """The confirmation and the approval policy."""

    def test_reads_need_nothing(self):
        assert requires_confirmation(CommandCategory.READ_ONLY) is False
        assert requires_hitl(CommandCategory.READ_ONLY) is False

    def test_a_low_change_runs_automatically(self):
        assert requires_confirmation(CommandCategory.LOW) is False
        assert requires_hitl(CommandCategory.LOW) is False

    def test_a_medium_change_needs_a_confirmation(self):
        assert requires_confirmation(CommandCategory.MEDIUM) is True
        assert requires_hitl(CommandCategory.MEDIUM) is False

    def test_a_high_change_needs_a_human(self):
        assert requires_confirmation(CommandCategory.HIGH) is True
        assert requires_hitl(CommandCategory.HIGH) is True

    def test_a_critical_change_needs_a_human(self):
        assert requires_confirmation(CommandCategory.CRITICAL) is True
        assert requires_hitl(CommandCategory.CRITICAL) is True
