# Git Toolkit

Git repository management and version control operations, exposed as tools
for a LlamaIndex `FunctionAgent`.

The toolkit is a **module** — a folder, not a loose file:

```
toolkits/git-toolkit/
├── __init__.py            # the public API surface
├── operations.py           # the Git operations — the library half
├── agent_git_toolkit.py    # the LlamaIndex adapter
├── py.typed                # PEP 561 marker
└── tests/                  # the module-local tests
```

## The two halves

| Module | Role | LlamaIndex | Third party |
|--------|------|------------|-------------|
| `operations.py` | the 27 Git operations | **no** | `pygit2` |
| `agent_git_toolkit.py` | the adapter — `get_all_tools()` | **yes** | `llama-index-core` |

The split is the point. `operations.py` carries **no** LlamaIndex import,
so the Git operations stay usable — and testable — as a plain Python
library. The adapter is the one module that knows about the agent
framework, and it is imported on demand. Importing the toolkit therefore
never pulls LlamaIndex into the process.

## Installing

Standalone:

```bash
pip install .            # the library half
pip install '.[agent]'   # and the LlamaIndex adapter
```

The library half depends on `pygit2` (the binding to `libgit2`) and on
nothing else.

## Importing

The directory name contains a hyphen, so the package is reached through the
alias that `toolkits/__init__.py` registers:

```python
from toolkits.git_toolkit import git_get_status, git_commit
from toolkits.git_toolkit.agent_git_toolkit import get_all_tools
```

The adapter pulls the library in with a *relative* import, so the adapter
and the library share one set of module objects — there is never a second
copy of `operations.py` in memory.

## Using the tools

```python
from toolkits.git_toolkit.agent_git_toolkit import get_all_tools

tools = get_all_tools()   # 27 FunctionTool objects
```

The 27 tools carry the **Version Control** category, so the startup tool
selection menu (`--select`, and `\tools` / `\tool-select` in the TUI) can
load the whole category on its own.

## The tool surface

**Tier 1 — basic operations**

| Tool | Purpose |
|------|---------|
| `git_get_latest_commit` | the SHA of the most recent commit |
| `git_init_repo` | initialise a repository in an existing directory |
| `git_add_files` | stage specific files, or everything with `['.']` |
| `git_commit` | commit the staged changes |
| `git_get_status` | staged / unstaged / untracked, categorised |
| `git_generate_changelog` | a changelog built from the commit history |
| `git_get_recent_changes` | the last *n* commits with author and date |
| `git_update_changelog` | add a changelog entry by hand |
| `git_get_email` | the configured `user.email` |
| `git_init_and_commit` | initialise **and** make the first commit |
| `git_add_all_changes` | stage every change; accepts relative paths |

**Tier 2 — remote operations**

| Tool | Purpose |
|------|---------|
| `git_remote_add` | configure a remote URL |
| `git_push` | push a branch, optionally setting the upstream |
| `git_remote_get` | list the configured remotes |
| `git_set_upstream` | link a local branch to a remote branch |
| `git_pull` | fetch **and** merge |
| `git_fetch` | fetch only — no working-tree change |

**Tier 3 — branch management**

| Tool | Purpose |
|------|---------|
| `git_branch_list` | list the local (or remote-tracking) branches |
| `git_branch_create` | create a branch from a start point |
| `git_branch_checkout` | switch to a branch |
| `git_branch_delete` | delete a branch |
| `git_branch_rename` | rename the current branch |

**Tier 4 — diff and sync**

| Tool | Purpose |
|------|---------|
| `git_diff` | the working tree, or a target, as a unified diff |
| `git_diff_staged` | what is about to be committed |
| `git_merge` | merge a branch, reporting conflicts |
| `git_rebase` | replay commits onto another branch |
| `git_log_compare` | what is ahead and what is behind |

## The error contract

A tool never raises. Every failure is reported as a value:

* the `bool`-returning tools return `False`
* the `dict`-returning tools return `{"success": False, "error": "..."}`
* the `str`-returning tools return `"Error: ..."`

The one exception is `git_update_changelog`, which catches broadly and
returns `False` — a changelog that cannot be written is not worth a
traceback.

## Authentication

The remote operations read `TORVALDS_GITHUB_TOKEN` from the environment
and pass it to `pygit2` as an OAuth credential. Without the variable, the
credentials callback returns `None` and the operation fails the way an
unauthenticated remote would.

## Tests

```bash
pytest toolkits/git-toolkit/tests
```

The suite covers the operations themselves and the **layout contract** —
the rules that keep the toolkit a module: the flat directory, the relative
imports, the alias, and the LlamaIndex-free library half.
