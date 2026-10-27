# The APT toolkit is a module

**Branch:** `refactor/apt-toolkit-module`
**Base:** `master` (`b55f9c1`)

The APT toolkit was a single loose module at the project root,
`agent_apt_toolkit.py`, next to the other `agent_*.py` files, while the
features that were already modules lived in folders under `toolkits/`.
This change makes it a module like the rest of the series.

```
agent_apt_toolkit.py  ->  toolkits/apt-toolkit/operations.py
                     ->  toolkits/apt-toolkit/agent_apt_toolkit.py
                     ->  toolkits/apt-toolkit/cli.py
```

---

## 1. The state before

The toolkit carried thirteen operations and one adapter in one file:

| Operation | What it does |
|-----------|--------------|
| `find_package_for_command(command)` | resolve a command to the package that provides it |
| `check_command_exists(command)` | is the command on the `PATH`? |
| `set_default_prompt_method(method)` | choose the default password prompt method |
| `get_default_prompt_method()` | the current default password prompt method |
| `_has_tty()` | is there a terminal to draw a dialog on? |
| `prompt_sudo_password(method="auto", ...)` | obtain the sudo password |
| `_prompt_console_password(result, max_attempts)` | the console prompt |
| `_prompt_whiptail_password(result, max_attempts, ...)` | the whiptail prompt |
| `test_sudo_password(password)` | is the password valid? |
| `clear_sudo_cache()` | forget the cached password |
| `install_package(package_name, ...)` | install one package |
| `install_multiple_packages(package_names, ...)` | install several, in order |
| `interactive_install_missing_command(command, ...)` | detect, resolve, install |

plus `get_all_tools()`, which turned ten of them into LlamaIndex
`FunctionTool` objects, and a `__main__` block with the command-line
interface.

### The call sites

Four places imported it:

| File | Import |
|------|--------|
| `agent-torvalds.py` | `from agent_apt_toolkit import get_all_tools as get_apt_tools` |
| `agent-torvalds-mw.py` | `from agent_apt_toolkit import get_all_tools as get_apt_tools` |
| `agent_tool_retriever.py` | `from agent_apt_toolkit import get_all_tools as _get_apt` |
| `agent_tool_selection.py` | `from agent_apt_toolkit import get_all_tools as _get_apt` |

**All four imported it unguarded.**  A broken or missing toolkit was a
failed boot.  Every toolkit already under `toolkits/` was imported behind
a guard, so the APT toolkit was one of the last holdouts of the old
arrangement.

---

## 2. The decision: split the file, do not just move it

The file carried three different things, and the series has one rule for
the first two: the **library half** carries no LlamaIndex import, the
**adapter** is the one module that knows about the agent framework.

| Module | Role | LlamaIndex | Third party |
|--------|------|------------|-------------|
| `operations.py` | the 13 package, sudo and install operations | **no** | `rich` |
| `agent_apt_toolkit.py` | the adapter — `get_all_tools()` | **yes** | `llama-index-core` |
| `cli.py` | the command-line interface | **no** | — |

### This toolkit's library half is *not* dependency-free

The OS and the Linux toolkit were built on the **standard library only**,
and their layout contracts pin that exact set.  The APT toolkit cannot
make the same claim, and the difference is worth stating plainly:

| Import | Where | Needed for | Without it |
|--------|-------|-----------|------------|
| `rich` | `_prompt_console_password` | the **console** password prompt — the default prompt method | the prompt fails with an error message |
| `components.whiptail_password` | `_prompt_whiptail_password` | the **whiptail** terminal dialog | the prompt falls back to the console one |

Both imports are **deferred to the call** and both are guarded, so the
module imports cleanly without either of them, and neither failure takes
the agent down.  The layout contract pins the exact set, so a new
dependency cannot slip in unnoticed.

`components.whiptail_password` is a module of **this** repository, not of
the distribution — so a standalone install of the package has no whiptail
dialog, and the documented fallback applies.  Moving that module into the
toolkit would have been a change to `components/whiptail_input_module.py`
and `components/__init__.py` as well, which belongs in its own change.

### The error contract

Every operation **reports** a failure; none of them raises.  A package
that cannot be resolved comes back with `success: False` and the reason
in `error`; a command that is not on the `PATH` comes back with
`exists: False`.

---

## 3. The hyphen, and the alias

The directory name contains a hyphen, which is not a valid Python
identifier, so the package is reached through the alias that
`toolkits/__init__.py` registers:

```python
from toolkits.apt_toolkit import install_package
from toolkits.apt_toolkit.agent_apt_toolkit import get_all_tools
```

The alias is a **literal** in the shim, not a computed one:

```python
_APT_PACKAGE = "toolkits.apt-toolkit"
_APT_ALIAS = "toolkits.apt_toolkit"
```

That matters for the same reason it matters for the other seven: a
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
    from toolkits.apt_toolkit.agent_apt_toolkit import (
        get_all_tools as get_apt_tools,
    )
except ImportError:  # pragma: no cover - the toolkit is optional

    def get_apt_tools() -> list:
        """The APT toolkit is unavailable - expose no tools."""
        return []
```

The APT toolkit was **mandatory** before this change.  It is optional
now.

---

## 5. The command-line interface

The interface used to be an `if __name__ == "__main__":` block at the
bottom of the module.  It is `toolkits/apt-toolkit/cli.py` now, with the
package as its entry point:

```bash
python -m toolkits.apt_toolkit --show-method
python -m toolkits.apt_toolkit --prompt-method whiptail
```

The options, the output and the exit codes are unchanged.  The one line
that had to change is the example in the help text, which named the file
the interface used to live in — that file does not exist any more.

The interface is part of the library half and carries **no** LlamaIndex
import, which matters: the shim imports it eagerly, so a LlamaIndex
import in it would pull the framework into every process that imports
`toolkits`.

---

## 6. The split was checked mechanically

The descriptions of the ten tools are behaviour: they are what the
retriever matches against and what the model reads.  So is the order of
the tools, the signatures, the docstrings and the error contract.  So is
the command-line interface.

`investigate/apt-toolkit-module/verify_split.py` compares the *committed*
original with the new files, by AST:

* the thirteen operation names, their order, their signatures, their
  docstrings and their bodies;
* the ten tool names, their order and their descriptions;
* the command-line interface: the description, the epilog, the options
  and the printed messages;
* the LlamaIndex boundary.

The original is **found, not assumed**.  It is the file as it was
committed before it was deleted, so the check asks git where that still
lives: a named ref that still carries the file (`master`,
`origin/master`, …), and otherwise the parent of the commit that deleted
it.  A hard-coded `master` would be a trap — a CI checkout is a
detached HEAD without that branch.

**The check caught a drift of my own.**  The `--show-method` help text
read "Show the current default **password** prompt method and exit" in
the new CLI, while the original said "Show the current default prompt
method and exit".  I had "improved" the wording.  The check compared the
two and refused to pass — which is the whole reason for having it.

**And the check had a hole of its own.**  The first cut of the split lost
*every* section header of the module — the `# 1. Package Resolution`
rules and the rest.  The script that cut the file took the code by AST
node range, and the comments around it were not part of any node, so
they fell on the floor.  Nothing in the check noticed, because the check
did not look at them.

The headers are the reader's map of the file, and they belong to the code
they head, so they are now part of the comparison: the six section
headers of the original have to be distributed over the three new files,
in order, with none missing and none renumbered.  Two more drifts were
added to the test of the check for that.

**And the check had a hole of its own.**  The first cut of the split lost
*every* section header of the module — the `# 1. Package Resolution`
rules and the rest.  The script that cut the file took the code by AST
node range, and the comments around it were not part of any node, so
they fell on the floor.  Nothing in the check noticed, because the check
did not look at them.

The headers are the reader's map of the file, and they belong to the code
they head, so they are now part of the comparison: the six section
headers of the original have to be distributed over the three new files,
in order, with none missing and none renumbered.  Two more drifts were
added to the test of the check for that.

---

## 7. The check is now a test

A check that has never failed proves nothing, and a check that is only
run by hand proves less.  `toolkits/apt-toolkit/tests/test_split_verification.py`
drives the checker with **fifteen deliberate drifts**:

| Drift | Caught by |
|-------|-----------|
| a reworded tool description | the description comparison |
| a changed parameter default | the signature comparison |
| a dropped docstring | the docstring comparison |
| a changed body | the body comparison |
| two operations swapped | the order comparison |
| a LlamaIndex import in the library half | the boundary comparison |
| a tool that went missing | the tool-surface comparison |
| an operation that went missing | the set comparison |
| a reworded command-line option | the interface comparison |
| narrowed command-line choices | the interface comparison |
| a reworded command-line message | the interface comparison |
| a dropped command-line option | the interface comparison |
| a lost section header | the section-header comparison |
| a renumbered section header | the section-header comparison |
| a lost module-level comment | the comment comparison |

All fifteen are caught.

---

## 8. The verification

**104 tests** in the toolkit suite — 44 operations tests, 37 layout
contract checks and 19 split-verification tests — and the CI gate reports
**no new failure**: 40 known failures, 0 new, 0 fixed.

The alias contract is green as well: **75 passed** (it was 58; the APT
toolkit joined it with seven new rows, and the `__main__` rule added ten
more).

