# GitHub Toolkit

GitHub API integration and Pull Request management, exposed as tools for a
LlamaIndex `FunctionAgent`.

The toolkit is a **module** — a folder, not a loose file:

```
toolkits/github-toolkit/
├── __init__.py              # the public API surface
├── operations.py            # the GitHub operations — the library half
├── agent_github_toolkit.py  # the LlamaIndex adapter
├── py.typed                 # PEP 561 marker
└── tests/                   # the module-local tests
```

## The two halves

| Module | Role | LlamaIndex | Third party |
|--------|------|------------|-------------|
| `operations.py` | the 13 GitHub operations | **no** | `requests` |
| `agent_github_toolkit.py` | the adapter — `get_all_tools()` | **yes** | `llama-index-core` |

The split is the point. `operations.py` carries **no** LlamaIndex import,
so the GitHub operations stay usable — and testable — as a plain Python
library. The adapter is the one module that knows about the agent
framework, and it is imported on demand. Importing the toolkit therefore
never pulls LlamaIndex into the process.

## Installing

Standalone:

```bash
pip install .            # the library half
pip install '.[agent]'   # and the LlamaIndex adapter
```

The library half depends on `requests` — the HTTP client the GitHub REST
API is called through — and on nothing else.

## Authentication

The token is resolved in this order:

1. the `GITHUB_TOKEN` environment variable;
2. the GitHub CLI — `gh auth token`;
3. nothing, in which case the API is called unauthenticated.

The toolkit never writes a token to disk and never sends one anywhere
except to `api.github.com`.

## Importing

The directory name contains a hyphen, so the package is reached through the
alias that `toolkits/__init__.py` registers:

```python
from toolkits.github_toolkit import github_create_pull_request
from toolkits.github_toolkit.agent_github_toolkit import get_all_tools
```

The adapter pulls the library in with a *relative* import, so the adapter
and the library share one set of module objects — there is never a second
copy of `operations.py` in memory.

## Using the tools

```python
from toolkits.github_toolkit.agent_github_toolkit import get_all_tools

tools = get_all_tools()   # 13 FunctionTool objects
```

The 13 tools carry the **Version Control** category, so the startup tool
selection menu (`--select`, and `\tools` / `\tool-select` in the TUI) can
load the whole category on its own.

## The tool surface

**Tier 4 — authentication and configuration**

| Tool | What it does |
|------|--------------|
| `git_check_auth` | Verify GitHub authentication — token source, API access, user |
| `git_get_user_info` | The authenticated user's profile |
| `git_configure_credentials` | Set `user.name` / `user.email` in the local repository |

**Tier 3 — Pull Request operations**

| Tool | What it does |
|------|--------------|
| `github_create_pull_request` | Open a PR |
| `github_list_pull_requests` | List PRs, filtered by state / head / base |
| `github_get_pull_request` | One PR in detail |
| `github_update_pull_request` | Change title, body, state, base or permissions |
| `github_close_pull_request` | Close a PR without merging it |
| `github_merge_pull_request` | Merge — `merge`, `squash` or `rebase` |
| `github_comment_on_pull_request` | Leave a comment |
| `github_review_file_changes` | The changed files and their patches |
| `github_get_pull_request_comments` | The comment thread |
| `github_get_pull_request_reviews` | The review submissions and their state |

## The error contract

A failure is **reported**, never raised:

* a `bool` — `git_configure_credentials` returns `False`;
* a dict with `"success": False` and an `"error"` key — every API
  operation;
* the success dicts carry the payload under `"data"`, plus a few
  convenience keys (`pr_number`, `pr_url`, `comment_id`, `count`,
  `files_changed`, `merged`, …).

The transport is covered too: a `requests` exception becomes
`{"success": False, "error": "Request failed: ..."}`, and anything else
becomes `{"success": False, "error": "Unexpected error: ..."}`.

## The tests

```bash
python -m pytest toolkits/github-toolkit/tests -q
```

The suite is offline: `requests` is stubbed at the transport boundary, so
no test reaches the network and no test needs a token.
