# Investigation: Refactor Git Toolkit to Use pygit2

**Date**: 2025-01-15  
**Target Branch**: `feature/pygit2-refactor`  
**Status**: Investigation complete — ready for implementation  

---

## 1. Objective

Refactor all Git tools in `agent_git_toolkit.py` to use **pygit2** (Python binding to libgit2) instead of shell-based Git commands executed via `subprocess`. The external interface—tool names, parameters, return formats, and the overall tool list structure—must remain **exactly the same** to ensure full compatibility with the FunctionalAgent system.

A new environment variable `TORVALDS_GITHUB_TOKEN` must be introduced for authentication when interacting with GitHub repositories.

---

## 2. Current State Analysis

### 2.1 File Under Analysis

**File**: `agent_git_toolkit.py`  
**Location**: `/home/kbush/ai-agent-investiagte/agent-torvalds/agent_git_toolkit.py`  
**Lines of Code**: ~900 lines  
**Current Dependencies**: `subprocess`, `os`, `logging`, `datetime`, `typing`, `llama_index.core.tools.FunctionTool`

### 2.2 Tool Inventory

The file exposes **26 Git tools** via `get_all_tools()`. Each tool currently uses `subprocess.run()` to invoke the Git CLI. Here is the complete inventory:

| # | Tool Function | Current Subprocess Command | Return Type |
|---|--------------|---------------------------|-------------|
| 1 | `git_get_latest_commit` | `git log -1 --format=%H` | `str` |
| 2 | `git_init_repo` | `git init` | `bool` |
| 3 | `git_add_files` | `git add <files>` | `dict` |
| 4 | `git_commit` | `git commit -m <msg>` (with `_has_staged_changes`) | `bool` |
| 5 | `git_get_status` | `git status --porcelain` (with `_parse_git_status_porcelain`) | `dict` |
| 6 | `git_generate_changelog` | `git log --pretty=format:%h\|%ad\|%s` | `bool` |
| 7 | `git_get_recent_changes` | `git log -<n> --pretty=format:%h\|%ad\|%s\|%an` | `list[dict]` |
| 8 | `git_update_changelog` | **No subprocess** — file read/write only | `bool` |
| 9 | `git_get_email` | `git config --get user.email` | `str` |
| 10 | `git_init_and_commit` | `git init`, `git config`, `git add .`, `git commit --allow-empty` | `bool` |
| 11 | `git_remote_add` | `git remote add <name> <url>` | `bool` |
| 12 | `git_push` | `git push [--set-upstream] <remote> <branch>` | `bool` |
| 13 | `git_remote_get` | `git remote -v` | `list[dict]` |
| 14 | `git_set_upstream` | `git branch --set-upstream-to <remote>/<branch>` | `bool` |
| 15 | `git_branch_list` | `git branch [-r]` | `list[str]` |
| 16 | `git_branch_create` | `git branch <name> <start_point>` | `bool` |
| 17 | `git_branch_checkout` | `git checkout <branch>` | `bool` |
| 18 | `git_branch_delete` | `git branch [-d\|-D] <branch>` | `bool` |
| 19 | `git_branch_rename` | `git branch -m <new_name>` | `bool` |
| 20 | `git_diff` | `git diff [target]` | `str` |
| 21 | `git_diff_staged` | `git diff --staged` | `str` |
| 22 | `git_pull` | `git pull [remote] [branch]` | `dict` |
| 23 | `git_fetch` | `git fetch <remote>` | `dict` |
| 24 | `git_merge` | `git merge [-s <strategy>] <branch>` | `dict` |
| 25 | `git_rebase` | `git rebase [-s <strategy>] <branch>` | `dict` |
| 26 | `git_log_compare` | `git log <b2>..<b1>` and `git log <b1>..<b2>` | `dict` |

### 2.3 Helper Functions (Internal)

| Helper | Purpose | Current Implementation |
|--------|---------|----------------------|
| `_has_staged_changes` | Check if HEAD has staged changes | `git rev-parse HEAD` + `git diff-index --cached --quiet HEAD` |
| `_parse_git_status_porcelain` | Parse porcelain output into structured dict | String parsing of `git status --porcelain` |

### 2.4 pygit2 Availability

pygit2 is **NOT currently installed** in the project. It needs to be added to `requirements.txt`.

