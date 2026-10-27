# The database toolkit is a module

**Status:** implemented and verified on `refactor/db-toolkit-module`,
based on `master` (`eb4e479`).

The database toolkit was a single loose module at the project root,
`agent_db_toolkit.py`, while the toolkits that had already moved live in
folders under `toolkits/`.  This change makes it a module like the rest
of the series — the **eighth** toolkit of the "every toolkit is a
module" refactoring, and the first one whose library half is **not**
dependency-free.

---

## 1. The state before

| Path | What it was |
|------|-------------|
| `agent_db_toolkit.py` | the whole toolkit: the configuration loader, the two SQL operations, the `get_all_tools` adapter and the module-level logger |
| `tests/` | **no** test suite for the toolkit at all |

The **five** call sites imported it **unguarded**:

| Call site | Import |
|-----------|--------|
| `agent-torvalds.py` | `from agent_db_toolkit import get_all_tools as get_db_tools` |
| `agent-torvalds-mw.py` | `from agent_db_toolkit import get_all_tools as get_db_tools` |
| `agent_tool_retriever.py` | `from agent_db_toolkit import get_all_tools as _get_db` |
| `agent_tool_selection.py` | `from agent_db_toolkit import get_all_tools as _get_db` |
| `agent-torvalds-cpp.py` | `from agent_db_toolkit import *` |

So the toolkit was **mandatory**: a missing or broken one took the whole
agent down at import time.  Every other toolkit under `toolkits/` is
optional, and this change makes this one optional too.

---

## 2. The decision: split the file, do not just move it

The file carried two things — the operations and the LlamaIndex adapter —
so it is split in two:

| Path | What it is |
|------|------------|
| `toolkits/db-toolkit/operations.py` | the configuration loader, the two SQL operations and the logger — the **library half** |
| `toolkits/db-toolkit/agent_db_toolkit.py` | the **adapter** — the only LlamaIndex-dependent module |
| `toolkits/db-toolkit/__init__.py` | the public API surface |
| `toolkits/db-toolkit/py.typed` | the PEP 561 marker |
| `toolkits/db-toolkit/pyproject.toml` | the standalone distribution |
| `toolkits/db-toolkit/README.md` | the module documentation |
| `toolkits/db-toolkit/tests/` | the module-local tests |

The split is the point.  `operations.py` carries **no** LlamaIndex
import, so the SQL operations stay usable — and testable — as a plain
Python library.  The adapter is the one module that knows about the
agent framework, and it is imported on demand.  Importing the toolkit
therefore never pulls LlamaIndex into the process.

### The library half is the first one with a real dependency profile

The OS, the Linux and the Windows toolkits are built on the standard
library alone; their layout contracts pin that exact set.  The database
toolkit cannot be: it needs `psycopg2` and `mysql-connector-python` —
the two drivers — and `PyYAML`, which reads the configuration file.  The
layout contract pins the exact set, so a new dependency cannot slip in
unnoticed — and a driver cannot quietly disappear either.

### The one thing that is *not* a plain library operation

The configuration is read **at import time**:

```python
# Load config once at import time (lazy reload available via _load_config)
_cfg = _load_config()
```

That is behaviour, and it moved with the operations: the operations read
the module-level `_cfg`, so a caller that imports the module and then
calls an operation sees exactly what it always saw.  The mechanical check
pins the statement, not only the function that produces the value.

The consequence is that importing the library half needs
`db_toolkit_config.yaml` in the working directory — and that it raises
`FileNotFoundError` without it, exactly as the original module did.  The
file is committed at the repository root, so a fresh checkout can import
the toolkit.

---

## 3. The hyphen, and the alias

The directory name contains a hyphen, so the package cannot be reached
with a plain `import` statement.  `toolkits/__init__.py` registers the
alias `toolkits.db_toolkit` for it, next to the other nine, and the
canonical path is spelled out as a **literal** — a computed alias is
invisible to every static reader, and a static reader that cannot see
the import path reports a missing reference.

The alias shim imports the package eagerly, and the package reads its
configuration while it does.  A missing configuration file therefore
means the alias is not registered — the toolkit is simply absent, which
is the degradation the optional-toolkit model asks for.

---

## 4. The call sites, and the guard that had to be wider

All five call sites import the adapter **behind a guard** now.  For
every other toolkit the guard is `except ImportError`; for this one it
cannot be:

```python
try:
    from toolkits.db_toolkit.agent_db_toolkit import (
        get_all_tools as get_db_tools,
    )
except Exception:  # pragma: no cover - the toolkit is optional
    def get_db_tools() -> list:
        """The DB toolkit is unavailable - expose no tools."""
        return []
```

The toolkit can fail to import for two reasons: the drivers are not
installed (`ImportError`), and its configuration file is missing or
malformed (`FileNotFoundError` / `yaml.YAMLError`) — it reads the file
when it is imported.  A guard that only caught `ImportError` would turn
a missing configuration file into a failed boot, which is the opposite
of what an optional toolkit should do.

**The behaviour of the tools did not change.**  A failing query is still
*reported* as a message string and never raised; the operations were
moved verbatim.

