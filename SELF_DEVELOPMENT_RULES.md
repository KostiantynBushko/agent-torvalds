# Self-Development Rules

These rules govern how the Torvalds agent modifies its own codebase. They are
**persisted here** so that they survive across sessions and are available to any
future agent invocation.

**Last updated:** 2026-10-26 (the **Windows** toolkit became a module
under `toolkits/` and was **squash-merged into `master` as PR #50**,
commit `9c48625` — the **seventh** PR of the "every toolkit is a module"
refactoring, and the **last** of the *Linux/Windows* pair to move; the
**APT** toolkit became a module under
`toolkits/` and was **squash-merged into `master` as PR #48**, commit
`5eb5151` — the **sixth** PR of the "every toolkit is a module"
refactoring, and the first one whose library half is **not**
dependency-free; the **Linux** toolkit became a module under
`toolkits/` and was **squash-merged into `master` as PR #46**, commit
`94fb513` — the **fifth** PR of the series, and the **last** of the six
*Linux/Windows* pair to move;
the **OS** toolkit became a module under `toolkits/` and was
**squash-merged into `master` as PR #45**, commit
`899f9b2` — the **fourth** PR of the series, and the last toolkit that
was still **mandatory**; the
GitHub toolkit was squash-merged into `master` as PR #43, commit
`83456a7`; the Git toolkit was squash-merged into `master` as PR #41,
commit `7d0e56a`; the math toolkit was merged into `master` as PR #39,
merge commit `e2fce1a`)

---

## Rule 1 — All self-modifications live in `./self-development`

Any change the agent makes to its own source code, toolkits, components, tests or
documentation MUST be performed inside the `self-development/` directory.

The main repository checkout is treated as **read-only** for the purposes of
self-modification. It may be inspected (status, log, diff, branch listing) but not
written to.

## Rule 2 — Never modify the main repository directly

The main repository is the operator's working copy. The `self-development/`
directory is a **separate Git clone** with its own `.git` directory, so that
self-modifications can be branched, committed, reviewed and merged deliberately
instead of appearing as uncommitted noise in the operator's working tree.

To work on a feature:

```bash
cd self-development
git checkout master
git pull origin master
git checkout -b feature/<name> master
```

Only after review and explicit operator approval should changes flow back to the
main repository (via a pull request or a merge).

## Rule 3 — These rules are persisted

This file **is** the persistence mechanism. It must be kept up to date whenever the
rules change, and must be read at the start of every self-development session.

If this file is missing, recreate it from the rules in the agent's operating
instructions before performing any self-modification.

## Rule 4 — Commit and push require explicit approval

The agent must never `git commit` or `git push` without the operator's explicit
approval for that specific action. Before asking, the agent shows the staged diff
and a summary of the changes.

## Rule 5 — Destructive operations require explicit confirmation

`rm`, branch deletion, force-push, history rewriting (rebase/reset) and any
irreversible action on the operator's data must be confirmed first.

## Rule 6 — Show changes before committing

`git status` and `git diff` (or `git diff --staged`) are presented to the operator
before any commit is created.

## Rule 7 — Waiting for the operator follows the timeout

When the agent asks the operator a question, the timeout decides what the
agent is allowed to do:

* **`timeout = -1`** (no timeout) — the agent **stops and waits**.  It must
  not decide the question on its own; the answer arrives when the operator
  answers, however long that takes.
* **`timeout = N`** (a finite timeout) — the agent waits up to N seconds.
  When the timeout expires, the agent **acts on its own judgement** — and it
  says so in the report.

The operator stated this on 2026-10-22.  It is the contract the HITL timeout
machinery implements (`components/hitl_timeout.py`, `components/hitl_agent.py`),
and it is verified end to end by
`self-development/investigate/hitl-timeout-policy/verify_timeout_policy.py`.

A timed-out question is never reported as if it had been answered: the
operator must be able to tell "nobody answered, the agent decided" from "the
operator said so".  Defect **D16** (the model was fed the fallback answer as
if the human had said it) is fixed in `components/hitl_agent.py`; the model
now reads *"No human response — the wait ended without an answer. The
question was not answered; act on your own judgement."*

---

## Current self-development work

| Item | Status |
|---|---|
| Branch | `refactor/windows-toolkit-module` — **squash-merged into `master` as PR #50** (commit `9c48625`, head `0b5f2af`; based on `master` at `02270ed`) |
| Scope | The **seventh** toolkit of the "every toolkit is a module under `toolkits/`" refactoring: `agent_windows_toolkit.py` leaves the project root and becomes `toolkits/windows-toolkit/`. It is the **last** of the *Linux/Windows* pair to move, and the last toolkit of the series whose library half is built on the **standard library alone**. |
| Status | Implemented, verified and **merged**. The loose root module is **split** into the library half (`operations.py` — the 6 PowerShell and system operations, the private `_get_powershell_command` helper and the module-level logger, no LlamaIndex import) and the adapter (`agent_windows_toolkit.py` — the only LlamaIndex-dependent module), with an `__init__.py`, a `py.typed` marker, a `README.md`, a `pyproject.toml` and the module-local tests. The hyphenated directory is reachable through the alias `toolkits.windows_toolkit`, which `toolkits/__init__.py` registers next to the other eight toolkits. The **four** call sites (both orchestrators, the retriever and the selection menu) were updated; all four imported the toolkit unguarded and now import it **behind a guard**, so the Windows toolkit goes from mandatory to optional. **The toolkit had no test suite at all** before this change; the one that came with it has 87 tests and is **platform-independent** — it drives the operations through a stubbed `subprocess.run`, so it needs neither Windows nor a PowerShell installation. The alias contract is green, and the full suite reports **no new failure** (the CI gate: 40 known failures, 0 new, 0 fixed) — `tests/ci_baseline.txt` did **not** need rewriting, because the toolkit had no known failures of its own. The tool menu is **unchanged**: it was dumped from `master` and from the branch and the two are byte-identical (155 tools) — and byte-identical again with the platform simulated as Windows, so the Windows toolkit's own six tools are in it. The report is `investigate/windows-toolkit-module/REPORT_windows_toolkit_module.md`. |
| Policy | The **behaviour did not change** — every function, every docstring, every tool description and the error contract (a failure is reported, never raised) were moved verbatim; the split was checked mechanically against the committed original, not by eye, and **the check itself is now a test**, driven with nine deliberate drifts. What changed is the *shape*: a toolkit is one folder, and the file inside it is split so that the reusable half carries no LlamaIndex import and the adapter is the single named exception. The one thing that did **not** move verbatim is the module header: the `os` import of the original was never used by any of the operations — `run_command_with_env` passes the variables to the shell as PowerShell assignments, not through `os.environ` — so it was dropped rather than carried along. One PR per toolkit, as the operator asked. The remaining loose toolkits are `agent_db_toolkit.py`, `agent_xlsx_toolkit.py` and `agent_data_analysis_toolkit.py`. |
| State | **Merged.** Committed as `0b5f2af`, pushed, opened as PR #50, and **squash-merged into `master` as `9c48625`** after CI ran green. The tree check holds: `master`'s tree after the merge (`7a49b8a`) is byte-identical to the head tree of `0b5f2af` that CI ran green. The next toolkit of the series starts from `master` (`9c48625`). |

### Latest change: the Windows toolkit is a module

**Squash-merged into `master` as PR #50** (commit `9c48625`, head
`0b5f2af`).  The PR is based on `master` — not on `main`.

The squash departs from the standing convention of a merge commit, as
PR #48, PR #46, PR #43 and PR #41 did before it, and for the same reason:
the convention exists for the *stacked* PR chain, and this PR is based
directly on the tip of `master` (`02270ed`), so the next PR's merge base
is `9c48625` and its diff does not balloon.  The tree check the
convention exists for holds as well — `master`'s tree after the merge
(`7a49b8a`) is byte-identical to the head tree of `0b5f2af` that CI ran
green.

The **seventh** toolkit of the "every toolkit is a module" series, and
the **last** of the *Linux/Windows* pair to move.  The two carry the
same six operations under the same names, and they are loaded on
different platforms, so exactly one of them is ever in the menu.

| Path | Change |
|------|--------|
| `toolkits/windows-toolkit/operations.py` | **New.** The 6 PowerShell and system operations, the private `_get_powershell_command` helper and the module-level logger — the library half. No LlamaIndex import, standard library only (`subprocess`, `logging`, `typing`). |
| `toolkits/windows-toolkit/agent_windows_toolkit.py` | **New.** The adapter — the only LlamaIndex-dependent module. It re-exports all 6 operations. |
| `toolkits/windows-toolkit/__init__.py` | **New.** The public API surface and the code-level reference to the canonical alias. |
| `toolkits/windows-toolkit/README.md`, `pyproject.toml`, `py.typed` | **New.** The module documentation, the standalone distribution (the adapter is the `agent` extra) and the PEP 561 marker. |
| `toolkits/windows-toolkit/tests/test_operations.py` | **New.** 45 tests. The toolkit had **no** suite; this one is platform-independent — it drives the operations through a stubbed `subprocess.run`. |
| `toolkits/windows-toolkit/tests/test_package_layout.py` | **New.** The layout contract — 30 checks. |
| `toolkits/windows-toolkit/tests/test_split_verification.py` | **New.** The test of the split-verification script — 12 tests, nine deliberate drifts. |
| `agent_windows_toolkit.py` | **Deleted** at the project root. Git tracked it as a rename to `toolkits/windows-toolkit/operations.py`. |
| `toolkits/__init__.py` | The `windows_toolkit` alias, the `_WINDOWS_PACKAGE` / `_WINDOWS_ALIAS` literals and the adapter in `_ADAPTER_MODULES`. |
| `agent-torvalds.py`, `agent-torvalds-mw.py` | The Windows adapter moved into the guarded block with the math, Git, GitHub, MikroTik, Shodan, OS, Linux and APT ones. |
| `agent_tool_retriever.py`, `agent_tool_selection.py` | The import path moved to the alias, behind a guard. |
| `pytest.ini` | `toolkits/windows-toolkit/tests` added to `testpaths`. |
| `tests/test_toolkit_alias_contract.py` | The Windows toolkit joined the alias contract — seven new rows. |
| `tests/test_logging_cli.py` | The logger now comes from `toolkits.windows_toolkit.operations`; the two new modules joined the static inspection. |
| `README.md`, `CHANGELOG.md` | The documentation. |
| `investigate/windows-toolkit-module/REPORT_windows_toolkit_module.md` | **New.** What was implemented and why. |
| `investigate/windows-toolkit-module/verify_split.py` | **New.** The mechanical check. |

