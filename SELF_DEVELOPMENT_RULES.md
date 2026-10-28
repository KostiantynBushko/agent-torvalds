# Self-Development Rules

These rules govern how the Torvalds agent modifies its own codebase. They are
**persisted here** so that they survive across sessions and are available to any
future agent invocation.

**Last updated:** 2026-10-28 (the **empty *Agent Response* section** was
traced to its cause: the answer of a run was read with `str(result)`, and
`AgentOutput.__str__` returns the text of the **TextBlocks** only — so a
model that *reasoned but wrote no answer* left the section blank while the
tool result that held the answer sat in the output, unread; the branch
`investigate/empty-agent-response` holds the investigation and the repair,
and it is **not committed yet** — Rule 4; before that, the
**documentation was audited** and the
**wiki became a submodule** of the repository: the root README had no
link to the wiki, the wiki had no link to the deployment guide, and the
README described five of its toolkits twice; before that, the
**deployment scripts** moved into a dedicated `deploy/` folder —
**squash-merged into `master` as PR #65**,
commit `5d63058` — and the script was repaired: a
non-interactive run can now obtain sudo by itself, the `.env` it writes
names the variables the agent actually reads, and an unknown option
fails instead of reporting success; before that, 2026-10-27 (the
**context window** is logged at the
`INFO` level and **proved** to be the window the *server* uses — the
model advertises 262144 tokens, the server runs with 8192 — and the
**empty lines** are gone from the prompt in the debug log; the **prompt
in the debug log is
readable** — the messages that go to the model are *rendered* instead of
being dumped as a Python repr; the **context guard** became **optional**
— off by default, turned on by `--context-guard-on`; the **Claude
co-author contributor** was purged
from the history, and the tooling that keeps it out was **squash-merged into
`master` as PR #58**, commit `f58eb56`; the **commit SHAs** that the rewrite
made stale were refreshed and **squash-merged into `master` as PR #59**,
commit `911a5cc`; the **data analysis** toolkit became a module
under `toolkits/` — the **tenth** and **last** PR of the "every toolkit is a
module" refactoring, and the one that emptied the project root of loose
toolkits, **squash-merged into `master` as PR #57**, commit `0779228` —;
the **Excel** toolkit
became a module
under `toolkits/` and was **squash-merged into `master` as PR #54**,
commit `1fd2063` (head `c3886bc`, based on `master` at `9a33678`) — the
**ninth** PR of the "every toolkit is a module" refactoring, and the
**last** of the two loose toolkits left at the project root apart from
the data-analysis one; the **database** toolkit
became a module
under `toolkits/` and was **squash-merged into `master` as PR #52**,
commit `41608e5` — the **eighth** PR of the "every toolkit is a module"
refactoring, and the first whose library half is pinned to a **database
driver** (`psycopg2` and `mysql-connector-python`); the **Windows**
toolkit became a module under `toolkits/` and was **squash-merged into
`master` as PR #50**,
commit `deb75aa` — the **seventh** PR of the "every toolkit is a module"
refactoring, and the **last** of the *Linux/Windows* pair to move; the
**APT** toolkit became a module under
`toolkits/` and was **squash-merged into `master` as PR #48**, commit
`ce75ade` — the **sixth** PR of the "every toolkit is a module"
refactoring, and the first one whose library half is **not**
dependency-free; the **Linux** toolkit became a module under
`toolkits/` and was **squash-merged into `master` as PR #46**, commit
`c9fa14f` — the **fifth** PR of the series, and the **last** of the six
*Linux/Windows* pair to move;
the **OS** toolkit became a module under `toolkits/` and was
**squash-merged into `master` as PR #45**, commit
`e6af6ac` — the **fourth** PR of the series, and the last toolkit that
was still **mandatory**; the
GitHub toolkit was squash-merged into `master` as PR #43, commit
`253bb20`; the Git toolkit was squash-merged into `master` as PR #41,
commit `7852f01`; the math toolkit was merged into `master` as PR #39,
merge commit `243b291`)

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
| Branch | `investigate/empty-agent-response` — based on `master` at `5a7a4a2` (the documentation audit, PR #66).  The branch holds the investigation of the **empty *Agent Response* section** and the repair that came out of it.  It is **not committed yet**: Rule 4 — the commit needs the operator's explicit approval. |
| Scope | A long run ends with an **empty *Agent Response* section**, while the run *had* a tool result to show.  Find where the answer is lost, and make the section say what the run found. |
| Status | Root cause found, fix implemented, **verified**.  The answer of a run was read with `str(result)`, and `AgentOutput.__str__` returns `self.response.content or ""` — the text of the **TextBlocks** only.  A model that *reasoned but wrote no answer* therefore left the section blank, while the tool result that held the answer sat in the output the whole time, unread.  The run reported no error (`errors=0`). |
| Policy | **A run that has something to show must show it.**  The answer of a run is read in one place (`components/agent_answer.py`), and that place never returns an empty string: when the model wrote nothing, the operator is told so and shown the last tool result and the thinking of the model.  The *model* is not what this project controls; the *rendering* is. |
| Investigation | `investigate/empty-agent-response/` — the report, the probes (the chain that loses the answer, the model at several prompt sizes, the truncation of an oversized prompt, the window filling up), the end-to-end reproduction, the six invariants and the proof that the harness catches six deliberate drifts. |
| State | **On the branch, not committed.** `components/agent_answer.py` (new), `components/hitl_agent.py` (one more turn when the model wrote nothing), the three entry points, `tests/test_agent_answer.py` (32 tests), the report and the probes.  The invariants: 16/16.  The drift harness: 6/6.  The CI gate: **0 new failures** (40 known, 0 new, 0 fixed). |

### Previous change: the deployment scripts have a home of their own

| Item | Status |
|---|---|
| Branch | `feature/deploy-folder` — based on `master` at `c6e92af` (the merge of PR #56, the deployment script). The branch was **renamed** from `fix/deploy-script-sudo-noninteractive`, which is what it was called when the repair was the only work on it. **Squash-merged into `master` as PR #65** — commit `5d63058`, head `05f3120`. The branch is kept, as every merged branch in this repository is. |
| Scope | Give the deployment scripts a **folder of their own**, and finish the repair of the script that was already in progress: a **non-interactive run must be able to obtain sudo by itself**. |
| Status | Implemented, **verified** and **merged**. The script and its example environment file moved from `investigate/deployment-script/` to `deploy/`, and the investigation documents stayed where they were — `investigate/` holds the *record* of a piece of work, and the implementations that came out of it live in their own place (the toolkits under `toolkits/`, the chat manager under `chat_manager/`). The script itself was repaired in nine places, and every repair is held by an invariant. |
| Policy | **The folder is named for what it holds.** A folder called `investigate/deployment-script/` holds an investigation; the day the script shipped, the investigation had become its archive. The operator asked for *"a dedicated folder for deployment scripts"*, and the rule the rest of the repository already follows — the toolkits, the chat manager, the components — says what that folder is called: `deploy/`. |
| Investigation | The **deployment script** itself: `investigate/deployment-script/` still holds the report, the requirements and the plan. The implementation is the deliverable and it lives in `deploy/`. |
| State | **Merged into `master`.** `deploy/tests/verify_deploy_layout.py` — eleven invariants, over the folder *and* the behaviour of the script. `deploy/tests/verify_harness_catches_regressions.py` — the proof that the harness catches eleven deliberate drifts, one per invariant. `deploy/tests/test_deploy_layout.py` — the harness under pytest. The CI gate reported **0 new failures** (40 known, 0 new, 0 fixed) — locally and in the CI run of PR #65, which was green. The merge result tree (`c8e80f3`) is **byte-identical** to the head tree of `05f3120` that CI ran green, so the merge introduced no untested content. Rule 4: the commit and the push were made on the operator's explicit approval. |

### Latest change: the documentation was audited, and the wiki became a submodule

**The operator asked for it on 2026-10-28**: *"can you verify all
information is properly documented and has link in root READADME file
also do check it has link in wiki page, anothe work is to add wiki repo
as a submodule in agent-torvalds repo"*.

Three things, and the first one turned up more than it looked.

#### The audit found five defects in the root README

**The README described five of its toolkits twice.**  Sections 1-5 and
sections 20-24 were the same five toolkits — 1 = 21 (OS), 2 = 22
(Linux), 3 = 24 (Windows), 4 = 20 (GitHub), 5 = 23 (APT) — and the
short versions ended with *"See section 21 and the ... README"*.  The
long versions were the supersets, so the short ones were replaced by
them and the long ones deleted.  The numbering stays **1-19**, so no
anchor changed and no other cross-reference broke.

**One cross-reference pointed at the wrong section.**  Section 7 said
*"The chat memory is provided by the **Chat History Manager** — see
§ 17"*, and § 17 is the **Shodan Toolkit**.  The Chat History Manager
is § 15.  It was right when the list was shorter.

**The "Recent Updates" section had stopped at PR #6** and still said
that the legacy `agent_chat_memory.py` had been *"reworked into a
compatibility layer"* — it was **removed** in PR #37.  The section now
covers October 2026 and the real recent work.

**`tools_menu_update.md` described a menu that does not exist.**  Six
categories, two of them invented (*Development*, *Networking*), with
counts of 18, 10, 6, 7, 12 and 4.  The live menu has **twelve**
categories and **155** tools.  The file is now generated from the live
menu, and it says how.

**The project-structure tree had drifted.**  It named neither
`DEPLOYMENT.md`, nor `SELF_DEVELOPMENT_RULES.md`, nor `scripts/`, nor
`project_manager/`, nor the `wiki/`, and its `docs/` entry named four
of the six documents.

#### The wiki had no link to the deployment guide, and two pages had no links at all

`Architecture.md` and `Usage.md` carried **no link whatsoever**.  The
deployment story — the `deploy/` folder, the script, its eight phases,
its `.env` — was **absent from the wiki entirely**, and the wiki's
project layout still listed `agent_chat_memory.py`, which was removed
in PR #37.

The wiki now has a **Deployment** page, every page links to the pages
around it and back to the repository, `Toolkits.md` links **all twelve**
toolkit READMEs instead of one, and `Configuration.md` documents the
`.env` the deployment script writes.

#### The wiki is now a submodule

```gitmodules
[submodule "wiki"]
	path = wiki
	url = https://github.com/KostiantynBushko/agent-torvalds.wiki.git
```

**This reverses a deliberate decision, and the reason given for it
does not hold.**  The `.gitignore` excluded the folder with this
comment:

> *The GitHub wiki clone.  It is its own repository, with its own
> remote (agent-torvalds.wiki.git) and its own history - the wiki pages
> are published from there, not from this repository.  Committing it
> here would record a gitlink that no clone of this repository could
> resolve.*

A submodule **is** a gitlink, and the wiki repository is **public** —
it was cloned over HTTPS with no credentials, so every clone can
resolve it.  What is true is narrower: a plain `git clone` leaves the
directory empty, and `git clone --recurse-submodules` brings the pages
with it.  The comment now says that, and the exclusion is gone.

**Verified after the push**: a fresh `git clone --recurse-submodules`
brings the **nine** wiki pages down, and a plain clone leaves the
directory empty and the build green.

### Latest change: the deployment scripts have a home of their own

**The operator asked for it on 2026-10-28**: *"I think we must has a
dedicated folder for deployment scripts"*, and — *"in self dev folder:
please check the last request and continue work on it"*.

Two things, and they were the same piece of work.  The **last request**
was the repair of the deployment script — a non-interactive run that
could not obtain sudo by itself — and it was **in the working tree**,
uncommitted, on the local-only branch
`fix/deploy-script-sudo-noninteractive`.  The **new request** was the
folder.  The script now lives in it.

#### The move

| Path | Change |
|---|---|
| `deploy/deploy-torvalds.sh` | **Moved** from `investigate/deployment-script/`. Git tracked it as a rename, and the executable bit came with it. |
| `deploy/deploy-torvalds.sh.example.env` | **Moved** from `investigate/deployment-script/`. |
| `deploy/README.md` | **New.** What the folder holds, how to use it, and what the contract is. |
| `deploy/tests/verify_deploy_layout.py` | **New.** The harness — eleven invariants. |
| `deploy/tests/verify_harness_catches_regressions.py` | **New.** The proof that the harness catches eleven deliberate drifts. |
| `deploy/tests/test_deploy_layout.py` | **New.** The harness, under pytest. |
| `investigate/deployment-script/` | The report, the requirements and the plan — **they stay**. |
| `pytest.ini` | `deploy/tests` added to `testpaths`. |
| `DEPLOYMENT.md`, `README.md`, `CHANGELOG.md` | The documentation. |

#### What the repair found

**The script could not install Python on a machine without Python.**
`check_python3()` returned 1 when the interpreter was missing or too
old, and `set -e` turned that into an exit — so the script died before
the phase that installs Python, on exactly the machine it exists to fix.
It is a warning now, and the hard check (`resolve_python3()`) runs after
the packages are in.

**An unwritable log file would have silently skipped every pip and apt
call.**  The default is `/var/log/torvalds-deploy.log`, which only root
may create, and every `2>>"$LOG_FILE"` in the script is a
*redirection*: a redirection that cannot be opened means the command
does not run at all.  The file is now made writable before anything
uses it, and it falls back to `~/.torvalds/logs/`.

**The `.env` configured nothing.**  The script wrote
`TORVALDS_CHAT_MODEL` and `TORVALDS_OLLAMA_BASE_URL`; the agent reads
`TORVALDS_MODEL` and `TORVALDS_OLLAMA_HOST`.

**`sudo DEBIAN_FRONTEND=noninteractive apt-get ...` may be refused
outright.**  sudo only honours a variable set on the command line when
the `setenv` option is set in sudoers, or when the variable survives
`env_reset` — and `/etc/sudoers` is root-only and distro dependent.
When the variable is refused, sudo aborts the whole command.  The form
`sudo env DEBIAN_FRONTEND=noninteractive apt-get ...` always works,
because `env` runs *as root*, after the environment has been reset.

**`dpkg -l <name>` exits 0 for a package that is not installed.**  It
reports the *state* of a package dpkg knows about, and "not installed"
is a state, not an absence.  `dpkg-query -f '${Status}'` is the check.

**Four more, found on the way:** an unknown option exited **0**;
`python3.-venv` was requested when `PYTHON_MINOR` was empty; a
half-built virtual environment was never repaired; and one bad
requirement left the whole environment empty, because pip builds every
wheel before it installs anything.

#### The proof

The harness has **eleven** invariants, and the drift proof breaks the
contract **eleven** times — once per invariant.

| | Invariant |
|---|---|
| **D1** | The script lives in `deploy/` and nowhere else. |
| **D2** | It is executable, it is bash, and it parses. |
| **D3** | `--help` is a query: stdout, exit 0, every option listed. |
| **D4** | `--version` is a query: stdout, exit 0. |
| **D5** | An unknown option fails instead of reporting success. |
| **D6** | The script bootstraps its own sudo timestamp. |
| **D7** | No `sudo VAR=value` form, which the sudoers policy may refuse. |
| **D8** | The `.env` names the variables the agent actually reads. |
| **D9** | No document still points at the old path. |
| **D10** | The log file is made writable before anything is redirected to it. |
| **D11** | A query is not reported as a deployment. |

**The drift proof found a hole in the harness, and that is the point of
it.**  The D7 check looked for `\bsudo\s+VAR=`, and the word boundary
means it never matched inside `run_sudo` — which is the form the script
actually uses.  The check was blind to the very thing it was written
for, and it had never failed, because nothing had ever broken it.  It
matches the word as a *command* now: anything that ends in `sudo` and
is followed by an assignment.

```bash
python3 deploy/tests/verify_deploy_layout.py
python3 deploy/tests/verify_harness_catches_regressions.py
python3 -m pytest deploy/tests -q
```

Eleven invariants hold, and **11 of 11** deliberate drifts are caught.

**The PR.**  <https://github.com/KostiantynBushko/agent-torvalds/pull/65> —
*feat: give the deployment scripts a dedicated folder*.  The CI gate is
green on it: 40 known failures, 0 new, 0 fixed.

**Merged.**  **Squash-merged into `master` as PR #65** (commit `5d63058`,
head `05f3120`, based on `master` at `c6e92af`) — the operator merged it
on 2026-10-28.  The squash departs from the standing convention of a
merge commit, as PR #54, #52, #50, #48 and #46 did before it, and for the
same reason: this PR was based directly on the tip of `master`, so the
next PR's merge base is `5d63058` and its diff does not balloon.  The tree
check the convention exists for holds as well — `master`'s tree after the
merge (`c8e80f3`) is **byte-identical** to the head tree of `05f3120` that
CI ran green, so the merge introduced no untested content.

**The empty `deploy/` directory in the operator's working copy was no
obstacle.**  It was created before the branch existed, and it was
untracked and empty — and an empty directory is invisible to git, so it
cannot conflict with a merge that writes files into it.  This was not
assumed: it was **measured**, on a clone at the pre-merge `c6e92af` with
an empty `deploy/` created in it.  The pull filled the directory, and the
working tree stayed clean.

**One PR, two concerns, deliberately.**  The move and the repair are
separate changes and would ordinarily be separate PRs.  They are folded
together because the repair is *of the thing being moved* — shipping
the script into its new home unchanged would have shipped it broken —
and because the branch was already open with the repair in progress,
uncommitted.

**A note for the merge.**  The operator's working copy has an **empty,
untracked `deploy/` directory** — it was created before the branch
existed.  A directory that is empty does not conflict with the merge:
git writes the files into it.  It would only refuse if a *file* stood
in the way.

### Latest change: the empty lines are gone, and the context window is logged

**The operator asked for it on 2026-10-27**, on the same branch:
*"first of all can we reduce empty string, and can you prove we actually
see context window? Also I want to see context windows size in info log
level add it as well in the same branch"*.

Three things.

**1. The empty lines are gone from the log.**  The system prompt ends
with a few newlines, and the log showed them as a wall of empty
records.  One empty line is kept — it is a paragraph break and it
carries meaning — and a run of them is reduced to one.  The leading
and the trailing empty lines are dropped, and a message that carries
nothing but whitespace reads as `(empty)`.

**2. The context window is logged at the `INFO` level**, together with
the place the number came from:

```
2026-10-27 21:24:03,517 [INFO] components.ollama_config: Context window: 8192 tokens — the running model (/api/ps)
```

The number alone says nothing about whether it is the window the server
really uses or merely the maximum the model advertises, so the source is
in the line as well.  The sources are tried in this order:
`TORVALDS_CONTEXT_LENGTH`, the running model (`/api/ps`),
`PARAMETER num_ctx` in the Modelfile, and finally the maximum the
model advertises.  With the context guard on, the budget it derives
from the window is logged too.

**3. The proof that the number is the server's.**  This is the part
worth keeping.  The agent's model advertises **262144** tokens; the
server runs it with **8192**.  The advertised maximum is 32 times
larger, and a prompt that exceeds the real window is truncated from the
front by the server — which drops the user request and makes the model
template fail with "No user query found in messages.".

`investigate/context-window-proof/verify_context_window.py` asks the
live server directly and compares:

| | Tokens | Where it comes from |
|---|---:|---|
| The model **advertises** | 262144 | `llm.metadata.context_window` |
| The server is **configured** | 8192 | `PARAMETER num_ctx` in the Modelfile |
| The server **allocated** | 8192 | `context_length` in `/api/ps` |
| The **agent reports** | **8192** | `components/ollama_config.py` |

Four invariants: **P1** the number is the server's, **P2** it is not
the advertised maximum, **P3** the log names the size *and* the source,
**P4** the number is *read* and not baked in.  P4 is the one that
matters: it takes the server away and checks that the number changes
(8192 with the server, 12345 with the override, 262144 without the
server).  A hardcoded number would answer 8192 in all three cases.

The second script proves the harness catches four deliberate drifts —
the same discipline as the chat-message harness: *a check that has
never failed proves nothing*.

| Path | Change |
|---|---|
| `components/chat_message.py` | `_tidy()` — the empty lines are reduced. |
| `components/ollama_config.py` | `resolve_context_window_with_source()` returns the number **and** its source; `apply_context_window()` logs both at the `INFO` level. |
| `components/hitl_agent.py` | The context guard logs the window and the budget it derives from it. |
| `tests/test_chat_message.py` | 8 more tests — the empty lines. |
| `tests/test_ollama_context_window.py` | 8 more tests — the sources and the log. |
| `investigate/context-window-proof/` | **New.** The proof: four invariants, the drift proof and `PROOF.md`. |
| `README.md`, `CHANGELOG.md` | The documentation. |

**Verifying the change**

```bash
self-development/.venv/bin/python -m pytest self-development/tests/test_chat_message.py self-development/tests/test_ollama_context_window.py -q
self-development/.venv/bin/python self-development/investigate/chat-message-debug/verify_chat_message.py
self-development/.venv/bin/python self-development/investigate/context-window-proof/verify_context_window.py
self-development/.venv/bin/python self-development/investigate/context-window-proof/verify_harness_catches_regressions.py
```

48 tests pass, the eight invariants hold, and every deliberate drift is
caught.

### Investigation: the logging into a file, with a rotation and a symlink

The operator asked for it on 2026-10-27:
*"I want be able to redirect logging into file, this solution must have a
posibility to rotare log when reaching current log file predefined size.
Inside directory we must have soft link to current log file the files"*.

**No source file of the agent was modified.**  The investigation folder
`investigate/logging-to-file/` was added: the report, a **working
prototype**, the verification harness and the drift proof.

#### The current state — half the feature is in the tree, and unreachable

`agent-torvalds-mw.py` has had a `to_file` parameter on
`configure_logging()` since the multi-window work, and **no caller ever
passes it** — the parameter is dead code.  The classic orchestrator has
no file support at all.  A plain `logging.FileHandler` never rotates:
the file grows until the disk is full.

#### The design

| | |
|---|---|
| The directory | `~/.torvalds/logs/` — the convention the project already uses (`~/.torvalds/chat_manager.db`, `~/.cache/torvalds/agent_cache.json`).  Not the working tree. |
| The files | `agent.log` (the current log, a **real** file), `agent-current.log -> agent.log` (the symlink), `agent.log.1` … `agent.log.N` (the generations). |
| The symlink | It points at the **path** of the live file, not at its inode.  `doRollover()` renames the file away and reopens the same path, so the link is valid before and after every rotation and never has to be re-pointed.  It is created atomically (`os.replace`) and re-asserted after a rollover, so it heals itself. |
| The rotation | `logging.handlers.RotatingFileHandler` — the **standard library**.  The subclass adds the symlink and the file mode.  The size limit is **soft**: the file can exceed it by the record that crossed it.  `backupCount = 0` disables the rotation, and is refused. |
| The size | `--log-max-size 10MB` — `B`, `KB`, `MB`, `GB`.  An unknown unit is a **typo that is reported**, because a log that never rotates is the failure this feature exists to prevent. |
| The tee | The stderr handler stays.  The file is a tee, not a replacement. |
| Off by default | The agent's behaviour does not change until the operator asks for it. |

| Flag | Environment variable | Default |
|---|---|---|
| `--log-file PATH` | `TORVALDS_LOG_FILE` | *off* |
| `--log-dir DIR` | `TORVALDS_LOG_DIR` | `~/.torvalds/logs` |
| `--log-max-size SIZE` | `TORVALDS_LOG_MAX_SIZE` | `10MB` |
| `--log-max-files N` | `TORVALDS_LOG_MAX_FILES` | `5` |
| `--log-symlink NAME` | `TORVALDS_LOG_SYMLINK` | `<stem>-current.log` |

#### What the harness found

**The file mode was wrong, and only the harness noticed.**  The stdlib
handler creates the file with `0666 & ~umask` — `0664` on this machine,
so a log carrying the prompts was readable by every account on the box.
The first run failed on it: `[FAIL] L6  the file mode is 0o664`.

**The symlink needs no maintenance at all — and that was a surprise.**
The first drift removed the "refresh the symlink after a rollover" call
and **the harness passed**.  The drift was not a defect: the symlink
points at a *path*, and the path does not change when the file is
rotated.  The refresh is only load-bearing for a symlink somebody
deleted while the agent runs, and that case is now a check of its own.

*"A check that has never failed proves nothing."*

#### The invariants

| | Invariant | Caught by |
|---|---|---|
| **L1** | Every record reaches the log file. | a record that is swallowed |
| **L2** | The log file is rotated when it reaches the size limit. | the rotation being disabled |
| **L3** | The symlink points at the file being written *now*, and it comes back after it was deleted. | the symlink pointing at the rotated file, or not being refreshed |
| **L4** | The number of retained generations is bounded. | the retention being ignored |
| **L5** | A symlink that cannot be created degrades the pointer, never the logging. | the failure being raised |
| **L6** | The log file is appended to, is private (`0600`), and is not truncated when the logging is reconfigured. | the truncation, and the missing mode |
| **L7** | The size limit is written the way an operator writes it, and an unknown unit is reported. | the typo being ignored |

**Verifying the investigation**

```bash
self-development/.venv/bin/python investigate/logging-to-file/prototype_file_logging.py
self-development/.venv/bin/python investigate/logging-to-file/verify_logging_to_file.py
self-development/.venv/bin/python investigate/logging-to-file/verify_harness_catches_regressions.py
```

13 checks hold, and **7 of 7** deliberate drifts are caught.

#### The known limitations

| | Limitation | What it means |
|---|---|---|
| Multi-process | `RotatingFileHandler` has no cross-process lock. | One log file per agent process. |
| The size limit is soft | The live file can exceed the limit by one record. | A record is never cut in half. |
| No compression | The generations are plain text. | The disk use is already bounded. |
| The log is not redacted | It carries the prompts and the tool output. | The file is `0600` and stays in the home directory. |

The report ends with **four open questions for the operator**: the name of
the symlink, the default size, whether the file replaces the terminal or
joins it, and whether the TUI should stop writing to stderr.

### Latest change: the answer is in the debug log

The operator asked: *"can you check is there another place in EventConsumer
ChatMessage we can update output formating to make it human redable"*.

**The answer was not in the log at all.**  `AgentOutput` has no `output`
field — the answer is in `event.response` — and the handler read
`event.output`, so the record said `output=None` **every single time**.
The code looked right because the *dummy* `AgentOutput` in
`event_consumer.py` — the one that exists for the case where LlamaIndex
is not installed — has `self.output`.  The fallback masked the real API.

The stop event carried the answer: `StopEvent.result` **is** the
`AgentOutput`.  It was logged as the repr of the whole model, with the
answer buried inside it.

| | Before | After |
|---|---|---|
| The answer | `output=None` — not logged | `assistant: The disk is 78% full: 12 GB of 16 GB are in use.` |
| The tool calls | inside the model repr | `tool call: execute_shell_command(command=df -h /)` |
| The stop event | `result=AgentOutput(response=ChatMessage(role=<MessageRole.ASSISTANT: ...` | the same rendering, one thing per line |

`to_output_string()` in `components/chat_message.py` renders the answer
event: the text, the tool calls, the structured response and the retry
messages — one thing per line, a call the answer already shows not
shown twice.  The state holds the readable answer, not the repr.

**What the harness found:** every `getattr` in the module now goes
through `_safe_getattr()`.  `getattr` only swallows the `AttributeError`
of a *missing* attribute, so a payload whose property *raises* would
have taken the agent down — in the middle of a run, over a **debug
log**.

| | Invariant | Caught by |
|---|---|---|
| **O1** | The answer is in the log, and the record does not say `output=None`. | the handler reading the field the framework does not have again |
| **O2** | The tool calls of the answer are in the log, each of them once. | the tool calls not being rendered |
| **O3** | The structured response is in the log. | it not being rendered |
| **O4** | The retry messages are in the log. | them not being rendered |
| **O5** | No object syntax leaks into the log. | the stop event logging the repr of the model again |
| **O6** | A payload that cannot be read does not break the run. | the renderer not being exception-proof |

**Verifying the change**

```bash
self-development/.venv/bin/python investigate/output-rendering/probe_output_rendering.py
self-development/.venv/bin/python investigate/output-rendering/verify_output_rendering.py
self-development/.venv/bin/python investigate/output-rendering/verify_harness_catches_regressions.py
```

8 checks hold, 6 of 6 drifts are caught, the 45 tests of
`tests/test_chat_message.py` pass, and the CI gate reports 0 new
failures.

**What is left, on purpose.**  Six places in the consumer still log a
plain string or a dict as a `repr` — the streamed token, the tool
arguments, the question, the operator's answer, the human's answer and
the workflow handler.  They are `%r` to `%s` away, and they are listed
in the report.  The report also asks whether the **dummy event classes**
should be made to match the framework, so that a mistake like the one
above cannot be made silently.

### The security findings of PR #63

The Aikido PR checks reported three findings on the branch, all of them
"low severity", all of them in the new `investigate/` proofs.

**Two of them were real.**  `replay_the_operator_log.py` used `assert`
for its two checks.  Under `python -O` the assert statements are
removed, and the script printed **"OK — no trailing empty lines, no run
of empty lines."** and exited **0** for a rendering that was broken — a
proof that lies about its own result.  The checks are explicit now, and
they fail with exit 1 under `-O` as well.

**The third one was a real hardening.**  `verify_context_window.py`
asked the server with `urllib.request.urlopen`, which follows a
redirect to any host.  The request now stays on the server it was aimed
at, refuses the link-local range where the cloud metadata service
lives, and caps the read at 1 MiB.  The URL is the operator's own
configuration — `TORVALDS_OLLAMA_HOST` — and not input that arrives
over a network, so this is not an SSRF in the sense the scanner means
it; it is the one path by which a request could have been steered at a
service the operator never named.

The rules are pinned by `tests/test_context_window_request_safety.py` —
15 checks that run in the CI, and that fail when the hardening is
taken away.  Two of the four drifts were **not** caught by the first
version of the tests: a redirect to an address that is not there fails
either way, and a body that is not valid JSON fails to parse either
way.  Both tests were wrong for the same reason — they could not tell
"refused" from "attempted and failed".

**What was left alone, and why.**  The agent's own call to `/api/ps`
in `components/ollama_config.py` has the same shape.  It is left as it
is: the URL is the operator's configuration, the answer is parsed for a
single integer and thrown away, and a strict redirect rule there could
cost the *agent* the server's window — silently, because the function
answers `None` and the agent would report the advertised maximum
instead.  A proof that says it failed is worth more than a feature that
quietly degrades.

### Previous change: the prompt in the debug log is readable

**The operator asked for it on 2026-10-27**: *"I want to improve debug
message for context window… I need human readable ChatMessage in
`EventConsumer._on_agent_input` on debug mode."*

The prompt was logged as a Python repr — the system prompt, the whole
chat history and the run's scratchpad, escaped and wrapped in object
syntax, spread over dozens of lines.  It now reads as the messages
themselves:

```
EventConsumer._on_agent_input: prompt: 5 messages
EventConsumer._on_agent_input:   [0] system: You are Torvalds, a technical AI assistant that interacts with the operating system.
EventConsumer._on_agent_input:   [1] user: I want to improve debug message for context window
EventConsumer._on_agent_input:   [3] assistant: thinking: The user asks for a better debug message. | tool call: pwd(path=/)
EventConsumer._on_agent_input:   [4] tool: output: /home/kbush
```

| Path | Change |
|---|---|
| `components/chat_message.py` | **New.** `to_string()` renders one message, `to_strings()` renders a prompt. The text, the thinking and the tool calls — in both shapes a chat history can carry a tool call in. |
| `components/event_consumer.py` | `_on_agent_input()` logs one line per message; the state handler holds the same readable text. |
| `tests/test_chat_message.py` | **New.** 26 tests. |
| `investigate/chat-message-debug/verify_chat_message.py` | **New.** The harness: four invariants. |
| `investigate/chat-message-debug/verify_harness_catches_regressions.py` | **New.** The proof that the harness catches four deliberate drifts. |
| `investigate/chat-message-debug/IMPLEMENTATION_REPORT.md` | **New.** What was implemented and why. |
| `README.md`, `CHANGELOG.md` | The documentation. |

**Verifying the change**

```bash
self-development/.venv/bin/python -m pytest self-development/tests/test_chat_message.py -q
self-development/.venv/bin/python self-development/investigate/chat-message-debug/verify_chat_message.py
self-development/.venv/bin/python self-development/investigate/chat-message-debug/verify_harness_catches_regressions.py
```

26 tests pass, the four invariants hold, and all four deliberate drifts
are caught.

**Two things this change is worth knowing about.**

*It is much smaller than the first attempt.*  The first implementation
was a **context report**: a token count, a percentage of the context
window, a budget, a per-message breakdown, a detail limit, an escape
hatch for the raw payload and a resolver for the window the server
really uses — a new module of 600 lines, 65 tests and a seven-invariant
harness.  The operator's answer to it was that it was too complex: *"I
do not think we need such a complex solution — my idea was just to
print ChatMessage in human readable way, something like ChatMessage has
a `to_string` method."*  All of it was removed.  What is left is **one
function** (`to_string()`), **one helper** (`to_strings()`) and **one
call site**.

*The tool call is in the rendering, and that is the part worth keeping.*
A chat history carries a tool call in two places: as a `ToolCallBlock`
in `message.blocks`, and in the OpenAI-shaped
`additional_kwargs["tool_calls"]` — the shape the Ollama adapter still
writes for histories that predate the blocks.  A rendering that showed
the text of an assistant turn and none of the tools it asked for would
be misleading, and the first implementation had that defect: the tool
call in `additional_kwargs` was **invisible**.  The rendering reads
both, and a call that is present in both is shown once.

### Previous change: the context guard is optional

**The operator asked for it on 2026-10-27**: make the context guard
optional — off by default, turned on by the command line argument
`--context-guard-on`.  It is implemented, tested, documented and
**committed** (`42f4640`).

**One branch for both context guard changes.**  The operator decided that
the loop fix and the on/off switch belong to **one** branch, so the
switch was committed on top of the loop fix on
`fix/context-guard-agent-loop`.

**Then the operator merged PR #61.**  It squash-merged the loop fix
into `master` as `0147443`, so the loop fix is in `master` while the
switch was still only on the branch.  The operator then asked for the
branch to be rebased onto `master` and for a PR to be opened for
review.  The rebase **dropped the loop-fix commit as already applied**
(its patch is byte-identical to `0147443`), leaving the switch alone on
`feature/context-guard-optional`.  The two touch the same two modules
(`components/context_guard.py`, `components/hitl_agent.py`).

**PR #62 is open** for the switch: <https://github.com/KostiantynBushko/agent-torvalds/pull/62>.
It is the operator's to review and merge.

**What the guard is.**  `components/context_guard.py` keeps the LLM prompt
inside the model's context window while always preserving the user query.
Without it, a long tool-using run grows the prompt without bound; the
Ollama server then truncates it from the front, which drops the user
request, and the model template refuses to render a conversation without
one ("No user query found in messages.").

**The switch.**

| Where | What |
|---|---|
| `components/hitl_agent.py` | `HITLFunctionAgent.context_guard_enabled` — `False` by default; `take_step()` stands down when it is `False` |
| `agent-torvalds.py` | `--context-guard-on`, and `TORVALDS_CONTEXT_GUARD` |
| `agent-torvalds-mw.py` | the same flag and the same environment variable |

The flag and the environment variable are folded together into one
effective value in `main()`, the same way the HITL flags are, and the
startup banner reports it: "Context guard: enabled" / "disabled".

**The trade-off is the price of the switch, and it is stated in the
CHANGELOG and in the README.**  With the guard off the prompt reaches the
model exactly as the agent assembled it — which is what the operator asked
for — and a run that reads a large file can overflow the window again.
The guard is one flag away.

**The tests.**  `tests/test_context_guard_toggle.py` (8 tests) pins the
contract: the guard stands down by default, the prompt grows past the
context window when it does, the prompt is trimmed and keeps the user
request when the guard is on, and the flag, the environment variable and
the multi-window variant all behave.  `tests/test_context_guard_agent.py`
(the pre-existing integration suite) now turns the guard on **explicitly**,
because the default is now off.  The CI gate reports **no new failure**
(40 known, 0 new, 0 fixed).

### Previous change: the Claude co-author contributor is gone

**Squash-merged into `master` as PR #58** (commit `f58eb56`, head `f50b79e`,
based on `master` at `0779228`), with the **SHA refresh** that followed it as
**PR #59** (commit `911a5cc`, head `4a8d732`, based on `master` at `0779228`).
Both CI green; the merged tree is byte-identical to a local trial merge whose
CI gate reported **no new failure** (40 known, 0 new, 0 fixed).

**The finding.** The contributor was **not** made by a pull-request footer.
GitHub builds its contributor list from the `Co-Authored-By:` trailers of the
**commit messages**, and renders an unlinked trailer as a contributor with
`login: "claude"` and a display name taken from the trailer — which is why
the entry read "claude" / "Claude Opus 4.8 (1M context)".

Exactly **one** commit carried such a trailer:

```
6d330699c545fef9c97d5439632beeaf84f44f11  Initial commit: shodan-toolkit
    Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
```

It entered `master` through the `git subtree` merge `3e4eab8`, so removing it
meant **rewriting the history**: every descendant changed SHA and the 29
branches carrying it were force-pushed. **No file in the repository changed** —
every tree before the rewrite is byte-identical to its tree after it.

**The pull requests were already clean.** All 57 PR bodies, all titles, all
comments and all review comments were checked through the API; none carried a
Claude Code footer. The footer had been on PR #20 and PR #22 only, and it was
removed on 2026-10-27.

| Path | Change |
|---|---|
| `investigate/claude-contributor-purge/verify_no_claude.py` | The check. Walks the GitHub side (every PR title and body, every comment, every review comment) and the Git side (every commit message of every ref). Grades a **co-author trailer** and a **Claude Code footer** as FAIL, and a bare mention as informational. |
| `investigate/claude-contributor-purge/strip_claude_trailer.py` | The `git filter-repo` message callback. Removes the trailer and the footer, line-wise, and nothing else. |
| `investigate/claude-contributor-purge/test_strip_claude_trailer.py` | The test of that callback — 7 cases, driven the way filter-repo drives it. |
| `investigate/claude-contributor-purge/purge_claude_contributor.sh` | The driver: baseline, scratch mirror clone, rewrite, verify, and — only with `--apply` — the force-push. |
| `investigate/claude-contributor-purge/refresh_commit_shas.py` | The SHA refresh. It arrived with PR #58 and was used by PR #59. |
| `investigate/claude-contributor-purge/REPORT_claude_contributor_purge.md` | The report. |
| `.gitignore` | The PR-body backup from 2026-10-27 is now ignored: it holds the bodies as they were *before* the footer normalisation, so it contains the very text the repository is being cleaned of. |
| `SELF_DEVELOPMENT_RULES.md`, `docs/shodan-toolkit.md`, ten investigation reports | The **104** stale SHA references, refreshed (PR #59). |

**Verifying the change**

```bash
python3 self-development/investigate/claude-contributor-purge/verify_no_claude.py
python3 self-development/investigate/claude-contributor-purge/test_strip_claude_trailer.py
```

The check reports **PASS** on both sides: no commit message of any ref carries
a co-author trailer or a Claude Code footer, and no PR title, body, comment or
review comment carries one either. The callback test reports 7/7.

### Previous change: the commit SHAs the rewrite made stale

**Squash-merged into `master` as PR #59** (commit `911a5cc`, head `4a8d732`,
based on `master` at `0779228`).

**104 lines, in 15 files.** Every one of them differs from its original by
exactly the hexadecimal tokens and nothing else — the words around them are
untouched.

| File | References |
|---|---|
| `SELF_DEVELOPMENT_RULES.md` | 43 |
| `docs/shodan-toolkit.md` | 4 |
| `investigate/ChatHistoryManager/STEP_AUDIT.md` | 11 |
| the ten investigation reports | the rest |

Tree hashes are **not** touched: a rewrite does not change a tree, so the tree
IDs the documentation records are still correct.

**The guard that matters.** The refresh is mechanical — `git filter-repo`
leaves the old→new mapping in `filter-repo/commit-map` — but the mapping
alone is not enough, and a naive substitution would have been wrong.

The rewrite changed **29** branches and left **26** alone: the ones that never
carried the offending commit. `filter-repo`, working in a scratch clone,
rewrote *every* commit there, so its map names a new SHA for the commits of
the branches that were never pushed — and **those SHAs do not exist in this
repository**.

So a substitution is made only when the new SHA **resolves to a commit here**.
161 of the 264 mapped pairs qualify; 103 do not, and the references to those
commits are left untouched — correctly, because those commits did not move.

A token that matches no old SHA is left alone, and a token that matches more
than one is reported and left alone. There were no ambiguous tokens.

**Verifying the change.** Every hexadecimal token in the changed files was
checked against the rewritten history:

* **115** resolve to a commit;
* **9** are tree hashes — still correct;
* **18** resolve to nothing — and they did not resolve before the rewrite
  either. They are pre-existing stale references, and this change does not
  touch them. **Working out what they were meant to be is the next piece of
  work.**

The tool that does the refresh is `investigate/claude-contributor-purge/refresh_commit_shas.py`,
which arrived with the purge tooling in #58.

#### Correction (2026-10-28): there is no such piece of work

**The 18 were never commit references.**  The count came from a token
scan, and a token scan cannot tell a commit SHA from anything else that
happens to be made of hex characters.  The whole repository was rescanned
on 2026-10-28 — **456** tracked text files, **58** tokens that resolve to
nothing — and every one of them was classified by its context:

| What the token really is | Examples |
|---|---|
| A **UUID fragment** — a chat key, a session id, a user id | `e89a145c`, `fab62e1a`, `7f2c1a44`, `2b8d5c1e0f11` |
| A **HITL question id** or a **request id** | `hitl-4934d309`, `hitl-c30af0fb`, `cab12ce4` |
| An **inode number**, a **float**, a **file size** | `53882449`, `0694212`, `10485760` |
| An **md5 checksum** of the tool menu | `db58a70628cfdc6d12faf17d91f159f1` |
| An **Ollama image digest** | `0a109f422b47`, `331499cb5960` |
| **Placeholder example data** | `a1b2c3d4…`, `abc1234`, `fedcba654321` |
| The **left half of a unicode escape** | `0001f511` (\U0001f511), `0001f680` (\U0001f680) |
| **Ordinary English** | `cceeded` (succeeded), `feedbac` (feedback) |

**Exactly one** of the 58 is a commit SHA that no longer exists: `21063431`
in `investigate/claude-contributor-purge/REPORT_claude_contributor_purge.md`,
where the table row reads *"`master` | `21063431` → `0779228`"*.  That one
is **correct as it stands** — it is the left-hand side of the record of
the rewrite, and replacing it would destroy the very thing the row
documents.  It is not a stale reference; it is the record of the rewrite.

So the item this file named as *the next piece of work* was **a false
premise**, and there is nothing to refresh: the commit map that the
rewrite left behind is gone, it was a temporary file, and no
substitution is needed.  The 18 tokens that the original count found were
found by looking for hex, not by looking for commits.

### Previous change: the data analysis toolkit is a module

**Squash-merged into `master` as PR #57** (commit `0779228`, head `bac2013`,
based on `master` at `1fd2063`).  The branch carried two commits: `340dd8b`
(the refactor) and `bac2013` (the record of this very work).

