"""
Tool Selection View for Torvalds Multi-Window Console.

Provides a TUI-friendly wrapper around the interactive startup tool selection
implemented in :mod:`agent_tool_selection`.

The classic orchestrator (``agent-torvalds.py``) offers a ``--select`` flag
that groups every tool by category and asks the user which categories to load.
The multi-window agent must offer the same capability, but it cannot use the
plain ``input()`` based flow because the Rich ``Live`` display owns the
terminal while the TUI is running.

This module provides:
  - :func:`render_categories_markdown` — renders the category menu as
    Markdown so it can be displayed inside the document pane.
  - :func:`select_tools_interactive_tui` — runs the selection flow against an
    arbitrary input/output pair, so the TUI can drive it through its own
    command bar.

Category: Infrastructure
"""

import sys
from typing import Callable, List, Optional, Sequence

from llama_index.core.tools import FunctionTool

from agent_tool_selection import (
    _build_category_description,
    _extract_category,
    _extract_short_description,
    group_tools_by_category,
    parse_tool_selection,
)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_all_tools() -> List[FunctionTool]:
    """
    Discover every tool available across all toolkits.

    Delegates to :func:`agent_tool_selection._discover_tools` so both
    orchestrators always present exactly the same tool inventory.

    Returns:
        List[FunctionTool]: All available tools.
    """
    from agent_tool_selection import _discover_tools

    return _discover_tools()


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def render_categories_markdown(
    groups: dict,
    total_tools: int,
) -> str:
    """
    Render the tool category menu as Markdown for the document pane.

    Args:
        groups: Mapping of category name -> list of tools.
        total_tools: Total number of tools across all categories.

    Returns:
        str: Markdown document describing the selectable categories.
    """
    lines = [
        "# 🧰 Startup Tool Selection",
        "",
        "Select the tool categories to load for this session.",
        "",
        f"**Total:** {total_tools} tools across {len(groups)} categories.",
        "",
        "| # | Category | Tools | Capabilities |",
        "| :--- | :--- | ---: | :--- |",
    ]

    for idx, (category, tools) in enumerate(groups.items(), start=1):
        summary = _build_category_description(tools)
        lines.append(f"| {idx} | {category} | {len(tools)} | {summary} |")

    lines.extend([
        "",
        "**How to select:**",
        "- Single category: `1`",
        "- Multiple categories: `1,3,5`",
        "- Range of categories: `1-4`",
        "- Mixed: `1-3,7,10`",
        "",
        "Type your selection in the command bar below and press **Enter**.",
    ])

    return "\n".join(lines)


def render_tool_list_markdown(tools: Sequence[FunctionTool]) -> str:
    """
    Render a flat numbered list of tools as Markdown.

    Args:
        tools: Tools to list.

    Returns:
        str: Markdown document listing every tool with its short description.
    """
    lines = [
        "# 🧰 Available Tools",
        "",
        "| # | Tool | Description |",
        "| ---: | :--- | :--- |",
    ]

    for idx, tool in enumerate(tools, start=1):
        description = tool.metadata.description or ""
        short = _extract_short_description(description)
        lines.append(f"| {idx} | `{tool.metadata.name}` | {short} |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Interactive selection
# ---------------------------------------------------------------------------

def select_tools_interactive_tui(
    all_tools: Optional[List[FunctionTool]] = None,
    input_func: Optional[Callable[[str], str]] = None,
    output_func: Optional[Callable[[str], None]] = None,
) -> List[FunctionTool]:
    """
    Run the interactive category selection flow using injectable I/O.

    This mirrors :func:`agent_tool_selection.select_tools_interactively` but
    accepts pluggable ``input_func``/``output_func`` callables so the
    multi-window TUI can drive the flow through its own command bar instead
    of blocking on the terminal.

    Args:
        all_tools: Optional pre-discovered tool list.
        input_func: Callable that receives a prompt and returns a string.
        output_func: Callable that writes a message.

    Returns:
        List[FunctionTool]: Tools belonging to the selected categories.
    """
    if all_tools is None:
        all_tools = discover_all_tools()

    if input_func is None:
        input_func = input
    if output_func is None:
        output_func = print

    groups = group_tools_by_category(all_tools)
    category_list = list(groups.keys())
    total_categories = len(category_list)

    if not category_list:
        output_func("No tools available for selection.")
        return []

    output_func(render_categories_markdown(groups, len(all_tools)))

    while True:
        try:
            raw = input_func(
                f"Select categories [example: 1,2,5 or 1-3] (1-{total_categories}): "
            )
        except EOFError:
            output_func("Input stream ended. Aborting selection.")
            return []
        except KeyboardInterrupt:
            output_func("Selection interrupted. Aborting.")
            return []

        raw = (raw or "").strip()

        if not raw:
            output_func("No selection made. Please enter at least one category index.")
            continue

        try:
            selected_indexes = parse_tool_selection(raw, maximum=total_categories)
        except ValueError as exc:
            output_func(f"  ✗ {exc}")
            continue

        if not selected_indexes:
            output_func("No categories selected. Please try again.")
            continue

        break

    selected_categories = {category_list[i - 1] for i in selected_indexes}
    selected_tools = [
        t for t in all_tools
        if _extract_category(t.metadata.description) in selected_categories
    ]

    summary_lines = [
        f"Selected {len(selected_categories)} categories "
        f"({len(selected_tools)} of {len(all_tools)} tools):"
    ]
    for cat in selected_categories:
        summary_lines.append(f"  ✓ {cat} ({len(groups[cat])} tools)")

    output_func("\n".join(summary_lines))

    return selected_tools


def is_tool_selection_command(cmd: str) -> bool:
    """
    Check whether a command string targets the tool selection flow.

    Recognised commands:
    - ``\\tools`` — open the category selection menu
    - ``\\tool-list`` — show the flat list of every available tool
    - ``\\tool-select <spec>`` — select categories non-interactively
      (e.g. ``\\tool-select 1-3,7``)

    Args:
        cmd: The command string to check.

    Returns:
        True if the command is a tool selection command.
    """
    cmd_lower = (cmd or "").strip().lower()
    if not cmd_lower:
        return False
    return (
        cmd_lower in ("\\tools", "\\tool-list", "\\tool-select")
        or cmd_lower.startswith("\\tool-select ")
    )


__all__ = [
    "discover_all_tools",
    "render_categories_markdown",
    "render_tool_list_markdown",
    "select_tools_interactive_tui",
    "is_tool_selection_command",
]
