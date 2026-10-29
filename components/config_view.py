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

__all__ = [
    "handle_config",
    "handle_config_markdown",
    "render_effective",
    "render_effective_markdown",
    "render_help",
    "render_setting",
    "render_setting_markdown",
]


#: The name of the command.
COMMAND_NAME = "\\config"

#: The one-line description the command registry shows.
DESCRIPTION = "Show the effective configuration and where every value came from"


def render_help() -> str:
    """The help text of the command."""
    return (
        "**\\\\config** — show the effective configuration, and change it.\n\n"
        "Every setting the agent resolved, the value that won, and the layer "
        "it came from: the command line flag, the environment variable, the "
        "configuration file or the built-in default.\n\n"
        "The configuration file is `~/.config/torvalds/config.toml`.  "
        "`--write-default-config` writes a commented template of it.\n\n"
        "**`\\\\config <setting>`** — one setting in detail: its value, "
        "where it came from and its default.\n\n"
        "**`\\\\config <setting> <value>`** — write the value into the "
        "configuration file.  The file is edited, not rewritten: your "
        "comments and the order of the settings stay as they are."
    )


def render_setting(
    config: Config,
    key: str,
    console: Optional[Console] = None,
) -> None:
    """Print one setting: its value, where it came from, and its default.

    Args:
        config: The configuration of the running agent.
        key: The dotted name of the setting — ``llm.model``.
        console: Where to print.  The shared console when it is omitted.
    """
    if console is None:
        console = Console()

    setting = config.settings.get(key)
    if setting is None:
        console.print(f"[yellow]There is no setting called {key}.[/yellow]")
        _print_the_settings(config, console)
        return

    value = config.get(key)
    console.print(f"[cyan]{key}[/cyan] = [green]{_render_value(value)}[/green]")
    console.print(f"[dim]  it came from: {config.source(key)}[/dim]")
    if setting.default is not None:
        console.print(
            f"[dim]  the default is: {_render_value(setting.default)}[/dim]"
        )
    if setting.env_var:
        console.print(
            f"[dim]  {setting.env_var} overrides the file, and the flag "
            f"overrides both.[/dim]"
        )
    console.print(
        f"[dim]  to change it: \\config {key} <value>[/dim]"
    )


def _print_the_settings(config: Config, console: Console) -> None:
    """Print the names of the settings, so the operator can pick one."""
    keys = sorted(config.settings)
    console.print("[dim]The settings are:[/dim]")
    console.print("[dim]  " + ", ".join(keys) + "[/dim]")


def handle_config(
    config: Config,
    argument: str,
    console: Optional[Console] = None,
) -> bool:
    """The ``\\config`` command.

    Three forms:

    * ``\\config`` — the effective configuration, as before;
    * ``\\config <setting>`` — one setting in detail;
    * ``\\config <setting> <value>`` — write the value into the
      configuration file.

    Args:
        config: The configuration of the running agent.
        argument: What came after the command.
        console: Where to print.  The shared console when it is omitted.

    Returns:
        Whether the command was handled.  It always is.
    """
    if console is None:
        console = Console()

    argument = (argument or "").strip()
    if not argument:
        render_effective(config, console)
        return True

    parts = argument.split(None, 1)
    key = parts[0]
    raw = parts[1].strip() if len(parts) > 1 else None

    if raw is None:
        render_setting(config, key, console)
        return True

    value, problem = config.set_value(key, raw)
    if problem is not None:
        console.print(f"[yellow]{problem}[/yellow]")
        return True

    console.print(
        f"[green]{key}[/green] is now [green]{_render_value(value)}[/green]"
    )
    console.print(f"[dim]  written to {config.path}[/dim]")
    setting = config.settings.get(key)
    if setting is not None and setting.env_var:
        console.print(
            f"[dim]  {setting.env_var} overrides the file — and the flag "
            f"overrides both.[/dim]"
        )
    console.print(
        "[dim]  the settings that were read when the agent started apply on "
        "the next start.[/dim]"
    )
    return True


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
            f"used.  The agent writes a commented template there when it "
            f"starts.[/dim]"
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
            f"The agent writes a commented template there when it starts."
        )

    if config.problems:
        lines.append("")
        lines.append("### The configuration file has problems")
        lines.append("")
        for problem in config.problems:
            lines.append(f"- {problem}")

    return "\n".join(lines)


def render_setting_markdown(config: Config, key: str) -> str:
    """One setting as markdown.

    Args:
        config: The configuration of the running agent.
        key: The dotted name of the setting — ``llm.model``.

    Returns:
        The markdown of the setting.
    """
    setting = config.settings.get(key)
    if setting is None:
        keys = sorted(config.settings)
        return (
            f"**There is no setting called `{key}`.**\n\n"
            f"The settings are: {', '.join(f'`{k}`' for k in keys)}"
        )

    value = config.get(key)
    lines = [
        f"## `{key}`",
        "",
        f"**{_render_value(value)}**",
        "",
        f"- it came from: {config.source(key)}",
    ]
    if setting.default is not None:
        lines.append(f"- the default is: {_render_value(setting.default)}")
    if setting.env_var:
        lines.append(
            f"- `{setting.env_var}` overrides the file, and the flag "
            f"overrides both"
        )
    lines.append(f"- to change it: `\\config {key} <value>`")
    return "\n".join(lines)


def handle_config_markdown(config: Config, argument: str) -> str:
    """The ``\\config`` command, as markdown.

    The multi-window agent renders its commands into the document pane,
    so the command returns the markdown instead of printing it.

    Args:
        config: The configuration of the running agent.
        argument: What came after the command.

    Returns:
        The markdown of the command.
    """
    argument = (argument or "").strip()
    if not argument:
        return render_effective_markdown(config)

    parts = argument.split(None, 1)
    key = parts[0]
    raw = parts[1].strip() if len(parts) > 1 else None

    if raw is None:
        return render_setting_markdown(config, key)

    value, problem = config.set_value(key, raw)
    if problem is not None:
        return f"**{problem}**"

    setting = config.settings.get(key)
    lines = [
        f"## `{key}` is now **{_render_value(value)}**",
        "",
        f"- written to `{config.path}`",
    ]
    if setting is not None and setting.env_var:
        lines.append(
            f"- `{setting.env_var}` overrides the file — and the flag "
            f"overrides both"
        )
    lines.append(
        "- the settings that were read when the agent started apply on the "
        "next start"
    )
    return "\n".join(lines)


def _render_value(value: object) -> str:
    """Render one value for the table."""
    if value is None:
        return "[dim]not set[/dim]"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