**Verifying the change**

```bash
self-development/.venv/bin/python -m pytest self-development/toolkits/windows-toolkit/tests -q
self-development/.venv/bin/python self-development/scripts/ci_test_gate.py
```

87 passed, and the CI gate reports **no new failure** (40 known failures,
0 new, 0 fixed).  The baseline was **not** rewritten — the Windows
toolkit had no known failures of its own, so no known failure changed
path.  (The APT toolkit before it *did* need a rewritten baseline, for
exactly the opposite reason: it carried four known failures, and the
move changed their paths.)

**Three things this change is worth knowing about.**

*It is the third dependency-free library half.*  The OS toolkit was the
first, the Linux toolkit the second, and this one the third: it is built
on `subprocess`, `logging` and `typing` and on nothing else, so the
PowerShell operations work in any Python that exists.  The layout
contract pins the exact set.

*The toolkit had no test suite at all.*  Every other toolkit of the
series carried one into its package; this one did not, so nothing
guarded its error contract — the "a failure is reported, never raised"
promise that is the whole point of the toolkit.  The suite that came
with the move has 87 tests, and it is **platform-independent**: it
drives the operations through a stubbed `subprocess.run`, so it needs
neither Windows nor a PowerShell installation.  That matters — the build
that has to stay green runs on Linux, and a suite that could only run on
Windows would never guard anything.

*One import did not move, and that is deliberate.*  The original
imported `os` and never used it: `run_command_with_env` passes the
variables to the shell as **PowerShell assignments** (`$env:NAME="value"`),
not through `os.environ`.  The unused import was dropped rather than
carried along.  It is the only difference between the original module
and the library half, apart from the module header itself.

### Previous change: the APT toolkit is a module

**Squash-merged into `master` as PR #48** (commit `5eb5151`, head
`4c2b941`).  The PR is based on `master` — not on `main`.

The squash departs from the standing convention of a merge commit, as
PR #46, PR #43 and PR #41 did before it, and for the same reason: the
convention exists for the *stacked* PR chain, and this PR is based
directly on the tip of `master` (`d7cb132`), so the next PR's merge base
is `5eb5151` and its diff does not balloon.  The tree check the
convention exists for holds as well — `master`'s tree after the merge
(`0af67be`) is byte-identical to the head tree of `4c2b941` that CI ran
green.

The **sixth** toolkit of the "every toolkit is a module" series, and the
first one whose library half is **not** dependency-free.  The OS and the
Linux toolkit are built on the standard library alone, and their layout
contracts pin that exact set.  The APT toolkit cannot: it needs `rich`
for the *console* password prompt — the default prompt method — and the
repository's own `components.whiptail_password` for the *whiptail* one.
Both imports are deferred to the call and both are guarded, so the module
imports cleanly without either and neither failure takes the agent down.
The layout contract pins the exact set, so a new dependency cannot slip
in unnoticed.

The file carried **three** things, so it was split in three: the library
half (`operations.py` — the 13 package, sudo and install operations), the
adapter (`agent_apt_toolkit.py` — the only LlamaIndex-dependent module)
and the command-line interface (`cli.py` — it used to be a
`if __name__ == "__main__":` block at the bottom of the module).

**The check caught a drift of my own.**  The `--show-method` help text
read "Show the current default **password** prompt method and exit" in
the new CLI, while the original said "Show the current default prompt
method and exit".  I had "improved" the wording; the mechanical check
compared the two and refused to pass.  That is the whole reason for
having it.

**And the check had a hole of its own.**  The first cut of the split
lost *every* section header of the module — the `# 1. Package
Resolution` rules and the rest — because the script that cut the file
took the code by AST node range, and the comments around it were not
part of any node.  Nothing in the check noticed, because the check did
not look at them.  The headers are the reader's map of the file, so they
are part of the comparison now, and two more drifts were added to the
test of the check for that.

**Four known failures carried over** — the same four, with the same
names, only the path of the test file changed, and
`tests/ci_baseline.txt` was rewritten to match (the way the math
toolkit's move did with its seven).  None of them is a defect of the
toolkit: two are stale assertions about a tool count that grew from 8 to
10, one is a stale mock, and one is a pytest collection artifact — the
suite imports the operation `test_sudo_password` into its own namespace,
and pytest collects every module-level name that starts with `test_`,
*including imported ones*.

**Two things were found and fixed.**  The alias shim published *every*
submodule of a toolkit under the toolkit's alias, including the
`__main__` modules — and a `__main__` module is meant to be **executed**,
not imported.  Publishing one puts it in `sys.modules`, and `runpy` then
refuses to execute it, so `python -m toolkits.shodan_toolkit` has been
broken since the Shodan toolkit was moved into this repository.  The shim
skips the `__main__` modules now, the way it already skipped the agent
adapters, and the alias contract has a new class for the rule.  And the
`collect_ignore` option in `pytest.ini` — which was there to keep pytest
from collecting the `test_sudo_password` operation — is **not** a pytest
ini option at all: pytest warned "Unknown config option" on every run
and ignored it.  It is gone, and the comment says why.

The **four** call sites (both orchestrators, the retriever and the
selection menu) were updated; all four imported the toolkit unguarded and
now import it **behind a guard**, so the APT toolkit goes from mandatory
to optional.

The toolkit suite is green (100 passed, 4 known failures), the alias
contract is green (75 passed), and the full suite reports **no new
failure** (the CI gate: 40 known failures, 0 new, 0 fixed).  The tool
menu is **unchanged**: it was dumped from `master` and from the branch
and the two are byte-identical.  The report is
`investigate/apt-toolkit-module/REPORT_apt_toolkit_module.md`.

| Path | Change |
|------|--------|
| `toolkits/apt-toolkit/operations.py` | **New.** The 13 package, sudo and install operations — the library half. No LlamaIndex import. |
| `toolkits/apt-toolkit/agent_apt_toolkit.py` | **New.** The adapter — the only LlamaIndex-dependent module. It re-exports all 10 public operations. |
| `toolkits/apt-toolkit/cli.py` | **New.** The command-line interface, which used to be a `__main__` block. |
| `toolkits/apt-toolkit/__main__.py` | **New.** The `python -m toolkits.apt_toolkit` entry point. |
| `toolkits/apt-toolkit/__init__.py` | **New.** The public API surface and the code-level reference to the canonical alias. |
| `toolkits/apt-toolkit/README.md`, `pyproject.toml`, `py.typed` | **New.** The module documentation, the standalone distribution (`rich`; the adapter is the `agent` extra) and the PEP 561 marker. |
| `toolkits/apt-toolkit/tests/test_operations.py` | **New** (moved from `tests/test_apt_toolkit.py`). Relative imports. |
| `toolkits/apt-toolkit/tests/test_package_layout.py` | **New.** The layout contract — 37 checks. |
| `toolkits/apt-toolkit/tests/test_split_verification.py` | **New.** The test of the split-verification script — 19 tests, fifteen deliberate drifts. |
| `agent_apt_toolkit.py` | **Deleted** at the project root. |
| `tests/test_apt_toolkit.py` | **Deleted** at the project root. Git tracked it as a rename to the module-local test. |
| `toolkits/__init__.py` | The `apt_toolkit` alias, the `_APT_PACKAGE` / `_APT_ALIAS` literals, the adapter in `_ADAPTER_MODULES` — and the `NEVER_PUBLISHED` rule that keeps a `__main__` module out of the eager publication. |
| `agent-torvalds.py`, `agent-torvalds-mw.py` | The APT adapter moved into the guarded block with the math, Git, GitHub, MikroTik, Shodan, OS and Linux ones. |
| `agent_tool_retriever.py`, `agent_tool_selection.py` | The import path moved to the alias, behind a guard. |
| `pytest.ini` | `toolkits/apt-toolkit/tests` added to `testpaths`; the dead `collect_ignore` option removed. |
| `tests/ci_baseline.txt` | The four APT node ids rewritten for the new path. |
| `tests/test_toolkit_alias_contract.py` | The APT toolkit joined the alias contract — seven new rows — and a new `TestNeverPublished` class for the `__main__` rule. |
| `tests/test_logging_cli.py` | The logger now comes from `toolkits.apt_toolkit.operations`; the two new modules joined the static inspection. |
| `spinner_manager.py` | The docstring names the new path. |
| `README.md`, `CHANGELOG.md`, `docs/ci.md` | The documentation. |
| `investigate/apt-toolkit-module/REPORT_apt_toolkit_module.md` | **New.** What was implemented and why. |
| `investigate/apt-toolkit-module/verify_split.py` | **New.** The mechanical check — the operations, the tool surface **and** the command-line interface. |

**Verifying the change**

```bash
self-development/.venv/bin/python -m pytest self-development/toolkits/apt-toolkit/tests -q
self-development/.venv/bin/python self-development/scripts/ci_test_gate.py
```

97 passed and the 4 known failures, and the CI gate reports **no new
failure** (40 known failures, 0 new, 0 fixed).

### Previous change: the Linux toolkit is a module

**Squash-merged into `master` as PR #46** (commit `94fb513`, head
`772f819`).  The PR is based on `master` — not on `main`.