The C++ orchestrator star-imported the loose module, and it star-imports
the adapter now — behind the same guard.  It uses none of the names the
old star import leaked (`yaml`, `psycopg2`, `mysql`); it imports
`logging` explicitly, and it does so *after* the star imports, so the
leak never reached it.  The adapter declares `__all__` in any case, so
the leak is gone.

---

## 5. The toolkit had no test suite, so it got one

The math, the Git, the OS, the Linux, the APT and the Windows toolkits
carried a suite into their package; the GitHub one did not, and it got
one with the move.  The database toolkit is in the same position.

`toolkits/db-toolkit/tests/test_operations.py` — **37 tests** that pin
the behaviour of the two operations: the shape of the result (a list of
dictionaries, keyed by the column names of the cursor), the empty list
for a query that produces no result set, the connection parameters that
reach the driver, the closed cursor and connection, and the error
contract — a failure is *reported* as a string, never raised.

The suite is **offline**: it drives the operations through a stubbed
`psycopg2` and a stubbed `mysql.connector`, so it needs no database
server.  That matters — the build that has to stay green runs in CI,
where no database is waiting.

Two files came with it:

| File | What it holds |
|------|---------------|
| `tests/test_package_layout.py` | the layout contract — 34 checks |
| `tests/test_split_verification.py` | the test of the mechanical check — 14 tests, eleven deliberate drifts |

### The configuration file and the test session

The library half reads its configuration **at import time**, so the
file has to be in the working directory *before* anything imports the
toolkit — and the alias shim imports every toolkit eagerly, so that is
before the first test module is even collected.

The file is committed at the repository root and every run of the suite
happens there, so this is normally a no-op.  A run from another
directory would otherwise fail to collect the toolkit's tests, so a
**root `conftest.py`** puts the file in place when it is missing and
removes it again when the session ends.  The toolkit's own
`tests/conftest.py` does the same for a session started inside the
toolkit directory, where the root one is not loaded at all.

---

## 6. The mechanical check

`investigate/db-toolkit-module/verify_split.py` compares the
*committed* original with the new files, by AST, and fails on:

* the operation names, their order, their signatures, their docstrings
  and their bodies;
* the tool names, their order and their descriptions;
* the LlamaIndex import — in the adapter, and nowhere else;
* the module-level logger;
* the import-time configuration load;
* the dependency profile of the library half.

The original is **found, not assumed**: a named ref that still carries
the file, and otherwise the parent of the commit that deleted it.  A
hard-coded `master` would have been a trap — a CI checkout is a
detached HEAD without that branch, and the check would have failed
there for a reason that has nothing to do with the split.

The check is **itself a test**, driven with eleven deliberate drifts —
a reworded tool description, a dropped docstring, a changed body, two
operations swapped, a LlamaIndex import in the library half, a tool
that went missing, an operation that went missing, a lost module-level
logger, a lost import-time configuration load, a lost dependency and an
unexpected one.  All eleven are caught.  A check that has never failed
proves nothing.

### The packaging

`pyproject.toml` describes a standalone distribution that depends on
the two drivers and on `PyYAML`; the adapter is the `agent` extra.  The
package directory is the package, and the mapping from the directory to
the package name is spelled out, because the directory's name contains a
hyphen.

---

## 7. Verification

```bash
self-development/.venv/bin/python -m pytest self-development/toolkits/db-toolkit/tests -q
self-development/.venv/bin/python self-development/scripts/ci_test_gate.py
```

**85 passed**, and the CI gate reports **no new failure**: 40 known
failures, 0 new, 0 fixed.  The baseline did not need rewriting — the
database toolkit had no known failures of its own, so no known failure
changed path.

The mechanical check:

```bash
self-development/.venv/bin/python self-development/investigate/db-toolkit-module/verify_split.py
```

reports *The split is behaviour-neutral.* — 3 operations compared, 2
tools compared.

### The tool menu is unchanged

The tool menu was dumped from `master` and from the branch — the names,
their order and their descriptions — and the two are **byte-identical**
(155 tools).  The move changed where the tools live, not what the model
sees.

### One small drive-by

The alias contract listed the canonical path of every toolkit, but the
Windows toolkit had never been added to the three literal checks — the
rows that pin `toolkits.windows_toolkit` as a *literal* in the shim.
The database toolkit joined them, and so did the Windows one: the
contract is now complete for all ten toolkits.

---

## 8. Two things worth knowing

**The toolkit is now optional, and the guard is wider than everywhere
else.**  Every other toolkit under `toolkits/` fails to import with an
`ImportError` when it is broken; this one can also fail with a
`FileNotFoundError`, because it reads its configuration when it is
imported.  The guard catches that, and the comment at every call site
says why.  Without it, a missing `db_toolkit_config.yaml` would still
take the whole agent down — which is what it did before this change.

**The operations are unchanged, but they are now *reachable*.**  Before
this change there was no test suite at all, so nothing guarded the error
contract of the toolkit — the "a failure is reported, never raised"
promise, and the shape of the result.  It is now pinned by 37 tests,
offline, with no database server anywhere near them.
