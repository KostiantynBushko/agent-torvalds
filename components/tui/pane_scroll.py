"""
The scroll of a pane of the Torvalds TUI.

Every scrollable pane carries its own scroll state: the offset of the
window, the number of lines the content has, the anchor -- the id of
the item at the top of the window -- and whether the window follows the
end of the content.

**The list is a log.**  The oldest task first, the newest at the
bottom, and the window stuck to the bottom: "down" walks forward in
time, the way it does in every scrollable thing the operator knows,
and the running task is the last line on the screen, where the eye
already is.

**The anchor keeps the operator where he is.**  A new task is inserted
at the end of the log, and the window is stuck to the end -- so the
operator who has scrolled up keeps the task he is reading, and the
operator who has not keeps the newest one.

Category: Infrastructure / TUI
Retriever Keywords: scroll, pane, offset, anchor, log, window, tui
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence


@dataclass
class PaneScroll:
    """The scroll state of one pane of the TUI.

    Attributes:
        offset: The first visible line of the window.
        total_lines: The number of lines the content has.
        anchor: The id of the item at the top of the window.
        height: The number of lines the window shows.
        stuck: Whether the window follows the end of the content.
    """

    offset: int = 0
    total_lines: int = 0
    anchor: str = ""
    height: int = 0
    stuck: bool = True

    #: The lines of the content, and the anchor of every one of them.
    lines: List[str] = field(default_factory=list)
    anchors: List[str] = field(default_factory=list)

    # -- the content ------------------------------------------------------

    def set_frame(
        self,
        lines: Sequence[str],
        anchors: Optional[Sequence[str]] = None,
        height: int = 0,
    ) -> None:
        """The pane drew this frame.

        The content of a pane grows while the operator reads it: a new
        tool task is inserted at the end of the log.  The window stays
        where it is -- unless it is stuck to the end, in which case it
        follows the end and the newest line is on the screen.

        Args:
            lines: The lines of the content.
            anchors: The anchor of every line -- the id of the item the
                line belongs to.  The lines without an anchor of their
                own belong to the item of the line above them.
            height: The number of lines the window shows.
        """
        self.lines = list(lines)
        self.anchors = list(anchors) if anchors is not None else []
        self.total_lines = len(self.lines)
        self.height = max(0, int(height))

        if self.stuck:
            # The window follows the end of the log.
            self.offset = self.maximum_offset
        elif self.anchor:
            # The operator is reading a task: the window keeps it at
            # the top, wherever the task is now.
            found = self.offset_of_anchor(self.anchor)
            if found is not None:
                self.offset = found

        self.offset = self._clamp(self.offset)

    def window(self) -> List[str]:
        """The lines the window shows."""
        if not self.lines:
            return []
        start = self._clamp(self.offset)
        return self.lines[start : start + max(1, self.height)]

    # -- the movement -----------------------------------------------------

    def scroll_up(self, lines: int = 1) -> None:
        """Scroll the window back, towards the beginning of the log."""
        self.offset = self._clamp(self.offset - max(1, int(lines)))
        self._remember()

    def scroll_down(self, lines: int = 1) -> None:
        """Scroll the window forward, towards the end of the log."""
        self.offset = self._clamp(self.offset + max(1, int(lines)))
        self._remember()

    def scroll_home(self) -> None:
        """Go to the top of the log."""
        self.offset = 0
        self._remember()

    def scroll_end(self) -> None:
        """Go to the bottom of the log."""
        self.offset = self.maximum_offset
        self._remember()

    # -- the position -----------------------------------------------------

    @property
    def maximum_offset(self) -> int:
        """The largest offset the window may have."""
        return max(0, self.total_lines - max(1, self.height))

    @property
    def at_bottom(self) -> bool:
        """Whether the window shows the end of the log."""
        return self.offset >= self.maximum_offset

    @property
    def remaining(self) -> int:
        """The number of lines below the window."""
        return max(0, self.total_lines - self.offset - max(1, self.height))

    def subtitle(self) -> str:
        """Where the operator is, the way the document pane says it."""
        if not self.total_lines:
            return ""

        parts: List[str] = []
        if self.offset > 0:
            parts.append(f"▲ {self.offset + 1}/{self.total_lines}")
        remaining = self.remaining
        if remaining > 0:
            parts.append(f"▼ {remaining} more")
        if not parts:
            return ""
        return " │ ".join(parts)

    # -- the helpers ------------------------------------------------------

    def _clamp(self, offset: int) -> int:
        """The offset, inside the content."""
        return max(0, min(int(offset), self.maximum_offset))

    def _remember(self) -> None:
        """The anchor is the item at the top of the window."""
        self.anchor = self.anchor_at(self.offset)
        self.stuck = self.at_bottom

    def anchor_at(self, offset: int) -> str:
        """The anchor of the line at an offset.

        A line without an anchor of its own belongs to the item of the
        line above it: the detail of a tool belongs to the tool.

        Args:
            offset: The offset of the line.

        Returns:
            The id of the item, and an empty string when there is none.
        """
        if not self.anchors:
            return ""
        index = max(0, min(int(offset), len(self.anchors) - 1))
        found = self.anchors[index]
        while not found and index > 0:
            index -= 1
            found = self.anchors[index]
        return found

    def offset_of_anchor(self, anchor: str) -> Optional[int]:
        """The offset of the first line of an item.

        Args:
            anchor: The id of the item.

        Returns:
            The offset of the item, or None when the content does not
            carry it any more.
        """
        if not anchor:
            return None
        for index, value in enumerate(self.anchors):
            if value == anchor:
                return index
        return None


__all__ = ["PaneScroll"]
