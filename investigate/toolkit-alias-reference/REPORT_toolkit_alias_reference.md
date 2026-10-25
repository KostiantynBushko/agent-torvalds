# Investigation report — the toolkit alias warnings

**Warnings investigated:** `/home/kbush/torvald-log/warnings/warnings.md`

```
agent_microtik_toolkit.py
WARNINGS:
1. Cannot find reference 'mikrotik_routeros' in '__init__.py'

agent_shodan_toolkit.py
WARNINGS:
1. Cannot find reference 'shodan_toolkit' in '__init__.py'
```

**Branch:** `fix/toolkit-alias-reference` (in `self-development/`)
**Status:** implemented, verified, **not committed** — awaiting operator approval.

---

## 1. Summary

Both warnings report the same defect, in the two toolkits that live in
hyphenated directories: **the canonical import path of a toolkit is not
visible to a static reader**.

The alias that makes `toolkits/MikroTik-RouterOS/` and
`toolkits/shodan-toolkit/` importable was registered with a *computed* name
(`__name__ + ".mikrotik_routeros"`). At run time that is correct, but a tool
that resolves imports **statically** — an IDE, an import resolver, a linter, a
packaging tool — cannot evaluate `__name__`. The canonical path
`toolkits.mikrotik_routeros` appeared nowhere in the source as a literal, and
the toolkit packages' own `__init__.py` mentioned their alias only in
**prose** (a docstring), never as a code-level reference. Such a tool
therefore concludes that the toolkit has no import path at all, and reports
it as a missing reference.

The same root cause carried a second, sharper defect: the alias registered
only the **root module** of a package. Importing a *submodule* through the
alias — which the MikroTik adapter does at `agent_mikrotik_toolkit.py:1175`
and `:1189` — loaded the file a **second time** and produced a second set of
classes. `isinstance()` across that boundary silently failed.

Both are fixed. The canonical paths are now literals, every toolkit package
carries a code-level reference to its own alias, and the alias namespace
shares one module object per file with the real namespace.

---

## 2. The evidence

### 2.1 The generator is not in this repository

The warning text is not produced by anything in `agent-torvalds`:

```
$ grep -rn "Cannot find reference" .            # no hit
$ git log --all -S "Cannot find reference"      # no hit
$ grep -rl "Cannot find reference" /home/kbush  # only the warnings file itself
```

The same is true for every branch in the clone. The checker is an **external**
tool; it is not part of the agent, and it could not be run to confirm its
exact algorithm.

Two details in the report do not match this repository and are worth
recording, because they show the report was produced against a *different*
snapshot (or a different tool):

* the file is named `agent_microtik_toolkit.py` — a misspelling. The file in
  this repository is `agent_mikrotik_toolkit.py`;
* the warning quotes the **bare module name** (`mikrotik_routeros`), not the
  dotted path.

The investigation therefore does not depend on the checker's exact
algorithm. It addresses the condition the warning describes — *a reference to
the canonical module name must exist in an `__init__.py`, at the code level* —
in the way that satisfies every reasonable reading of it:

* the **bare name** and the **full dotted path** are both literals in
  `toolkits/__init__.py`;
* the **bare name** is a code-level reference in each toolkit package's own
  `__init__.py`.

### 2.2 The alias was invisible to a static reader

Before the fix, `toolkits/__init__.py` computed the alias path:

```python
_MIKROTIK_ALIAS = __name__ + ".mikrotik_routeros"
```

The literal string `toolkits.mikrotik_routeros` therefore appeared in the
file **nowhere** — only `.mikrotik_routeros` did, as the tail of an
expression. The same held for the Shodan alias. A static reader looking for
`toolkits.mikrotik_routeros` in `__init__.py` found nothing.

In the toolkit packages' own `__init__.py` the alias name appeared only in
the **docstring**:

```
toolkits/MikroTik-RouterOS/__init__.py:17:    from toolkits.mikrotik_routeros import MikroTikTarget
```

Prose is not a reference. The repository's own contract verifier makes the
same distinction elsewhere — `verify_layout_contract.py` uses an AST scan
rather than a grep precisely so that "the prose in docstrings that mentions
the import path" is not mistaken for an import.

### 2.3 The alias duplicated every module (the sharper defect)

Registering the root module is not enough. The adapter reaches into a
submodule through the alias:

```python
# agent_mikrotik_toolkit.py:1175
from toolkits.mikrotik_routeros.parser import parse_identity
```

Because `toolkits/MikroTik-RouterOS/parser.py` was never published under the
alias namespace, the import system loaded the file **again** under the alias
name — and the second copy's relative import `from .models import
RouterIdentity` created a *second* copy of `models.py` as well.

Measured on the unmodified code:

```
$ python -c "..."
parse_identity -> <class 'toolkits.mikrotik_routeros.models.RouterIdentity'>
isinstance(identity, RouterIdentity from package root): False
RouterIdentity module:            toolkits.mikrotik_routeros.models
package-root RouterIdentity module: toolkits.MikroTik-RouterOS.models