The **tenth** and **last** toolkit of the "every toolkit is a module"
series, and the one that **emptied the project root of loose toolkits**.
Every other toolkit had already moved under `toolkits/`, where a missing
or broken toolkit degrades to "no tools" instead of a failed boot; the
data analysis toolkit was still a top-level module that both call sites
imported unguarded.

| Path | Change |
|------|--------|
| `toolkits/data-analysis-toolkit/operations.py` | **New.** The 13 analysis operations and the module-level logger — the library half. No LlamaIndex import. |
| `toolkits/data-analysis-toolkit/agent_data_analysis_toolkit.py` | **New.** The adapter — the only LlamaIndex-dependent module. It re-exports all 13 operations. |
| `toolkits/data-analysis-toolkit/__init__.py` | **New.** The public API surface and the code-level reference to the canonical alias. |
| `toolkits/data-analysis-toolkit/README.md`, `pyproject.toml`, `py.typed` | **New.** The module documentation, the standalone distribution (the adapter is the `agent` extra) and the PEP 561 marker. |
| `toolkits/data-analysis-toolkit/tests/test_operations.py` | **New** (moved from `tests/test_data_analysis_toolkit.py`). Relative imports; extended from 39 to 44 tests. |
| `toolkits/data-analysis-toolkit/tests/test_package_layout.py` | **New.** The layout contract — 33 checks. |
| `toolkits/data-analysis-toolkit/tests/test_split_verification.py` | **New.** The test of the split-verification script — 17 tests, fourteen deliberate drifts. |
| `agent_data_analysis_toolkit.py` | **Deleted** at the project root. Git tracked it as a rename to `toolkits/data-analysis-toolkit/operations.py`. |
| `tests/test_data_analysis_toolkit.py` | **Deleted** at the project root. Git tracked it as a rename to the module-local test. |
| `toolkits/__init__.py` | The `data_analysis_toolkit` alias, the `_DATA_ANALYSIS_PACKAGE` / `_DATA_ANALYSIS_ALIAS` literals and the adapter in `_ADAPTER_MODULES`. |
| `agent_tool_retriever.py`, `agent_tool_selection.py` | The import path moved to the alias, behind a guard. |
| `pytest.ini` | `toolkits/data-analysis-toolkit/tests` added to `testpaths`. |
| `tests/test_toolkit_alias_contract.py` | The data analysis toolkit joined the alias contract — seven new rows. |
| `tests/test_logging_cli.py` | The logger now comes from `toolkits.data_analysis_toolkit.operations`; the two new modules joined the static inspection. |
| `requirements.txt` | `numpy` moved into the Excel & Data Analysis section, next to `pandas`. |
| `README.md`, `CHANGELOG.md` | The documentation — the toolkit was not mentioned in the README at all before this change. |
| `investigate/data-analysis-toolkit-module/REPORT_data_analysis_toolkit_module.md` | **New.** What was implemented and why. |
| `investigate/data-analysis-toolkit-module/verify_split.py` | **New.** The mechanical check. |
| `investigate/data-analysis-toolkit-module/verify_optional_dependency.py` | **New.** The measurement of what a missing `pandas` does. |
| `investigate/data-analysis-toolkit-module/dump_tool_menu.py` | **New.** The tool menu dump. |

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

