# The Linux toolkit is a module

**Branch:** `refactor/linux-toolkit-module`
**Base:** `master` (`64a8061`)

The Linux toolkit was a single loose module at the project root,
`agent_linux_toolkit.py`, next to the other `agent_*.py` files, while the
features that were already modules lived in folders under `toolkits/`.
This change makes it a module like the rest of the series.

```
agent_linux_toolkit.py  ->  toolkits/linux-toolkit/operations.py
                     ->  toolkits/linux-toolkit/agent_linux_toolkit.py
```

---

## 1. The state before

The toolkit carried six operations and one adapter in one file:

| Operation | What it does |
|-----------|--------------|
| `execute_shell_command(command, timeout=30, cwd=None, shell=True)` | run a shell command |
| `execute_multiple_commands(commands, timeout=30)` | run commands in sequence |
| `parse_command_output(output)` | split output into lines and metadata |
| `get_system_info()` | OS, CPU, memory and disk, through the shell |
| `check_file_permissions(filepath)` | permissions, owner and group |
| `run_command_with_env(command, env_vars)` | run a command with extra environment |

plus `get_all_tools()`, which turned them into LlamaIndex `FunctionTool`
objects.

### The call sites

Four places imported it:

| File | Import |
|------|--------|
| `agent-torvalds.py` | `from agent_linux_toolkit import get_all_tools as get_linux_tools` |
| `agent-torvalds-mw.py` | `from agent_linux_toolkit import get_all_tools as get_linux_tools` |
| `agent_tool_retriever.py` | `from agent_linux_toolkit import get_all_tools as _get_linux` |
| `agent_tool_selection.py` | `from agent_linux_toolkit import get_all_tools as _get_linux` |

**All four imported it unguarded.**  A broken or missing toolkit was a
failed boot.  Every toolkit already under `toolkits/` was imported
behind a guard, so the Linux toolkit was one of the last holdouts of the
old arrangement.

---

## 2. The decision: split the file, do not just move it

The file carried two different things, and the series has one rule for
that: the **library half** carries no LlamaIndex import, the **adapter**
is the one module that knows about the agent framework.

| Module | Role | LlamaIndex | Third party |
|--------|------|------------|-------------|
| `operations.py` | the 6 shell and system operations | **no** | **none** |
| `agent_linux_toolkit.py` | the adapter — `get_all_tools()` | **yes** | `llama-index-core` |

Like the OS toolkit, this toolkit's library half is built on the
**standard library only** — `subprocess`, `os`, `logging` and `typing`.
There is no third-party dependency at all, so the shell operations are
usable in any Python that exists.

The split was not a preference here: the toolkit had a test suite, and
the suite could only keep testing the operations if they were reachable
without the agent framework.

### The error contract

Every operation **reports** a failure; none of them raises.  A command
that exits non-zero comes back with `success: False` and the error text
in `stderr`; a command that times out comes back with `returncode: -1`.
The suite now pins that contract for all six operations.

---

## 3. The hyphen, and the alias

The directory name contains a hyphen, which is not a valid Python
identifier, so the package is reached through the alias that
`toolkits/__init__.py` registers:

```python
from toolkits.linux_toolkit import execute_shell_command
from toolkits.linux_toolkit.agent_linux_toolkit import get_all_tools
```

The alias is a **literal** in the shim, not a computed one:

```python
_LINUX_PACKAGE = "toolkits.linux-toolkit"
_LINUX_ALIAS = "toolkits.linux_toolkit"
```

That matters for the same reason it matters for the other six: a
computed alias is invisible to every *static* reader — an IDE, an import
resolver, a linter, a packaging tool — and such a tool reports it as a
missing reference.

The adapter is a submodule of the package, so it is **not** published
eagerly: publishing a submodule means importing it, and `import toolkits`
must never pull LlamaIndex into the process.

---

## 4. The call sites

All four now import the adapter **behind a guard**, like every other
toolkit under `toolkits/`:

```python
try:
    from toolkits.linux_toolkit.agent_linux_toolkit import (
        get_all_tools as get_linux_tools,
    )
except ImportError:  # pragma: no cover - the toolkit is optional

    def get_linux_tools() -> list:
        """The Linux toolkit is unavailable - expose no tools."""
        return []
```

