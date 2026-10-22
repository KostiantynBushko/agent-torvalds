# Self-Development Rules

These rules govern how the Torvalds agent modifies its own codebase. They are
**persisted here** so that they survive across sessions and are available to any
future agent invocation.

**Last updated:** 2026-10-22

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

---

## Current self-development work

| Item | Status |
|---|---|
| Branch | `feature/shodan-toolkit` (off `master`, `b068337`) |
| Scope | Shodan internet-exposure toolkit — the project moved into `toolkits/shodan-toolkit/` and wired into the agent |
| Status | Implemented, tests green, **committed** on the branch. Push pending operator approval |

### Latest change: the Shodan toolkit

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
| `agent_shodan_toolkit.py` | The LlamaIndex adapter. Re-uses the upstream tool functions verbatim; only the descriptions are rewritten so they carry `Category: Security`. |
| `agent_tool_retriever.py` | New `include_shodan_tools` flag (on by default). |
| `agent_tool_selection.py` | The tools are discovered for the startup menu, and dedicated action patterns were added. |
| `agent-torvalds.py`, `agent-torvalds-mw.py` | The tools are loaded in the full-inventory mode. |
| `docs/shodan-toolkit.md` | The end-user reference. |
| `toolkits/shodan-toolkit/tests/test_agent_adapter.py` | 19 tests for the adapter. |
| `pytest.ini` | `toolkits/shodan-toolkit/src` on the path; the upstream suite added to `testpaths`. |
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

### Previous work: the HITL timeout is now "no timeout" by default

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
| `agent_mikrotik_toolkit.py`, `project_manager/agent_project_manager_toolkit.py` | The two remaining places that read `TORVALDS_HITL_TIMEOUT` directly. |
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
| `agent_mikrotik_toolkit.py` | The LlamaIndex adapter - the eight tools. |
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
