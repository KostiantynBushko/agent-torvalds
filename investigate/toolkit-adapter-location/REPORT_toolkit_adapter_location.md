# The toolkits own their adapters

**Date:** 2026-10-25
**Branch:** `refactor/toolkit-adapter-location`
**Base:** `fix/toolkit-alias-reference` (PR #31)
**Request:** *"`agent_shodan_toolkit.py` must be under `toolkits/shodan-toolkit`;
`agent_mikrotik_toolkit.py` also must be placed under the appropriate folder
under the `toolkits` path."*

---

## 1. What was asked, and what it means

The two agent adapters sat at the project root, next to 20 other loose
`agent_*.py` modules:

```
agent-torvalds/
├── agent_mikrotik_toolkit.py      ← the adapter
├── agent_shodan_toolkit.py        ← the adapter
├── agent_git_toolkit.py
├── agent_os_toolkit.py
└── … 20 more
```

while the features they belong to lived in folders:

```
toolkits/
├── MikroTik-RouterOS/            ← the library half of the MikroTik feature
└── shodan-toolkit/               ← the library half of the Shodan feature
```

The request is to close that gap: a toolkit becomes **one folder** — the
library, the adapter that exposes it to the agent, and the tests.

The naive version of this move is three lines (`git mv` + fix the imports).
The two things that make it more than that are stated in §2 and §3.

---

## 2. The hyphen: why the adapter cannot simply be imported

`toolkits/MikroTik-RouterOS/` and `toolkits/shodan-toolkit/` contain a
hyphen. A hyphen is not a valid Python identifier, so **no `import`
statement can name them**:

```python
>>> from toolkits.MikroTik-RouterOS import MikroTikTarget
  File "<string>", line 1
    from toolkits.MikroTik-RouterOS import MikroTikTarget
                                  ^
SyntaxError: invalid syntax
```

`toolkits/__init__.py` already solves this: it registers a
valid-identifier alias for each toolkit — `toolkits.mikrotik_routeros` and
`toolkits.shodan_toolkit` — and the alias **is** the package object, not a
copy, so both spellings resolve to one module.

That gives the rule the move follows:

> **The adapter is a submodule of its toolkit package, and is reached
> through the package's alias.**

```python
from toolkits.mikrotik_routeros.agent_mikrotik_toolkit import get_all_tools
from toolkits.shodan_toolkit.agent_shodan_toolkit import get_all_tools
```

### 2.1 Where exactly the file goes

| Toolkit | Package directory | The adapter ends up at |
|---|---|---|
| MikroTik | `toolkits/MikroTik-RouterOS/` | `toolkits/MikroTik-RouterOS/agent_mikrotik_toolkit.py` |
| Shodan | `toolkits/shodan-toolkit/src/shodan_toolkit/` | `toolkits/shodan-toolkit/src/shodan_toolkit/agent_shodan_toolkit.py` |

The Shodan toolkit keeps its upstream `src/` layout, so its importable
package sits one level deeper. The adapter has to live **inside the
importable package** — that is what makes it a submodule, and a submodule
is what makes it importable by a plain `import` statement.

`toolkits/shodan-toolkit/agent_shodan_toolkit.py` (the toolkit root, one
level up) would also have satisfied "under `toolkits/shodan-toolkit/`", but
it is not inside a package: `toolkits.shodan-toolkit` is a namespace-package
portion, and a hyphenated dotted path cannot appear in an `import`
statement. Reaching it would need `importlib.import_module(...)` at every
call site — a string that no static reader can resolve, which is exactly
the defect PR #31 set out to remove.

The two placements are therefore not identical, but they follow one rule.

### 2.2 Verified, not assumed

```
A alias-submodule import        : OK CommandResult      # toolkits.mikrotik_routeros._probe
B alias-submodule import        : OK dict 16            # toolkits.shodan_toolkit._probe
D plain statement w/ hyphen      : FAIL SyntaxError      # from toolkits.shodan-toolkit.x import y
C importlib hyphenated root path : OK                    # the alternative, rejected
```

---

## 3. The contract that had to change: "the library has no LlamaIndex"

The MikroTik toolkit has a binding rule, **R1**:

> No LlamaIndex import anywhere under `toolkits/MikroTik-RouterOS/`.

The reason is a good one: the library half has to stay usable as a plain
library by any Python application, without the agent framework installed.

Moving the adapter into the package collides with the rule **as it was
written** — the adapter imports LlamaIndex, and it now sits inside the
package.

The rule was not thrown away. It was made **precise**, and the part that
actually matters was turned into a *behavioural* check:

| Before | After |
|---|---|
| R1: no LlamaIndex import anywhere under the package | R1: no LlamaIndex import under the **library half**; the adapter is the single, named exception |
| — | R1b: the adapter exists, and it is the one that imports LlamaIndex |
| — | R1c: `import toolkits` and `import toolkits.mikrotik_routeros` do **not** pull LlamaIndex into the process |
| — | R4: the adapter is reachable through the alias |

R1c is the check that carries the original intent. It was verified as
failing before the fix:

```
`import toolkits` -> llama_index loaded: True   ← the eager publication leaks it
`import toolkits` -> llama_index loaded: False  ← after the fix
```

The leak came from the alias shim: publishing a submodule means *importing*
it, and the shim published every submodule of a toolkit. The adapters are
now excluded from that eager publication and imported on demand.

### 3.1 The Shodan toolkit did not have this problem

`toolkits/shodan-toolkit/pyproject.toml` already declares
`llama-index-core>=0.12` as a **hard dependency**, and the library already
imports LlamaIndex in `tools.py`. Its adapter could move in without
changing a single contract.

The asymmetry is worth recording: the two toolkits had opposite rules
about LlamaIndex, and the move had to respect each of them.

---

## 4. The relative import, and why it is not the alias

The adapters used to reach their core package through the alias:

```python
from toolkits.mikrotik_routeros import CommandResult, ...   # absolute
from toolkits.shodan_toolkit import TOOL_REGISTRY           # absolute
```

They now use a **relative** import:

```python
from . import CommandResult, ...
from . import TOOL_REGISTRY
```

Two reasons:

1. **The adapter is part of the package now.** A relative import is the
   idiomatic form for a submodule, and it keeps the package free of an
   absolute self-reference (which is what R2 polices).
2. **It keeps working when the package is installed standalone.** The Shodan
   toolkit is a distributable package (`pip install shodan-toolkit`). With
   the alias form, `import shodan_toolkit.agent_shodan_toolkit` would fail
   outside this repository, because there is no `toolkits` package to
   register the alias. With the relative form, it works in both places.

The relative import is also what makes the adapter *consistent with its own
package*: whichever spelling was used to import it, it gets that package's
objects — never a second copy.

---

## 5. The degradation contract: a broken toolkit must not break the boot

This is the one real regression the move would have introduced, and it was
caught by reading the old code rather than by running it.

Before the move, the adapter file was at the project root. It always
existed, and it guarded its own import of the core package:

```python
try:
    from toolkits.mikrotik_routeros import (...)
except Exception:
    MIKROTIK_AVAILABLE = False
```

So a **broken** core package degraded to "no tools" and the agent still
booted.

After the move, the adapter is a submodule of that same package. If the
package fails to import, the alias is not registered, and the adapter
becomes unreachable — `from toolkits.mikrotik_routeros.agent_mikrotik_toolkit
import ...` raises `ImportError` at the call site.

The two orchestrators imported the adapters **unguarded**, at module level.
Left alone, the move would have turned "a broken optional toolkit" into
"the agent does not start". The retriever and the `--select` menu already
guarded their imports; the orchestrators did not, because they never had
to.

They now guard them, exactly like the other two load paths:

```python
try:
    from toolkits.mikrotik_routeros.agent_mikrotik_toolkit import (
        get_all_tools as get_mikrotik_tools,
    )
except ImportError:  # pragma: no cover - the toolkit is optional

    def get_mikrotik_tools() -> list:
        """The MikroTik toolkit is unavailable - expose no tools."""
        return []
```

---

## 6. What changed

### 6.1 The move

| From | To |
|---|---|
| `agent_mikrotik_toolkit.py` | `toolkits/MikroTik-RouterOS/agent_mikrotik_toolkit.py` |
| `agent_shodan_toolkit.py` | `toolkits/shodan-toolkit/src/shodan_toolkit/agent_shodan_toolkit.py` |

Both were `git mv`, so the history follows the file.

### 6.2 The call sites

| File | Change |
|---|---|
| `agent-torvalds.py` | guarded import through the alias |
| `agent-torvalds-mw.py` | guarded import through the alias |
| `agent_tool_retriever.py` | import path (already guarded) |
| `agent_tool_selection.py` | import path (already guarded) |
| `components/mikrotik_commands.py` | `from toolkits.mikrotik_routeros import agent_mikrotik_toolkit as mikrotik` |
| `tests/test_mikrotik_*.py` (6 files) | `from toolkits.mikrotik_routeros import agent_mikrotik_toolkit as mikrotik` |
| `tests/test_tool_selection_menu.py` | import path (4 places) |
| `toolkits/shodan-toolkit/tests/test_agent_adapter.py` | import path + the new file location |

### 6.3 The contracts

| File | Change |
|---|---|
| `toolkits/__init__.py` | the adapters are excluded from the eager submodule publication; the layout is documented |
| `toolkits/MikroTik-RouterOS/__init__.py` | the docstring states the new layout and the new import path |
| `toolkits/MikroTik-RouterOS/tests/test_package_layout.py` | R1 scoped to the library half; R1b, R1c, R4 added |
| `investigate/MikroTik-RouterOS/verify_layout_contract.py` | R1b, R1c, R4 added (20 → 23 checks) |
| `investigate/MikroTik-RouterOS/MODULE_SPECIFICATION.md` | the tree, the naming rules, §4.1, §4.2 R1, §6 and §7 |

### 6.4 The documentation

`README.md`, `docs/mikrotik-toolkit.md`, `docs/shodan-toolkit.md`,
`toolkits/MikroTik-RouterOS/README.md`, `SELF_DEVELOPMENT_RULES.md`,
`CHANGELOG.md`, `investigate/MikroTik-RouterOS/README.md`.

The historical documents — `INVESTIGATION_REPORT.md`,
`IMPLEMENTATION_PLAN.md`, `PROPOSAL_mikrotik_toolkit.md` — were **left
alone**. They record what was proposed at the time, and rewriting them
would falsify the record.

---

## 7. Verification

| Check | Result |
|---|---|
| Full suite, before / after | 39 failed, 1511 passed → **39 failed, 1518 passed** — the *same* 39 failures, by test id |
| `scripts/ci_test_gate.py` | **0 new failures**, 0 fixed — the build may proceed |
| `verify_layout_contract.py` | **23/23** (was 20/20; R1b, R1c, R4 are new) |
| `verify_test_contract.py` | **13/13** |
| `toolkits/MikroTik-RouterOS/tests/test_package_layout.py` | 18 passed (was 15) |
| `tests/test_toolkit_alias_contract.py` | 23 passed (was 20) |
| MikroTik adapter | 8 tools |
| Shodan adapter | 12 tools (read-only default) |
| `import toolkits` | does **not** import LlamaIndex |
| Both orchestrators | import cleanly, 8 + 12 tools |

### 7.1 The properties that matter, checked directly

```
mikrotik tools: 8
shodan tools  : 12
adapter module identity (mikrotik): toolkits.mikrotik_routeros.agent_mikrotik_toolkit
adapter module identity (shodan)  : toolkits.shodan_toolkit.agent_shodan_toolkit
models identity: True
shodan registry identity: True
adapter tool fn is registry fn: True
```

The last two lines are the point of the relative import: the adapter and
the library share **one** set of objects, so the `isinstance` checks the
adapter's own error handling depends on keep working.

---

## 8. Notes for the reviewer

- **The adapters are still importable under exactly one name.** The
  canonical path is the alias path. The real path
  (`toolkits.MikroTik-RouterOS.agent_mikrotik_toolkit`) cannot be written
  in an `import` statement at all, and only `importlib` can reach it — so
  it is not a second spelling in practice, but it is worth knowing.
- **The Shodan toolkit now ships its adapter inside the installable
  package.** `pyproject.toml` already requires `llama-index-core`, so the
  distribution is unaffected; the module is simply never imported unless
  somebody asks for it.
- **The pre-existing double-import hazard in the Shodan toolkit is
  unchanged, not fixed here.** `pytest.ini` puts
  `toolkits/shodan-toolkit/src` on `pythonpath`, so the library is
  importable both as `shodan_toolkit` and as `toolkits.shodan_toolkit` —
  two objects in one pytest process. The adapter always uses the alias
  namespace, and the adapter's own test asserts the identity
  (`tool.fn is TOOL_REGISTRY[...].fn`), so nothing breaks today. But a test
  that patched `shodan_toolkit.tools.get_client` would not affect the
  adapter. Worth a separate look.
- **The layout contract was changed, deliberately.** R1 now has one named
  exception instead of none, and R1c was added to keep the *behavioural*
  guarantee the original rule was about. The change is recorded in
  `MODULE_SPECIFICATION.md` §4.2, in the layout test and in the verify
  script — not silently applied.
- **`toolkits/MikroTik-RouterOS/agent_mikrotik_toolkit.py` is the one
  module of the package that is not library code.** A reader of the
  package now meets an adapter before the library. The package docstring
  and the README both say so explicitly.