The Linux toolkit goes from **mandatory** to **optional**.  A missing or
broken toolkit now degrades to "no tools", never to a failed boot.

That was checked, not assumed: with the toolkit made unimportable, both
orchestrators still boot, `get_linux_tools()` returns no tools, and the
OS toolkit is unaffected.

---

## 5. The suite moved with the toolkit — and grew

The toolkit already had a test suite, and it moved with it, so
"behaviour-neutral" was something the suite could show.

| | Before | After |
|---|--------|-------|
| `tests/test_linux_toolkit.py` | 11 tests | — |
| `toolkits/linux-toolkit/tests/test_operations.py` | — | 36 tests |
| `toolkits/linux-toolkit/tests/test_package_layout.py` | — | 31 tests |
| `toolkits/linux-toolkit/tests/test_split_verification.py` | — | 11 tests |
| **Total** | **11** | **78** |

The eleven original tests moved unchanged (apart from the import, which
became relative).  The new ones cover the error contract of every
operation, and three of them pin behaviour that is easy to get wrong:

* **`shell=False` treats the command as a *path*.**  Without a shell the
  string is the program to run, not a line for a shell to interpret.
  A test that assumed `execute_shell_command("echo direct", shell=False)`
  would print `direct` failed — it tries to execute a file called
  `echo direct`.
* **A command that writes to `stderr` may still have succeeded.**  The
  exit code decides; `stderr` is only the text the command wrote.
* **`run_command_with_env` has a hard-coded 30 second timeout.**  It
  takes no timeout parameter, unlike `execute_shell_command`.

These are not bugs the move introduced; they are the behaviour the
toolkit has always had, and the suite now documents it instead of
leaving it to be discovered.

---

## 6. What was added, not just moved

### The layout contract

`toolkits/linux-toolkit/tests/test_package_layout.py` — 31 checks:

* the flat layout (the toolkit directory *is* the package; no `src/`
  level, no nested package directory, no stray modules);
* the relative imports (an absolute import of a hyphenated package is a
  `SyntaxError`);
* the alias resolves to this very package, and to one module object;
* the LlamaIndex boundary — the adapter is the single, named exception,
  and importing the library does not pull LlamaIndex in;
* the dependency profile of the library half — the standard library, and
  nothing else;
* the six-tool surface: the names, their order, and the `System`
  category every one of them carries;
* the old root module and the old root test file are gone;
* no call site imports `agent_linux_toolkit` any more, and every one of
  them imports the adapter behind a guard.

### The split was checked mechanically, not by eye

`investigate/linux-toolkit-module/verify_split.py` compares the
**committed original** (taken from git) with the two new files, by AST:

* the six operation names, their order, their signatures, their
  docstrings and their bodies;
* the six tool names, their order and their descriptions;
* the LlamaIndex import is in the adapter only.

The reference the original is taken from is **found, not assumed** — see
section 9.

```
$ python investigate/linux-toolkit-module/verify_split.py

original            : master:agent_linux_toolkit.py
library half        : toolkits/linux-toolkit/operations.py
agent adapter       : toolkits/linux-toolkit/agent_linux_toolkit.py

operations compared : 6
tools compared      : 6

The split is behaviour-neutral.
```

**And the check was itself tested.**  A check that has never failed
proves nothing, so
`toolkits/linux-toolkit/tests/test_split_verification.py` drives it with
seven deliberate drifts — the kind of change a reader would not reliably
notice:

| Drift | Caught by |
|-------|-----------|
| a tool description reworded from "for" to "on" | the description comparison |
| a parameter default changed from 30 to 60 | the signature comparison |
| a dropped docstring | the docstring comparison |
| a changed function body | the body comparison |
| two operations swapped | the order comparison |
| a LlamaIndex import in the library half | the boundary check |
| a tool missing from the adapter | the tool-surface comparison |

All seven are caught, and the real sources produce no failures at all.

### The packaging

`toolkits/linux-toolkit/pyproject.toml` makes the toolkit a standalone
distribution: `pip install ./toolkits/linux-toolkit` installs the library
half, which depends on the standard library and on nothing else, and
`linux-toolkit[agent]` adds the adapter.

---

## 7. Verification

```bash
self-development/.venv/bin/python -m pytest self-development/toolkits/linux-toolkit/tests -q
self-development/.venv/bin/python self-development/scripts/ci_test_gate.py
```

