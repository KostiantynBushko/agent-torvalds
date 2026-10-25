# Self-Development Rules

These rules govern how the Torvalds agent modifies its own codebase. They are
**persisted here** so that they survive across sessions and are available to any
future agent invocation.

**Last updated:** 2026-10-25 (the current-work section refreshed — the
flat-layout commit `6920d03`)

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
| Branch | `refactor/shodan-toolkit-flat-layout` — **implemented, committed** (`6920d03`) and **merged into `master`** as PR #33 |
| Scope | The Shodan toolkit's layout: the toolkit directory **is** the package. The `src/` level and the nested `shodan_toolkit/` directory are gone — every source file sits directly in `toolkits/shodan-toolkit/`, next to `tests/` and `examples/`, the same shape as the MikroTik toolkit. The import name is unchanged (`toolkits.shodan_toolkit` through the alias, `shodan_toolkit` in a standalone install). |
| Status | Implemented: the modules moved, the tests use relative imports, the alias shim points at the new path, the distribution maps the package explicitly, and a new layout contract test (`toolkits/shodan-toolkit/tests/test_package_layout.py`, 11 checks) guards the rule. The toolkit suite is green (162 passed, 2 skipped), the alias contract is green (23/23), and the full suite reports **no new failure** (the CI gate: 40 known failures, 0 new). Committed as `6920d03` ("refactor: make the Shodan toolkit a flat package") and pushed to `origin/refactor/shodan-toolkit-flat-layout` — the operator approved both the commit and the push (rule 4). Merged into `master` as PR #33 (merge commit `e3d1511`), after PR #31 (`6986111`) and PR #32 (`1fef7d3`) were merged first: the stack had to go bottom-up. |
| Policy | The `toolkits` package must be imported **before** pytest imports a module from inside a hyphenated toolkit package, or pytest's "importlib" mode loads the package twice and the import alias goes stale. `consider_namespace_packages = true` in `pytest.ini` and in the toolkit's `pyproject.toml` makes pytest resolve the name through the normal import machinery, so there is exactly one copy of the package. |

### Latest change: the Shodan toolkit is a flat package

Committed as `6920d03` ("refactor: make the Shodan toolkit a flat package")
on the branch `refactor/shodan-toolkit-flat-layout`, pushed to
`origin/refactor/shodan-toolkit-flat-layout`, and merged into `master` as
PR #33 (merge commit `e3d1511`).

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