**Three things this change is worth knowing about.**

*The toolkit is no longer able to take the agent down.*  Both call sites
imported it **unguarded**, so a missing `pandas` raised an unhandled
`ModuleNotFoundError` out of the tool discovery and the agent did not
boot at all.  This was measured on both trees with `pandas` blocked at
the import machinery: `master` raised, the branch booted with **142**
tools instead of 155.  The *tools* did not change — the thirteen
operations still report a failure as a message string and never raise —
but the agent around them is no longer hostage to a data-science stack
it may not need.

*The guard here is the ordinary one.*  `except ImportError`, not the
database toolkit's wider `except Exception`, because the data analysis
toolkit has **no import-time state**: its only import-time failure is a
missing `pandas` or `numpy`, which is an `ImportError`.  `openpyxl` is
needed at *run* time — when pandas actually reads a workbook — and it is
caught by the operation like every other failure.

*The one import that did not move is pinned, not ignored.*  The original
imported `json` and never used it.  The library half drops it, the way
the Windows toolkit dropped its unused `os` — and the check pins the
**exact** difference between the two dependency sets (`{"json",
"llama_index"}`), so no *other* difference can slip in unnoticed.

### Previous change: the Excel toolkit is a module

**Squash-merged into `master` as PR #54** (commit `1fd2063`, head
`c3886bc`).  The PR is based on `master` — not on `main`.