The squash departs from the standing convention of a merge commit, as
PR #43 and PR #41 did before it, and for the same reason: the
convention exists for the *stacked* PR chain, and this PR is based
directly on the tip of `master` (`dead333`), so the next PR's merge
base is `94fb513` and its diff does not balloon.  The tree check the
convention exists for holds as well — `master`'s tree after the merge
(`395a8f0f`) is byte-identical to the head tree of `772f819` that CI ran
green.

The **fifth** toolkit of the "every toolkit is a module" series, and the
**last** of the Linux/Windows pair to move.  Its counterpart, the
Windows toolkit, is the natural next one: the two carry the same six
operations under the same names, and they are loaded on different
platforms, so exactly one of them is ever in the menu.

| Path | Change |
|------|--------|
| `toolkits/linux-toolkit/operations.py` | **New.** The 6 shell and system operations — the library half. No LlamaIndex import, standard library only. |
| `toolkits/linux-toolkit/agent_linux_toolkit.py` | **New.** The adapter — the only LlamaIndex-dependent module. It re-exports all 6 functions. |
| `toolkits/linux-toolkit/__init__.py` | **New.** The public API surface and the code-level reference to the canonical alias. |
| `toolkits/linux-toolkit/README.md`, `pyproject.toml`, `py.typed` | **New.** The module documentation, the standalone distribution (the adapter is the `agent` extra) and the PEP 561 marker. |
| `toolkits/linux-toolkit/tests/test_operations.py` | **New** (moved from `tests/test_linux_toolkit.py`). Relative imports; extended from 11 to 36 tests. |
| `toolkits/linux-toolkit/tests/test_package_layout.py` | **New.** The layout contract — 31 checks. |
| `toolkits/linux-toolkit/tests/test_split_verification.py` | **New.** The test of the split-verification script — 10 tests, seven deliberate drifts. |
| `agent_linux_toolkit.py` | **Deleted** at the project root. Git tracked it as a rename to `toolkits/linux-toolkit/operations.py`. |
| `tests/test_linux_toolkit.py` | **Deleted** at the project root. Git tracked it as a rename to the module-local test. |
| `toolkits/__init__.py` | The `linux_toolkit` alias, the `_LINUX_PACKAGE` / `_LINUX_ALIAS` literals and the adapter in `_ADAPTER_MODULES`. |
| `agent-torvalds.py`, `agent-torvalds-mw.py` | The Linux adapter moved into the guarded block with the math, Git, GitHub, MikroTik, Shodan and OS ones. |
| `agent_tool_retriever.py`, `agent_tool_selection.py` | The import path moved to the alias, behind a guard. |
| `pytest.ini` | `toolkits/linux-toolkit/tests` added to `testpaths`. |
| `tests/test_toolkit_alias_contract.py` | The Linux toolkit joined the alias contract — seven new rows. |
| `tests/test_logging_cli.py` | The logger now comes from `toolkits.linux_toolkit.operations`; the two new modules joined the static inspection. |
| `README.md`, `CHANGELOG.md` | The documentation. |
| `investigate/linux-toolkit-module/REPORT_linux_toolkit_module.md` | **New.** What was implemented and why. |
| `investigate/linux-toolkit-module/verify_split.py` | **New.** The mechanical check. |

**Verifying the change**

```bash
self-development/.venv/bin/python -m pytest self-development/toolkits/linux-toolkit/tests -q
self-development/.venv/bin/python self-development/scripts/ci_test_gate.py
```

78 passed, and the CI gate reports **no new failure** (40 known failures,
0 new, 0 fixed) — and, because the Linux toolkit had no known failures of
its own, no *fixed* one either.

**Three things this change is worth knowing about.**

*It is the second dependency-free library half.*  The OS toolkit was the
first; the Linux toolkit is built on `subprocess`, `os`, `logging` and
`typing` and on nothing else, so the shell operations work in any
Python that exists.  The layout contract pins the exact set.

*The check is now a test.*  The previous toolkits had their split verified
by a script that was exercised by hand.  Here the script
(`investigate/linux-toolkit-module/verify_split.py`) has a pure
`compare()` function, so it can be driven with deliberately broken
sources — and it is: seven drifts, from a reworded tool description to a
swapped operation, all caught.  A check that has never failed proves
nothing, and a check that is only run by hand proves less.

**The build found a defect the developer's machine could not.**  The
split-verification check asked git for the committed original *by name*
— `git show master:agent_linux_toolkit.py` — and the test that drove it
hard-coded the same name.  That works in a clone; it fails in CI, where
the checkout is a detached HEAD of the merge commit with a shallow
history, so there is no `master` branch to ask.  The first CI run went
red with **ten new failures**, every one of them in the check and none
in the toolkit.

The fix is to stop assuming a name.  The original is *the file as it was
committed before it was deleted*, so the check now **finds** it: a
named ref that still carries the file (`master`, `origin/master`,
`main`, `origin/main`), and otherwise the **parent of the commit that
deleted it**.  The second step is what makes the check work in CI, and
it is the more precise definition anyway — it names the original by the
deletion rather than by a branch that may or may not exist.  The
workflow now checks the repository out with `fetch-depth: 0`, because a
shallow history cannot answer the question at all.

The lesson is worth keeping: **a check that only runs where its author
sits is not a check.**  It ran green locally for the whole of the
change, and the build found it in two minutes.  The next toolkit of the
series must run its verification the way CI runs it — from the
repository root of the branch, and with the history the check needs.

*Two findings, both left alone.*  `agent-torvalds.py:759` holds an
invalid escape sequence (`\toggle-hitl`, `\hitl-status` in a non-raw
string), which is a pre-existing `SyntaxWarning`; the layout contract
parses that file and surfaced it, so the test suppresses it — but the
**bug stays**, because this is a behaviour-neutral refactoring and the
fix belongs in its own change.  And `get_system_info` is defined by
**both** the Linux and the OS toolkit, so the tool menu carries the name
twice on Linux; that duplicate is pre-existing (it is on `master` too)
and the move neither created nor changed it.

### Previous change: the OS toolkit is a module

**Squash-merged into `master` as PR #45** (commit `899f9b2`, head
`7120bb9`).  The PR is based on `master` — not on `main`.

The operator asked for a **squash**, as for PR #43 and PR #41.  The
departure from the standing convention of a merge commit is safe here,
for the reason recorded under the Git toolkit: the convention exists for
the *stacked* PR chain, and this PR is based directly on the tip of
`master`, so the next PR's merge base is `899f9b2` and its diff does not
balloon.  The tree check the convention exists for holds as well —
`master`'s tree after the merge (`0688c763`) is byte-identical to the
head tree of `7120bb9` that CI ran green.

The **fourth** toolkit of the series, and the **last** one that was still
mandatory.  Every other toolkit had already moved under `toolkits/`,
where a missing or broken toolkit degrades to "no tools" instead of a
failed boot; the OS toolkit was still a top-level module that every
orchestrator imported unguarded.

**The "C++ orchestrator" was a false alarm.**  The series' notes called
this the toolkit the C++ orchestrator leans on.  There is no compiled
binary in the repository — `agent-torvalds-cpp.py` is Python, and the
"cpp" is the `llama-cpp-python` binding behind its LLM.  `find` for
`*.cpp`, `*.hpp`, `*.cc` and `*.h` returns only files inside `.venv/`.
So there was no artefact that a renamed module could have broken.

**What was real is the star import.**  `agent-torvalds-cpp.py` does
`from toolkits.os_toolkit.agent_os_toolkit import *`, and the old module
had **no `__all__`**, so its star import also leaked `os`, `shutil`,
`logging`, `Path` and `platform` into that module.  The adapter declares
`__all__`, so the leak is gone — deliberately, and safely: the file uses
none of those names (`asyncio`, `Console` and `logging` are imported
explicitly).  The layout contract pins the narrowing, so it cannot
drift back unnoticed.

**The library half has no third-party dependency at all** — `os`,
`shutil`, `pathlib` and `platform`, the standard library.  It is the
first toolkit of the series whose reusable half is dependency-free, and
the layout contract now enforces it.  The file-system operations work
in any Python that exists.

**The toolkit already had a test suite**, and it moved with it — so
"behaviour-neutral" was something the suite could *show*, as it was for
the math and the Git toolkits.  The suite was extended from 17 to 37
tests, covering the error contract of all eleven operations: a failure
is *reported*, never raised.  One existing test was made robust — it
asserted `"README.md" in ls(".")`, which only held when pytest was
started from the repository root.

**The split was checked mechanically against the committed original**,
by AST: the eleven operation names, their order, their signatures, their
docstrings, their bodies, and the eleven tool names, their order and
their descriptions.  The check was itself tested against three
deliberate drifts — a reworded description, a changed parameter
default, a dropped docstring — and caught all three.  A check that has
never failed proves nothing.

