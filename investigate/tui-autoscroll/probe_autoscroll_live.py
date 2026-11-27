"""
The document pane of the **live** TUI: what does the operator really see?

The probe builds the **real** application, draws the **real** layout
with the **real** panes -- the layout is printed, so that the map of
the frame is the one the operator sees -- and streams an answer the way
the workflow streams it: token by token.  After every piece it reports
what is on the screen: the offset of the window, the end of the
document, the height the layout really gives to the pane, the subtitle
of the pane, and whether the newest line of the answer is on the
screen.

It writes nothing.

    python investigate/tui-autoscroll/probe_autoscroll_live.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import io  # noqa: E402

from rich.console import Console  # noqa: E402

from components.tui.state_bridge import TuiState  # noqa: E402
from components.tui.tui_app import TuiApp  # noqa: E402

WIDTH = 120
HEIGHT = 40
PIECES = 30


def an_app() -> TuiApp:
    """The real application, with the real layout and the real panes."""
    console = Console(
        width=WIDTH,
        height=HEIGHT,
        color_system=None,
        record=True,
        file=io.StringIO(),
    )
    state = TuiState()

    async def handler(**kwargs):  # pragma: no cover - the probe never runs
        return ("the answer", None)

    return TuiApp(
        agent=None,
        prompt_handler_fn=handler,
        state=state,
        console=console,
    )


def the_subtitle(app: TuiApp) -> str:
    """The subtitle of the document pane, as the operator reads it."""
    panel = app.layout["markdown_pane"].renderable
    return str(getattr(panel, "subtitle", ""))


def the_screen(app: TuiApp) -> str:
    """The screen of the operator, as it was drawn."""
    # ``export_text`` clears the recording by default: the frames are
    # read, and the last one is still there.
    return app.console.export_text(clear=False)


def main() -> int:
    """Stream an answer and report the window of the pane."""
    app = an_app()
    state = app.state

    state.set_busy(True, "what is the answer?")
    state.markdown_content = ""

    # The first frame: the layout is printed, and the map of the frame
    # is the one the operator sees.
    app._update_layout_panes()
    app.console.print(app.layout)

    print("piece  offset   end  lines  height  stuck  newest  subtitle")
    print("-" * 100)

    for number in range(1, PIECES + 1):
        marker = f"NEWEST-LINE-{number}"
        state.append_stream_token(
            f"Paragraph {number} of the answer of the agent.\n\n{marker}\n\n"
        )
        app._update_layout_panes()
        app.console.print(app.layout)

        screen = the_screen(app)
        subtitle = the_subtitle(app).replace("\n", " ")
        print(
            f"{number:>5}  {state.scroll_offset:>6}  "
            f"{state.max_scroll():>4}  {state.total_rendered_lines:>5}  "
            f"{state.document_height:>6}  {str(state.document_scroll.stuck):>5}  "
            f"{str(marker in screen):>6}  {subtitle}"
        )

    print()
    print("the window is at the end of the answer: "
          f"{state.scroll_offset == state.max_scroll()}")
    marker = f"NEWEST-LINE-{PIECES}"
    print(f"the newest line is on the screen: {marker in the_screen(app)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
