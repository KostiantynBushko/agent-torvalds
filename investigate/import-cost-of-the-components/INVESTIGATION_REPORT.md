# The import of one module of the agent costs a second

**Status:** implemented, covered by the gate of the repository.
**Reported by:** the author, on 2026-11-20 — while the gate of PR #105 was red on three tests of the
command bar, and the reason was that the reader of the terminal was too slow to reach the terminal
before the keys were typed.

**Probe:** [`probe_import_cost.py`](probe_import_cost.py) — read-only.  It measures the cost of every
import in a fresh interpreter and prints the import tree.  It writes nothing and talks to no service.

---

## 1. The question

A program that wants **one** small module of the TUI — `components/tui/input_reader.py`, which needs
nothing but the standard library — pays for the whole of llama_index.

How much does it pay, and where does the time go?

## 2. The measurement

The budget is the one of the helper of the multiline input test: the parent types the keys into the
pseudo-terminal after **1.2 seconds**, whatever the reader in the child is doing.

**Before** — the packages import their modules eagerly:

```
1. The cost of every import, against the 1.2 s budget
------------------------------------------------------------------------
import                                   seconds  of the budget
components.tui.input_reader                0.976         81.4%
components.tui.input_text                  0.974         81.2%
components.tui.layout_manager              0.995         82.9%
components.tui.tui_app                     0.970         80.8%
components.tui.tool_selection_view         0.969         80.7%
components.tui                             0.964         80.3%
components                                 0.960         80.0%

2. What the reader of the terminal pays for
------------------------------------------------------------------------
   the import of the reader      : 0.974 s
   the budget before the keys    : 1.200 s
   the margin                    : 0.226 s

3. Where the time goes in the reader's import
------------------------------------------------------------------------
     cumulative  module
       0.829 s  components.tui.input_reader
       0.829 s  components.tui
       0.807 s  components
       0.774 s  components.event_consumer
       0.711 s  llama_index.core.workflow
       0.711 s  llama_index.core
       0.494 s  llama_index.core.indices
       0.426 s  llama_index.core.indices.composability.graph
       0.426 s  llama_index.core.indices.composability
       0.426 s  llama_index.core.indices.composability.graph
```

The reader of the terminal costs **0.976 s** — **81 % of the budget**, and the margin is **0.226 s**.

**After** — the packages import their modules when a name of them is asked for:

```
1. The cost of every import, against the 1.2 s budget
------------------------------------------------------------------------
import                                   seconds  of the budget
components.tui.input_reader                0.025          2.1%
components.tui.input_text                  0.021          1.8%
components.tui.layout_manager              0.058          4.8%
components.tui.tui_app                     0.264         22.0%
components.tui.tool_selection_view         0.880         73.4%
components.tui                             0.020          1.6%
components                                 0.020          1.6%

2. What the reader of the terminal pays for
------------------------------------------------------------------------
   the import of the reader      : 0.020 s
   the budget before the keys    : 1.200 s
   the margin                    : 1.180 s

3. Where the time goes in the reader's import
------------------------------------------------------------------------
     cumulative  module
       0.009 s  components.tui.input_reader
       0.009 s  components.tui
       0.009 s  components
       0.008 s  pkgutil
       0.005 s  typing
       0.003 s  re
       0.002 s  site
       0.001 s  re._compiler
       0.001 s  collections
       0.001 s  enum

4. The price of the tools of llama_index
------------------------------------------------------------------------
   the reader                    : 0.019 s
   the tools of llama_index      : 0.891 s
   the ratio                     : 46 to 1
```

The reader costs **0.025 s** — **2.1 % of the budget** — and the margin grows from **0.226 s** to
**1.180 s**.  The tools of llama_index still cost **0.891 s**, but only the programs that speak to
them pay it.

## 3. The root cause

The import tree says it plainly:

```
components.tui.input_reader
  components.tui            0.829 s
    components              0.807 s
      components.event_consumer   0.774 s
        llama_index.core.workflow  0.711 s
```

**`components/__init__.py` is the bottleneck, and not `components/tui/__init__.py`.**  The package of
the components imported all five of its modules when it was imported, and one of them —
`components/event_consumer.py` — carries the workflow engine of llama_index.  Every import of *any*
module of the agent paid that price: importing `components.tui.input_reader` runs the `components`
package first, and the `components` package runs llama_index first.

`components/tui/__init__.py` had the same shape, one level down: it imported the whole of the TUI,
and `components/tui/tool_selection_view.py` carries `llama_index.core.tools`.

The consequence was not only slow.  The reader of the terminal had **0.226 s** of margin against the
budget of the test helper, and on a loaded CI runner the import is slower than on a quiet machine.
The keys were typed into a terminal that was still in its old mode, and the terminal threw them away
— that is the red gate of PR #105, and the report of it is in the commit that fixed it.

## 4. The fix

Both packages import their modules **when a name of them is asked for**, and not before.  The
mechanism is the `__getattr__` of a module (PEP 562):

* `components/__init__.py` and `components/tui/__init__.py` carry a map of the name to the module
  that holds it, and `__getattr__` imports that module and returns the name.
* A module of the package is reachable as an attribute as well, so `components.tui.tui_app` still
  works.
* `__all__` is **byte-identical** to the one of the packages before, and every name in it resolves to
  **the very same object** the submodule carries — the public API of the packages did not change.
* `dir()` of a package carries the names that are not loaded yet.

Nothing in the five modules of `components/` and in the fourteen modules of `components/tui/` has a
side effect at import time — they set constants and loggers, and nothing else.  Deferring the import
therefore changes *when* the work happens and nothing else.

## 5. Verification

* **The gate of the repository is green:** 40 known failures, **0 new**, 0 fixed.
* **The public API is unchanged:** both `__all__` lists are byte-identical to the ones of `master`,
  and every name resolves to the same object as before.
* **The import patterns of the repository still work:** `from components import X`,
  `from components.tui import X`, `from components.tui import <module>`, `from components import
  <module>`, `import components.tui.<module>` and `from components.tui import *`.
* **The entry points still import:** `agent-torvalds.py` and `agent-torvalds-mw.py`.
* **The reader of the terminal pays 0.025 s** for its import, against 0.976 s before.

## 6. What is *not* in this change, and why

* **The modules of llama_index are not made lighter.**  `components/tui/tool_selection_view.py` still
  costs 0.891 s to import, and so does the workflow engine of `components/event_consumer.py`.  That
  is the price of llama_index, and it is paid by the programs that use it.  Making llama_index itself
  lighter is a change of a different size and a different risk, and nothing in this question needs
  it.
* **The import of the whole TUI is not made fast.**  `from components.tui.tui_app import TuiApp` still
  costs 0.264 s, because the application is the application.  The change makes the *small* modules
  cheap, which is what was asked for.
* **The race in the test helper is not closed by this change.**  It is closed by the handshake that
  waits for the reader to say that it is ready.  This change makes the race *unlikely* — the margin
  grows from 0.226 s to 1.180 s — and the handshake makes it *impossible*.  Both are wanted: a test
  that depends on a machine being fast is a test that will fail on a busy one.

## 7. The recommendation to the operator

Accept the change.  It costs nothing at run time — the modules are imported when they are needed, and
the programs that need them pay exactly what they paid before — and it gives the test suite back the
margin it had lost.

The measurement is cheap to repeat: the probe is read-only and takes a minute.
