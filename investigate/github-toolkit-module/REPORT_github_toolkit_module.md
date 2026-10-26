# The GitHub toolkit is a module

**Branch:** `refactor/github-toolkit-module`
**Base:** `master`
**Status:** implemented and verified, awaiting the operator's approval to
commit and push

---

## 1. The state before

`agent_github_toolkit.py` was a single loose file at the project root —
842 lines, next to 18 other `agent_*.py` modules, while the features that
were already modules lived in folders under `toolkits/`.

It carried two different things:

* **13 GitHub operations** — the REST API calls, the token resolution and
  the credential configuration;
* **`get_all_tools()`** — the LlamaIndex adapter, the only part of the
  file that knew about the agent framework.

The file also had **no test suite**.  There was no
`tests/test_github_toolkit.py`, and nothing in `tests/ci_baseline.txt`
mentioned it either.  That is the fact that shaped this change, and
section 5 is about it.

### The call sites

| Site | How it imported the toolkit |
|------|----------------------------|
| `agent-torvalds.py:74` | `from agent_github_toolkit import get_all_tools as get_github_tools` |
| `agent-torvalds-mw.py:86` | the same |
| `agent_tool_retriever.py:100` | `from agent_github_toolkit import get_all_tools as _get_github` |
| `agent_tool_selection.py:58` | the same |
| `tests/test_logging_cli.py:35` | `from agent_github_toolkit import logger as github_logger` |

Four of the five imported the adapter **unguarded**.  A toolkit under
`toolkits/` is optional by definition, so that had to change.

Unlike the Git toolkit, the C++ orchestrator never imported the GitHub
toolkit at all — `agent-torvalds-cpp.py` has no reference to it.  So
there was no star import to preserve; the adapter re-exports the 13
functions anyway, because the toolkit used to be a single module and
`from agent_github_toolkit import *` was a natural way to reach them.

---

## 2. The decision: split the file, do not just move it

Exactly as for the math and the Git toolkits, the file is split:

| Module | Role | LlamaIndex | Third party |
|--------|------|------------|-------------|
| `operations.py` | the 13 GitHub operations | **no** | `requests` |
| `agent_github_toolkit.py` | the adapter — `get_all_tools()` | **yes** | `llama-index-core` |

The library half keeps `requests`, the HTTP client the REST API is
called through.  A GitHub operation is a GitHub operation whether or not
an agent framework is installed, so the dependency belongs to the
library half — the same argument as `pygit2` for the Git toolkit, and the
reason the contract pins the *exact* dependency set rather than merely
"no LlamaIndex".

### The error contract

A failure is **reported**, never raised:

* a `bool` — `git_configure_credentials` returns `False`;
* a dict with `"success": False` and an `"error"` key — every API
  operation;
* the transport is covered too: a `requests` exception becomes
  `{"success": False, "error": "Request failed: ..."}`, and anything else
  becomes `{"success": False, "error": "Unexpected error: ..."}`.

All of it moved verbatim.

---

## 3. The hyphen, and the alias

The directory is `toolkits/github-toolkit/`, reached through the alias
`toolkits.github_toolkit` that `toolkits/__init__.py` registers — as a
**literal**, next to the other four.

```python
from toolkits.github_toolkit import github_create_pull_request
from toolkits.github_toolkit.agent_github_toolkit import get_all_tools
```

The adapter pulls the library in with a **relative** import, so the two
share one set of module objects — there is never a second copy of
`operations.py` in memory.  A layout-contract check pins it.

---

## 4. The call sites

The adapter is now imported **behind a guard**, like the other toolkits
under `toolkits/`: a missing or broken toolkit degrades to "no tools",
never to a failed boot.

```python
try:
    from toolkits.github_toolkit.agent_github_toolkit import (
        get_all_tools as get_github_tools,
    )
except ImportError:  # pragma: no cover - the toolkit is optional

    def get_github_tools() -> list:
        """The GitHub toolkit is unavailable - expose no tools."""
        return []
```

The retriever and the selection menu got the same treatment.  The
retriever keeps its `include_github_tools` flag, so the toolkit can
still be left out of the inventory.

---

## 5. The suite the toolkit never had

This is the part that differs from the other two toolkits.

The math and the Git toolkits had tests that moved with them, so
"behaviour-neutral" was something the existing suite could **show**.  The
GitHub toolkit had no tests at all — so a move of it would have been an
entirely unverified refactoring, and the layout contract alone would not
have made the claim true.

So the toolkit got a suite: `toolkits/github-toolkit/tests/test_operations.py`,
**95 tests** that pin the behaviour of every operation.

