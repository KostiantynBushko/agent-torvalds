# The document pane and the end of the answer

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

**The operator asked on 2026-11-26 for a window that does not move by
itself.**  The window that follows the end of the answer moves the text
under the reader while the answer is written: a paragraph he is reading
slides up and away, and he reads the same line twice.  The operator
wants the text under him to stay where it is.

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

The second point is the heart of it.  The panes of the sidebar -- the
progress pane and the telemetry pane -- carry a `PaneScroll`, and that
scroll knows two things the document pane did not: whether the window
is **stuck** to the end of the content, and whether the operator has
**left** the end.

## 2. What the change is

**The document pane carries a scroll of its own -- a `PaneScroll`.**
The machinery is not new: `components/tui/pane_scroll.py` carries it
for the panes of the sidebar, and its own words name the document pane
as the first of the logs that grow downwards:

> The end of the list is the **bottom** for a log that grows downwards
> -- the document pane, and the telemetry pane.

The document pane uses it now, and the two rules of it are the ones the
operator asked for:

* **the window holds its place while the answer is written** -- the
  text the operator reads does not slide away under him.  The operator
  may move the window himself -- `Up`, `Down`, `Home`, `End` -- and the
  answer that grows does not move it back;
* **the window goes to the end of the answer when the answer is
  complete** -- the operator reads the last lines of the answer without
  scrolling for them.

The second rule has a **care** in it: the answer that is complete does
not take the operator away from a paragraph he is reading.  The operator
who moved the window while the answer was written -- and who is not at
the end of it -- keeps his place.

**A new document opens at its beginning.**  The output of a command --
`\help`, `\tools`, `\projects` -- is a document the operator has never
seen.  It opens at its first line, and the window does not follow it.

The three places that knew the old rule now say the new one:

| the place | before | after |
| --- | --- | --- |
| `components/tui/state_bridge.py` | `scroll_offset` was a number | the scroll of the pane is a `PaneScroll`, and the number is its offset |
| `components/tui/markdown_view.py` | the view clamped the number and sliced | the view hands the lines to the scroll, and the scroll says where the window is |
| `components/tui/tui_app.py` | the answer of the run replaced the document | the answer of the run **is** the document that was already there, and the window goes to the end of it |

## 3. What it costs

**The newest line of the answer is not on the screen while the answer
is written.**  The operator reads the beginning of the answer, and the
pane does not show him the part that is new -- not until the answer is
complete, and the window goes to the end of it.  The pane says so in
its subtitle: *the answer is being written*, beside the number of the
lines that are below the window.

**The window of the pane does not follow the end of the content.**  The
scroll of a pane remembers whether the operator is at the end of the
content, and a scroll that reaches the end follows the content that
grows afterwards.  While the answer is written, the window does not
follow: the operator may scroll to the end to follow the answer
himself, and the answer that grows afterwards does not carry the window
with it.

## 4. The evidence

* `tests/test_tui_document_auto_scroll.py` -- 16 tests: the window does
  not move while the answer is written, the operator moves it himself,
  the operator keeps his place, the answer that is complete goes to the
  end, the answer that is complete does not take the operator away, and
  a new document opens at its beginning.
* `investigate/tui-document-auto-scroll/probe_document_auto_scroll.py`
  -- the measurement, and the screen of the operator.  The probe runs on
  the tree **before** the change as well: the name of the argument of
  the call that carries the answer is read from the signature of the
  method, because the probe measures the behaviour and not the API.

  One of the five checks does not hold before the change -- *the window
  goes to the end when the answer is complete* -- and the other four
  hold: they are the rules the change must **not** break.  All five
  hold now.

  ```
    PASS  the window stays where it is while the answer is written
    PASS  the window goes to the end when the answer is complete
    PASS  the operator keeps his place while the answer grows
    PASS  the operator moves the window himself while the answer is written
    PASS  a new document opens at its beginning
  ```