The squash departs from the standing convention of a merge commit, as
PR #52, PR #50, PR #48, PR #46, PR #43 and PR #41 did before it, and
for the same reason: the convention exists for the *stacked* PR chain,
and this PR is based directly on the tip of `master` (`9a33678`), so the
next PR's merge base is `1fd2063` and its diff does not balloon.  The
tree check the convention exists for holds as well — `master`'s tree
after the merge (`0b2045b`) is byte-identical to the head tree of
`c3886bc` that CI ran green.

The **ninth** toolkit of the "every toolkit is a module" series, and the
**first** of the two that were still loose at the project root.  The
data-analysis toolkit is the last one.

| Path | Change |
|------|--------|
| `toolkits/xlsx-toolkit/operations.py` | **New.** The 9 Excel operations and the module-level logger — the library half. No LlamaIndex import. |
| `toolkits/xlsx-toolkit/agent_xlsx_toolkit.py` | **New.** The adapter — the only LlamaIndex-dependent module. It re-exports all 9 operations. |
| `toolkits/xlsx-toolkit/__init__.py` | **New.** The public API surface and the code-level reference to the canonical alias. |
| `toolkits/xlsx-toolkit/README.md`, `pyproject.toml`, `py.typed` | **New.** The module documentation, the standalone distribution (the adapter is the `agent` extra) and the PEP 561 marker. |
| `toolkits/xlsx-toolkit/tests/test_operations.py` | **New** (moved from `tests/test_xlsx_toolkit.py`). Relative imports; extended from 30 to 46 tests. |
| `toolkits/xlsx-toolkit/tests/test_package_layout.py` | **New.** The layout contract — 33 checks. |
| `toolkits/xlsx-toolkit/tests/test_split_verification.py` | **New.** The test of the split-verification script — 16 tests, twelve deliberate drifts. |
| `agent_xlsx_toolkit.py` | **Deleted** at the project root. Git tracked it as a rename to `toolkits/xlsx-toolkit/operations.py`. |
| `tests/test_xlsx_toolkit.py` | **Deleted** at the project root. Git tracked it as a rename to the module-local test. |
| `toolkits/__init__.py` | The `xlsx_toolkit` alias, the `_XLSX_PACKAGE` / `_XLSX_ALIAS` literals and the adapter in `_ADAPTER_MODULES`. |
| `agent_tool_retriever.py`, `agent_tool_selection.py` | The import path moved to the alias, behind a guard. |
| `investigate/no-user-query-error/repro_live.py` | The import path moved to the alias. |
| `pytest.ini` | `toolkits/xlsx-toolkit/tests` added to `testpaths`. |
| `tests/test_toolkit_alias_contract.py` | The Excel toolkit joined the alias contract — the three literal checks and the two tables. |
| `tests/test_logging_cli.py` | The logger now comes from `toolkits.xlsx_toolkit.operations`; the two new modules joined the static inspection. |
| `README.md`, `CHANGELOG.md` | The documentation. |
| `investigate/xlsx-toolkit-module/REPORT_xlsx_toolkit_module.md` | **New.** What was implemented and why. |
| `investigate/xlsx-toolkit-module/verify_split.py` | **New.** The mechanical check. |