---

## 3. pygit2 API Mapping Analysis

### 3.1 Core Repository Access Pattern

All tools will follow this common pattern:

```python
import pygit2

repo = pygit2.Repository(path)
# ... perform operations ...
```

For repository initialization:
```python
pygit2.init_repository(path)
```

### 3.2 Tool-by-Tool pygit2 Mapping

#### Tier 1: Basic Operations

| Tool | pygit2 Equivalent | Complexity |
|------|------------------|------------|
| `git_get_latest_commit` | `repo.heads[repo.head.shorthand].target.hex` or `repo.head.peel(pygit2.Commit).id.hex` | Low |
| `git_init_repo` | `pygit2.init_repository(path)` | Low |
| `git_add_files` | `repo.index.add(files)` then `repo.index.write()` | Low |
| `git_commit` | `repo.create_commit('HEAD', author, committer, message, tree, parents)` | Medium |
| `git_get_status` | `repo.status()` returns dict of file statuses | Medium |
| `git_generate_changelog` | Iterate `repo.walk(repo.head.target)` filtering merges | Medium |
| `git_get_recent_changes` | Same as above with author/date extraction | Medium |
| `git_update_changelog` | **No change** — already pure file I/O | None |
| `git_get_email` | `repo.config.get('user.email')` | Low |
| `git_init_and_commit` | Combination of init, config, add, commit | Medium |

#### Tier 2: Remote Operations

| Tool | pygit2 Equivalent | Complexity |
|------|------------------|------------|
| `git_remote_add` | `repo.create_remote(name, url)` | Low |
| `git_push` | `repo.push(remote_name, [branch], credentials=...)` | High (auth) |
| `git_remote_get` | Iterate `repo.remotes` getting name and fetch URL | Low |
| `git_set_upstream` | `repo.branches.local[branch].set_upstream(target_branch)` | Medium |
| `git_pull` | `repo.fetch(remote)` + `repo.merge(...)` | High (auth+merge) |
| `git_fetch` | `repo.fetch(remote, credentials=...)` | High (auth) |

#### Tier 3: Branch Management

| Tool | pygit2 Equivalent | Complexity |
|------|------------------|------------|
| `git_branch_list` | `list(repo.branches.local)` or `list(repo.branches.remote)` | Low |
| `git_branch_create` | `repo.create_branch(name, repo.revparse_single(start_point))` | Low |
| `git_branch_checkout` | `repo.checkout('refs/heads/branch_name')` | Medium |
| `git_branch_delete` | `repo.branches.local.delete(name)` | Low |
| `git_branch_rename` | `repo.branches.local.rename(name, new_name, force=True)` | Low |

#### Tier 4: Diff & Sync

| Tool | pygit2 Equivalent | Complexity |
|------|------------------|------------|
| `git_diff` | `repo.diff(old_tree, new_tree)` or `repo.index.diff(head)` | Medium |
| `git_diff_staged` | `repo.index.diff('HEAD')` | Medium |
| `git_merge` | `repo.merge_analysis(branch)` + `repo.merge(branch)` | High |
| `git_rebase` | **pygit2 has no direct rebase API** — needs workaround | Very High |
| `git_log_compare` | `repo.graph_ahead_behind(commit1, commit2)` + walk | Medium |

### 3.3 Authentication Mechanism

pygit2 supports credentials via callback functions. The `TORVALDS_GITHUB_TOKEN` env var will be used to construct credentials:

```python
import os

def get_credentials(url, username_from_url, allowed_types):
    token = os.environ.get("TORVALDS_GITHUB_TOKEN")
    if token and pygit2.credentials.CREDTYPE_USER_PASS in allowed_types:
        return pygit2.credentialscred_string("oauth2", token)
    return None
```

This credential callback will be used in `git_push`, `git_pull`, and `git_fetch`.

---

## 4. Issues Identified

### 4.1 Critical Challenges

1. **`git_rebase` has no direct pygit2 API** — pygit2 does not expose a native rebase function. Options:
   - Use `repo.rebase()` if available (pygit2 >= 1.7+)
   - Fall back to a subprocess call for rebase only
   - Implement manual rebase using cherry-pick operations

2. **`git_diff` unified format output** — pygit2's `Diff` object produces structured diff data, not the traditional unified text format. We need to use `diff.diffstring` to get the text output that matches current behavior.

