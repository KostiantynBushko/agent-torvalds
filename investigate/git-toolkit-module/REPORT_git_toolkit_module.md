# The Git toolkit is a module

**Date:** 2026-10-26
**Branch:** `refactor/git-toolkit-module`
**Base:** `master`
**Status:** implemented, verified — awaiting the operator's approval to commit and push

The second toolkit of the "every toolkit is a module" refactoring.  The
math toolkit (PR #39) established the shape; this one applies it to the
Git toolkit, which is the first toolkit with a **real third-party
dependency** — and that turns out to be the interesting part.

---

## 1. The state before

`agent_git_toolkit.py` sat at the project root, 1835 lines, next to 19
other loose `agent_*.py` modules.  It carried two different things in one
file:

* the **Git operations** — 27 functions over `pygit2`, the Python binding
  to `libgit2`; and
* the **LlamaIndex adapter** — `get_all_tools()`, which wrapped those 27
  functions into `FunctionTool` objects.

It was, in other words, exactly the file the math toolkit was: a library
and its adapter, welded together.

The toolkit had **no known failures**.  `tests/test_git_toolkit.py` had
56 tests, all passing, and the CI baseline did not mention it.  That is
worth stating plainly, because it means this refactoring is a pure
no-op on behaviour — there is no error contract to preserve *or* to
accidentally change.

### The call sites

| File | Import | Guarded? |
|---|---|---|
| `agent-torvalds.py` | `from agent_git_toolkit import get_all_tools as get_git_tools` | no |
| `agent-torvalds-mw.py` | same | no |
| `agent-torvalds-cpp.py` | `from agent_git_toolkit import *` | no |
| `agent_tool_retriever.py` | `from agent_git_toolkit import get_all_tools as _get_git` | no |
| `agent_tool_selection.py` | `from agent_git_toolkit import get_all_tools as _get_git` | no |
| `test_callback_events_debug.py` | `from agent_git_toolkit import get_all_tools as get_git_tools` | no |
| `tests/test_logging_cli.py` | `from agent_git_toolkit import logger as git_logger` | n/a |
| `tests/test_git_toolkit.py` | 24 functions | n/a |

Not one of them was guarded.  The math toolkit's six call sites had
already been converted to guarded imports; the Git toolkit's had not.

---

## 2. The decision: split the file, do not just move it

Same rule as the math toolkit, and for the same reason — the two halves
have different dependency profiles, and only one of them is allowed to
know about the agent framework.

```
agent_git_toolkit.py  ->  toolkits/git-toolkit/operations.py
                       ->  toolkits/git-toolkit/agent_git_toolkit.py
```

### The difference from the math toolkit: the dependency profile

The math toolkit's library half is **pure standard library**.  The Git
toolkit's is not — it is built on `pygit2`.  So the split is not "no
dependency versus one dependency"; it is:

| Module | Third-party dependencies | LlamaIndex |
|---|---|---|
| `operations.py` | `pygit2` | **no** |
| `agent_git_toolkit.py` | `llama-index-core` | **yes** |

`pygit2` belongs to the **library half**.  A Git operation is a Git
operation whether or not an agent framework is installed, and the binding
to `libgit2` is not a LlamaIndex concern.  What must not leak into the
library half is the *agent* dependency — the one that decides how a tool
is described, wrapped and dispatched.

This is worth a sentence because the naive reading of "a toolkit has no
dependencies" is false here, and a layout contract that asserted it
would have been wrong.  The contract therefore pins the *exact* set:
the library half may import `pygit2` and the standard library, and
nothing else.

### The error contract

Unchanged, and worth recording because it is a real design decision
rather than an accident:

* the `bool`-returning tools return `False`;
* the `dict`-returning tools return `{"success": False, "error": "..."}`;
* the `str`-returning tools return `"Error: ..."`.

No tool raises.  The model gets a message it can reason about instead of
a traceback.  All of it moved verbatim.

One exception already existed and was left alone: `git_update_changelog`
catches broadly and returns `False`.  A changelog that cannot be written
is not worth a traceback.

---

## 3. The hyphen, and the alias

The directory is `toolkits/git-toolkit/`, reached through the alias
`toolkits.git_toolkit` that `toolkits/__init__.py` registers — as a
literal, next to the other three:

```python
from toolkits.git_toolkit import git_get_status, git_commit        # the library
from toolkits.git_toolkit.agent_git_toolkit import get_all_tools    # the adapter
```

The alias shim gained three things:

* `git_toolkit` in `_ALIAS_NAMES`;
* `agent_git_toolkit` in `_ADAPTER_MODULES` — the adapter is never
  published eagerly, so `import toolkits` still does not pull LlamaIndex
  into the process;
* the `_GIT_PACKAGE` / `_GIT_ALIAS` constants and the registration call.

### One module, not two

The adapter pulls the library in with a **relative** import, so
`toolkits.git_toolkit.operations` and `toolkits.git-toolkit.operations`
are the same module object.  There is never a second copy of
`operations.py` in memory, and the functions the adapter exposes are the
very same objects the library defines.

### The star import

`agent-torvalds-cpp.py` imports the toolkit with a **star**:

```python
from toolkits.git_toolkit.agent_git_toolkit import *
```

and then names `git_get_latest_commit` and `git_init_repo` directly in
its tool list.  A star import only binds the names in the module's
namespace, so the adapter has to re-export all 27 functions — not just
the ones `get_all_tools()` uses.  It does, and the layout contract
pins the count, so the star cannot silently lose a tool.

---

## 4. The call sites

All six now import the adapter **behind a guard**, like the other
toolkits under `toolkits/`: a missing or broken toolkit degrades to "no
tools", never to a failed boot.

```python
try:
    from toolkits.git_toolkit.agent_git_toolkit import (
        get_all_tools as get_git_tools,
    )
except ImportError:  # pragma: no cover - the toolkit is optional

    def get_git_tools() -> list:
        """The Git toolkit is unavailable - expose no tools."""
        return []
```

Two of them needed a different shape:

* `agent_tool_retriever.py` and `agent_tool_selection.py` are inside a
  function, so the guard wraps the import *and* the call — the import
  alone would not help, because the call is what raises.
* `agent-torvalds-cpp.py` uses a star import and cannot be guarded that
  way; it points at the new path directly.

`tests/test_logging_cli.py` needed its own update: it imported
`logger` from the old module, and it lists the toolkit modules whose
source is scanned for a duplicate `logging.basicConfig()`.  Both now
name the two new modules:

```python
from toolkits.git_toolkit.operations import logger as git_logger
```

```python
TOOLKIT_MODULES = [
    ...
    "toolkits.git_toolkit.operations",
    "toolkits.git_toolkit.agent_git_toolkit",
]
```

---

## 5. The tests moved with the toolkit

`tests/test_git_toolkit.py` → `toolkits/git-toolkit/tests/test_operations.py`,
switched to relative imports:

```python
from ..operations import (
    git_init_repo,
    git_add_files,
    ...
)
```

The `sys.path.insert(...)` dance the old file needed is gone — the
package is imported through the alias, so the relative import resolves
on its own.

`pytest.ini` gained `toolkits/git-toolkit/tests` in `testpaths`.

### The baseline moved with it

The Git toolkit had **no** known failures, so `tests/ci_baseline.txt` did
not change.  That is the point: the baseline is a list of node ids, and
the Git toolkit's node ids were never in it.  A refactoring that had
*added* a failure would have shown up in the gate as a new failure; a
refactoring that had *changed a path* of a known failure would have
shown up as a new failure **and** a fixed one.  Neither happened.

---

## 6. What was added, not just moved

### The layout contract

`toolkits/git-toolkit/tests/test_package_layout.py` is new — **24
checks** that pin:

* the flat layout (the toolkit directory *is* the package, no `src/`
  level, no nested package directory);
* that the old root module and the old root test file are gone;
* the relative-import rule — no module may import the package by its
  absolute name, because the hyphen makes that a `SyntaxError`;
* the alias: it is a literal, it resolves to *this* package, and the
  package carries a code-level reference to its canonical name;
* the **LlamaIndex boundary** — the library half has no LlamaIndex
  import, the adapter is the one that has it, and importing the package
  does not pull LlamaIndex into the process (checked in a subprocess);
* that the adapter and the library share one module object;
* the **dependency profile** of the library half — `pygit2` and the
  standard library, and nothing else;
* the **tool surface** — all 27 functions are exported by the package,
  re-exported by the adapter, and `get_all_tools()` returns exactly
  those 27.

That last group is new for this toolkit.  The math contract pinned the
shape; this one also pins the *content*, because 27 functions that
silently vanish one at a time would not fail any other test.

### A catch worth recording

The contract caught a violation of itself.  The first version of the
LlamaIndex scan used `PKG_DIR.rglob("*.py")`, which reaches into the
`tests/` directory — and the test that asserts the adapter returns
`FunctionTool` objects has to *name* `FunctionTool`.  The scan tripped
over the test that checks the rule.

The fix was not to weaken the rule but to scope it correctly: the rule is
about the *modules of the toolkit*, so the scan now skips
`PKG_TESTS`.  The math toolkit's contract has the same shape and would
trip the same way if its tests ever named `llama_index` — worth
knowing before the next toolkit copies it.

### The packaging

`pyproject.toml` for a standalone install:

```bash
pip install ./toolkits/git-toolkit          # pygit2
pip install './toolkits/git-toolkit[agent]' # and the adapter
```

`README.md` with the module reference, and `py.typed`.

---

## 7. Verification

```
toolkits/git-toolkit/tests       80 passed  (56 operations + 24 layout contract)
toolkits/math-toolkit/tests      46 passed, 7 known failures
full suite                       1703 passed, 9 skipped
CI gate                          40 known → 40 actual, 0 new, 0 fixed
```

The gate is the number that matters: **no new failure, and no fixed
one** — which is what a pure refactoring has to report.  The 40 known
failures are the same 40, in the same files, with the same names.

The alias contract suite now covers the Git toolkit, and
`import toolkits` still does not import LlamaIndex.

The startup tool selection menu finds the 27 Git tools under the
**Version Control** category — 40 in that category in total, the other
13 being the GitHub toolkit's.

---

## 8. What is left for the next toolkits

The remaining eight loose toolkits:

| Toolkit | Note |
|---|---|
| `agent_github_toolkit.py` | uses `requests`; its 13 tools share the Version Control category |
| `agent_os_toolkit.py` | the biggest one — it is the toolkit the C++ orchestrator leans on |
| `agent_linux_toolkit.py` | |
| `agent_windows_toolkit.py` | |
| `agent_apt_toolkit.py` | **has 4 known failures** — the baseline path will have to be rewritten |
| `agent_db_toolkit.py` | |
| `agent_xlsx_toolkit.py` | |
| `agent_data_analysis_toolkit.py` | |

The template is settled: split the file, keep the library half free of
LlamaIndex, register the alias, guard the call sites, move the tests
inside the package, and add the layout contract.

Two things the next ones will hit that this one did not:

* **a toolkit with known failures** (`agent_apt_toolkit.py`) — the
  baseline holds *node ids*, so the paths have to be rewritten in the
  same commit, or the gate reports the old ids as fixed and the new ones
  as new;
* **a toolkit with a heavier dependency** (`agent_data_analysis_toolkit.py`
  — pandas and NumPy) — the dependency profile of the library half has to
  be pinned explicitly, the way this contract does it.
