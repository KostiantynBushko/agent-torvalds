# The math toolkit is a module

**Date:** 2026-10-26
**Branch:** `refactor/math-toolkit-module`
**Base:** `master` (PR #38)
**Request:** *"most of the toolkit are located under torvalds root folder but some
of them, like MikroTik-RouterOS and shodan-toolkit are designed as a separate
modules and located under toolkits folder. So We need make a refactoring so that
all toolkits are designed as a modules and are located under toolkits folder. We
will start with the agent_math_toolkit and will process one by one. One PR per
toolkit."*

---

## 1. The state before

The repository had two shapes of toolkit side by side:

```
agent-torvalds/
├── agent_mikrotik_toolkit.py      ← a module under toolkits/
├── agent_shodan_toolkit.py        ← a module under toolkits/
├── agent_math_toolkit.py          ← a loose file at the root
├── agent_git_toolkit.py
├── agent_os_toolkit.py
└── … 18 more
```

The two that had already been converted are **folders**: the reusable library
half, the adapter that exposes it to the agent, and the tests, side by side.
The math toolkit was still a single file at the project root.

This is the first of the remaining toolkits, so the shape decided here becomes
the template for the rest.

---

## 2. The decision: split the file, do not just move it

The naive move is `git mv agent_math_toolkit.py toolkits/math-toolkit/`. That
would put a *file* in a folder that is supposed to *be* a package, and it would
carry the existing problem along: `agent_math_toolkit.py` mixed two different
things.

| | What it is | LlamaIndex |
|---|---|---|
| `operations.py` | the mathematics — arithmetic, trigonometry, logarithms, the RPN evaluator | **no** |
| `agent_math_toolkit.py` | the adapter — wraps the operations as `FunctionTool`s | **yes** |

The split is the same one the MikroTik and the Shodan toolkit already use, and
the rule behind it is the one their layout contracts enforce:

> The adapter is the only module of a toolkit that depends on LlamaIndex; the
> reusable library half around it does not.

Keeping the mathematics in a LlamaIndex-free module buys three things:

* the maths is usable as a plain library — `from toolkits.math_toolkit import
  add` — with no agent framework in the process;
* it is testable without LlamaIndex at all;
* `import toolkits` cannot drag the agent framework into the process, which is
  a contract the alias test already checks for the other two toolkits.

**The behaviour did not change.**  Every function, every docstring and the
error contract (an invalid input is reported as a readable *string*, not raised)
were moved verbatim.  The seven known failures of the math toolkit are the same
seven, with the same names — only the path of the file changed.

---

## 3. The hyphen, and the alias

`toolkits/math-toolkit/` contains a hyphen, so — exactly like the other two —
no `import` statement can name it:

```python
>>> from toolkits.math-toolkit import add
  File "<string>", line 1
    from toolkits.math-toolkit import add
                       ^
SyntaxError: invalid syntax
```

`toolkits/__init__.py` already carries the shim that solves this.  The math
toolkit joined it:

```
toolkits/math-toolkit/  ->  toolkits.math_toolkit
```

so the canonical import paths are:

```python
from toolkits.math_toolkit import add, multiply, evaluate_rpn     # the library half
from toolkits.math_toolkit.agent_math_toolkit import get_all_tools  # the adapter
```

The shim publishes every submodule of a toolkit under its alias — and
*publishing* means *importing*.  The adapter is therefore excluded from the
eager publication (`_ADAPTER_MODULES`), so the library half stays usable
without LlamaIndex, and the adapter is imported on demand, by whoever needs it.

### One module, not two

The alias has to cover the submodules as well.  Without that,
`toolkits.math_toolkit.operations` and `toolkits.math-toolkit.operations` would
be two different module objects with two different sets of functions, and an
`isinstance` check across that boundary would silently fail.

The adapter therefore pulls the library in with a **relative** import
(`from . import ...`), and the layout contract checks that the two really are
one object:

```python
def test_the_adapter_and_the_library_share_one_module_object():
    adapter = importlib.import_module("toolkits.math_toolkit.agent_math_toolkit")
    operations = importlib.import_module("toolkits.math-toolkit.operations")
    assert adapter.add is operations.add
```

---

## 4. The call sites

Six places imported the toolkit.  All of them moved to the alias path:

| File | Before | After |
|---|---|---|
| `agent-torvalds.py` | `from agent_math_toolkit import get_all_tools` | guarded import of the adapter |
| `agent-torvalds-mw.py` | the same | the same |
| `agent-torvalds-cpp.py` | `from agent_math_toolkit import *` | `from toolkits.math_toolkit.agent_math_toolkit import *` |
| `agent_tool_retriever.py` | `from agent_math_toolkit import get_all_tools` | guarded import of the adapter |
| `agent_tool_selection.py` | the same | the same |
| `test_callback_events_debug.py` | the same | the same |

**The imports are now guarded.**  A toolkit under `toolkits/` is optional by
definition — that is the contract the two converted toolkits already follow:

```python
try:
    from toolkits.math_toolkit.agent_math_toolkit import (
        get_all_tools as get_math_tools,
    )
except ImportError:  # pragma: no cover - the toolkit is optional

    def get_math_tools() -> list:
        """The math toolkit is unavailable - expose no tools."""
        return []
```

The math toolkit cannot actually fail to import — its library half is pure
standard library — but the guard costs nothing and keeps the rule uniform: a
missing or broken toolkit degrades to *no tools*, never to a failed boot.

---

## 5. The tests moved with the toolkit

`tests/test_math_toolkit.py` became
`toolkits/math-toolkit/tests/test_operations.py`.  Two things changed with it:

* the `sys.path.insert(...)` hack and the absolute import were replaced by a
  relative import (`from ..operations import ...`);
* the module-local `tests/` directory has **no** `__init__.py`, and the suite
  runs with `--import-mode=importlib` (set in `pytest.ini` through `addopts`).
  With an `__init__.py` in there, pytest resolves the test module against the
  *root* `tests` package, the relative imports fail with *"attempted relative
  import beyond top-level package"*, and a basename collision aborts the whole
  collection.

`pytest.ini` lists the new directory in `testpaths`, so a bare `pytest` run
collects it.

### The baseline moved with it

The seven known failures are recorded in `tests/ci_baseline.txt` by node id,
and a node id contains the path of the file.  The seven ids were rewritten to
the new path — the *same* seven tests, not a new set:

```
toolkits/math-toolkit/tests/test_operations.py::TestBasicArithmetic::test_divide_by_zero
```

The gate confirms it: **40 known failures before, 40 after, 0 new, 0 fixed.**

---

## 6. What was added, not just moved

| Path | What it is |
|---|---|
| `toolkits/math-toolkit/__init__.py` | the public API surface, and the code-level reference to the canonical alias |
| `toolkits/math-toolkit/operations.py` | the library half — the mathematics |
| `toolkits/math-toolkit/agent_math_toolkit.py` | the adapter — the only LlamaIndex-dependent module |
| `toolkits/math-toolkit/py.typed` | the PEP 561 marker |
| `toolkits/math-toolkit/README.md` | the module documentation |
| `toolkits/math-toolkit/pyproject.toml` | the standalone distribution |
| `toolkits/math-toolkit/tests/test_operations.py` | the moved test suite |
| `toolkits/math-toolkit/tests/test_package_layout.py` | the layout contract — 18 new checks |

The distribution has **no** third-party dependency: the library half is pure
standard library, and the adapter is an extra (`math-toolkit[agent]`).  That is
the split expressed in the packaging metadata as well.

### The layout contract

`test_package_layout.py` pins the rules that the other two toolkits already
enforce, so the math toolkit cannot drift back:

* the directory is the package — no `src/` level, no nested package directory;
* the module-local `tests/` directory has no `__init__.py`;
* the package uses relative imports only;
* the library half imports **no** LlamaIndex, and the adapter is the single
  named exception (the check is AST-based, so prose in a docstring does not
  trip it);
* importing the package — or the alias shim — does not pull LlamaIndex into the
  process (checked in a subprocess);
* the toolkit no longer sits at the project root;
* the alias resolves to the same package object, and the adapter shares one
  module object with the library.

---

## 7. Verification

```
toolkits/math-toolkit/tests      46 passed, 7 failed  (the 7 known failures)
toolkits/MikroTik-RouterOS/tests  unchanged
toolkits/shodan-toolkit/tests     unchanged
tests/test_toolkit_alias_contract.py  unchanged count, 3 new rows for math
```

The full suite: **1672 passed, 39 failed, 1 error, 9 skipped** — and the CI
gate reports **0 new failures** against the 40 recorded in the baseline.

The behaviour of the toolkit itself was checked separately, against the old
module:

* the adapter exposes the same **14** tools, with the same descriptions;
* `add(2, 3) == 5`, `evaluate_rpn("3 4 + 2 *") == 14`;
* the error contract is unchanged — `divide(1, 0)` still returns
  `"Error: Division by zero"`;
* both orchestrators import and expose 14 math tools.

---

## 8. What is left for the next toolkits

The shape decided here is the template for the remaining ones:

1. the toolkit becomes a folder under `toolkits/`, hyphenated, with the alias
   registered in `toolkits/__init__.py`;
2. the file is **split** — the library half (no LlamaIndex) and the adapter
   (LlamaIndex) — instead of being moved as one piece;
3. the tests move with the toolkit, with relative imports and no `__init__.py`;
4. the baseline node ids are rewritten for the moved file;
5. the call sites are guarded, like the other toolkits.

The remaining loose toolkits are `agent_git_toolkit.py`,
`agent_github_toolkit.py`, `agent_os_toolkit.py`, `agent_linux_toolkit.py`,
`agent_windows_toolkit.py`, `agent_apt_toolkit.py`, `agent_db_toolkit.py`,
`agent_xlsx_toolkit.py` and `agent_data_analysis_toolkit.py` — one PR each.