**The tool menu is unchanged**: 155 tools, 154 distinct names, the same
pre-existing `get_system_info` duplicate (the OS toolkit and the Windows
toolkit both define it, and both are loaded into one process).  The
duplicate is on `master` too, so the move neither created nor changed
it.

**One thing changed on purpose:** the logger's name moved from
`agent_os_toolkit` to `toolkits.os-toolkit.operations`, because that is
what `logging.getLogger(__name__)` does when the module moves.  The
math, Git and GitHub moves changed theirs the same way.  The adapter
re-exports the operations' logger, so the whole toolkit still logs
through one logger, as the single module did.

### Previous change: the GitHub toolkit is a module

**Squash-merged into `master` as PR #43** (commit `83456a7`, head
`0533206`).  The PR is based on `master` — not on `main`.

The operator asked for a **squash**, as for PR #41.  The departure from
the standing convention of a merge commit is safe here, for the reason
recorded under the Git toolkit: the convention exists for the *stacked*
PR chain, and this PR is based directly on the tip of `master`, so the
next PR's merge base is `83456a7` and its diff does not balloon.  The
tree check the convention exists for holds as well — `master`'s tree
after the merge (`74a5f5b`) is byte-identical to the head tree of
`0533206` that CI ran green.

The **third** toolkit of the series, and the first one of them that
arrived **without a test suite**.  That changed what the work was.

The math and the Git toolkits had tests that moved with them, so
"behaviour-neutral" was something the suite could show.  The GitHub
toolkit had **no tests at all** — no `tests/test_github_toolkit.py`, and
nothing in `tests/ci_baseline.txt` either.  A move of it would have been
an entirely unverified refactoring, and the layout contract alone would
not have made the claim true.

So the toolkit got a suite: `toolkits/github-toolkit/tests/test_operations.py`,
**95 tests** that pin the behaviour of every operation — the token
resolution, the headers, the status-code mapping, the error contract and
the payload of all thirteen tools.  It is **offline**: `requests` is
stubbed at the transport boundary and the GitHub CLI is stubbed too, so
no test reaches `api.github.com` and no test needs a token.  A developer
who has `gh` installed, or a `GITHUB_TOKEN` exported, gets the same result
as everybody else.

The split is the same as the Git toolkit's, and the dependency profile
matches it too: the library half is built on `requests` — the HTTP
client the REST API is called through — and on nothing else, so the
contract pins the *exact* set rather than merely "no LlamaIndex".

| Path | Change |
|------|--------|
| `toolkits/github-toolkit/operations.py` | **New.** The 13 GitHub operations — the library half. No LlamaIndex import. |
| `toolkits/github-toolkit/agent_github_toolkit.py` | **New.** The adapter — the only LlamaIndex-dependent module. It re-exports all 13 functions, so a star import keeps working. |
| `toolkits/github-toolkit/__init__.py` | **New.** The public API surface and the code-level reference to the canonical alias. |
| `toolkits/github-toolkit/README.md`, `pyproject.toml`, `py.typed` | **New.** The module documentation, the standalone distribution (`requests`; the adapter is the `agent` extra) and the PEP 561 marker. |
| `toolkits/github-toolkit/tests/test_operations.py` | **New.** 95 tests — the suite the toolkit never had. |
| `toolkits/github-toolkit/tests/test_package_layout.py` | **New.** The layout contract — 25 checks. |
| `agent_github_toolkit.py` | **Deleted** at the project root. Git tracked it as a rename to `toolkits/github-toolkit/operations.py`. |
| `toolkits/__init__.py` | The `github_toolkit` alias, the `_GITHUB_PACKAGE` / `_GITHUB_ALIAS` literals and the adapter in `_ADAPTER_MODULES`. |
| `agent-torvalds.py`, `agent-torvalds-mw.py` | The GitHub adapter moved into the guarded block with the math, Git, MikroTik and Shodan ones. |
| `agent_tool_retriever.py`, `agent_tool_selection.py` | The import path moved to the alias, behind a guard. |
| `pytest.ini` | `toolkits/github-toolkit/tests` added to `testpaths`. |
| `tests/test_toolkit_alias_contract.py` | The GitHub toolkit joined the alias contract — three new rows. |
| `tests/test_logging_cli.py` | The logger now comes from `toolkits.github_toolkit.operations`; the two new modules joined the static inspection. |
| `README.md`, `CHANGELOG.md` | The documentation. |
| `investigate/github-toolkit-module/REPORT_github_toolkit_module.md` | The report. |

**Verifying the change**

```bash
self-development/.venv/bin/python -m pytest self-development/toolkits/github-toolkit/tests -q
self-development/.venv/bin/python self-development/scripts/ci_test_gate.py
```

120 passed, and the CI gate reports **no new failure** (40 known failures,
0 new, 0 fixed) — and, because the GitHub toolkit had no known failures
of its own, no *fixed* one either.

**One thing the split was checked against.**  The descriptions of the
thirteen tools are behaviour: they are what the retriever matches
against and what the model reads.  So the split was verified
mechanically — the tool names, their order and their descriptions were
compared, by AST, against the original file at `HEAD`; the thirteen
signatures and every docstring likewise.  That check caught a drift that
eyeballing would not have: a description that had been reworded from
"review submissions **for** a Pull Request" to "review submissions **on**
a Pull Request".  The rule for the rest of the series: move verbatim, and
let a script prove it.

**Two findings the move surfaced.**

*A collision that does not happen — yet.*  The GitHub toolkit's three
authentication tools are named `git_check_auth`, `git_get_user_info` and
`git_configure_credentials` — in the namespace the **Git** toolkit owns,
and both toolkits are now loaded into the same process.  The two tool
surfaces are **disjoint** (27 + 13 = 40 distinct names), and the whole
menu is 155 tools with 154 distinct names; the single duplicate,
`get_system_info`, comes from the OS and the Windows toolkits and is
**pre-existing** — it is on `master` too, with the same count of 155.
But it is a live hazard for the rest of the series: a future Git
toolkit operation called `git_check_auth` would collide for real.
Renaming the three GitHub tools to `github_*` would remove the hazard,
and it belongs in its own PR — the names are in the tool descriptions
the retriever matches against, so they are **behaviour**.

*A latent inconsistency, left alone.*  `git_check_auth()` reports the
method as `"gh_cli"` only when `GITHUB_TOKEN` is `None`, while
`_get_github_token()` treats an **empty** `GITHUB_TOKEN` as absent and
falls through to the CLI.  So with `GITHUB_TOKEN=""` exported and a
working `gh` CLI, the token comes from the CLI but the method is
reported as `"token"`.  The behaviour is **unchanged** — this is a
refactoring, and the point of the series is that nothing moves.  The
suite pins the current behaviour as a characterisation test, so the
inconsistency is now *documented* rather than invisible.  Fixing it
belongs in its own PR, where the change is the change.

### Previous change: the Git toolkit is a module

**Squash-merged into `master` as PR #41** (commit `7d0e56a`, head
`79c69d8`).  The PR is based on `master` — not on `main`.

The operator asked for a **squash** here, which departs from the standing
convention of this file (a **merge commit**).  The departure is safe for
this PR, and the reason is worth recording:

* the standing rationale for the merge commit is the **stacked** PR
  chain — "squashing drops the original SHAs from `master`'s history and
  the next PR's diff balloons to include every layer below it".  This
  PR is **not** stacked: it is based directly on the tip of `master`
  (`10fc1f0`), so the next PR's merge base is `7d0e56a` and its diff is
  computed against that.  Nothing balloons.
* the second reason for the merge commit — "the merge result tree must
  equal the tree the CI gate already validated" — **does** hold for a
  squash, and it was checked: `master`'s tree after the merge
  (`d3242f5`) is byte-identical to the head tree of `79c69d8` that CI
  ran green.  The merge introduced no untested content.

The one thing a squash does drop is the branch's own commit from
`master`'s history: `79c69d8` is reachable only through the branch
`refactor/git-toolkit-module`, not through `master`.  The content is
identical, so nothing is lost that the tests or the tree check would
have caught.

The **second** toolkit of the series, and the first one with a real
third-party dependency: `pygit2`.  The split is the same, but the
dependency profile is not — the library half keeps `pygit2` (a Git
operation is a Git operation whether or not an agent framework is
installed) and the adapter is the only module that knows about
LlamaIndex.  The layout contract therefore pins the *exact* set of
dependencies of the library half, not merely "no LlamaIndex".

The Git toolkit had **no** known failures, so `tests/ci_baseline.txt` did
not change at all — which is the cleanest possible confirmation that the
refactoring was behaviour-neutral.

