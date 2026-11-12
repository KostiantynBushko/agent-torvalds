"""
A minimal ANSI terminal emulator - just enough to replay what Rich writes.

Rich's multi-window TUI drives the terminal with a very small set of
control codes (``ESC[H`` to go home, ``ESC[2J`` to clear, ``ESC[K`` to
erase the line, cursor moves, SGR for colour).  This emulator implements
those, keeps a screen buffer, and records what the terminal *would*
have shown at any moment.

The point of the emulator is reproducibility: the defects under
investigation (a screen that blinks, a selection that picks up the
wrong pane) are properties of the byte stream the application writes,
and the byte stream can be captured in a pty and replayed offline.

Usage:
    python term_emulator.py <capture.bin> [--rows N] [--cols N]
"""
from __future__ import annotations

import argparse
import re
from typing import List, Optional


class Screen:
    """A character grid with a cursor - the state of a terminal screen."""

    def __init__(self, rows: int = 40, cols: int = 120) -> None:
        self.rows = rows
        self.cols = cols
        self.buffer: List[List[str]] = [[" "] * cols for _ in range(rows)]
        self.x = 0
        self.y = 0
        #: How many times the screen scrolled (a line fell off the top).
        self.scroll_count = 0

    # -- helpers ---------------------------------------------------------
    def _scroll(self) -> None:
        self.buffer.pop(0)
        self.buffer.append([" "] * self.cols)
        self.scroll_count += 1

    def _put(self, ch: str) -> None:
        if self.x >= self.cols:
            self.x = 0
            self.y += 1
        if self.y >= self.rows:
            self._scroll()
            self.y = self.rows - 1
        self.buffer[self.y][self.x] = ch
        self.x += 1

    def text_lines(self) -> List[str]:
        return ["".join(row).rstrip() for row in self.buffer]

    def dump(self) -> str:
        return "\n".join(self.text_lines())


class TerminalEmulator:
    """Replays a byte stream into a :class:`Screen`."""

    _CSI = re.compile(r"\x1b\[([0-9;?]*)([a-zA-Z])")

    def __init__(self, rows: int = 40, cols: int = 120) -> None:
        self.screen = Screen(rows, cols)
        self.rows = rows
        self.cols = cols
        self._pending = ""

    # -- public API ------------------------------------------------------
    def feed(self, data: str) -> None:
        """Feed a chunk of terminal output into the emulator."""
        self._pending += data
        text, self._pending = self._pending, ""
        i = 0
        n = len(text)
        while i < n:
            ch = text[i]
            if ch == "\x1b":
                consumed = self._handle_escape(text, i)
                if consumed is None:
                    # Incomplete escape sequence - keep it for the next chunk.
                    self._pending = text[i:]
                    return
                i += consumed
                continue
            if ch == "\n":
                # A real terminal runs the ONLCR output flag: a bare LF
                # becomes CRLF, so the cursor returns to column 0 before
                # the next line is written.  Without this the emulator
                # draws a staircase and invents scroll events that the
                # operator never sees.
                self.screen.x = 0
                self.screen.y += 1
                if self.screen.y >= self.rows:
                    self.screen._scroll()
                    self.screen.y = self.rows - 1
                i += 1
                continue
            if ch == "\r":
                self.screen.x = 0
                i += 1
                continue
            if ch == "\b":
                self.screen.x = max(0, self.screen.x - 1)
                i += 1
                continue
            if ch == "\x07":
                i += 1
                continue
            self.screen._put(ch)
            i += 1

    def dump(self) -> str:
        return self.screen.dump()

    # -- internals -------------------------------------------------------
    def _handle_escape(self, text: str, pos: int) -> Optional[int]:
        """Handle an escape sequence at *pos*.

        Returns the number of characters consumed, or ``None`` when the
        sequence is incomplete (more bytes are needed).
        """
        rest = text[pos:]
        if rest.startswith("\x1b]"):
            # OSC - terminated by BEL or ST.
            bel = rest.find("\x07")
            st = rest.find("\x1b\\")
            if bel == -1 and st == -1:
                return None
            if bel == -1 or (st != -1 and st < bel):
                return st + 2
            return bel + 1
        if rest.startswith("\x1b[") or rest.startswith("\x1b?"):
            m = self._CSI.match(text, pos)
            if not m:
                return None
            self._apply_csi(m.group(1), m.group(2))
            return m.end() - pos
        if len(rest) < 2:
            return None
        # ESC + single character (e.g. ESC c) - consume both.
        return 2

    def _apply_csi(self, params: str, final: str) -> None:
        screen = self.screen
        if params.startswith("?"):
            # Private modes: alt screen, cursor visibility.  Not visible
            # in the character grid.
            return
        values = [int(p) if p else 0 for p in params.split(";")] if params else []

        def arg(idx: int, default: int = 1) -> int:
            if idx < len(values) and values[idx] != 0:
                return values[idx]
            return default

        if final == "H" or final == "f":
            screen.y = min(screen.rows - 1, max(0, arg(0, 1) - 1))
            screen.x = min(screen.cols - 1, max(0, arg(1, 1) - 1))
        elif final == "A":
            screen.y = max(0, screen.y - arg(0))
        elif final == "B":
            screen.y = min(screen.rows - 1, screen.y + arg(0))
        elif final == "C":
            screen.x = min(screen.cols - 1, screen.x + arg(0))
        elif final == "D":
            screen.x = max(0, screen.x - arg(0))
        elif final == "G":
            screen.x = min(screen.cols - 1, max(0, arg(0, 1) - 1))
        elif final == "J":
            mode = arg(0, 0)
            if mode == 2:
                screen.buffer = [[" "] * screen.cols for _ in range(screen.rows)]
            elif mode == 0:
                for x in range(screen.x, screen.cols):
                    screen.buffer[screen.y][x] = " "
                for y in range(screen.y + 1, screen.rows):
                    screen.buffer[y] = [" "] * screen.cols
        elif final == "K":
            mode = arg(0, 0)
            if mode == 0:
                for x in range(screen.x, screen.cols):
                    screen.buffer[screen.y][x] = " "
            elif mode == 1:
                for x in range(0, screen.x + 1):
                    screen.buffer[screen.y][x] = " "
            else:
                screen.buffer[screen.y] = [" "] * screen.cols
        elif final == "L":
            for _ in range(arg(0)):
                screen.buffer.insert(screen.y, [" "] * screen.cols)
                screen.buffer.pop()
        elif final == "M":
            for _ in range(arg(0)):
                screen.buffer.pop(screen.y)
                screen.buffer.append([" "] * screen.cols)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", help="The captured byte stream")
    parser.add_argument("--rows", type=int, default=40)
    parser.add_argument("--cols", type=int, default=120)
    args = parser.parse_args()

    with open(args.capture, "rb") as handle:
        data = handle.read().decode("utf-8", errors="replace")

    emulator = TerminalEmulator(rows=args.rows, cols=args.cols)
    emulator.feed(data)
    print(emulator.dump())
    print()
    print(f"[scroll events: {emulator.screen.scroll_count}]")


if __name__ == "__main__":
    main()
