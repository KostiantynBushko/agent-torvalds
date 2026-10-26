# The Windows toolkit is a module

**Status:** implemented and verified on `refactor/windows-toolkit-module`,
based on `master` (`02270ed`).

The Windows PowerShell toolkit was a single loose module at the project
root, `agent_windows_toolkit.py`, while the toolkits that had already
moved live in folders under `toolkits/`.  This change makes it a module
like the rest of the series — the **seventh** toolkit of the "every
toolkit is a module" refactoring, and the last of the **Linux/Windows**
pair.

---

## 1. The state before

| Path | What it was |
|------|-------------|
| `agent_windows_toolkit.py` | the whole toolkit: six operations, the private `_get_powershell_command` helper, the `get_all_tools` adapter and the module-level logger |
| `tests/` | **no** test suite for the toolkit at all |

The four call sites imported it **unguarded**:

| Call site | Import |
|-----------|--------|
| `agent-torvalds.py` | `from agent_windows_toolkit import get_all_tools as get_windows_tools` |
| `agent-torvalds-mw.py` | `from agent_windows_toolkit import get_all_tools as get_windows_tools` |
| `agent_tool_retriever.py` | `from agent_windows_toolkit import get_all_tools as _get_windows` |
| `agent_tool_selection.py` | `from agent_windows_toolkit import get_all_tools as _get_windows` |

So the toolkit was **mandatory**: a missing or broken one took the whole
agent down at import time.  Every other toolkit under `toolkits/` is
optional, and this change makes this one optional too.

---

## 2. The decision: split the file, do not just move it

The file carried two things — the operations and the LlamaIndex adapter —
so it is split in two:

| Path | What it is |
|------|------------|
| `toolkits/windows-toolkit/operations.py` | the six operations, the private helper and the logger — the **library half** |
| `toolkits/windows-toolkit/agent_windows_toolkit.py` | the **adapter** — the only LlamaIndex-dependent module |
| `toolkits/windows-toolkit/__init__.py` | the public API surface |
| `toolkits/windows-toolkit/py.typed` | the PEP 561 marker |
| `toolkits/windows-toolkit/pyproject.toml` | the standalone distribution |
| `toolkits/windows-toolkit/README.md` | the module documentation |
| `toolkits/windows-toolkit/tests/` | the module-local tests |

The split is the point.  `operations.py` carries **no** LlamaIndex
import, so the PowerShell operations stay usable — and testable — as a
plain Python library.  The adapter is the one module that knows about the
agent framework, and it is imported on demand.  Importing the toolkit
therefore never pulls LlamaIndex into the process.

The library half is built on the **standard library alone** —
`subprocess`, `logging` and `typing` — like the OS and the Linux
toolkits before it.  The PowerShell operations work in any Python that
exists.

### The one thing that did not move verbatim

The original imported `os` and never used it: the environment variables
of `run_command_with_env` are passed to the shell as **PowerShell
assignments** (`$env:NAME="value"`), not through `os.environ`.  The
unused import was dropped rather than carried along.  Nothing else about
the module header changed.

---

## 3. The hyphen, and the alias

The directory name contains a hyphen, so the package cannot be reached
with a plain `import` statement.  `toolkits/__init__.py` registers the
alias `toolkits.windows_toolkit` for it, next to the other eight, and
the canonical path is spelled out as a **literal** — a computed alias is
invisible to every static reader, and a static reader that cannot see
the import path reports a missing reference.

```python
from toolkits.windows_toolkit import execute_shell_command          # the library
from toolkits.windows_toolkit.agent_windows_toolkit import get_all_tools  # the adapter
```

The adapter is a **submodule** of the package and is **not** published
eagerly, so `import toolkits` never imports LlamaIndex.

---

## 4. The call sites

All four now import the adapter **behind a guard**, through the alias:

```python
try:
    from toolkits.windows_toolkit.agent_windows_toolkit import (
        get_all_tools as get_windows_tools,
    )
except ImportError:  # pragma: no cover - the toolkit is optional

    def get_windows_tools() -> list:
        """The Windows toolkit is unavailable - expose no tools."""
        return []
```

A missing or broken toolkit now degrades to "no tools" instead of a
failed boot.  The toolkit went from **mandatory** to **optional**.

---

## 5. The suite is new