| Group | What it pins |
|-------|--------------|
| `TestGetGithubToken` | the environment variable, the `gh` CLI fallback, and that a failing, missing, hanging or empty CLI is not an error |
| `TestGetHeaders` | the base headers, and the `Authorization` header when there is a token |
| `TestMakeRequest` | 200 / 201 / 204, the API error message, the error *details*, the non-JSON fallback, the truncation at 200 characters, the transport error and the unexpected error |
| `TestCheckAuth` | the token source (`token` / `gh_cli` / `none`), the profile, and a token the API rejects |
| `TestGetUserInfo` | the profile and the failure |
| `TestConfigureCredentials` | both `git config` calls, a failing `git`, a nonzero return code |
| `TestCreatePullRequest` | the payload, the defaults, the `pr_number` / `pr_url` convenience keys |
| `TestListPullRequests` | the default query, the optional filters, and the `per_page` cap at 100 |
| `TestGetPullRequest`, `TestUpdatePullRequest` | the URL, the PATCH payload, and that **no** request is made when there is no field to update |
| `TestClosePullRequest` | that it is an update with `state='closed'` |
| `TestMergePullRequest` | the `PUT`, the merge method, the commit title and message |
| `TestCommentOnPullRequest` | the issues endpoint, the `comment_id` / `comment_url` keys |
| `TestReviewFileChanges` | the files endpoint and `files_changed` |
| `TestGetPullRequestComments`, `TestGetPullRequestReviews` | the endpoints and the counts |
| `TestErrorContract` | that **no** operation ever raises, whatever the transport does |
| `TestSerialisable` | that the result can be handed to the model as JSON |

**The suite is offline.**  `requests` is stubbed at the transport
boundary, and the GitHub CLI is stubbed too.  No test reaches
`api.github.com` and no test needs a token.  An autouse fixture removes
`GITHUB_TOKEN` from the environment and makes `gh` missing, so a
developer who happens to have either of them exported gets the same
result as everybody else.

### The baseline did not move

`tests/ci_baseline.txt` is **unchanged** — the toolkit had no known
failures of its own, so there was nothing to rewrite.  The CI gate
reports the same 40 known failures, **0 new and 0 fixed**.

---

## 6. What was added, not just moved

### The layout contract

`toolkits/github-toolkit/tests/test_package_layout.py` — **25 checks**:
the flat layout, the relative imports, the alias, the LlamaIndex
boundary (AST-based, so prose in a docstring does not trip it), the
dependency profile of the library half, the 13-tool surface, and the
rule that the toolkit is not a loose file at the project root.

One of the 25 is new to the series: **`test_the_toolkit_is_tested`**.  The
GitHub toolkit is the first one of the series that arrived without tests,
so the contract now says so.

### The split was checked mechanically, not by eye

The tool descriptions are **behaviour**: they are what the retriever
matches against and what the model reads.  So the split was verified by
AST against the original file at `HEAD`:

* the 13 tool names, their **order** and their **descriptions** — compared
  one by one;
* the 13 signatures — every parameter and every default;
* every docstring, byte for byte;
* the module-level constants.

**That check caught a drift that reading would not have.**  The
description of `github_get_pull_request_reviews` had been reworded from
"Get review submissions **for** a Pull Request" to "Get review submissions
**on** a Pull Request".  A one-word change, in a string that feeds the
retriever.  It is fixed, and the comparison is now a script.

The rule for the rest of the series: **move verbatim, and let a script
prove it.**

### The packaging

`toolkits/github-toolkit/pyproject.toml` — a standalone distribution
(`pip install ./toolkits/github-toolkit`) that depends on `requests` and
on nothing else; the adapter is the `agent` extra.  `py.typed` is the
PEP 561 marker.

---

## 7. Verification

```
toolkits/github-toolkit/tests   120 passed (95 operations + 25 layout contract)
alias contract                   44 passed
logging CLI test                 28 passed
full suite                       1830 passed, 9 skipped, 39 failed + 1 error
CI gate                          40 known -> 40 actual, 0 new, 0 fixed
```

The 39 failures and the 1 error are the **40 known failures** of the
baseline — the same 40, in the same files, with the same names.  The
suite grew by 127 tests: the 120 of the new toolkit and the 7 the alias
contract gained.

The CI gate is the number that matters: **no new failure, and no fixed
one** — which is what a pure refactoring has to report.

`import toolkits` still does not import LlamaIndex, and the startup tool
selection menu still finds the 13 GitHub tools under the **Version
Control** category — 40 in that category in total, the other 27 being the
Git toolkit's.

### A collision that does not happen

The GitHub toolkit's three authentication tools are named `git_*` —
`git_check_auth`, `git_get_user_info`, `git_configure_credentials` — and
the Git toolkit owns the `git_*` namespace.  Both are now loaded into the
same process, so the names could have shadowed each other.

They do not: the two surfaces are **disjoint** (27 + 13 = 40 distinct
names), and the whole menu is 155 tools with 154 distinct names.  The
one duplicate — `get_system_info`, from the OS and the Windows toolkits —
is **pre-existing**: it is there on `master` too, with the same count of
155, and this change neither added nor removed a tool.

The naming is still a hazard for the rest of the series, though: a
future Git toolkit operation called `git_check_auth` would collide for
real.  Renaming the three GitHub tools to `github_*` would remove the
hazard, and it belongs in its own PR — the names are in the tool
descriptions the retriever matches against, so they are behaviour.

---

## 8. A latent inconsistency, left alone

`git_check_auth()` reports the authentication method as:

```python
method = "gh_cli" if os.environ.get("GITHUB_TOKEN") is None else "token"
```

That is `is None`, while `_get_github_token()` treats an **empty**
`GITHUB_TOKEN` as absent and falls through to the CLI.  So with
`GITHUB_TOKEN=""` exported and a working `gh` CLI, the token comes from
the CLI but the method is reported as `"token"`.

The behaviour is **unchanged** — this is a refactoring, and the point of
the series is that nothing moves.  The test suite pins the current
behaviour as a characterisation test, so the inconsistency is now
*documented* rather than invisible.  Fixing it belongs in its own PR,
where the change is the change.
