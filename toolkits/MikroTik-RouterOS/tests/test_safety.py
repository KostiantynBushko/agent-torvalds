"""
Tests for the safety classifier and the confirmation policy.

These tests live inside the hyphenated package directory, so they use
**relative** imports (``from ..safety import ...``).

This directory must **not** contain an ``__init__.py`` - see
MODULE_SPECIFICATION.md section 3.4. The suite runs under
``--import-mode=importlib``, which ``pytest.ini`` sets through ``addopts``.
"""

from __future__ import annotations

import pytest

from ..models import CommandCategory
from ..safety import (
    classify,
    contains_injection_patterns,
    is_management_path_change,
    requires_confirmation,
    requires_hitl,
)


# ---------------------------------------------------------------------------
# Read-only commands
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "command",
    [
        "/system/resource/print",
        "/system/identity/print",
        "/ip/address/print",
        "/ip/route/print",
        "/ip/dns/print",
        "/ip/dns/static/print",
        "/interface/print",
        "/interface/ether1/print",
        "/log/print",
        "/export",
        "/ip/firewall/filter/print",
        "/user/print",
        "/certificate/print",
        "/system/clock/print",
    ],
)
def test_read_only_commands(command):
    category, reasons = classify(command)

    assert category == CommandCategory.READ_ONLY
    assert reasons == []
    assert requires_confirmation(category) is False
    assert requires_hitl(category) is False


# ---------------------------------------------------------------------------
# Change commands
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "command",
    [
        "/system/clock/set/date=2026-01-01",
        "/system/note/set/note=hello",
        "/interface/ether1/set/comment=hello",
    ],
)
def test_low_risk_commands(command):
    category, reasons = classify(command)

    assert category == CommandCategory.LOW
    assert reasons
    assert requires_confirmation(category) is False
    assert requires_hitl(category) is False


@pytest.mark.parametrize(
    "command",
    [
        "/interface/ether1/set/mtu=1500",
        "/ip/address/add/address=1.1.1.1/24/interface=ether1",
    ],
)
def test_medium_risk_commands(command):
    category, reasons = classify(command)

    assert category == CommandCategory.MEDIUM
    assert reasons
    assert requires_confirmation(category) is True
    assert requires_hitl(category) is False


@pytest.mark.parametrize(
    "command",
    [
        "/system/reboot",
        "/interface/ether1/set/disabled=yes",
        "/ip/firewall/filter/add/chain=input/action=accept",
        "/ip/address/remove/=1.1.1.1/24",
    ],
)
def test_high_risk_commands(command):
    category, reasons = classify(command)

    assert category == CommandCategory.HIGH
    assert reasons
    assert requires_confirmation(category) is True
    assert requires_hitl(category) is True


@pytest.mark.parametrize(
    "command",
    [
        "/system/reset-configuration",
        "/system/shutdown",
        "/user/set/admin/password=secret",
    ],
)
def test_critical_commands(command):
    category, reasons = classify(command)

    assert category == CommandCategory.CRITICAL
    assert reasons
    assert requires_confirmation(category) is True
    assert requires_hitl(category) is True


def test_an_unrecognised_command_is_never_read_only():
    """An unknown command must be treated as a change, not as a read."""
    category, reasons = classify("/some/unknown/thing")

    assert category != CommandCategory.READ_ONLY
    assert category == CommandCategory.MEDIUM
    assert reasons


def test_an_empty_command_is_read_only():
    category, reasons = classify("")

    assert category == CommandCategory.READ_ONLY
    assert reasons == []


# ---------------------------------------------------------------------------
# The multi-line / chaining guard
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "command",
    [
        "/ip/print\n/system/shutdown",
        "/ip/print; reboot",
        "/ip/print && reboot",
        "/ip/print | grep x",
        "/ip/print || reboot",
        "{ /ip/print }",
    ],
)
def test_multiline_commands_are_critical(command):
    category, reasons = classify(command)

    assert category == CommandCategory.CRITICAL
    assert reasons


@pytest.mark.parametrize(
    "command,expected",
    [
        ("/ip/print", []),
        ("/ip/print; reboot", ["semicolon"]),
        ("/ip/print\n/system/shutdown", ["newline"]),
        ("/ip/print && reboot", ["and-chain"]),
        ("/ip/print | grep x", ["pipe"]),
        ("{ /ip/print }", ["script-block"]),
    ],
)
def test_contains_injection_patterns(command, expected):
    assert contains_injection_patterns(command) == expected


def test_contains_injection_patterns_with_empty_input():
    assert contains_injection_patterns("") == []


# ---------------------------------------------------------------------------
# Management path escalation
# ---------------------------------------------------------------------------

def test_disabling_the_management_interface_is_a_management_path_change():
    assert is_management_path_change(
        "/interface/ether1/set/disabled=yes", ["ether1"]
    ) is True


def test_disabling_another_interface_is_not():
    assert is_management_path_change(
        "/interface/ether5/set/disabled=yes", ["ether1"]
    ) is False


def test_removing_the_management_interface_is_a_management_path_change():
    assert is_management_path_change("/interface/ether1/remove", ["ether1"]) is True


def test_a_non_interface_command_is_not_a_management_path_change():
    assert is_management_path_change("/ip/address/print", ["ether1"]) is False


def test_a_cosmetic_interface_change_is_not_a_management_path_change():
    assert (
        is_management_path_change("/interface/ether1/set/mtu=1500", ["ether1"])
        is False
    )


def test_the_default_management_interfaces_are_used_when_none_are_given():
    assert is_management_path_change("/interface/ether1/set/disabled=yes") is True
    assert is_management_path_change("/interface/ether9/set/disabled=yes") is False


# ---------------------------------------------------------------------------
# Category ordering
# ---------------------------------------------------------------------------

def test_categories_are_ordered_by_risk():
    assert CommandCategory.READ_ONLY < CommandCategory.CRITICAL
    assert CommandCategory.LOW < CommandCategory.MEDIUM
    assert CommandCategory.MEDIUM < CommandCategory.HIGH
    assert CommandCategory.HIGH < CommandCategory.CRITICAL


def test_the_policy_thresholds_are_where_the_spec_says():
    assert requires_confirmation(CommandCategory.LOW) is False
    assert requires_confirmation(CommandCategory.MEDIUM) is True
    assert requires_hitl(CommandCategory.MEDIUM) is False
    assert requires_hitl(CommandCategory.HIGH) is True
