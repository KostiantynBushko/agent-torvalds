# The data analysis toolkit is a module

**Branch:** `refactor/data-analysis-toolkit-module`
**Base:** `master` at `1f44d7e`
**Scope:** the tenth and **last** toolkit of the "every toolkit is a module
under `toolkits/`" refactoring.

`agent_data_analysis_toolkit.py` leaves the project root and becomes
`toolkits/data-analysis-toolkit/`.  The file is split in two — the reusable
library half and the LlamaIndex adapter — the package joins the alias shim,
the two call sites are updated, and the test suite moves with the toolkit and
grows.

---

## 1. The state before

The data analysis toolkit was the **last** loose module at the project root:

```
agent_data_analysis_toolkit.py     # 13 operations + get_all_tools()
tests/test_data_analysis_toolkit.py
```

Thirteen operations, one adapter, one suite.  It sat next to
`agent_cache_system.py` — the only other top-level `agent_*.py` module left,
and that one is a component, not a toolkit.

The file was already split *internally* — the operations at the top, the tool
registry at the bottom, under a `# Tool registry` header — so the shape of
the package was decided by the file itself.

---

## 2. The decision: split the file, do not just move it

The file carries two different things, and they have different dependencies:

| | Depends on | Needed by |
|---|---|---|
| the 13 operations | `pandas`, `numpy`, `os`, `logging` | anybody who wants to analyse a table |
| `get_all_tools()` | `llama_index.core.tools` | the agent |

So the split is the same as every other toolkit of the series:

| Path | Role |
|---|---|
| `toolkits/data-analysis-toolkit/operations.py` | the 13 operations and the module-level logger — the **library half** |
| `toolkits/data-analysis-toolkit/agent_data_analysis_toolkit.py` | the adapter — the only LlamaIndex-dependent module |
| `toolkits/data-analysis-toolkit/__init__.py` | the public API surface |
| `toolkits/data-analysis-toolkit/README.md`, `pyproject.toml`, `py.typed` | the documentation, the standalone distribution, the PEP 561 marker |
| `toolkits/data-analysis-toolkit/tests/` | the module-local tests |

### The library half is built on `pandas` and `numpy`

`pandas` is the data model — every operation works on a DataFrame — and
`numpy` is what the pivot table uses to infer the numeric columns.  The
reasoning is the same as for the Git toolkit (`pygit2`) and the Excel toolkit
(`openpyxl`): **a data analysis operation is a data analysis operation
whether or not an agent framework is installed**.  The layout contract pins
that exact set, so a new dependency cannot slip in unnoticed.

`openpyxl` is deliberately **not** a dependency of the library half.  It is
needed at *run time*, when pandas actually reads or writes a workbook, and
pandas declares it itself.  That distinction matters for the guard at the
call sites, and it is discussed below.

---

## 3. What changed

| Path | Change |
|------|--------|
| `toolkits/data-analysis-toolkit/operations.py` | **New.** The 13 analysis operations and the module-level logger — the library half.  No LlamaIndex import. |
| `toolkits/data-analysis-toolkit/agent_data_analysis_toolkit.py` | **New.** The adapter — the only LlamaIndex-dependent module.  It re-exports all 13 operations. |
| `toolkits/data-analysis-toolkit/__init__.py` | **New.** The public API surface and the code-level reference to the canonical alias. |
| `toolkits/data-analysis-toolkit/README.md`, `pyproject.toml`, `py.typed` | **New.** The module documentation, the standalone distribution (the adapter is the `agent` extra) and the PEP 561 marker. |
| `toolkits/data-analysis-toolkit/tests/test_operations.py` | **New** (moved from `tests/test_data_analysis_toolkit.py`).  Relative imports; extended from 39 to 44 tests. |
| `toolkits/data-analysis-toolkit/tests/test_package_layout.py` | **New.** The layout contract — 33 checks. |
| `toolkits/data-analysis-toolkit/tests/test_split_verification.py` | **New.** The test of the split-verification script — 17 tests, fourteen deliberate drifts. |
| `agent_data_analysis_toolkit.py` | **Deleted** at the project root.  Git tracked it as a rename to `toolkits/data-analysis-toolkit/operations.py`. |
| `tests/test_data_analysis_toolkit.py` | **Deleted** at the project root.  Git tracked it as a rename to the module-local test. |
| `toolkits/__init__.py` | The `data_analysis_toolkit` alias, the `_DATA_ANALYSIS_PACKAGE` / `_DATA_ANALYSIS_ALIAS` literals and the adapter in `_ADAPTER_MODULES`. |
| `agent_tool_retriever.py`, `agent_tool_selection.py` | The import path moved to the alias, behind a guard. |
| `pytest.ini` | `toolkits/data-analysis-toolkit/tests` added to `testpaths`. |
| `tests/test_toolkit_alias_contract.py` | The data analysis toolkit joined the alias contract — seven new rows. |
| `tests/test_logging_cli.py` | The logger now comes from `toolkits.data_analysis_toolkit.operations`; the two new modules joined the static inspection. |
| `requirements.txt` | `numpy` moved into the Excel & Data Analysis section, next to `pandas`, with a comment saying which toolkit uses it. |
| `README.md`, `CHANGELOG.md` | The documentation — the toolkit was not mentioned in the README at all before this change. |
| `investigate/data-analysis-toolkit-module/REPORT_data_analysis_toolkit_module.md` | **New.** What was implemented and why. |
| `investigate/data-analysis-toolkit-module/verify_split.py` | **New.** The mechanical check. |
| `investigate/data-analysis-toolkit-module/verify_optional_dependency.py` | **New.** The measurement of what a missing `pandas` does. |
| `investigate/data-analysis-toolkit-module/dump_tool_menu.py` | **New.** The tool menu dump. |

