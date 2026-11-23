"""
The scroll of a pane of the Torvalds TUI.

Every scrollable pane carries its own scroll state: the offset of the
window, the number of lines the content has, the anchor -- the id of
the item at the top of the window -- and whether the window follows the
end of the content.

**The end of the list is where the work is.**  A list that grows
while the operator reads it has a current position, and the window
follows it: the newest task is on the screen, and it stays on the
screen while the work goes on.

The end of the list is the **bottom** for a log that grows downwards
-- the document pane, and the telemetry pane.  It is the **top** for
the stack of the tool tasks: the recent tool tasks are shown upside
down, the newest one is on the top, and the task that ran before it
is right below it.  The pane tells the scroll which end it follows,
with ``follow_end``.

**The anchor keeps the operator where he is.**  A new task is inserted
at the current position of the list, and the window stays where it is
-- so the operator who has scrolled away keeps the task he is reading,
and the operator who has not keeps the newest one.

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
        stuck: Whether the window follows the current position of the
            content.
        follow_end: Whether the current position of the content is its
            **end**.  It is the end for a log that grows downwards, and
            the **beginning** for the stack of the tool tasks, which is
            shown upside down.
    """

    offset: int = 0
    total_lines: int = 0
    anchor: str = ""
    height: int = 0
    stuck: bool = True
    follow_end: bool = True

    #: The lines of the content, and the anchor of every one of them.
    lines: List[str] = field(default_factory=list)
    anchors: List[str] = field(default_factory=list)

    # -- the content ------------------------------------------------------

    def set_frame(
        self,
        lines: Sequence[str],
        anchors: Optional[Sequence[str]] = None,
        height: int = 0,
        follow_end: bool = True,
    ) -> None:
        """The pane drew this frame.

        The content of a pane grows while the operator reads it: a new
        tool task is inserted at the current position of the list.  The
        window stays where it is -- unless it is stuck to the current
        position, in which case it follows it and the newest line is on
        the screen.

        Args:
            lines: The lines of the content.
            anchors: The anchor of every line -- the id of the item the
                line belongs to.  The lines without an anchor of their
                own belong to the item of the line above them.
            height: The number of lines the window shows.
            follow_end: Whether the current position of the content is
                its end.  The **stack** of the tool tasks is shown
                upside down, and its current position is its beginning.
        """
        self.lines = list(lines)
        self.anchors = list(anchors) if anchors is not None else []
        self.total_lines = len(self.lines)
        self.height = max(0, int(height))
        self.follow_end = bool(follow_end)

        if self.stuck:
            # The window follows the current position of the list.
            self.offset = self.maximum_offset if self.follow_end else 0
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
        """Scroll the window back, towards the beginning of the list.

        For the **stack** of the tool tasks the beginning is the current
        position of the work: the newest task, and the task that ran
        before it.
        """
        self.offset = self._clamp(self.offset - max(1, int(lines)))
        self._remember()

    def scroll_down(self, lines: int = 1) -> None:
        """Scroll the window forward, towards the end of the log."""
        self.offset = self._clamp(self.offset + max(1, int(lines)))
        self._remember()

    def scroll_home(self) -> None:
        """Go to the top of the list.

        The top of the **stack** of the tool tasks is the current
        position of the work: the newest task, and the task that ran
        before it.
        """
        self.offset = 0
        self._remember()

    def scroll_end(self) -> None:
        """Go to the bottom of the list.

        The bottom of the **stack** of the tool tasks is the oldest
        task of the run: the far end of the history.
        """
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
    def at_start(self) -> bool:
        """Whether the window shows the beginning of the list.

        The beginning is the current position of the **stack** of the
        tool tasks: the newest task is on the top of it, and it is
        where the work is.
        """
        return self.offset <= 0

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
        self.stuck = self.at_bottom if self.follow_end else self.at_start

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
