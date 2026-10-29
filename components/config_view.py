"""
The ``\\config`` command — the effective configuration, and where it came from.

Four layers decide what the agent does: the command line flag, the
environment variable, the configuration file and the built-in default.
When a setting is not what the operator expected, the only useful
question is **"which layer won?"** — and that question has to have an
answer, or the configuration file is a mystery box.

This module renders that answer: every setting the agent resolved, the
value that won, and the layer it came from.

    \\config

Category: Infrastructure / Configuration
Retriever Keywords: config, configuration, effective, source, provenance,
                    where did this value come from
"""

from __future__ import annotations

from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from components.config import Config

__all__ = ["render_effective", "render_effective_markdown", "render_help"]


#: The name of the command.
COMMAND_NAME = "\\config"

#: The one-line description the command registry shows.
DESCRIPTION = "Show the effective configuration and where every value came from"


def render_help() -> str:
    """The help text of the command."""
    return (
        "**\\\\config** — show the effective configuration.\n\n"
        "Every setting the agent resolved, the value that won, and the layer "
        "it came from: the command line flag, the environment variable, the "
        "configuration file or the built-in default.\n\n"
        "The configuration file is `~/.config/torvalds/config.toml`.  "
        "`--write-default-config` writes a commented template of it."
    )


def render_effective(config: Config, console: Optional[Console] = None) -> None:
    """Print the effective configuration.

    Args:
        config: The configuration of the running agent.
        console: Where to print.  The shared console when it is omitted.
    """
    if console is None:
        console = Console()

    rows = config.effective()

    table = Table(
        title="The effective configuration",
        title_justify="left",
        show_lines=False,
        header_style="bold cyan",
    )
    table.add_column("setting", style="cyan", no_wrap=True)
    table.add_column("value", overflow="fold")
    table.add_column("source", style="dim")

    for row in rows:
        table.add_row(row.key, _render_value(row.value), row.source)

    if rows:
        console.print(table)
    else:
        console.print("[dim]No setting was resolved yet.[/dim]")

    # The file itself.
    if config.present:
        console.print(
            f"[dim]The configuration file: {config.path}[/dim]"
        )
    else:
        console.print(
            f"[dim]No configuration file at {config.path} — the defaults are "
            f"used.  `--write-default-config` writes a commented template of "
            f"it.[/dim]"
        )

    # The problems.  A file that cannot be read, a setting of the wrong
    # type, a name the agent does not know — the operator has to see them.
    if config.problems:
        console.print()
        console.print("[bold yellow]The configuration file has problems:[/bold yellow]")
        for problem in config.problems:
            console.print(f"  [yellow]•[/yellow] {problem}")


def render_effective_markdown(config: Config) -> str:
    """The effective configuration as markdown.

    The multi-window agent renders its commands into the document pane,
    and the configuration table belongs there like every other command.

    Args:
        config: The configuration of the running agent.

    Returns:
        The markdown of the table, of the file and of the problems.
    """
    rows = config.effective()

    lines = ["## The effective configuration", ""]
    if rows:
        lines.append("| setting | value | source |")
        lines.append("|---|---|---|")
        for row in rows:
            lines.append(
                f"| `{row.key}` | {_render_value(row.value)} | {row.source} |"
            )
    else:
        lines.append("_No setting was resolved yet._")

    lines.append("")
    if config.present:
        lines.append(f"The configuration file: `{config.path}`")
    else:
        lines.append(
            f"No configuration file at `{config.path}` — the defaults are used.  "
            f"`--write-default-config` writes a commented template of it."
        )

    if config.problems:
        lines.append("")
        lines.append("### The configuration file has problems")
        lines.append("")
        for problem in config.problems:
            lines.append(f"- {problem}")

    return "\n".join(lines)


def _render_value(value: object) -> str:
    """Render one value for the table."""
    if value is None:
        return "[dim]not set[/dim]"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
