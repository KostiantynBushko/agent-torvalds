"""
Markdown rendering for the console.

The agent writes Markdown — bold, code spans, headings, lists.  The
Human-in-the-Loop used to print that source verbatim (``rich.markup.escape``),
so the operator read ``**Phase 0**`` and ``- item`` instead of *Phase 0*
and a bullet list.  This module renders the Markdown properly, so what the
operator sees is what the agent wrote.

One detail of ``rich.markdown`` is fixed here: an ordered list is rendered
as `` 1 item`` — the dot is missing.  For a report that is a cosmetic
wart; for a *menu* it is a bug, because the prompt asks the operator to
type the number of the choice and the list does not show one.  ``rich``
offers no knob for it, so the list item is subclassed here.

Usage:
    from components.console_markdown import render_markdown, render_options

    render_markdown(console, "**Phase 0** — shall I start?", style="magenta")
    render_options(console, ["Patch the config", "Use an env var"])

Category: HITL / Presentation
Retriever Keywords: hitl, markdown, render, console, menu, options
"""

from __future__ import annotations

from typing import List, Sequence

from rich._loop import loop_first
from rich.console import Console, ConsoleOptions, RenderResult
from rich.markdown import ListItem, Markdown
from rich.segment import Segment


class _NumberedListItem(ListItem):
    """A list item whose number is rendered as ``1.`` instead of ``1``.

    ``rich`` renders the marker of an ordered list as the bare number, so a
    numbered menu reads " 1 Patch the config" — the operator cannot tell
    that the answer is a number.
    """

    def render_number(
        self, console: Console, options: ConsoleOptions, number: int, last_number: int
    ) -> RenderResult:
        number_width = len(str(last_number)) + 2
        render_options = options.update(width=options.max_width - number_width)
        lines = console.render_lines(self.elements, render_options, style=self.style)
        number_style = console.get_style("markdown.item.number", default="none")

        new_line = Segment("\n")
        padding = Segment(" " * number_width, number_style)
        numeral = Segment(f"{number}.".rjust(number_width - 1) + " ", number_style)
        for first, line in loop_first(lines):
            yield numeral if first else padding
            yield from line
            yield new_line


class AgentMarkdown(Markdown):
    """``rich``'s Markdown with a readable ordered-list marker."""

    elements = {**Markdown.elements, "list_item_open": _NumberedListItem}


def render_markdown(console: Console, text: str, style: str = "") -> None:
    """Render *text* as Markdown on *console*.

    Args:
        console: The console to print on.
        text: The Markdown source.  Nothing is printed when it is empty.
        style: The style of the whole block.
    """
    if not text or not text.strip():
        return
    console.print(AgentMarkdown(text, justify="left", style=style or "none"))


def render_options(
    console: Console, options: Sequence[str], style: str = ""
) -> None:
    """Render the choices of a menu question as a numbered list.

    The list is built as Markdown, so the numbering matches what the
    prompt asks the operator to type ("1", "2", …) and the choice text is
    rendered as Markdown too.

    Args:
        console: The console to print on.
        options: The choices.
        style: The style of the whole block.
    """
    choices: List[str] = [str(option) for option in options if str(option).strip()]
    if not choices:
        return

    lines: List[str] = []
    for index, choice in enumerate(choices, 1):
        # A choice that spans several lines stays inside its item.
        body = choice.replace("\n", "\n   ")
        lines.append(f"{index}. {body}")

    render_markdown(console, "\n".join(lines), style=style)