**Verifying the change**

```bash
self-development/.venv/bin/python -m pytest self-development/toolkits/xlsx-toolkit/tests -q
self-development/.venv/bin/python self-development/scripts/ci_test_gate.py
```

95 passed, and the CI gate reports **no new failure** (40 known failures,
0 new, 0 fixed).  The baseline was **not** rewritten — the Excel toolkit
had no known failures of its own.

**Three things this change is worth knowing about.**

*The toolkit is no longer able to take the agent down.*  Both call sites
imported it **unguarded**, so a missing `openpyxl` raised an unhandled
`ModuleNotFoundError` out of `_discover_tools()` and the agent did not
boot at all.  This was measured on both trees with `openpyxl` blocked at
the import machinery: `master` raised, the branch booted with **146**
tools instead of 155.  The *tools* did not change — the nine operations
still report a failure as a message string and never raise — but the
agent around them is no longer hostage to a spreadsheet library it may
not need.

*The error contract is pinned now.*  The suite that came with the
toolkit covered the happy paths and two failure paths; the other seven
operations had no failure coverage at all.  "A failure is *reported*,
never raised" is the whole point of the toolkit — an agent calls a tool,
gets a message back and carries on — and it is now pinned for every
operation.

*The guard here is the ordinary one.*  The database toolkit needed
`except Exception`, because its library half reads a configuration file
*at import time* and a missing or malformed one raises something that is
not an `ImportError`.  The Excel toolkit has no import-time state, so
`except ImportError` is enough — and the layout contract checks that
the guard is not widened by accident, because a wider guard would hide a
real problem.