### The tool menu is unchanged

The tool menu was dumped from `master` and from the branch — the names,
their order and their descriptions — and the two are **byte-identical**
(155 tools, 154 distinct names).  The move changed where the tools live,
not what the model sees.

### The four known failures carried over

The suite had **four** known failures before the move, and it has the same
four after it.  Only the path of the test file changed, and
`tests/ci_baseline.txt` was rewritten to match — exactly as the math
toolkit's move did with its seven.

They are worth naming, because none of them is a defect of the toolkit:

| Test | What is actually wrong |
|------|------------------------|
| `TestGetAllTools::test_returns_list_of_tools` | asserts `len(tools) == 8`; the toolkit registers **10**.  `set_default_prompt_method` and `get_default_prompt_method` were added to the toolkit without the assertion being updated. |
| `TestGetAllTools::test_tool_names` | the same drift: the expected set still has eight names, and the error message names the two that are missing from it. |
| `TestInteractiveInstallMissingCommand::test_full_workflow_success` | the mock's `side_effect` list has **four** returns, but the workflow calls `check_command_exists` only **twice** — `install_package` is itself mocked out, so its own pre- and post-checks never happen.  The second element of the list is therefore consumed by the *final* check, and `command_available` comes back `False`. |
| `test_sudo_password` | a **collection error**.  The suite imports the operation `test_sudo_password` into its own namespace, and pytest collects every module-level name that starts with `test_` — *including imported ones*.  The operation takes a `password` argument, so pytest treats it as a test asking for a fixture named `password`: `fixture 'password' not found`. |

All four are **pre-existing** and they are **documented** rather than
invisible now.  Fixing them belongs in its own change, where the change
is the change.

---

## 9. Three things found along the way

**`python -m <toolkit>` was broken — for the Shodan toolkit too.**  The
alias shim publishes every submodule of a toolkit under the toolkit's
alias, so that both spellings resolve to one module object.  It skipped
the agent adapters, because they import LlamaIndex.  It did **not** skip
the `__main__` modules.

A `__main__` module is meant to be **executed**, not imported.  Publishing
one puts it in `sys.modules`, and `runpy` then refuses to execute it:

```
RuntimeWarning: 'toolkits.shodan_toolkit.__main__' found in sys.modules
after import of package 'toolkits.shodan_toolkit', but prior to execution
of 'toolkits.shodan_toolkit.__main__'
```

The Shodan toolkit has carried a `__main__.py` since it was moved into
this repository, and `python -m toolkits.shodan_toolkit` has been broken
ever since.  The APT toolkit's move ran into the same wall, because it
wanted an entry point of its own.

The shim skips the `__main__` modules now, the way it already skipped
the adapters, and the alias contract has a new class for the rule.  Both
entry points work again.

**The `collect_ignore` in `pytest.ini` never worked.**  It named
`agent_apt_toolkit.py`, and it was there to keep pytest from collecting
the toolkit's `test_sudo_password` operation as a test.  But
`collect_ignore` is **not** a pytest ini option — it belongs in a
`conftest.py` — so pytest warned "Unknown config option: collect_ignore"
on every run and ignored it.  Running `pytest agent_apt_toolkit.py`
collected the operation anyway, with and without the option.

The option is gone, and the comment says why.  The source module is not
collected because it is not in `testpaths`, which is the protection every
other toolkit relies on.  The hazard itself — an operation whose name
starts with `test_` — is unchanged, and it is now the fourth known
failure above.

**A pre-existing inconsistency in the CLI's help text.**  The
`--show-method` option says "Show the current default **prompt** method",
while the tool of the same name says "Get the current default **password**
prompt method".  The move preserved it verbatim — the split check
compares the help texts, and "fixing" it would have failed the check.
The inconsistency is in the original, and it belongs in its own change.

---

## 10. One thing that changed on purpose

The logger's name moved from `agent_apt_toolkit` to
`toolkits.apt-toolkit.operations`, because that is what
`logging.getLogger(__name__)` does when the module moves.  The adapter
re-exports it, so the toolkit still logs through one logger, as the
single module did.

`tests/test_logging_cli.py` was updated to import the new logger, and the
two new modules joined the static inspection that looks for a duplicate
`basicConfig` call.

---

## 11. What is left

The remaining loose toolkits are `agent_windows_toolkit.py`,
`agent_db_toolkit.py`, `agent_xlsx_toolkit.py` and
`agent_data_analysis_toolkit.py`.

The Windows toolkit is the natural next one: it carries the same six
PowerShell operations under the same names as the Linux toolkit, and the
two are loaded on different platforms, so exactly one of them is ever in
the menu.