models module identical? False
parser module identical? False
```

and the process carried two module objects for every file:

```
toolkits.MikroTik-RouterOS.models        toolkits.mikrotik_routeros.models
toolkits.MikroTik-RouterOS.parser        toolkits.mikrotik_routeros.parser
toolkits.MikroTik-RouterOS.config        toolkits.mikrotik_routeros.config
...
```

`CommandCategory` is a `str`-enum, so its members still compare equal across
the split. `CommandResult` and `RouterIdentity` are pydantic models, and
`isinstance()` against the package's own classes **fails**. The adapter's
own error handling depends on exactly that kind of check:

```python
# agent_mikrotik_toolkit.py:316
if MIKROTIK_AVAILABLE and isinstance(exc, MikroTikError):
```

A `MikroTikError` raised through the alias namespace would not be recognised
and the tool would report the generic `UNREACHABLE` code instead of the real
one (`AUTH_FAILED`, `TIMEOUT`, `COMMAND_REJECTED`, …).

The split also reached the test suite: the package-local tests import through
the real namespace (`from ..models import ...`), the root-level tests through
the alias (`from toolkits.mikrotik_routeros.parser import ...`) — so the two
suites exercised two different objects for the same file.

---

## 3. The fix

### 3.1 `toolkits/__init__.py` — literal paths, and the whole package

* `_MIKROTIK_ALIAS` and `_SHODAN_ALIAS` are now **literal** dotted paths
  (`"toolkits.mikrotik_routeros"`, `"toolkits.shodan_toolkit"`), so the
  canonical names are greppable and statically resolvable.
* `_publish_submodules()` imports every submodule under its **real** name and
  publishes the *same module object* under the alias name. Both spellings now
  resolve to one object, and there is exactly one instance of the code in
  memory — the property MODULE_SPECIFICATION.md §3.3 asks for.
* `_register_alias()` replaces the two duplicated try/except blocks.
* `__all__` is derived from the aliases that were *actually* registered, so
  `from toolkits import *` no longer fails when an optional toolkit is
  missing (it did before: `__all__` named `shodan_toolkit` unconditionally).

The degradation contract is unchanged: `import toolkits` still never raises
(R5), and a toolkit that explodes on import is still ignored silently
(§3.3c).

### 3.2 The toolkit packages — a code-level reference

Each package's own `__init__.py` now declares its canonical alias:

```python
# toolkits/MikroTik-RouterOS/__init__.py
__toolkit_alias__ = "mikrotik_routeros"

# toolkits/shodan-toolkit/src/shodan_toolkit/__init__.py
__toolkit_alias__ = "shodan_toolkit"
```

This is a *code-level* reference, not prose, and it is what a static reader
was looking for in an `__init__.py`.

### 3.3 `tests/test_toolkit_alias_contract.py` — 20 new tests

Two groups, matching the two properties:

* **`TestStaticReference`** — the canonical dotted path is a literal in the
  shim; the bare name is a literal; each package carries a code-level
  reference (checked with an **AST** scan, so a docstring does not count);
  the alias is not computed.
* **`TestSingleInstance`** — the alias is the same object as the real
  package; no submodule is loaded twice; importing a submodule through the
  alias does not copy it; one file, one class.
* **`TestInstanceIdentity`** — a value parsed through the alias satisfies the
  package's own classes, and carries the real module as its origin.
* **`TestDegradation`** — `import toolkits` never raises, even when a
  toolkit explodes on import.

The test was checked against the **unmodified** code: **11 of the 20 fail**,
and they are exactly the two conditions the warnings describe. With the fix,
all 20 pass.

---

## 4. Verification

| Check | Result |
|---|---|
| `tests/test_toolkit_alias_contract.py` | **20 passed** (11 fail without the fix) |
| Full suite, before the fix | 39 failed, 1511 passed, 9 skipped, 1 error |
| Full suite, after the fix | 39 failed, 1511 passed, 9 skipped, 1 error |
| Failure sets compared by test id | **identical** — no new failure, none hidden |
| `verify_layout_contract.py` (MODULE_SPECIFICATION.md §2.2/§3.2/§3.3/§4.2) | **20/20 passed** |
| `verify_test_contract.py` | **13/13 passed** |
| Adapters still load | MikroTik 8 tools, Shodan 12 tools |

`isinstance()` across the alias boundary, after the fix:

```
parse_identity -> <class 'toolkits.MikroTik-RouterOS.models.RouterIdentity'>
isinstance(identity, RouterIdentity from package root): True
models module identical? True
parser module identical? True
```

---

## 5. What was deliberately **not** changed

* **The directory names.** `toolkits/MikroTik-RouterOS/` and
  `toolkits/shodan-toolkit/` keep their exact spelling — MODULE_SPECIFICATION.md
  §2.2 fixes them, and `verify_layout_contract.py` asserts them.
* **The public API of the packages.** The new `__toolkit_alias__` attribute
  is additive; `__all__` of the MikroTik package is untouched.
* **The adapters.** `agent_mikrotik_toolkit.py` still imports the parser
  through the alias. The fix is at the root, so the import resolves to the
  one real module — no call site had to change.
* **The separate `shodan_toolkit` copy in the test suite.** `pytest.ini` puts
  `toolkits/shodan-toolkit/src` on `pythonpath`, so the toolkit's own tests
  import `shodan_toolkit.*` while the adapter imports
  `toolkits.shodan_toolkit.*` — two objects in one pytest process. The two
  spellings are *not* interchangeable there (the upstream `src/` layout is
  deliberate, and the toolkit is meant to work standalone), and the existing
  tests are self-consistent, so nothing breaks today. It is a latent hazard
  of the same family: a test that patched `shodan_toolkit.tools.get_client`
  would not affect the adapter. Worth a separate look; out of scope here.
* **The unknown checker.** It is not in the repository, so the fix could not
  be validated against it. The fix addresses the condition the warning
  describes in the strictest reasonable way, so a checker should now find the
  reference it was looking for.

---

## 6. Files changed

```
toolkits/__init__.py                                   | 128 ++++++++++-----
toolkits/MikroTik-RouterOS/__init__.py                 |  10 ++++++
toolkits/shodan-toolkit/src/shodan_toolkit/__init__.py  |  11 ++++++
tests/test_toolkit_alias_contract.py                   | 232 ++++++++++++++ (new)
```

All changes are inside the `self-development/` clone, on branch
`fix/toolkit-alias-reference`. The main repository is untouched.