**78 passed** in the toolkit suite (36 operations + 31 layout contract +
11 split verification), and the CI gate reports **no new failure** —
40 known failures, 0 new, 0 fixed.

The alias contract is green as well: **58 passed** (it was 51; the
Linux toolkit joined it with seven new rows).

### The tool menu is unchanged

The tool menu was dumped from `master` and from the branch — the names,
their order and their descriptions — and the two are **byte-identical**.
The move changed where the tools live, not what the model sees.

### The pre-existing duplicate

`get_system_info` is defined **twice**: once by the Linux toolkit, once
by the OS toolkit.  Both are loaded into the same process on Linux, so
the tool menu carries the name twice.

That duplicate is **pre-existing** — it is on `master` too, with the
same count — and the move neither created nor changed it.  The two
functions are genuinely different:

| | Linux toolkit | OS toolkit |
|---|---|---|
| how | shells out to `uname`, `lscpu`, `free`, `df` | reads `platform` directly |
| returns | the output of those commands, as strings | a dictionary of structured fields |

The package `__init__.py` says so, so the next reader does not have to
rediscover it.

---

## 8. One thing that changed on purpose

The logger's name moved from `agent_linux_toolkit` to
`toolkits.linux-toolkit.operations`, because that is what
`logging.getLogger(__name__)` does when the module moves.  The adapter
re-exports it, so the toolkit still logs through one logger, as the
single module did.

`tests/test_logging_cli.py` was updated to import the new logger, and
the two new modules joined the static inspection that looks for a
duplicate `basicConfig` call.

---

## 9. Three things found along the way

**A pre-existing `SyntaxWarning` in `agent-torvalds.py`.**  Line 759
holds:

```python
help="Disable runtime HITL toggle commands (\toggle-hitl, \hitl-status, etc.)",
```

`\t` and `\h` are not valid escape sequences in a non-raw string.  The
layout contract parses that file to check its imports, and the warning
surfaced there — the test now suppresses it.

**The bug itself is left alone on purpose.**  This is a
behaviour-neutral refactoring, and the point of the series is that
nothing moves.  The fix belongs in its own change, where the change is
the change.  It is recorded here so it is not lost.

**A stale line in the project structure.**  The README's directory
listing still names `tests/test_os_toolkit.py`, which the OS toolkit
moved into its package in the previous change of the series.  The
Linux toolkit's own line is correct this time — `tests/test_linux_toolkit.py`
is gone from the listing, because the suite moved into the package.

**The check only worked on a developer's machine.**  The split
verification asked git for the original by name — `git show
master:agent_linux_toolkit.py` — and the test that drove it hard-coded
the same name.  That works in a clone, and it fails in CI: a CI
checkout is a **detached HEAD** of the merge commit with a shallow
history, so there is no `master` branch to ask.  The build went red with
ten new failures — `fatal: invalid object name 'master'` — and every one
of them was in the check, not in the toolkit.

The fix is to stop assuming a name.  The original is *the file as it was
committed before it was deleted*, so the check now asks git where that
still lives:

1. a named ref that still carries the file — `master`, `origin/master`,
   `main`, `origin/main`;
2. otherwise, the **parent of the commit that deleted it** — which is
   exactly the state the file was in when it was removed.

The second step is what makes the check work in CI, and it is the more
precise definition anyway: it names the original by the deletion, not
by a branch that may or may not exist.  The CI workflow now checks the
repository out with `fetch-depth: 0`, because a shallow history cannot
answer the question at all.

The lesson is the one the series keeps learning: **a check that only
runs where the author sits is not a check.**  It ran green on the
developer's machine for the whole of the change, and the build found it
in two minutes.

---

## 10. What is left

The remaining loose toolkits are `agent_windows_toolkit.py`,
`agent_apt_toolkit.py`, `agent_db_toolkit.py`, `agent_xlsx_toolkit.py`
and `agent_data_analysis_toolkit.py`.

The Windows one is the interesting case: it is the **counterpart** of
this toolkit, with the same six operations and the same names, and it is
loaded on Windows where the Linux toolkit is not.  The two are mutually
exclusive today, which is why the tool menu carries one `get_system_info`
from them rather than two.