### Previous change: the database toolkit is a module

**Squash-merged into `master` as PR #52** (commit `41608e5`, head
`84f9fa7`).  The PR is based on `master` — not on `main`.

The squash departs from the standing convention of a merge commit, as
PR #50, PR #48, PR #46, PR #43 and PR #41 did before it, and for the
same reason: the convention exists for the *stacked* PR chain, and this
PR is based directly on the tip of `master` (`eb4e479`), so the next
PR's merge base is `41608e5` and its diff does not balloon.  The tree
check the convention exists for holds as well — `master`'s tree after
the merge (`ab2dac5`) is byte-identical to the head tree of `84f9fa7`
that CI ran green.

The **eighth** toolkit of the "every toolkit is a module" series, and
the first whose library half is pinned to a **database driver**.

| Path | Change |
|------|--------|
| `toolkits/db-toolkit/operations.py` | **New.** The configuration loader, the two SQL operations and the module-level logger — the library half. No LlamaIndex import. |
| `toolkits/db-toolkit/agent_db_toolkit.py` | **New.** The adapter — the only LlamaIndex-dependent module. |
| `toolkits/db-toolkit/__init__.py` | **New.** The public API surface and the code-level reference to the canonical alias. |
| `toolkits/db-toolkit/README.md`, `pyproject.toml`, `py.typed` | **New.** The module documentation, the standalone distribution (the adapter is the `agent` extra) and the PEP 561 marker. |
| `toolkits/db-toolkit/tests/test_operations.py` | **New.** 37 tests. The toolkit had **no** suite; this one is **offline** — it drives the operations through a stubbed `psycopg2` and a stubbed `mysql.connector`. |
| `toolkits/db-toolkit/tests/test_package_layout.py` | **New.** The layout contract — 34 checks. |
| `toolkits/db-toolkit/tests/test_split_verification.py` | **New.** The test of the split-verification script — 14 tests, eleven deliberate drifts. |
| `toolkits/db-toolkit/tests/conftest.py` | **New.** Puts the configuration file in place for a session started inside the toolkit directory. |
| `agent_db_toolkit.py` | **Deleted** at the project root. Git tracked it as a rename to `toolkits/db-toolkit/operations.py`. |
| `toolkits/__init__.py` | The `db_toolkit` alias, the `_DB_PACKAGE` / `_DB_ALIAS` literals and the adapter in `_ADAPTER_MODULES`. |
| `agent-torvalds.py`, `agent-torvalds-mw.py`, `agent-torvalds-cpp.py` | The database adapter moved into the guarded block with the other optional ones. |
| `agent_tool_retriever.py`, `agent_tool_selection.py` | The import path moved to the alias, behind a guard. |
| `conftest.py` | **New** at the repository root — the configuration file has to be in place before the alias shim imports the toolkit. |
| `pytest.ini` | `toolkits/db-toolkit/tests` added to `testpaths`. |
| `requirements.txt` | The two drivers and `PyYAML` are declared. |
| `tests/test_toolkit_alias_contract.py` | The database toolkit joined the alias contract; the Windows toolkit was added to the three literal checks as well. |
| `tests/test_logging_cli.py` | The logger now comes from `toolkits.db_toolkit.operations`; the new modules joined the static inspection. |
| `README.md`, `CHANGELOG.md` | The documentation. |
| `investigate/db-toolkit-module/REPORT_db_toolkit_module.md` | **New.** What was implemented and why. |
| `investigate/db-toolkit-module/verify_split.py` | **New.** The mechanical check. |

