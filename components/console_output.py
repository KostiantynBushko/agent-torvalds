"""Printing text that must reach the operator exactly as it is.

The agent prints the result of a chat command — and the result of
``\\chat-export`` is the **content of a session**: what the operator typed
and what the model answered.  Rich reads square brackets as markup, and
the effect of that was never cosmetic:

    '[dim]text[/dim]'  ->  'text'           the text is eaten
    'a [b] c'          ->  'a  c'           the text is eaten
    '[/nope] broken'   ->  MarkupError      the REPL dies

So the text of a session is printed with the markup switched off, the
highlighting switched off, and the wrapping switched off: what reaches the
terminal is what the session holds, character for character, in the lines
it was written in.

The colour of the output is kept — the chat commands are cyan, and they
stay cyan.

Category: Infrastructure
Retriever Keywords: console, print, verbatim, markup, rich, export
"""

from __future__ import annotations

from rich.console import Console

__all__ = ["print_verbatim"]


def print_verbatim(console: Console, text: str, style: str = "cyan") -> None:
    """Print *text* exactly as it is.

    The markup of Rich is not interpreted, the text is not highlighted,
    and it is not wrapped: the output is the input, character for
    character.

    Args:
        console: The console to print to.
        text: The text to print.
        style: The style of the output.  The chat commands are cyan.

    Returns:
        None.
    """
    console.print(
        text,
        style=style,
        markup=False,
        highlight=False,
        soft_wrap=True,
    )