The toolkit had **no** test suite before this change.  The one that came
with it has **87 tests** in three files:

| File | Tests | What it holds |
|------|-------|----------------|
| `test_operations.py` | 45 | the six operations and the private helper |
| `test_package_layout.py` | 30 | the layout contract |
| `test_split_verification.py` | 12 | the test of the mechanical check |

The operations suite is **platform-independent**: it drives the
operations through a stubbed `subprocess.run`, so it needs neither
Windows nor a PowerShell installation.  That matters — the build that
has to stay green runs on Linux, and a suite that could only run on
Windows would never guard anything.

---

## 6. What was added, not just moved

### The layout contract

`toolkits/windows-toolkit/tests/test_package_layout.py` pins the rules
the series has established: the flat layout (the toolkit directory *is*
the package), the relative imports, the canonical alias, the LlamaIndex
boundary, the dependency profile of the library half, the six-tool
surface and its order, and the fact that no call site imports the old
module name any more.

### The split was checked mechanically, not by eye

`investigate/windows-toolkit-module/verify_split.py` compares the
**committed original** with the new files, by AST:

* the operation names, their order, their signatures, their docstrings
  and their bodies;
* the tool names, their order and their descriptions;
* the LlamaIndex import — in the adapter, and nowhere else;
* the module-level logger.

The original is **found, not assumed**: a named ref that still carries
the file, and otherwise the parent of the commit that deleted it.  A
hard-coded `master` would have been a trap — a CI checkout is a
detached HEAD without that branch, and the check would have failed
there for a reason that has nothing to do with the split.

The check is **itself a test**, driven with nine deliberate drifts — a
reworded tool description, a changed parameter default, a dropped
docstring, a changed body, two operations swapped, a LlamaIndex import
in the library half, a tool that went missing, an operation that went
missing, and a lost module-level logger.  All nine are caught.  A check
that has never failed proves nothing.

### The packaging

`pyproject.toml` describes a standalone distribution with **no**
dependency; the adapter is the `agent` extra.  The package directory is
the package, and the mapping from the directory to the package name is
spelled out, because the directory's name contains a hyphen.

---

## 7. Verification

```bash
self-development/.venv/bin/python -m pytest self-development/toolkits/windows-toolkit/tests -q
self-development/.venv/bin/python self-development/scripts/ci_test_gate.py
```

**87 passed**, and the CI gate reports **no new failure**: 40 known
failures, 0 new, 0 fixed.  The baseline did not need rewriting — the
Windows toolkit had no known failures of its own, so no known failure
changed path.

The mechanical check:

```bash
self-development/.venv/bin/python self-development/investigate/windows-toolkit-module/verify_split.py
```

reports *The split is behaviour-neutral.* — 7 operations compared, 6
tools compared.

### The tool menu is unchanged

The tool menu was dumped from `master` and from the branch — the names,
their order and their descriptions — and the two are **byte-identical**
(155 tools).  The move changed where the tools live, not what the model
sees.

The same dump was taken with the platform **simulated** as Windows, so
that the Windows toolkit's own six tools are in it: 155 tools on both
sides, byte-identical.

### The pre-existing duplicate

`get_system_info` is defined by **three** toolkits: the Windows one,
the Linux one and the OS one.  The three are genuinely different
functions:

| | Windows toolkit | Linux toolkit | OS toolkit |
|---|---|---|---|
| how | PowerShell cmdlets | `uname`, `lscpu`, `free`, `df` | reads `platform` directly |
| returns | the output of those commands, as strings | the output of those commands, as strings | a dictionary of structured fields |

The Windows toolkit is loaded **only on Windows** and the Linux one
**only on Linux**, so at most one of the three is ever in the menu.  The
duplicate on Linux is **pre-existing** — it is on `master` too, with the
same count — and the move neither creates nor changes it.

---

## 8. Two things worth knowing

**The toolkit is now optional, and it was the last mandatory one that
did not have to be.**  `agent_db_toolkit` is still a loose module at the
project root and is still imported unguarded; it is the next one of the
series.

**The operations are unchanged, but they are now *reachable*.**  Before
this change there was no test suite at all, so nothing guarded the error
contract of the toolkit — the "a failure is reported, never raised"
promise.  It is now pinned by 45 tests, on a platform that is not
Windows.
