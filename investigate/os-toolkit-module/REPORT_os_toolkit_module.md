# The OS toolkit is a module

The fourth toolkit of the "every toolkit is a module under `toolkits/`"
refactoring, and the one the series had been putting off.

`agent_os_toolkit.py` was the toolkit the orchestrator leans on: eleven
file-system operations that the agent calls in almost every session. It
was also the last toolkit that was still *mandatory* — every other one had
already moved under `toolkits/`, where a missing or broken toolkit
degrades to "no tools" instead of a failed boot.

---

## 1. The state before

```
agent_os_toolkit.py      14 KB   11 operations + get_all_tools()
tests/test_os_toolkit.py  5 KB   17 tests
```

A single loose module at the project root, next to the other
`agent_*.py` files, while the features that were already modules lived in
folders under `toolkits/`.

Unlike the GitHub toolkit, this one **arrived with a test suite** — 17
tests in `tests/test_os_toolkit.py`. That matters: "behaviour-neutral"
was something the existing suite could *show*, so the move was
verifiable rather than merely asserted.

And unlike every toolkit of the series, its library half would have **no
third-party dependency at all**.

### The call sites

| File | What it imported | Note |
|------|------------------|------|
| `agent-torvalds.py` | `from agent_os_toolkit import get_all_tools as get_os_tools` | unguarded, top level |
| `agent-torvalds-mw.py` | same | unguarded, top level |
| `agent_tool_retriever.py` | `from agent_os_toolkit import get_all_tools as _get_os` | unguarded, in a function |
| `agent_tool_selection.py` | `from agent_os_toolkit import get_all_tools as _get_os` | unguarded, in a function |
| `agent-torvalds-cpp.py` | `from agent_os_toolkit import *` | **a star import** |
| `test_callback_events_debug.py` | `from agent_os_toolkit import get_all_tools as get_os_tools` | unguarded, top level |
| `tests/test_os_toolkit.py` | `from agent_os_toolkit import (pwd, ls, ...)` | the suite |
| `tests/test_logging_cli.py` | `from agent_os_toolkit import logger as os_logger` | and the module list |

### The "C++ orchestrator"

The series' notes called this the toolkit "the C++ orchestrator leans on".
That turned out to be a false alarm, and it was worth checking rather than
assuming.

There is **no compiled binary** in the repository. `agent-torvalds-cpp.py`
is Python; the "cpp" is the `llama-cpp-python` binding behind its LLM:

```python
from llama_index.llms.llama_cpp import LlamaCPP
```

`find` over the whole tree for `*.cpp`, `*.hpp`, `*.cc` and `*.h` returns
only files inside `.venv/`. So there was no compiled artefact that a
renamed module could have broken.

What *was* real is the **star import**. `from agent_os_toolkit import *`
brings in every public name of the module — and the old module had **no
`__all__`**, so that included the modules it had imported: `os`, `shutil`,
`logging`, `Path`, `platform` and `FunctionTool`.

---

## 2. The decision: split the file, do not just move it

The file carried two different things, exactly as the GitHub one did:

| New path | Role | LlamaIndex | Third party |
|---|---|---|---|
| `toolkits/os-toolkit/operations.py` | the 11 file-system operations — the **library half** | **no** | **none** |
| `toolkits/os-toolkit/agent_os_toolkit.py` | the **adapter** (`get_all_tools`) | yes — the only one | `llama-index-core` |

`operations.py` is built on `os`, `shutil`, `pathlib` and `platform` —
the standard library, and nothing else. It is the first toolkit of the
series whose reusable half is **dependency-free**, which is worth keeping
true; the layout contract now enforces it.

### The error contract

Every operation **reports** a failure; none of them raises.

```python
>>> ls("/nonexistent")
'Directory not found: /nonexistent'
>>> rm("/nonexistent")
'Path not found: /nonexistent'
>>> read_file("/nonexistent")
'Error reading file: [Errno 2] No such file or directory: ...'
>>> get_system_info()          # on a platform that raises
{'error': '...'}
```

This is the contract the agent relies on: a tool that raises breaks the
turn, a tool that reports lets the model recover. It was preserved
exactly, and the extended suite now pins it for all eleven operations.

---

## 3. The hyphen, and the alias

The directory is `toolkits/os-toolkit/`, reached through the alias
`toolkits.os_toolkit` that `toolkits/__init__.py` registers — as a
*literal*, next to the other five:

```python
from toolkits.os_toolkit import pwd, ls, mkdir, read_file, write_file
from toolkits.os_toolkit.agent_os_toolkit import get_all_tools
```

The alias shim was extended in the same way as for the GitHub toolkit:
the name in `_ALIAS_NAMES`, the adapter in `_ADAPTER_MODULES`, the
package/alias constants, and the registration call.

---

## 4. The call sites

All six were updated, and the four that imported the toolkit
**unguarded** now import it behind a guard, like every other toolkit
under `toolkits/`:

```python
try:
    from toolkits.os_toolkit.agent_os_toolkit import (
        get_all_tools as get_os_tools,
    )
except ImportError:  # pragma: no cover - the toolkit is optional

    def get_os_tools() -> list:
        """The OS toolkit is unavailable - expose no tools."""
        return []
```

This is a **real change in the degradation contract**, and it is the same
one the GitHub, Git and math moves made: the OS toolkit goes from
*mandatory* to *optional*. A broken OS toolkit now costs the agent its
file access instead of the whole boot. That is the trade the series made
consistently, and the OS toolkit was the last one still outside it.

### The star import

