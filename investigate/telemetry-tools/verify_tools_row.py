#!/usr/bin/env python3
"""Verify: the telemetry panel names the tools the operator selected.

The panel showed "Git, OS, DB, Math" - four toolkits that were written
into the source, whatever the operator had selected.  The row is a
measurement now, and this script is the evidence that it is one.

It drives the three modes of the agent - the retriever, ``--full`` and
``--select`` - renders the panel for each of them, and checks that the
row names the tools the agent really has.

In the ``--select`` mode the operator picks a **category**, and the
panel names the category: "Operating System, System" says what the
agent can do, and the name of one tool out of the eleven of a category
says nothing about the other ten.

Usage::

    python investigate/telemetry-tools/verify_tools_row.py
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(REPO_ROOT))

from components.tui.state_bridge import TuiState  # noqa: E402
from components.tui.telemetry_view import TelemetryView  # noqa: E402


def load_mw_agent():
    """Load agent-torvalds-mw.py as an importable module."""
    path = REPO_ROOT / "agent-torvalds-mw.py"
    spec = importlib.util.spec_from_file_location("agent_torvalds_mw", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["agent_torvalds_mw"] = module
    spec.loader.exec_module(module)
    return module


def render(state, width: int = 46) -> str:
    """Render the telemetry panel as plain text."""
    from rich.console import Console

    console = Console(width=width, color_system=None)
    panel = TelemetryView().render(state)
    lines = console.render_lines(panel, console.options.update(width=width))
    return "\n".join("".join(segment.text for segment in line) for line in lines)


def mentions(text: str, name: str) -> bool:
    """Whether the panel names the tool.

    The name is matched as a word: the tool "ls" is inside the word
    "Tools", and a row that names the word "Tools" does not name the
    tool "ls".
    """
    return bool(re.search(rf"\b{re.escape(name)}\b", text))


def the_row(text: str) -> str:
    """The line of the panel that carries the tools."""
    for line in text.splitlines():
        if "Tools" in line:
            return line.strip()
    return ""


def main() -> int:
    mw = load_mw_agent()
    failures: list[str] = []

    modes = (
        ("the retriever", True, None, "indexed"),
        ("--full", False, None, "loaded"),
    )

    for label, use_retriever, selected, scope in modes:
        inventory = mw._agent_tool_inventory(use_retriever, selected)

        state = TuiState()
        state.mode = label
        state.update_tools(
            [tool.metadata.name for tool in inventory], scope=scope
        )

        print(f"=== {label}: {len(inventory)} tools")
        print(render(state))
        print(f"    the row says: {the_row(render(state))}")
        print()

        if not inventory:
            failures.append(f"{label}: the agent has no tools at all")
        if f"{len(inventory)} {scope}" not in render(state):
            failures.append(f"{label}: the row does not carry the count")

    # --select: the operator picks one category, and only that one is
    # named.
    from agent_tool_selection import group_tools_by_category

    groups = group_tools_by_category(mw._agent_tool_inventory(True))
    for category in ("Network", "Database", "Security"):
        if category not in groups:
            print(f"=== --select {category}: the category is not installed")
            continue

        selected = groups[category]
        inventory = mw._agent_tool_inventory(False, selected)

        picked = mw._selected_tool_groups(inventory)

        state = TuiState()
        state.mode = "Selected tools"
        state.update_tools(
            [tool.metadata.name for tool in inventory],
            scope="selected",
            groups=picked,
        )

        print(f"=== --select {category}: {len(inventory)} tools")
        print(render(state))
        print(f"    the row says: {the_row(render(state))}")
        print()

        panel = render(state)
        if f"{len(inventory)} selected" not in panel:
            failures.append(
                f"--select {category}: the row does not carry the count"
            )

        # The panel names the groups the operator picked: the category
        # is on the screen, and the tools are not.
        if category not in panel:
            failures.append(
                f"--select {category}: the row does not name the group"
            )

        for tool in inventory:
            if mentions(panel, tool.metadata.name):
                failures.append(
                    f"--select {category}: the row names the tool "
                    f"{tool.metadata.name} instead of the group"
                )
                break

        # The panel shows a few names and counts the rest: the names
        # that are shown must be the first ones, and the ones that are
        # not shown must be counted.
        shown = picked[: TelemetryView.TOOL_NAMES_SHOWN]
        for group in shown:
            if group not in panel:
                failures.append(
                    f"--select {category}: the row does not name "
                    f"{group}"
                )
                break

        hidden = len(picked) - len(shown)
        if hidden and f"+{hidden} more" not in panel:
            failures.append(
                f"--select {category}: the row does not count the "
                f"{hidden} groups it does not show"
            )

    # --select with several categories at once: the operator picked a
    # category and not a tool, and the panel names the categories.
    several = [
        category
        for category in ("Operating System", "System", "Database")
        if category in groups
    ]
    if len(several) > 1:
        selected = [tool for category in several for tool in groups[category]]
        inventory = mw._agent_tool_inventory(False, selected)
        picked = mw._selected_tool_groups(inventory)

        state = TuiState()
        state.mode = "Selected tools"
        state.update_tools(
            [tool.metadata.name for tool in inventory],
            scope="selected",
            groups=picked,
        )

        print(f"=== --select {', '.join(several)}: {len(inventory)} tools")
        print(render(state))
        print(f"    the row says: {the_row(render(state))}")
        print()

        panel = render(state)
        if f"{len(inventory)} selected" not in panel:
            failures.append(
                "several categories: the row does not carry the count"
            )

        shown = picked[: TelemetryView.TOOL_NAMES_SHOWN]
        for group in shown:
            if group not in panel:
                failures.append(
                    f"several categories: the row does not name {group}"
                )
                break

        hidden = len(picked) - len(shown)
        if hidden and f"+{hidden} more" not in panel:
            failures.append(
                f"several categories: the row does not count the "
                f"{hidden} groups it does not show"
            )

        for tool in inventory:
            if mentions(panel, tool.metadata.name):
                failures.append(
                    f"several categories: the row names the tool "
                    f"{tool.metadata.name} instead of the groups"
                )
                break

    print("=" * 60)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1

    print("OK: the panel names the groups the operator selected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