| Path | Change |
|------|--------|
| `toolkits/git-toolkit/operations.py` | **New.** The 27 Git operations — the library half. No LlamaIndex import. |
| `toolkits/git-toolkit/agent_git_toolkit.py` | **New.** The adapter — the only LlamaIndex-dependent module. It re-exports all 27 functions, because the C++ orchestrator imports it with a star. |
| `toolkits/git-toolkit/__init__.py` | **New.** The public API surface and the code-level reference to the canonical alias. |
| `toolkits/git-toolkit/README.md`, `pyproject.toml`, `py.typed` | **New.** The module documentation, the standalone distribution (`pygit2`; the adapter is the `agent` extra) and the PEP 561 marker. |
| `toolkits/git-toolkit/tests/test_operations.py` | **New** (moved from `tests/test_git_toolkit.py`). Relative imports. |
| `toolkits/git-toolkit/tests/test_package_layout.py` | **New.** The layout contract — 24 checks, including the dependency profile and the 27-tool surface. |
| `agent_git_toolkit.py` | **Deleted** at the project root. Git tracked it as a rename to `toolkits/git-toolkit/operations.py`. |
| `tests/test_git_toolkit.py` | **Deleted** at the project root. Git tracked it as a rename to the module-local test. |
| `toolkits/__init__.py` | The `git_toolkit` alias, the `_GIT_PACKAGE` / `_GIT_ALIAS` literals and the adapter in `_ADAPTER_MODULES`. |
| `agent-torvalds.py`, `agent-torvalds-mw.py` | The Git adapter moved into the guarded block with the math, MikroTik and Shodan ones. |
| `agent-torvalds-cpp.py`, `agent_tool_retriever.py`, `agent_tool_selection.py`, `test_callback_events_debug.py` | The import path moved to the alias, behind a guard. |
| `pytest.ini` | `toolkits/git-toolkit/tests` added to `testpaths`. |
| `tests/test_toolkit_alias_contract.py` | The Git toolkit joined the alias contract — three new rows. |
| `tests/test_logging_cli.py` | The logger now comes from `toolkits.git_toolkit.operations`; the two new modules joined the static inspection. |
| `README.md`, `CHANGELOG.md` | The documentation. |
| `investigate/git-toolkit-module/REPORT_git_toolkit_module.md` | The report. |

**Verifying the change**

```bash
self-development/.venv/bin/python -m pytest self-development/toolkits/git-toolkit/tests -q
self-development/.venv/bin/python self-development/scripts/ci_test_gate.py
```

80 passed, and the CI gate reports **no new failure** (40 known failures,
0 new, 0 fixed) — and, because the Git toolkit had no known failures of
its own, no *fixed* one either.  That is the cleanest confirmation that
the refactoring was behaviour-neutral.

### Previous change: the math toolkit is a module

**Merged into `master` as PR #39** (merge commit `e2fce1a`, head `04ce149`).
The PR is based on `master` — not on `main` — and the merge used a **merge
commit**, never a squash, for the reason the rules below give: squashing
drops the original SHAs from `master`'s history and the next PR's diff
balloons to include every layer below it.

| Path | Change |
|------|--------|
| `toolkits/math-toolkit/operations.py` | **New.** The mathematics — the library half. No LlamaIndex import. |
| `toolkits/math-toolkit/agent_math_toolkit.py` | **New.** The adapter — the only LlamaIndex-dependent module of the toolkit. |
| `toolkits/math-toolkit/__init__.py` | **New.** The public API surface and the code-level reference to the canonical alias. |
| `toolkits/math-toolkit/README.md`, `pyproject.toml`, `py.typed` | **New.** The module documentation, the standalone distribution and the PEP 561 marker. |
| `toolkits/math-toolkit/tests/test_operations.py` | **New** (moved from `tests/test_math_toolkit.py`). Relative imports. |
| `toolkits/math-toolkit/tests/test_package_layout.py` | **New.** The layout contract — 18 checks. |
| `agent_math_toolkit.py` | **Deleted** at the project root. Git tracked it as a rename to `toolkits/math-toolkit/operations.py`. |
| `tests/test_math_toolkit.py` | **Deleted** at the project root. Git tracked it as a rename to the module-local test. |
| `toolkits/__init__.py` | The `math_toolkit` alias, the `_MATH_PACKAGE` / `_MATH_ALIAS` literals and the adapter in `_ADAPTER_MODULES`. |
| `agent-torvalds.py`, `agent-torvalds-mw.py` | The math adapter moved into the guarded block with the MikroTik and the Shodan ones. |
| `agent-torvalds-cpp.py`, `agent_tool_retriever.py`, `agent_tool_selection.py`, `test_callback_events_debug.py` | The import path moved to the alias. |
| `pytest.ini` | `toolkits/math-toolkit/tests` added to `testpaths`. |
| `tests/test_toolkit_alias_contract.py` | The math toolkit joined the alias contract — three new rows. |
| `tests/test_logging_cli.py` | The logger now comes from `toolkits.math_toolkit.operations`; the adapter joined the static inspection. |
| `tests/ci_baseline.txt` | The seven math node ids rewritten for the new path. |
| `README.md`, `CHANGELOG.md`, `docs/ci.md` | The documentation. |

**Verifying the change**

```bash
self-development/.venv/bin/python -m pytest self-development/toolkits/math-toolkit/tests -q
self-development/.venv/bin/python self-development/scripts/ci_test_gate.py
```

46 passed and the 7 known failures, and the CI gate reports **no new
failure** (40 known failures, 0 new, 0 fixed).

### Previous change: the legacy chat memory is gone

| Path | Change |
|------|--------|
| `agent_chat_memory.py` | **Deleted.** The compatibility layer over `chat_manager` — `get_chat_store()`, `get_chat_memory()`, the `chat_memory` proxy, `get_all_tools()`. |
| `chat_manager/startup.py` | `get_memory_buffer()` and `get_in_memory_buffer()`. The first returns the active session's buffer and falls back to the in-memory one; both are cached process-wide, so every caller sees the same conversation. |
| `agent-torvalds.py`, `agent-torvalds-mw.py` | The import and the six call sites; the dead `TOKEN_LIMITS`; the `--no-chat-history` help text and the deprecation notice. |
| `agent-torvalds-cpp.py` | The import and the two call sites. |
| `tests/test_logging_cli.py` | Imports `chat_manager.startup`'s logger instead of the deleted module's. |
| `chat_manager/tests/test_startup_memory.py` | **New.** 9 tests. |
| `investigate/chat-manager-remove-legacy-memory/IMPLEMENTATION_REPORT_remove_legacy.md` | **New.** What was implemented and why. |
| `chat_manager/README.md`, `README.md`, `CHANGELOG.md` | The documentation. |

**Verifying the change**

```bash
self-development/.venv/bin/python -m pytest self-development/chat_manager/tests -q
self-development/.venv/bin/python self-development/scripts/ci_test_gate.py
```

207 tests pass, and the CI gate reports **no new failure** (40 known failures, 0 new).

**Why it matters.** The legacy module had one job left after Phase B — keeping the agent's
memory alive when the database was down. The local fallback does that job properly now,
with the sessions intact instead of as one flat key. Keeping both meant two
implementations of the same idea, and the second one was the one the agent actually used
during an outage.

**Merged.** PR #37, merge commit `4e06b4e` — the top of the chat-manager stack.

### Previous work: the chat history survives a database outage

| Path | Change |
|------|--------|
| `chat_manager/storage/connector.py` | The fallback: `_prepare_sqlite_uri()`, `_resolve_fallback_uri()`, `_connect_to()`, the new `connect()`, and the `is_degraded` / `active_uri` / `degradation_reason` properties. |
| `chat_manager/manager.py` | The `fallback_uri` constructor argument, the `is_degraded` and `storage_mode` properties, and the degradation log line in `initialize()`. |
| `chat_manager/commands/cli.py` | The `Storage:` line in `\chat-info`. |
| `agent-torvalds.py`, `agent-torvalds-mw.py` | The yellow startup notice. |
| `chat_manager/tests/test_fallback.py` | **New.** 23 tests. |
| `chat_manager/tests/conftest.py` | The two new environment variables are cleared around every test. |
| `investigate/chat-manager-sqlite-fallback/IMPLEMENTATION_REPORT_sqlite_fallback.md` | **New.** What was implemented and why. |
| `chat_manager/README.md`, `README.md`, `CHANGELOG.md` | The documentation. |

**Verifying the change**

```bash
self-development/.venv/bin/python -m pytest self-development/chat_manager/tests -q
self-development/.venv/bin/python self-development/scripts/ci_test_gate.py
```

127 tests pass, and the CI gate reports **no new failure** (40 known failures, 0 new).

**Why it matters.** The investigation found the asymmetry that kept the legacy
chat memory alive: the *message* layer degraded on its own (to an in-memory
store), the *metadata* layer did not — so a database outage cost the agent its
sessions entirely, and the orchestrators fell back to the legacy single-key
buffer. The metadata layer now degrades the same way, which is the
precondition the investigation set for removing the legacy path.

### Previous work: the user can finally change their own settings

Phase A of the same investigation: the **user-settings API** and the **`\chat-user` command**,
plus the rename of `token_limit` → **`chat_token_limit`**.

