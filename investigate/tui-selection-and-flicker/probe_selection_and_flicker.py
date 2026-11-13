"""
Probe: the selection picks up the wrong pane, and the screen blinks.

The probe answers five questions, each with a number:

1. **What size does Rich believe the terminal is?**  Rich's
   ``Console.size`` prefers the ``LINES`` and ``COLUMNS`` environment
   variables over the real terminal size.  When the shell exported
   stale values, Rich lays the TUI out for a terminal that is not
   there.

2. **Does the frame fit the terminal?**  A frame wider or taller than
   the terminal wraps and scrolls the screen.  Every scroll is a jump
   of the whole picture - the blink.

3. **Are the panes where the layout put them?**  The terminal hands the
   operator the *physical* screen, and a selection is made by column.
   When the frame does not fit, the border of the "Workflow & Tools
   Progress" pane lands in the middle of the answer of the agent, and
   the operator copies both.

4. **Does the log stay off the screen?**  The operator decided on
   2026-11-13: while the TUI is up, the log goes into the file.

5. **Does the fix hold?**  The same measurement, with the production
   code.

The probe never touches the terminal of the operator: the TUI runs in a
pty of its own, and the byte stream it produces is replayed through a
terminal emulator.

Usage:
    python probe_selection_and_flicker.py [--seconds 3] [--rows 40] [--cols 120]

Exit code 0 when the defect reproduces and the fix holds, 1 otherwise.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(HERE, "repro"))

from capture_pty import main as capture_main  # noqa: E402
from term_emulator import TerminalEmulator  # noqa: E402

_ANSI = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07")

#: The two vertical bars that separate the document pane from the
#: sidebar.
SEPARATOR = "││"


def run_capture(out_path: str, size_file: str, log_dir: str, seconds: float,
                mode: str, rows: int, cols: int, stale_lines: int = 0,
                stale_cols: int = 0, clear_env: bool = False,
                legacy_console: bool = False, noisy: bool = False) -> tuple[bytes, dict]:
    """Capture the TUI byte stream under one set of conditions."""
    argv = sys.argv
    sys.argv = [
        "capture_pty.py",
        "--out", out_path,
        "--seconds", str(seconds),
        "--mode", mode,
        "--rows", str(rows),
        "--cols", str(cols),
        "--log-dir", log_dir,
    ]
    if clear_env:
        sys.argv.append("--clear-env")
    if stale_lines:
        sys.argv.extend(["--stale-lines", str(stale_lines)])
    if stale_cols:
        sys.argv.extend(["--stale-cols", str(stale_cols)])
    if legacy_console:
        sys.argv.append("--legacy-console")
    if noisy:
        sys.argv.append("--noisy")
    os.environ["TORVALDS_PROBE_SIZE_FILE"] = size_file
    try:
        capture_main()
    finally:
        sys.argv = argv
    with open(out_path, "rb") as handle:
        payload = handle.read()

    report = {"console": (0, 0), "log_file": ""}
    if os.path.exists(size_file):
        with open(size_file, "r", encoding="utf-8") as handle:
            for line in handle:
                key, _, value = line.strip().partition("=")
                if key == "console" and "x" in value:
                    width, _, height = value.partition("x")
                    report["console"] = (int(width), int(height))
                elif key == "log_file":
                    report["log_file"] = value
    return payload, report


def expected_separator_column(cols: int) -> int:
    """The column the layout puts the pane separator at.

    The layout is asked, not guessed: it is rendered at the width of
    the terminal and the separator is looked for.
    """
    from rich.console import Console

    from components.tui.layout_manager import (
        build_torvalds_layout,
        render_footer,
        render_header,
    )
    from components.tui.markdown_view import MarkdownView
    from components.tui.progress_view import ProgressView
    from components.tui.state_bridge import TuiState
    from components.tui.telemetry_view import TelemetryView

    console = Console(width=cols, height=40, color_system=None)
    state = TuiState()
    layout = build_torvalds_layout()
    layout["header"].update(render_header("", 0, True, state.session_start_time))
    layout["markdown_pane"].update(MarkdownView(console).render(state))
    layout["progress_pane"].update(ProgressView().render(state))
    layout["telemetry_pane"].update(TelemetryView().render(state))
    layout["footer"].update(render_footer("", 0))
    for line in console.render_lines(layout, console.options.update(height=40, width=cols)):
        text = "".join(segment.text for segment in line)
        index = text.find(SEPARATOR)
        if index >= 0:
            return index
    return -1


def analyse(payload: bytes, rows: int, cols: int, separator_column: int,
            believed: tuple[int, int]) -> dict:
    """Replay the capture and measure what the operator would see."""
    text = payload.decode("utf-8", errors="replace")
    emulator = TerminalEmulator(rows=rows, cols=cols)
    emulator.feed(text)

    screen = emulator.screen
    lines = screen.text_lines()

    believed_width, believed_height = believed

    # Output that was written *into* the frame: the tail of a frame is
    # the last row of the screen plus whatever else was written before
    # the next repaint.  More rows than the screen has means that
    # something was written into the layout - a log line, or the
    # chatter of a tool.
    foreign = 0
    for frame in text.split("\x1b[H")[1:]:
        rows_in_frame = _ANSI.sub("", frame).split("\n")
        if believed_height and len(rows_in_frame) > believed_height:
            foreign += 1

    # Where the panes ended up on the physical screen.  A selection is
    # made by column: when the separator is not in the column the
    # layout chose, the selection crosses the panes.
    separator_columns = set()
    for line in lines:
        index = line.find(SEPARATOR)
        if index >= 0:
            separator_columns.add(index)
    misplaced = sum(
        1 for line in lines
        if SEPARATOR in line and line.find(SEPARATOR) != separator_column
    )

    return {
        "scrolls": screen.scroll_count,
        "believed_width": believed_width,
        "believed_height": believed_height,
        "terminal_cols": cols,
        "terminal_rows": rows,
        "overflows": believed_width > cols or believed_height > rows,
        "separator_columns": sorted(separator_columns),
        "expected_separator_column": separator_column,
        "misplaced_rows": misplaced,
        "foreign_frames": foreign,
        "screen": lines,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument("--rows", type=int, default=40)
    parser.add_argument("--cols", type=int, default=120)
    parser.add_argument(
        "--stale-lines", type=int, default=33, help="The stale LINES value."
    )
    parser.add_argument(
        "--stale-cols", type=int, default=229, help="The stale COLUMNS value."
    )
    args = parser.parse_args()

    separator_column = expected_separator_column(args.cols)

    print("=" * 78)
    print("PROBE: the selection picks up the wrong pane, and the screen blinks")
    print("=" * 78)
    print(f"\nThe real terminal is {args.cols}x{args.rows}.")
    print(f"The layout puts the pane separator at column {separator_column}.")

    cases = {}
    with tempfile.TemporaryDirectory() as workdir:
        runs = [
            ("broken", "the old console, stale LINES/COLUMNS",
             dict(stale_lines=args.stale_lines, stale_cols=args.stale_cols,
                  legacy_console=True)),
            ("clean", "the old console, no LINES/COLUMNS",
             dict(clear_env=True, legacy_console=True)),
            ("fixed", "the production TUI, stale LINES/COLUMNS",
             dict(stale_lines=args.stale_lines, stale_cols=args.stale_cols)),
            ("noisy", "the production TUI, and the agent logs while it works",
             dict(clear_env=True, noisy=True)),
        ]
        for name, label, options in runs:
            log_dir = os.path.join(workdir, f"log-{name}")
            payload, report = run_capture(
                os.path.join(workdir, f"{name}.bin"),
                os.path.join(workdir, f"{name}.size"),
                log_dir,
                args.seconds, "request", args.rows, args.cols, **options
            )
            cases[name] = analyse(payload, args.rows, args.cols, separator_column,
                                   report["console"])
            cases[name]["label"] = label
            cases[name]["log_file"] = report["log_file"]
            cases[name]["log_lines"] = _log_lines(report["log_file"])

        print()
        for name, _label, _options in runs:
            case = cases[name]
            print(f"    {case['label']}")
            print(f"        Rich believes the terminal is : "
                  f"{case['believed_width']}x{case['believed_height']}")
            print(f"        the frame overflows             : {case['overflows']}")
            print(f"        screen scrolls                  : {case['scrolls']}")
            print(f"        pane separator found at column  : "
                  f"{case['separator_columns']} "
                  f"(expected {case['expected_separator_column']})")
            print(f"        rows with the panes misplaced  : "
                  f"{case['misplaced_rows']}")
            print(f"        frames with foreign output      : "
                  f"{case['foreign_frames']}")
            print(f"        the log went into the file      : "
                  f"{case['log_lines']} line(s) in {case['log_file']}")
            print()

    print("=" * 78)
    ok = (
        # The defect: the frame does not fit, the screen scrolls, and
        # the panes are not where the layout put them.
        cases["broken"]["overflows"]
        and cases["broken"]["scrolls"] > 50
        and cases["broken"]["misplaced_rows"] > 0
        # Without the stale environment: everything is in its place.
        and not cases["clean"]["overflows"]
        and cases["clean"]["scrolls"] <= 5
        and cases["clean"]["misplaced_rows"] == 0
        # The production TUI holds, even with the stale environment.
        and not cases["fixed"]["overflows"]
        and cases["fixed"]["scrolls"] <= 5
        and cases["fixed"]["misplaced_rows"] == 0
        # And the log of the agent stays off the screen: it is in the
        # file, and it does not scroll the layout.
        and cases["noisy"]["foreign_frames"] == 0
        and cases["noisy"]["scrolls"] <= 5
        and cases["noisy"]["log_lines"] > 0
    )
    print("RESULT:", "the defect reproduces and the fix holds" if ok
          else "the measurement did not come out as expected")
    print("=" * 78)
    return 0 if ok else 1


def _log_lines(log_file: str) -> int:
    """How many lines the log file holds."""
    if not log_file or not os.path.exists(log_file):
        return 0
    with open(log_file, "r", encoding="utf-8", errors="replace") as handle:
        return sum(1 for line in handle if line.strip())


if __name__ == "__main__":
    sys.exit(main())