3. **`git_merge` conflict detection** — pygit2's merge returns conflict information differently than the CLI. We need to check `repo.index.conflicts` after merge.

4. **`git_set_upstream`** — pygit2's branch upstream API requires full ref names (`refs/remotes/origin/branch`), not just `origin/branch`.

### 4.2 Medium Complexity Issues

5. **`git_get_status` return format** — pygit2's `repo.status()` returns a dict mapping paths to status flags (integers), not porcelain strings. We need to:
   - Convert pygit2 status flags to porcelain-equivalent strings
   - Maintain the exact same return structure
   - Reuse `_parse_git_status_porcelain` or adapt it

6. **`git_init_and_commit`** — needs to handle empty repo commits. pygit2's `create_commit` requires a valid tree OID. For empty commits, we need to use `repo.root_tree.id`.

7. **`git_pull`** — pygit2 doesn't have a direct `pull` operation. It requires `fetch` + `merge` (or `rebase`). We need to replicate the exact behavior.

### 4.3 Low Complexity Issues

8. **Error message formatting** — subprocess errors produce specific CLI error messages. pygit2 raises different exceptions (`GitError`, `OSError`). We need to catch and format these consistently.

9. **`git_log_compare`** — the current implementation uses `git log A..B` range syntax. pygit2 equivalent requires manual commit walking with `repo.walk()`.

---

## 5. Authentication Analysis

### 5.1 Current Auth Mechanism

Currently, the Git CLI handles authentication transparently via:
- SSH keys configured in `~/.ssh/`
- Git credential helpers
- `.gitconfig` settings

### 5.2 New Auth Mechanism with pygit2

pygit2 requires explicit credential callbacks for remote operations. The tools that need authentication:

| Tool | Auth Needed? | pygit2 Method |
|------|-------------|---------------|
| `git_push` | Yes | `credentials=get_credentials` callback |
| `git_pull` | Yes | Same callback |
| `git_fetch` | Yes | Same callback |
| `git_remote_add` | No | Just stores URL |
| `git_remote_get` | No | Just reads config |
| `git_set_upstream` | No | Local operation |

### 5.3 Environment Variable Design

```python
TORVALDS_GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

- Read via `os.environ.get("TORVALDS_GITHUB_TOKEN")`
- Used in credential callback for HTTPS URLs
- Falls back gracefully if not set (for local/SSH operations)

---

## 6. Files to Modify

| File | Change | Scope |
|------|--------|-------|
| `agent_git_toolkit.py` | Replace all subprocess calls with pygit2 | Major refactor |
| `requirements.txt` | Add `pygit2` dependency | 1 line |

---

## 7. Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|------------|
| pygit2 API differences cause return format changes | High | Medium | Extensive testing against current behavior |
| `git_rebase` not fully supported by pygit2 | High | High | Subprocess fallback for rebase only |
| Authentication breaks for existing SSH setups | Medium | Medium | Graceful fallback, only use token for HTTPS |
| Performance regression on large repos | Low | Low | pygit2 is typically faster than subprocess |
| Missing pygit2 on deployment systems | Medium | Low | Add to requirements.txt, CI check |

---

## 8. Verification Checklist

- [ ] All 26 tools return identical data structures
- [ ] No `subprocess` imports remain in `agent_git_toolkit.py`
- [ ] `TORVALDS_GITHUB_TOKEN` is used for HTTPS auth
- [ ] Error messages match current format where possible
- [ ] All existing tests pass
- [ ] New tests for pygit2-specific error handling
- [ ] `get_all_tools()` returns identical tool list
- [ ] Function signatures unchanged
- [ ] Docstrings preserved

---

## 9. Estimated Effort

| Task | Estimated Time |
|------|---------------|
| pygit2 installation & environment setup | 15 min |
| Implement basic operations (Tier 1) | 4 hours |
| Implement remote operations (Tier 2) | 4 hours |
| Implement branch management (Tier 3) | 2 hours |
| Implement diff & sync operations (Tier 4) | 4 hours |
| Implement credential callback & auth | 2 hours |
| Testing & debugging | 4 hours |
| **Total** | **~17 hours** |

---

*Investigation complete. Ready to proceed with implementation proposal.*
