# The panes of the sidebar hide — and the layout survives it

**The operator reported on 2026-11-23** that hiding both panes of the
sidebar crashed the TUI:

> *it happens when we hide both "Agent Telemetry & State" and "Workflow &
> Tool Progress" or vice versa*

with the stack of the crash:

```
  File ".../rich/console.py", line 1339, in render
    for render_output in iter_render:
  File ".../rich/layout.py", line 401, in __rich_console__
    render_map = self.render(console, options.update_dimensions(width, height))
  File ".../rich/console.py", line 240, in update_dimensions
    options = self.copy()
RecursionError: maximum recursion depth exceeded
```

This report is the evidence: what was measured, what the cause is, what
was built, and what the tests hold together.

---

## What was measured

The probe — `investigate/tui-hidden-panes/probe_hidden_panes.py` — drives
the **real** application with the keys the operator presses, and it draws
what the operator would see.

| the state | the document pane | the progress pane | the telemetry pane | the crash |
| :--- | :--- | :--- | :--- | :--- |
| both panes shown | 78 × 26 | 42 × 13 | 42 × 13 | — |
| the telemetry pane hidden | 78 × 26 | 42 × 26 | *not on the screen* | — |
| **both panes hidden** | — | — | — | **RecursionError** |
| the panes back | 78 × 26 | 42 × 13 | 42 × 13 | — |

The crash needs **both** panes to be hidden, and it needs nothing else:
the order of the two keys does not matter, and the crash happens on the
frame that follows the second key.

## The cause

Rich draws a layout in two steps, and the two steps do not agree with
each other when a partition has no visible child.

**The region map** — `Layout._make_region_map()` — walks the **visible**
children of every partition:

```python
children = layout.children          # the visible children only
for child_and_region in layout.splitter.divide(children, region):
```

**The drawing** — `Layout.render()` — then asks which partitions are
leaves, and a leaf is a partition with **no visible child**:

```python
layout_regions = [
    (layout, region)
    for layout, region in region_map.items()
    if not layout.children            # the visible children only
]
for layout, region in layout_regions:
    lines = render_lines(layout.renderable, ...)
```

**The content of a leaf** — `Layout.renderable` — is the partition itself
when the partition has children of its own:

```python
@property
def renderable(self) -> RenderableType:
    return self if self._children else self._renderable
```

Put the three together and the sidebar is the trap:

* the sidebar has **two children** — the progress pane and the telemetry
  pane;
* the operator hid **both** of them, so the sidebar has **no visible
  child** — and the sidebar is a leaf;
* the content of the sidebar is **the sidebar itself**, because it has
  children of its own.

So the layout draws the sidebar, the sidebar draws the layout, and the
drawing never ends.  The stack of the crash is the proof: it is the same
four frames, over and over:

```
console.py:1339  render
layout.py:401   __rich_console__
layout.py:389   render
console.py:1379  render_lines
```

**The rule Rich obeys, and the rule the TUI has to keep:**

> A partition that is **drawn** and has **children** must have at least
> one **visible** child.  A partition that is drawn and has no child at
> all is drawn as its own content, and that content is itself — an
> endless recursion.

A partition that is **hidden** is of no matter: Rich never walks it, and
it is never drawn.

## The fix

The sidebar leaves the layout together with its last pane
(`components/tui/layout_manager.py`, `apply_pane_visibility()`):

```python
def apply_pane_visibility(layout: Layout, hidden_panes: Iterable[str]) -> None:
    hidden = set(hidden_panes)

    for pane in SIDEBAR_PANES:
        layout[pane].visible = pane not in hidden

    # The sidebar keeps a pane on the screen, or it leaves the layout
    # with them: a partition without a visible child is drawn as
    # itself, and that is an endless recursion.
    layout["sidebar"].visible = any(
        pane not in hidden for pane in SIDEBAR_PANES
    )
```

The rule is applied from the state on **every frame**, so it is
idempotent and it survives a resize — the same rule §11.7 of
`docs/tui/hotkeys.md` already follows for a single pane.

**The space goes where it belongs.**  The sidebar has no pane left, so
it has no place on the screen: the document pane takes the whole of the
body — 120 cells of a terminal of 120 cells, instead of the 78 it takes
while the sidebar is there.

| the state | the document pane | the progress pane | the telemetry pane |
| :--- | :--- | :--- | :--- |
| both panes shown | 78 × 26 | 42 × 13 | 42 × 13 |
| one pane hidden | 78 × 26 | 42 × 26 | *not on the screen* |
| **both panes hidden** | **120 × 26** | *not on the screen* | *not on the screen* |
| the panes back | 78 × 26 | 42 × 13 | 42 × 13 |

## The evidence

**The tests** — `tests/test_tui_hidden_panes.py` — hold it together:

* the layout is drawn with every pane of the sidebar hidden (the
  regression the report is about);
* the sidebar leaves the layout with its last pane, and the document
  pane takes the whole of the body;
* the pane that is left takes the whole of the sidebar;
* **no drawn partition has children that are all hidden** — the
  invariant that keeps Rich from drawing a partition as itself;
* the panes come back, and the layout is the one it was;
* the application survives the two keys, **in any order**.

**The suite.**  The whole suite of the repository: `29 failed, 2098
passed` — the 29 failures are the known ones of
`tests/ci_baseline.txt`, and they are the same 29 the suite failed
with before the change (`29 failed, 2089 passed`).

**The probe.**  `python investigate/tui-hidden-panes/probe_hidden_panes.py`
draws the four states of the table above, and it shows the defect itself:
the last part of the probe builds the sidebar the way the code did
before the fix — the flag of the two panes, and nothing else — and it
catches the `RecursionError`.

## How to reverse it

The fix is one rule: **the sidebar is hidden when it has no pane left**.
It is written in one place — `apply_pane_visibility()` in
`components/tui/layout_manager.py` — and the application calls it from
`_apply_visibility()` on every frame.

To reverse it, drop the last three lines of `apply_pane_visibility()`:
the sidebar stays on the screen without a pane, and Rich draws the
sidebar as itself.  The crash comes back with them.