| Path | Change |
|------|--------|
| `chat_manager/settings.py` | **New.** The settings, their ranges, their validation, the `UserSettings` snapshot. `UserSettings`, `SettingSpec`, `SettingError` and the `DEFAULT_/MIN_/MAX_CHAT_TOKEN_LIMIT` constants are exported from the package root. |
| `chat_manager/manager.py` | `get_user_settings()`, `update_user_settings()`, `set_chat_token_limit()`. The update drops the cached memory buffer, so a changed limit is live on the next turn (defect **C2**), and `get_memory_buffer()` now rebuilds the buffer when the effective limit differs (defect **C3**). |
| `chat_manager/user.py` | `token_limit` → `chat_token_limit`. The old name survives as a deprecated property, as a constructor keyword, and in `to_dict()`. |
| `chat_manager/storage/models.py`, `chat_manager/storage/connector.py` | The column was renamed; a SQLAlchemy `synonym` keeps the old attribute working, and `connect()` renames the column in place on an existing database. |
| `chat_manager/commands/cli.py`, `handler.py`, `__init__.py` | The `\chat-user` command: `cmd_chat_user`, `cmd_chat_user_get`, `cmd_chat_user_set`, `cmd_chat_user_help`, plus the registry entry and the dispatch branch. |
| `components/command_registry.py` | The `CommandSpec` — `\help` lists the command in both orchestrators. |
| `components/tui/chat_history_view.py` | `render_chat_user_markdown()` — the settings as a Markdown table. |
| `agent-torvalds.py`, `agent-torvalds-mw.py` | The startup hints and the command list. |
| `chat_manager/tests/test_settings.py` | **New.** 22 tests. |
| `chat_manager/tests/test_user_settings.py` | **New.** 40 tests. |
| `chat_manager/tests/test_migration.py` | **New.** 9 tests. |
| `tests/test_user_settings_command.py` | **New.** 16 tests — the integration. |
| `investigate/chat-manager-user-settings/PROPOSAL_chat_token_limit.md` | **New.** The naming proposal. |
| `investigate/chat-manager-user-settings/IMPLEMENTATION_REPORT_user_settings.md` | **New.** What was implemented and why. |
| `chat_manager/README.md`, `README.md`, `CHANGELOG.md` | The documentation. |

**Verifying the change**

```bash
self-development/.venv/bin/python -m pytest self-development/chat_manager/tests -q
self-development/.venv/bin/python -m pytest self-development/tests/test_user_settings_command.py -q
self-development/.venv/bin/python self-development/scripts/ci_test_gate.py
```

175 + 16 tests pass, and the CI gate reports **no new failure** (40 known failures, 0 new).

**The naming.** `token_limit` said the unit but not the scope, and the scope is the interesting
part — the codebase uses that word for at least three other things (the model's
`context_window`, the legacy `TORVALDS_TOKEN_LIMIT`, the dead `TOKEN_LIMITS` constant). The
canonical name is now **`chat_token_limit`**. The rename breaks nothing: the column is migrated
in place, `User.token_limit` survives as a deprecated property, and `\chat-user set token_limit
12000` still works.

### Previous work: the Shodan toolkit is a flat package

| Item | Status |
|---|---|
| Branch | `refactor/shodan-toolkit-flat-layout` — **implemented, committed** (`6920d03`) and **merged into `master`** as PR #33 |
| Scope | The Shodan toolkit's layout: the toolkit directory **is** the package. The `src/` level and the nested `shodan_toolkit/` directory are gone — every source file sits directly in `toolkits/shodan-toolkit/`, next to `tests/` and `examples/`, the same shape as the MikroTik toolkit. The import name is unchanged (`toolkits.shodan_toolkit` through the alias, `shodan_toolkit` in a standalone install). |
| Status | Implemented: the modules moved, the tests use relative imports, the alias shim points at the new path, the distribution maps the package explicitly, and a new layout contract test (`toolkits/shodan-toolkit/tests/test_package_layout.py`, 11 checks) guards the rule. The toolkit suite is green (162 passed, 2 skipped), the alias contract is green (23/23), and the full suite reports **no new failure** (the CI gate: 40 known failures, 0 new). Committed as `6920d03` ("refactor: make the Shodan toolkit a flat package") and pushed to `origin/refactor/shodan-toolkit-flat-layout` — the operator approved both the commit and the push (rule 4). Merged into `master` as PR #33 (merge commit `e3d1511`), after PR #31 (`6986111`) and PR #32 (`1fef7d3`) were merged first: the stack had to go bottom-up. |
| Policy | The `toolkits` package must be imported **before** pytest imports a module from inside a hyphenated toolkit package, or pytest's "importlib" mode loads the package twice and the import alias goes stale. `consider_namespace_packages = true` in `pytest.ini` and in the toolkit's `pyproject.toml` makes pytest resolve the name through the normal import machinery, so there is exactly one copy of the package. |

### Investigation: the chat manager's user settings and the legacy implementation

The operator asked three questions about `chat_manager`: how `user.token_limit` is changed,
whether a command to manage user settings is needed, and whether the old chat-history
implementation is still there.  The investigation is in
`investigate/chat-manager-user-settings/` — the report, an executable probe, and a
verifier that checks every `file:line` reference in the report.

**No source file of the agent was modified.**  Only the investigation folder was added.

| Question | Answer |
|----------|--------|
| How is `user.token_limit` changed? | **It cannot be.**  `ChatHistoryManager` has no user-update API; the only write path is the private `manager._db.update_user()`, and even that does not reach the live buffer, because the buffer caches the limit and is only invalidated by `switch_session()` / `clear_messages()`.  The `token_limit` argument of `get_memory_buffer()` is ignored on every call after the first. |
| Is a user-settings command needed? | **Yes.**  The design documents call `users` the home of the user's *preferences*, but no command reads or writes them, and the current limit is not even displayed.  The `\chat-*` layer is the right shape for it: dispatched before the LLM, so it costs no tokens. |
| Is the old implementation still there? | **Yes, in four layers** — `agent_chat_memory.py` (273 lines, with the raw-`PostgresChatStore` path), the `--no-chat-history` flag in both orchestrators, the `TORVALDS_CHAT_KEY` migration hook in the manager, and the dead `TOKEN_LIMITS` constant in both orchestrators (four competing defaults: 400 / 10000 / 5000 / 5000). |

**The legacy implementation cannot be deleted yet.**  The message layer degrades on its own
(`SimpleChatStoreBackend`), but the **metadata** layer does not: when PostgreSQL is
unreachable, `initialize()` raises `RuntimeError: CustomDBConnector is not connected` and the
orchestrators fall back to the legacy single-session memory.  The removal therefore waits for
a SQLite fallback in `CustomDBConnector` — the manager already runs on SQLite, because the
whole test suite does.

| Phase | Scope | State |
|-------|-------|-------|
| **A** | The user-settings API and the `\chat-user` command | **implemented and merged** — PR #35, merge commit `eaeb20e` |
| **B** | The SQLite fallback in `CustomDBConnector` | **implemented and merged** — PR #36, merge commit `fc86a48` |
| **C** | The removal of the legacy implementation | **implemented and merged** — PR #37, merge commit `4e06b4e` |

> **Update — the stack is merged.** The paragraph above is the investigation's conclusion
> *at the time*; it no longer holds. The legacy implementation **has** been removed, and
> the removal was safe because Phase B's fallback shipped first. `master` is `4e06b4e`.

**Phase A closed four of the nine defects:** C1 (no public API), C2 (the changed limit never
reached the live buffer), C3 (the `get_memory_buffer()` override was silently dropped) and C4
(no command read or wrote the settings). C7 is closed *partly* — the manager's limit is now
`users.chat_token_limit`, and the name says which of the four competing defaults it is; the
the dead `TOKEN_LIMITS` constants and the legacy `TORVALDS_TOKEN_LIMIT` are Phase C. C5, C6, C8 and
C9 were untouched at that point — they belonged to the legacy implementation, which was still
load-bearing.

**The stack closed the rest.** Phase B closed **C8** (the metadata layer got the same
fallback the message layer already had). Phase C closed **C5**, **C6** and **C9**, and took
**C7** as far as it goes: the dead `TOKEN_LIMITS` constant is gone from both orchestrators,
so the four competing defaults collapse to the single documented `chat_token_limit`, with
`TORVALDS_TOKEN_LIMIT` surviving as one legacy override in `chat_manager/startup.py`.

Nine defects were catalogued (C1–C9) with their locations, the risks and the full removal
checklist are in `investigate/chat-manager-user-settings/INVESTIGATION_REPORT.md`.

**Verifying the investigation**

```bash
self-development/.venv/bin/python investigate/chat-manager-user-settings/probe_user_settings.py
self-development/.venv/bin/python investigate/chat-manager-user-settings/verify_report_references.py
```

The probe needs no database server.  The reference check reports **PASS** — 28 distinct
`file:line` references, each resolving to the claimed construct.  The `chat_manager` suite
is green (104 passed) and is the regression baseline for the work that follows.

### Latest change: the Shodan toolkit is a flat package

Committed as `6920d03` ("refactor: make the Shodan toolkit a flat package")
on the branch `refactor/shodan-toolkit-flat-layout`, pushed to
`origin/refactor/shodan-toolkit-flat-layout`, and merged into `master` as
PR #33 (merge commit `e3d1511`).

### Merge order for the chat-manager stack

The chat-manager work is a **stacked PR** chain too, and the order is forced:

| # | Branch | Base | Merge commit |
|---|---|---|---|
| #35 | `feature/chat-user-settings` | `master` | `eaeb20e` |
| #36 | `feature/chat-manager-sqlite-fallback` | `feature/chat-user-settings` | `fc86a48` |
| #37 | `feature/chat-manager-remove-legacy-memory` | `feature/chat-manager-sqlite-fallback` | `4e06b4e` |