`agent-torvalds-cpp.py` now reads:

```python
from toolkits.os_toolkit.agent_os_toolkit import *
```

The adapter re-exports the eleven operations, so the file's
`tools=[..., pwd, ls, touch, check_path_exists, mkdir, rm, cp, mv,
read_file, write_file, get_system_info]` resolves unchanged.

The adapter also declares `__all__`, so the star import no longer leaks
`os`, `shutil`, `platform` and `Path` into that module's namespace. That
is a deliberate narrowing, and it is safe: `agent-torvalds-cpp.py` uses
none of them — `asyncio`, `Console` and `logging` are all imported
explicitly. The layout contract pins the narrowing so it cannot drift
back unnoticed.

---

## 5. The suite moved with the toolkit — and grew

The 17 tests moved to `toolkits/os-toolkit/tests/test_operations.py` and
were extended to 41, covering:

- the **error contract** of all eleven operations — a failure is reported,
  never raised;
- `touch` creating missing parent directories, and leaving an existing
  file's content alone;
- `cp` of a directory tree, and `rm` of a directory removing its
  contents;
- `write_file` overwriting;
- the full key set of `get_system_info` — the docstring promises ten
  keys, and that is part of the contract.

One test was made **robust**: `test_ls_current_dir` used to assert
`"README.md" in ls(".")`, which only held when pytest was started from
the repository root. It now computes the root from `__file__`.

The suite is hermetic: every test works in a temporary directory, and
none of them touches anything outside it.

---

## 6. What was added, not just moved

### The layout contract

`toolkits/os-toolkit/tests/test_package_layout.py` — 28 checks: the flat
layout, the relative imports, the alias, the LlamaIndex boundary, the
dependency profile of the library half and the eleven-tool surface.

Two of them are specific to this toolkit:

```python
ALLOWED_LIBRARY_DEPENDENCIES = frozenset()
```

The library half may not reach for anything but the standard library, and
the tool *order* is pinned — the order is what the model sees first.

### The split was checked mechanically, not by eye

`investigate/os-toolkit-module/verify_split.py` compares the new files
against the **committed** original (`git show HEAD:agent_os_toolkit.py`),
by AST:

- the eleven operation names, their order, their signatures, their
  docstrings and their **bodies**, compared one by one;
- the eleven tool names, their order and their **descriptions**;
- the LlamaIndex boundary.

The check was itself tested against three deliberate drifts — a reworded
description, a changed parameter default, and a dropped docstring — and
caught all three. A check that has never failed proves nothing.

### The packaging

`pyproject.toml` for a standalone install (`pip install
./toolkits/os-toolkit`). The distribution depends on the standard library
and on nothing else; the adapter is an extra (`os-toolkit[agent]`).

---

## 7. Verification

```
toolkits/os-toolkit/tests    69 passed (41 operations + 28 layout contract)
alias contract                51 passed   (was 44)
logging CLI test              28 passed   (unchanged)
full suite                    1889 passed, 9 skipped, 39 failed + 1 error
CI gate                       40 known -> 40 actual, 0 new, 0 fixed
```

The 39 failures and the 1 error are the **40 known failures** of the
baseline — the same 40, in the same files, with the same names.

The suite grew by 59 tests: 69 from the new toolkit suite, minus the 17
that moved with it, plus the 7 the alias contract gained.

`tests/ci_baseline.txt` is **unchanged** — the OS toolkit was not in it,
because it had no known failures. That is the cleanest possible
confirmation that the move was behaviour-neutral.

### The tool menu is unchanged

The startup tool selection menu is the observable surface of the whole
project, so it was compared before and after:

| | before | after |
|---|---|---|
| total tools | 155 | 155 |
| distinct names | 154 | 154 |
| duplicates | `get_system_info` (OS + Windows) | `get_system_info` (OS + Windows) |

All eleven OS tools are in the menu, in the same order, under the same
**Operating System** category.

### The pre-existing duplicate

`get_system_info` is defined by **both** the OS toolkit and the Windows
toolkit, and both are loaded into one process. The duplicate is
**pre-existing** — it is on `master` too, with the same count of 155 —
so the move did not create it and did not change it. It remains a
hazard for the rest of the series: a future tool with that name in
either toolkit would silently replace the other.

---

## 8. One thing that changed on purpose

The logger's name changed from `agent_os_toolkit` to
`toolkits.os-toolkit.operations`.

That is not a choice — it is what `logging.getLogger(__name__)` does when
the module moves. The math, Git and GitHub moves changed theirs the same
way, and the logging test only asserts that the name is non-empty, so
nothing depends on the old spelling.

The adapter re-exports the operations' logger, so the **whole** toolkit
still logs through one logger, exactly as the single module did.

---

## 9. What is left

Six loose toolkits remain at the project root:

| Toolkit | Note |
|---------|------|
| `agent_apt_toolkit.py` | **4 known failures** — the baseline holds node ids, so its paths must be rewritten in the same commit, or the gate reports the old ids as fixed and the new ones as new |
| `agent_linux_toolkit.py` | |
| `agent_windows_toolkit.py` | defines the second `get_system_info` |
| `agent_db_toolkit.py` | has an `__all__`-less module; its star import in the cpp file is the one that still leaks |
| `agent_xlsx_toolkit.py` | |
| `agent_data_analysis_toolkit.py` | |

The OS toolkit was the one the series deferred, because it was the one
the orchestrator leans on. It is done, and the deferral was not
necessary: there was no compiled binary, and the star import turned out
to be the only thing that needed care.