**Verifying the change**

```bash
self-development/.venv/bin/python -m pytest self-development/toolkits/db-toolkit/tests -q
self-development/.venv/bin/python self-development/scripts/ci_test_gate.py
```

85 passed, and the CI gate reports **no new failure** (40 known failures,
0 new, 0 fixed).  The baseline was **not** rewritten — the database
toolkit had no known failures of its own.

**Three things this change is worth knowing about.**

*The guard at the call sites is wider than everywhere else.*  Every other
toolkit under `toolkits/` fails to import with an `ImportError` when it
is broken.  This one can also fail with a `FileNotFoundError`, because
the library half reads its configuration **when it is imported**.  The
guard catches that — `except Exception`, not `except ImportError` —
and the comment at every call site says why.  Without it, a missing
`db_toolkit_config.yaml` would still take the whole agent down, which is
what it did before this change.

*The import-time configuration load is behaviour, so it moved.*  The
operations read the module-level `_cfg`, so a caller that imports the
module and then calls an operation sees exactly what it always saw.  The
mechanical check pins the *statement*, not only the function that
produces the value.

*The toolkit had no test suite at all.*  Nothing guarded its error
contract — the "a failure is reported, never raised" promise that is
the whole point of the toolkit.  It is now pinned by 37 tests, offline,
with no database server anywhere near them.

**One small drive-by.**  The alias contract listed the canonical path of
every toolkit, but the Windows toolkit had never been added to the three
literal checks — the rows that pin `toolkits.windows_toolkit` as a
*literal* in the shim.  The database toolkit joined them, and so did the
Windows one: the contract is now complete for all ten toolkits.

### Previous change: the Windows toolkit is a module

**Squash-merged into `master` as PR #50** (commit `deb75aa`, head
`966fedb`).  The PR is based on `master` — not on `main`.

The squash departs from the standing convention of a merge commit, as
PR #48, PR #46, PR #43 and PR #41 did before it, and for the same reason:
the convention exists for the *stacked* PR chain, and this PR is based
directly on the tip of `master` (`f20fb34`), so the next PR's merge base
is `deb75aa` and its diff does not balloon.  The tree check the
convention exists for holds as well — `master`'s tree after the merge
(`7a49b8a`) is byte-identical to the head tree of `966fedb` that CI ran
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

**Squash-merged into `master` as PR #48** (commit `ce75ade`, head
`a4b46ec`).  The PR is based on `master` — not on `main`.