---

## 4. The three things this change is worth knowing about

### The toolkit is no longer able to take the agent down

Both call sites imported it **unguarded**, so a missing `pandas` — or a
broken install — raised straight out of the tool discovery and the agent did
not boot at all.

This was measured on both trees, with `pandas` blocked at the import
machinery:

```
master:  THE RETRIEVER RAISED: ImportError('pandas is blocked: pandas')
branch:  retriever tools  : 142
         selection tools  : 142
         analysis tools   : 0
```

The *tools* did not change — the thirteen operations still report a failure
as a message string and never raise — but the agent around them is no longer
hostage to a data-science stack it may not need.

### The guard here is the ordinary one

`except ImportError`, not the database toolkit's wider `except Exception`.
The reason is the same reason `openpyxl` is not a dependency of the library
half: the data analysis toolkit has **no import-time state**.  Its only
import-time failure is a missing `pandas` or `numpy`, and that is an
`ImportError`.  A missing `openpyxl` is not one of them — pandas raises it
at *call* time, inside the operation, where it is caught and reported like
every other failure.

The layout contract checks that the guard is not widened by accident, because
a wider guard would hide a real problem.

### The error contract is pinned now

The suite that came with the toolkit covered the happy paths and a failure
path for every operation.  What was added is a *systematic* check of the
contract the toolkit is built on: **a failure is reported, never raised**.
Every operation is called with a missing file and has to return a message
string that names the operation that failed — the model reads that message,
and an agent that cannot tell which of the thirteen operations failed has to
guess.

---

## 5. One import did not move, and that is deliberate

The original imported `json` and never used it: nothing in the thirteen
operations touches the `json` module.  The library half drops it rather than
carrying an unused import along — the same decision the Windows toolkit
made for its unused `os` import.

The check pins that difference instead of ignoring it.  The dependency sets
of the original and the library half are allowed to differ by **exactly**
`{"json", "llama_index"}` — the first because the import was unused, the
second because it moved to the adapter.  Any other difference is a failure,
so a dependency that quietly appeared or vanished cannot slip in.

---

## 6. The split was checked mechanically

`investigate/data-analysis-toolkit-module/verify_split.py` compares the
*committed* original with the new files, by AST:

* the thirteen operation names, their order, their signatures, their
  docstrings and their bodies;
* the thirteen tool names, their order and their descriptions;
* the LlamaIndex boundary — the library half must not import it, the adapter
  must;
* the module-level logger;
* the dependency profile, and the exact difference from the original;
* the `pandas` and the `numpy` import statements, one by one.

The original is **found, not assumed**: a named ref that still carries the
file, and otherwise the parent of the commit that deleted it — so the check
also works in a CI checkout with a detached HEAD.

The check is itself a **test**
(`toolkits/data-analysis-toolkit/tests/test_split_verification.py`), driven
with fourteen deliberate drifts.  A check that has never failed proves
nothing.

---

## 7. The tool menu is unchanged

The menu was dumped from `master` and from the branch and the two are
byte-identical:

```
master: 155 tools, md5 db58a70628cfdc6d12faf17d91f159f1
branch: 155 tools, md5 db58a70628cfdc6d12faf17d91f159f1
```

**Verifying the change**

```bash
self-development/.venv/bin/python -m pytest self-development/toolkits/data-analysis-toolkit/tests -q
self-development/.venv/bin/python self-development/investigate/data-analysis-toolkit-module/verify_split.py
self-development/.venv/bin/python self-development/investigate/data-analysis-toolkit-module/verify_optional_dependency.py
self-development/.venv/bin/python self-development/scripts/ci_test_gate.py
```

94 passed, the split is behaviour-neutral, the agent still boots without
`pandas`, and the CI gate reports **no new failure** (40 known failures,
0 new, 0 fixed).  The baseline was **not** rewritten — the data analysis
toolkit had no known failures of its own.

---

## 8. One CI run was red, and it was a flake

The first CI run of the branch failed with **one** new failure:

```
tests/test_tui_input_reader.py::TestInputReaderInPseudoTerminal::test_burst_of_keystrokes_is_fully_captured
```

That test is **timing-dependent**: it forks a pseudo-terminal, sleeps 1.5
seconds, writes nine characters, sleeps another 0.5 seconds, writes ENTER,
and then requires every one of the ten keys to have been captured by a
child process that polls the terminal every 20 milliseconds.  Under load,
the child may not be scheduled in time.

It is also **untouched by this change** — it drives
`components/tui.input_reader`, and nothing in `components/` or in the TUI
is part of this diff.  It passed ten times out of ten locally, and the
**re-run of the very same commit passed**.

The baseline was deliberately **not** rewritten to include it.  The
baseline is a list of failures that are *known* — a test that fails
intermittently is not one, and putting it there would mask a real
regression the next time it fails for a different reason.

---

## 9. What is left

Nothing.  Every toolkit is a module under `toolkits/`, and the project root
holds no loose toolkit any more: `agent_cache_system.py` is a component, not
a toolkit, and the `agent-torvalds*.py` files are the orchestrators.