**Status: merged.** The stack landed in `master` bottom-up: `eaeb20e` (#35), `fc86a48`
(#36), `4e06b4e` (#37). The **Base** column records the branch each PR was *opened
against*; every PR was retargeted to `master` before it was merged, so each merge commit
brought in one layer only. Each merge result tree is byte-identical to the CI-validated
head tree of the branch it merged — the merge introduced no untested content.

**Bottom-up: 35, then 36, then 37.** The order is not a preference — it is what the
work *is*. #36 adds the local fallback, and #37 removes the legacy path on the
strength of it: without the fallback, a database outage would leave the agent with
no memory at all, because the thing that used to catch the outage is the thing
#37 deletes. Merging #37 first would land a removal whose safety net is not in
`master` yet.

Each PR's base is retargeted to `master` **after** the PR below it has been merged,
then merged with a **merge commit** — never a squash, for the same reason as the
toolkit stack: squashing drops the original SHAs from `master`'s history and the
next PR's diff balloons to include every layer below it.

### Merge order for the toolkit refactor stack

The toolkit refactor is a **stacked PR** chain, and the order is forced:

| # | Branch | Base | Merge commit |
|---|---|---|---|
| #31 | `fix/toolkit-alias-reference` | `master` | `6986111` |
| #32 | `refactor/toolkit-adapter-location` | `fix/toolkit-alias-reference` | `1fef7d3` |
| #33 | `refactor/shodan-toolkit-flat-layout` | `refactor/toolkit-adapter-location` | `e3d1511` |

**Bottom-up: 31, then 32, then 33.** Merging #33 first would drag #31 and
#32's commits into `master`, leave those two PRs empty, and break #32's base
branch. To land them all in `master`, each PR's base is retargeted to
`master` **after** the PR below it has been merged, then merged with a
**merge commit** (never squash: squashing drops the original SHAs from
`master`'s history, the next PR's merge base moves back to `ca17d8a`, and its
diff balloons to include all three layers).

Merge commits were used for a second reason: the merge result tree must equal
the tree the CI gate already validated. With merge commits, `master`'s tree
after #33 (`37bde2d`) is byte-identical to the head tree of `26a7f0e` that
CI ran green — the merge introduces no untested content.

The toolkit used to be a project folder that held the package one level
down (`src/shodan_toolkit/`, then `shodan_toolkit/`). It is now the
package itself: `toolkits/shodan-toolkit/` holds `__init__.py`,
`__main__.py`, `agent.py`, `agent_shodan_toolkit.py`, `cli.py`,
`client.py`, `config.py`, `parsers.py`, `runner.py` and `tools.py`, next to
`tests/` and `examples/`. The import name did not change, and neither did
the wheel: `pip install ./toolkits/shodan-toolkit` still produces the
`shodan_toolkit` package with the same ten modules, the same console
script and the same `python -m shodan_toolkit` entry point.

### Latest change: a timeout the model can see

Committed as `2acce6d` ("fix: a timeout the model can see") and pushed to
`origin/fix/hitl-question-detection`.

The operator stated the timeout policy: *"-1 means stop and wait; a finite
timeout means wait, and when it expires act on your own judgement."*  The
plumbing already honoured it — but the **model** was fed the fallback answer
as if the human had said it, and with the shipped default (no fallback
answer) it was fed an empty turn, which for a yes/no question reads as a
"no".  The agent therefore acted on a fabricated answer instead of on its own
judgement.  `HITLFunctionAgent._answer_message()` now tells the model that
nobody answered.

### Previous change: a decorated question is asked as the question it is

The operator reported it a third time
(`/home/kbush/torvald-log/hitl_questions_issue/wrong-user-input.txt`): a
question with three choices was prompted with `[y/N]`. The agent had written
the question as `question: 'Which one should I use?'` — the quotes and the
label kept the "which" out of the head of the question, so the "should I"
*inside* it turned the question into a confirmation.

| Path | Change |
|---|---|
| `components/hitl_question.py` | `_question_core()` — the question is read (and shown) without the quotes, the Markdown emphasis and the label that wrap it. The wh-word veto also fires when the question word heads a *clause* ("so which one should I use?"). |
| `components/human_loop_handler.py` | The history records the type the operator was asked for: the options travel with the question. |
| `scripts/hitl_question_bank.py` | Six new cases: five catch the defect, one guards the fix against being too broad (a relative clause stays a yes/no question). 17 → 23. |
| `tests/test_hitl_question_presentation.py` | New `TestDecoratedQuestion` — 9 tests, 6 of which fail without the fix. |
| `investigate/hitl-questions-issue/diag_decorated_question.py` | **New.** The diagnostic: 8 mis-classifications before the fix, 0 after. |
| `investigate/hitl-questions-issue/verify_hitl_question_presentation.py` | The new invariant I9 — a decorated question is not a yes/no question. 8 → 9 invariants. |
| `investigate/hitl-questions-issue/IMPLEMENTATION_REPORT_question_prompt.md` | Section 9 — the third round. |
| `CHANGELOG.md` | The entry. |

Committed as `ab3fbb9` ("fix: a decorated question is asked as the question it
is") and pushed to `origin/fix/hitl-question-detection`.

**Verifying the change**

```bash
self-development/.venv/bin/python -m pytest self-development/tests/test_hitl_question_bank.py -q
self-development/.venv/bin/python investigate/hitl-questions-issue/diag_decorated_question.py
self-development/.venv/bin/python investigate/hitl-questions-issue/verify_hitl_question_presentation.py
```

23 bank cases, 9 invariants, 0 mis-classifications. The CI gate reports
**no new failure** (40 known failures, unchanged).

### Previous change: what the operator actually sees

The question, the report and the menu — the first round was judged on the
rules, the second on the screen. The three defects the screen showed (the
question printed twice, two numbered lists with one meaning, the choices
coming before the question) are closed; the report is section 8.

### Earlier change: the Shodan toolkit

The `shodan-toolkit` project, which lived in its own repository, was moved
into this one and turned into a first-class toolkit.

**The move.** The commits were transplanted with `git subtree`, so the
history is preserved rather than squashed:

```
*   Add 'toolkits/shodan-toolkit/' from commit '26b1fb2...'
|\
| * 26b1fb2 chore: remove project-root RULES.md
| * 72b3239 fix: correct Shodan CLI argument vectors and harden library packaging
| * 6d33069 Initial commit: shodan-toolkit
* b068337 fix: make the HITL timeout default to "no timeout" (wait for the user) (#23)
```

Every file under `toolkits/shodan-toolkit/` has the same blob hash as in the
upstream repository, so the upstream project stays the source of truth and
`git subtree pull` can bring in later work. The upstream repository is
registered as the remote `shodan-local`.

**The integration.** The toolkit is wired into every load path, exactly like
the MikroTik toolkit:

| Path | Change |
|---|---|
| `toolkits/shodan-toolkit/` | The upstream project, verbatim. |
| `toolkits/__init__.py` | Registers the alias `toolkits.shodan_toolkit` next to `toolkits.mikrotik_routeros`. |
| `toolkits/shodan-toolkit/agent_shodan_toolkit.py` | The LlamaIndex adapter, a submodule of the toolkit package. Re-uses the upstream tool functions verbatim; only the descriptions are rewritten so they carry `Category: Security`. |
| `agent_tool_retriever.py` | New `include_shodan_tools` flag (on by default). |
| `agent_tool_selection.py` | The tools are discovered for the startup menu, and dedicated action patterns were added. |
| `agent-torvalds.py`, `agent-torvalds-mw.py` | The tools are loaded in the full-inventory mode. |
| `docs/shodan-toolkit.md` | The end-user reference. |
| `toolkits/shodan-toolkit/tests/test_agent_adapter.py` | 19 tests for the adapter. |
| `pytest.ini` | `toolkits/shodan-toolkit` on the path; the upstream suite added to `testpaths`. |
| `README.md`, `CHANGELOG.md` | The toolkit is documented. |

**Read-only by default.** The four tools that change account state or
consume credits (alerts, scans, downloads) are not exposed. The opt-in is
`TORVALDS_SHODAN_ALLOW_MUTATING=1`, which the adapter reads itself, so the
retriever, the `--select` menu and both orchestrators behave identically.
`shodan_raw` cannot be used to bypass the split: the toolkit screens the
subcommand and refuses the mutating ones.

**Verifying the change**

```bash
self-development/.venv/bin/python -m pytest self-development/toolkits/shodan-toolkit/tests -q
self-development/.venv/bin/python -m pytest self-development/toolkits/shodan-toolkit/tests/test_agent_adapter.py -q
```

19 tests and 152 tests pass. The whole suite is part of the standard
`pytest` run.

**Every Shodan test lives under `toolkits/shodan-toolkit/tests/`.** The
adapter suite used to sit in `tests/test_shodan_toolkit.py`, next to the
other repository-level suites; it is now
`toolkits/shodan-toolkit/tests/test_agent_adapter.py`, so the feature is
tested from one directory. The file skips itself when the toolkit is used
as a standalone library, because the agent-side modules it needs are not
part of that distribution.

### Latest change: the Shodan tools in the selection menu

The Shodan toolkit was already wired into `_discover_tools()`, so the
**Security** category showed up in the `--select` menu - but nothing
locked that down. The MikroTik toolkit had lost its **Network** category
the same way once, so the Shodan tools are now covered by the same kind of
regression suite.

| Path | Change |
|---|---|
| `tests/test_tool_selection_menu.py` | New `TestSecurityCategory`, `TestSecurityCategoryDescription` and `TestSelectingSecurity` suites: the category must exist, hold exactly the twelve read-only tools, be selectable through `select_tools_by_category()` and through the interactive prompt, and be rendered in the menu. The four write-capable tools must stay out unless the opt-in is set. |
| `tests/test_tool_selection_menu.py` | `TestMenuParity` now checks that the Shodan tools are reachable through every load path (menu, retriever, both orchestrators). |
| `agent_tool_selection.py` | `shodan_myip` did not match any action pattern and fell through to the raw first word, so the summary read `Actions: discover, inspect, diagnose, get, execute`. It is now `inspect`. |
| `toolkits/shodan-toolkit/tests/test_agent_adapter.py` | An autouse fixture removes `TORVALDS_SHODAN_ALLOW_MUTATING`, so the suite no longer fails for a developer who has the opt-in exported. |
| `docs/shodan-toolkit.md` | New *Selecting the tools* section. |

**Verifying the change**

```bash
self-development/.venv/bin/python -m pytest self-development/tests/test_tool_selection_menu.py -q
self-development/.venv/bin/python -m pytest self-development/toolkits/shodan-toolkit/tests/test_agent_adapter.py -q
```

30 tests and 19 tests pass, with and without the opt-in exported.

### Previous work: the HITL timeout is now "no timeout" by default

| Branch | `feature/docs/ollama-local-setup` (off `master`, `b068337`) |
| Scope | Document and enable the local Ollama setup: install Ollama, pull the models, run the agent |
| Status | Implemented, verified against a live Ollama server, **committed** (`3398cdb`) and pushed to `origin/feature/docs/ollama-local-setup` |

### Latest change: the local LLM setup is documented end to end

The agent has no cloud fallback: it serves the chat model and the embedding
model from a local Ollama instance, but the README only mentioned Ollama as
"optional, for on-demand tool retrieval with embeddings". That was wrong —
Ollama *is* the LLM backend — and there was no instruction anywhere for
installing it, pulling the models or pointing the agent at them.

| Path | Change |
|---|---|
| `README.md` | New **"Local LLM Setup (Ollama)"** section: install (Linux/macOS/Windows/Docker), verify the server, pull the chat and the embedding model, configure `TORVALDS_MODEL` / `TORVALDS_OLLAMA_HOST`, run the agent, hardware sizing and a troubleshooting matrix. The installation steps now include the Ollama install and the two `ollama pull` commands, and Ollama moved to **required** in the prerequisites. |
| `docs/ollama-setup.md` | **New.** The long form of the guide: architecture, the full environment-variable reference, the model catalogue with hardware sizing, a three-step verification of the whole chain and the housekeeping commands. |
| `components/ollama_config.py` | **New.** `get_ollama_base_url()` resolves the endpoint: `TORVALDS_OLLAMA_HOST` → `OLLAMA_HOST` → `http://localhost:11434`, normalising a bare `host:port` into a full URL. |
| `agent-torvalds.py`, `agent-torvalds-mw.py` | The chat model is created with `base_url=OLLAMA_BASE_URL`. |
| `agent_tool_retriever.py` | The embedding model is created with `base_url=get_ollama_base_url()`. |
| `CHANGELOG.md` | Entry for the documentation and the new configuration variable. |

The default behaviour is unchanged: with nothing configured the agent still
talks to `http://localhost:11434`, which is where a standard Ollama install
listens.

### Verifying the change

The chain was checked against a live local Ollama 0.33.2 server:

```bash
# chat model
curl http://localhost:11434/api/generate -d '{"model":"richardyoung/qwen3.6-27b-abliterated:Q4_K_M","prompt":"Reply with exactly: OK","stream":false}'
# embedding model
curl http://localhost:11434/api/embeddings -d '{"model":"nomic-embed-text","prompt":"hello world"}'
```

Both answer, and the agent's own client returns `OK` for the chat model and a
768-dimension embedding for `nomic-embed-text`.

### Previous work: the HITL "no timeout" default

| Item | Status |
|---|---|
| Branch | `feature/hitl-no-timeout` (off `master`, `1736839`) |
| Scope | HITL: no timeout by default — the agent waits for the user |
| Status | Implemented, tests green, **committed** and pushed to `origin/feature/hitl-no-timeout` |

#### Latest change: the HITL timeout is now "no timeout" by default

The Human-in-the-Loop timeout used to default to 30 seconds, so the agent
gave up on the user and fell back to the default answer. The default is
now **`-1`, meaning "no timeout"**: the agent waits for the answer
constantly, for as long as the human needs.

The value was also corrupted on its way to the prompt in four different
places, each of which turned "wait forever" into a short wait:

| Place | What was wrong | Fix |
|---|---|---|
| `timeout_manager.py`, `console_input_module.py`, `whiptail_input_module.py` | `asyncio.wait_for()` expires **immediately** for any value `<= 0` | `normalize_timeout()` turns `-1` into the `None` asyncio calls "forever" |
| `human_loop_handler.py` | `max(1, default_timeout)` turned `-1` into 1 second | the value is kept as-is |
| `hitl_agent.py` | the step padded the timeout with `timeout=timeout + 5`, which would have turned `-1` into a 4 second deadline | the grace period now only applies to a finite timeout |
| `tui/state_bridge.py` | counted down from a negative value and showed `0s` | no countdown is shown when there is no timeout |

| Path | Change |
|---|---|
| `components/hitl_timeout.py` | **New.** The single source of truth: `NO_TIMEOUT`, `normalize_timeout()`, `is_no_timeout()`, `validate_timeout()`, `describe_timeout()`. |
| `components/timeout_manager.py` | Default `-1`; `-1` accepted; `wait_for()` gets `None`. |
| `components/console_input_module.py` | Default `-1`; `prompt_with_status()` and `password()` translate it. |
| `components/whiptail_input_module.py` | Default `-1`; `prompt()`, `confirm()` and `menu()` translate it. |
| `components/hitl_events.py` | `AgentQuestionEvent.timeout` defaults to `-1`; `validate()` accepts it. |
| `components/human_loop_handler.py` | Default `-1`; the `max(1, ...)` clamp is gone. |
| `components/hitl_agent.py` | Default `-1`; `wait_for_event()` gets `timeout=None`. |
| `components/event_consumer.py` | Default `-1`. |
| `components/tui/state_bridge.py`, `components/tui/tui_app.py` | Default `-1`; no countdown; the status shows `none`. |
| `agent-torvalds.py`, `agent-torvalds-mw.py` | `TORVALDS_HITL_TIMEOUT` defaults to `-1`; `--hitl-timeout` defaults to `-1`; the banner shows `none`. |
| `toolkits/MikroTik-RouterOS/agent_mikrotik_toolkit.py`, `project_manager/agent_project_manager_toolkit.py` | The two remaining places that read `TORVALDS_HITL_TIMEOUT` directly. |
| `tests/test_hitl_no_timeout.py` | **New.** 28 tests. |
| `README.md`, `CHANGELOG.md` | The convention is documented. |

### Verifying the change

```bash
self-development/.venv/bin/python -m pytest self-development/tests/test_hitl_no_timeout.py -q
```

28 passed, and the dedicated check
`investigate/hitl-investigate/verify_hitl_no_timeout.py` reports 12/12.

The full suite shows **no new failures** against the baseline: the failure
set at `HEAD` (`1736839`) and after the change is byte-identical —
77 pre-existing failures, unchanged (76 failed + 1 error).

### Earlier work: the MikroTik RouterOS toolkit

| Item | Status |
|---|---|
| Branch | `feature/mikrotik-routeros-toolkit` (off `master`, `b1ec326`) |
| Scope | MikroTik RouterOS toolkit implementation |
| Plan | `investigate/MikroTik-RouterOS/IMPLEMENTATION_PLAN.md` |
| Proposal | `investigate/MikroTik-RouterOS/PROPOSAL_mikrotik_toolkit.md` |
| Investigation | `investigate/MikroTik-RouterOS/INVESTIGATION_REPORT.md` |
| Specification | `investigate/MikroTik-RouterOS/MODULE_SPECIFICATION.md` |
| Phases | 0-5 implemented. Only the real-router validation (precondition P6) is outstanding - it needs a physical router or a CHR image, and MikroTik's download server is unreachable from this environment. |

### Latest change: the MikroTik tools in the selection menu

The toolkit was fully wired into the retriever and into both
orchestrators, but `agent_tool_selection._discover_tools()` - the one
function that builds the `--select` menu - never imported the adapter, so
the **Network** category was missing from the menu. Fixed, together with
the action summary (the RouterOS path `/ip/firewall/filter` was matched by
the data-analysis `filter` pattern) and locked down by
`tests/test_tool_selection_menu.py`.

| Path | Change |
|---|---|
| `agent_tool_selection.py` | The MikroTik adapter is imported by `_discover_tools()`; dedicated **Network** action patterns were added. |
| `tests/test_tool_selection_menu.py` | New regression suite for the menu inventory and the **Network** category. |
| `docs/mikrotik-toolkit.md` | New section 4.1 *Selecting the tools*. |
| `README.md`, `CHANGELOG.md` | The **Network** category is documented. |

### Where the code lives

| Path | Role |
|---|---|
| `toolkits/MikroTik-RouterOS/` | The core package. No LlamaIndex imports; importable as `toolkits.mikrotik_routeros`. |
| `toolkits/MikroTik-RouterOS/agent_mikrotik_toolkit.py` | The LlamaIndex adapter - the eight tools. A submodule of the toolkit package. |
| `components/mikrotik_commands.py` | The `\routers` / `\router-*` interactive commands. |
| `docs/mikrotik-toolkit.md` | The operator documentation. |
| `mikrotik_targets.yaml.example` | The annotated target file. The real one is git-ignored. |

### Verifying the contracts

```bash
self-development/.venv/bin/python \
    self-development/investigate/MikroTik-RouterOS/verify_layout_contract.py
self-development/.venv/bin/python \
    self-development/investigate/MikroTik-RouterOS/verify_test_contract.py
```

Both must report a full pass (20/20 and 13/13).