The squash departs from the standing convention of a merge commit, as
PR #46, PR #43 and PR #41 did before it, and for the same reason: the
convention exists for the *stacked* PR chain, and this PR is based
directly on the tip of `master` (`b55f9c1`), so the next PR's merge base
is `ce75ade` and its diff does not balloon.  The tree check the
convention exists for holds as well — `master`'s tree after the merge
(`0af67be`) is byte-identical to the head tree of `a4b46ec` that CI ran
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

**Squash-merged into `master` as PR #46** (commit `c9fa14f`, head
`9439f3e`).  The PR is based on `master` — not on `main`.

The squash departs from the standing convention of a merge commit, as
PR #43 and PR #41 did before it, and for the same reason: the
convention exists for the *stacked* PR chain, and this PR is based
directly on the tip of `master` (`64a8061`), so the next PR's merge
base is `c9fa14f` and its diff does not balloon.  The tree check the
convention exists for holds as well — `master`'s tree after the merge
(`395a8f0f`) is byte-identical to the head tree of `9439f3e` that CI ran
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

**Squash-merged into `master` as PR #45** (commit `e6af6ac`, head
`070f2dc`).  The PR is based on `master` — not on `main`.

The operator asked for a **squash**, as for PR #43 and PR #41.  The
departure from the standing convention of a merge commit is safe here,
for the reason recorded under the Git toolkit: the convention exists for
the *stacked* PR chain, and this PR is based directly on the tip of
`master`, so the next PR's merge base is `e6af6ac` and its diff does not
balloon.  The tree check the convention exists for holds as well —
`master`'s tree after the merge (`0688c763`) is byte-identical to the
head tree of `070f2dc` that CI ran green.

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

**Squash-merged into `master` as PR #43** (commit `253bb20`, head
`f32ffe0`).  The PR is based on `master` — not on `main`.

The operator asked for a **squash**, as for PR #41.  The departure from
the standing convention of a merge commit is safe here, for the reason
recorded under the Git toolkit: the convention exists for the *stacked*
PR chain, and this PR is based directly on the tip of `master`, so the
next PR's merge base is `253bb20` and its diff does not balloon.  The
tree check the convention exists for holds as well — `master`'s tree
after the merge (`74a5f5b`) is byte-identical to the head tree of
`f32ffe0` that CI ran green.

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

**Squash-merged into `master` as PR #41** (commit `7852f01`, head
`35d489f`).  The PR is based on `master` — not on `main`.

The operator asked for a **squash** here, which departs from the standing
convention of this file (a **merge commit**).  The departure is safe for
this PR, and the reason is worth recording:

* the standing rationale for the merge commit is the **stacked** PR
  chain — "squashing drops the original SHAs from `master`'s history and
  the next PR's diff balloons to include every layer below it".  This
  PR is **not** stacked: it is based directly on the tip of `master`
  (`5f0302a`), so the next PR's merge base is `7852f01` and its diff is
  computed against that.  Nothing balloons.
* the second reason for the merge commit — "the merge result tree must
  equal the tree the CI gate already validated" — **does** hold for a
  squash, and it was checked: `master`'s tree after the merge
  (`d3242f5`) is byte-identical to the head tree of `35d489f` that CI
  ran green.  The merge introduced no untested content.

The one thing a squash does drop is the branch's own commit from
`master`'s history: `35d489f` is reachable only through the branch
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

**Merged into `master` as PR #39** (merge commit `243b291`, head `8a3fe31`).
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

**Merged.** PR #37, merge commit `592b133` — the top of the chat-manager stack.

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
| Branch | `refactor/shodan-toolkit-flat-layout` — **implemented, committed** (`048c2fb`) and **merged into `master`** as PR #33 |
| Scope | The Shodan toolkit's layout: the toolkit directory **is** the package. The `src/` level and the nested `shodan_toolkit/` directory are gone — every source file sits directly in `toolkits/shodan-toolkit/`, next to `tests/` and `examples/`, the same shape as the MikroTik toolkit. The import name is unchanged (`toolkits.shodan_toolkit` through the alias, `shodan_toolkit` in a standalone install). |
| Status | Implemented: the modules moved, the tests use relative imports, the alias shim points at the new path, the distribution maps the package explicitly, and a new layout contract test (`toolkits/shodan-toolkit/tests/test_package_layout.py`, 11 checks) guards the rule. The toolkit suite is green (162 passed, 2 skipped), the alias contract is green (23/23), and the full suite reports **no new failure** (the CI gate: 40 known failures, 0 new). Committed as `048c2fb` ("refactor: make the Shodan toolkit a flat package") and pushed to `origin/refactor/shodan-toolkit-flat-layout` — the operator approved both the commit and the push (rule 4). Merged into `master` as PR #33 (merge commit `d46ceb4`), after PR #31 (`7df8119`) and PR #32 (`01a393f`) were merged first: the stack had to go bottom-up. |
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
| **A** | The user-settings API and the `\chat-user` command | **implemented and merged** — PR #35, merge commit `5af9371` |
| **B** | The SQLite fallback in `CustomDBConnector` | **implemented and merged** — PR #36, merge commit `be60328` |
| **C** | The removal of the legacy implementation | **implemented and merged** — PR #37, merge commit `592b133` |

> **Update — the stack is merged.** The paragraph above is the investigation's conclusion
> *at the time*; it no longer holds. The legacy implementation **has** been removed, and
> the removal was safe because Phase B's fallback shipped first. `master` is `592b133`.

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

Committed as `048c2fb` ("refactor: make the Shodan toolkit a flat package")
on the branch `refactor/shodan-toolkit-flat-layout`, pushed to
`origin/refactor/shodan-toolkit-flat-layout`, and merged into `master` as
PR #33 (merge commit `d46ceb4`).

### Merge order for the chat-manager stack

The chat-manager work is a **stacked PR** chain too, and the order is forced:

| # | Branch | Base | Merge commit |
|---|---|---|---|
| #35 | `feature/chat-user-settings` | `master` | `5af9371` |
| #36 | `feature/chat-manager-sqlite-fallback` | `feature/chat-user-settings` | `be60328` |
| #37 | `feature/chat-manager-remove-legacy-memory` | `feature/chat-manager-sqlite-fallback` | `592b133` |

**Status: merged.** The stack landed in `master` bottom-up: `5af9371` (#35), `be60328`
(#36), `592b133` (#37). The **Base** column records the branch each PR was *opened
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
| #31 | `fix/toolkit-alias-reference` | `master` | `7df8119` |
| #32 | `refactor/toolkit-adapter-location` | `fix/toolkit-alias-reference` | `01a393f` |
| #33 | `refactor/shodan-toolkit-flat-layout` | `refactor/toolkit-adapter-location` | `d46ceb4` |

**Bottom-up: 31, then 32, then 33.** Merging #33 first would drag #31 and
#32's commits into `master`, leave those two PRs empty, and break #32's base
branch. To land them all in `master`, each PR's base is retargeted to
`master` **after** the PR below it has been merged, then merged with a
**merge commit** (never squash: squashing drops the original SHAs from
`master`'s history, the next PR's merge base moves back to `080e876`, and its
diff balloons to include all three layers).

Merge commits were used for a second reason: the merge result tree must equal
the tree the CI gate already validated. With merge commits, `master`'s tree
after #33 (`37bde2d`) is byte-identical to the head tree of `d831346` that
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

Committed as `6d64cba` ("fix: a timeout the model can see") and pushed to
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

Committed as `e81672a` ("fix: a decorated question is asked as the question it
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
*   Add 'toolkits/shodan-toolkit/' from commit 'db3fbc8...'
|\
| * db3fbc8 chore: remove project-root RULES.md
| * b18ab77 fix: correct Shodan CLI argument vectors and harden library packaging
| * 759ba0b Initial commit: shodan-toolkit
* c069e91 fix: make the HITL timeout default to "no timeout" (wait for the user) (#23)
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

| Branch | `feature/docs/ollama-local-setup` (off `master`, `c069e91`) |
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
| Branch | `feature/hitl-no-timeout` (off `master`, `35600f7`) |
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
set at `HEAD` (`35600f7`) and after the change is byte-identical —
77 pre-existing failures, unchanged (76 failed + 1 error).

### Earlier work: the MikroTik RouterOS toolkit

| Item | Status |
|---|---|
| Branch | `feature/mikrotik-routeros-toolkit` (off `master`, `de3bfaf`) |
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
