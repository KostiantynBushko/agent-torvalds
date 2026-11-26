# The document pane follows the end of the answer

**The operator asked for the auto scroll of the document pane:**

> auto scroll in "Markdown Document Viewer"

The *Markdown Document Viewer* is the pane that carries the answer of
the agent.  The answer is **written while the operator watches it**:
the workflow streams the answer token by token, and every token lands
in the document of the pane.

The pane had **no auto scroll at all**.  The window of the pane stayed
where it was while the answer grew, and the operator was shown the
**beginning** of an answer that was still being written -- the part he
had already read, and never the part that was new.

The measurement is in
[`probe_document_auto_scroll.py`](probe_document_auto_scroll.py) -- it
builds the **real** state, draws the pane in the **real** layout at the
width and the height of the terminal of the operator, and reports what
is on the screen.  It writes nothing.

```bash
python investigate/tui-document-auto-scroll/probe_document_auto_scroll.py
```

---

## 1. What the pane was

The pane carried a **number**: `scroll_offset`, the first line of the
window in the content.  The view rendered the markdown, counted the
lines, and sliced the content at that number:

```python
state.scroll_offset = min(state.scroll_offset, state.max_scroll())
start_idx = max(0, min(state.scroll_offset, max(0, len(lines) - 1)))
end_idx = min(len(lines), start_idx + height_limit)
```

The clamp is the whole of the rule.  It keeps the window **inside** the
content -- the operator cannot walk past the end -- and it does nothing
else.  In particular:

* when the content grows, the number does not move, and the window
  stays where it was;
* nothing in the state said whether the operator was **at the end** of
  the document or **away from it**.

The second point is the heart of it.  The panes of the sidebar --
the progress pane and the telemetry pane -- carry a `PaneScroll`, and
that scroll knows two things the document pane did not: whether the
window is **stuck** to the end of the content, and whether the
operator has **left** the end.

The probe, against the real pane, says:

```
  FAIL  the pane follows the end of the answer
        the offset of the window: 0 of 170 lines
        the newest line of the answer is on the screen: False
  PASS  the operator keeps his place while the answer grows
        the line of the paragraph before: 31
        the line of the paragraph after:  31
        the offset of the window: 80
  FAIL  the follow comes back when the operator scrolls to the end
        the offset of the window: 88 of 170 lines
        the newest line of the answer is on the screen: False
  PASS  a new document opens at its beginning
        the first line of the window: 'THE-TOOLS-OF-THE-AGENT'
        the offset of the window: 0
  FAIL  a new run follows the answer that is written
        the offset of the window: 0 of 49 lines
        the newest line of the answer is on the screen: False
```

Three of the five do not hold.  The two that hold are the ones the
change must **not** break: the operator who scrolls away keeps his
place, and a new document opens at its beginning.

## 2. What the change is

**The document pane carries a scroll of its own -- a `PaneScroll`.**
The machinery is not new: `components/tui/pane_scroll.py` carries it
for the panes of the sidebar, and its own words name the document pane
as the first of the logs that grow downwards:

> The end of the list is the **bottom** for a log that grows downwards
> -- the document pane, and the telemetry pane.

The document pane now uses it, and the three rules follow from it:

* **the window follows the end** -- the scroll is *stuck* to the end,
  and the content that grows keeps the newest line on the screen;
* **the operator keeps his place** -- the operator who scrolls up
  leaves the end, the scroll is no longer stuck, and the content that
  grows does not move his window;
* **the follow comes back** -- the operator who scrolls to the end
  again is at the end of the answer from then on.

**A run follows the answer it writes.**  The window follows the end
while the answer is written, and it stays at the end when the answer
is complete.

**A new document opens at its beginning.**  The output of a command --
`\help`, `\tools`, `\projects` -- is a document the operator has never
seen.  It opens at its first line, and the window does not follow it.

The three places that knew the old rule now say the new one:

| the place | before | after |
| --- | --- | --- |
| `components/tui/state_bridge.py` | `scroll_offset` was a number | the scroll of the pane is a `PaneScroll`, and the number is its offset |
| `components/tui/markdown_view.py` | the view clamped the number and sliced | the view hands the lines to the scroll, and the scroll says where the window is |
| `components/tui/tui_app.py` | the answer of the run replaced the document | the answer of the run **is** the document that was already there, and the window stays where it is |

## 3. What it costs

**The window moves on its own.**  The operator reads the answer while
it is written, and the text he is reading moves up as the answer
grows.  He leaves the end with the keys of the pane, and the window
holds his place until he comes back.

**The number of the window is still there.**  `scroll_offset` and
`total_rendered_lines` are still the names the state carries -- they
are the offset and the number of lines of the scroll of the pane now,
and not a number of their own.

## 4. The evidence

* `tests/test_tui_document_auto_scroll.py` -- the window follows the
  end, the operator keeps his place, the follow comes back, a new
  document opens at its beginning, and a new run follows its answer.
* `investigate/tui-document-auto-scroll/probe_document_auto_scroll.py`
  -- the measurement, and the screen of the operator.
* The gate of the repository stays green: the known failures stay
  known, and no new one comes.
