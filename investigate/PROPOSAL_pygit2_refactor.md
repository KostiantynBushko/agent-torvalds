# Proposal: Refactor Git Toolkit to Use pygit2

## Overview

This proposal outlines the implementation plan for refactoring all Git tools in `agent_git_toolkit.py` to use **pygit2** (Python binding to libgit2) instead of shell-based Git commands executed via `subprocess`. The external interface—tool names, parameters, return formats, and the overall tool list structure—will remain **exactly the same** to ensure full compatibility with the FunctionalAgent system.

## Problem Statement

The current Git toolkit implementation relies entirely on `subprocess.run()` calls to the Git CLI. This approach has several drawbacks:

1. **Performance overhead** — Each tool invocation spawns a new process, adds I/O latency, and requires parsing CLI output strings.
2. **Fragile output parsing** — Tools like `git_get_status`, `git_remote_get`, and `git_get_recent_changes` parse CLI output via string splitting, which is brittle and breaks if Git changes its output format.
3. **Error handling inconsistency** — `subprocess.CalledProcessError` messages differ from native Python exceptions, making debugging harder.
4. **Platform compatibility** — subprocess-based Git commands depend on the Git CLI being available in the system PATH.
5. **Security** — Spawning subprocesses for every Git operation introduces potential injection vectors if paths are not properly sanitized.

## Proposed Solution

Replace all subprocess-based Git operations with native pygit2 API calls. pygit2 provides a clean, Pythonic interface to libgit2 (the same C library that Git is built on top of), giving us:

- **Direct API access** — No string parsing needed; return structured Python objects.
- **Better performance** — In-process operations avoid process spawning overhead.
- **Consistent error handling** — Native `GitError` exceptions with structured data.
- **Cross-platform reliability** — pygit2 bundles libgit2, removing CLI dependency.

### New Environment Variable

```
TORVALDS_GITHUB_TOKEN
```

This variable will be used by the refactored pygit2 implementation for authentication when interacting with GitHub repositories over HTTPS. It will be read internally by tools that perform authenticated operations (`git_push`, `git_pull`, `git_fetch`).

---

## Implementation Plan

### Phase 1: Infrastructure & Dependencies

**Tasks:**
1. Add `pygit2` to `requirements.txt`
2. Create a shared credential callback function that reads `TORVALDS_GITHUB_TOKEN`
3. Create a helper function `_open_repo(path)` that opens a pygit2 repository with proper error handling

**Files:** `agent_git_toolkit.py`, `requirements.txt`

### Phase 2: Basic Operations (Tier 1)

Refactor tools that perform local repository operations:

| Tool | pygit2 API |
|------|-----------|
| `git_get_latest_commit` | `repo.head.peel(pygit2.Commit).id.hex` |
| `git_init_repo` | `pygit2.init_repository(path)` |
| `git_add_files` | `repo.index.add(files)` + `repo.index.write()` |
| `git_commit` | `repo.create_commit(...)` |
| `git_get_status` | `repo.status()` with status flag conversion |
| `git_generate_changelog` | `repo.walk(repo.head.target)` with merge filtering |
| `git_get_recent_changes` | Same walk + author/date extraction |
| `git_update_changelog` | **No change** (pure file I/O) |
| `git_get_email` | `repo.config.get('user.email')` |
| `git_init_and_commit` | Combination of init + config + add + commit |

### Phase 3: Remote Operations (Tier 2)

Refactor tools that interact with remote repositories:

| Tool | pygit2 API |
|------|-----------|
| `git_remote_add` | `repo.create_remote(name, url)` |
| `git_push` | `repo.push(remote, branches, credentials=callback)` |
| `git_remote_get` | Iterate `repo.remotes` |
| `git_set_upstream` | `repo.branches.local[branch].set_upstream(...)` |
| `git_pull` | `repo.fetch()` + `repo.merge()` |
| `git_fetch` | `repo.fetch(remote, credentials=callback)` |

### Phase 4: Branch Management (Tier 3)

Refactor branch-related tools:

| Tool | pygit2 API |
|------|-----------|
| `git_branch_list` | `list(repo.branches.local)` / `repo.branches.remote` |
| `git_branch_create` | `repo.create_branch(name, commit)` |
| `git_branch_checkout` | `repo.checkout('refs/heads/branch')` |
| `git_branch_delete` | `repo.branches.local.delete(name)` |
| `git_branch_rename` | `repo.branches.local.rename(old, new)` |

### Phase 5: Diff & Sync Operations (Tier 4)

Refactor diff, merge, and rebase tools:

| Tool | pygit2 API |
|------|-----------|
| `git_diff` | `repo.index.diff(head)` or `repo.diff(old, new)` |
| `git_diff_staged` | `repo.index.diff('HEAD')` |
| `git_merge` | `repo.merge_analysis()` + `repo.merge()` |
| `git_rebase` | `repo.rebase()` (pygit2 >= 1.7) or fallback |
| `git_log_compare` | `repo.graph_ahead_behind()` + commit walk |

### Phase 6: Testing & Validation

1. Run all existing tests against the refactored implementation
2. Verify return formats match exactly
3. Test error handling paths
4. Test authentication with `TORVALDS_GITHUB_TOKEN`

---

## Technical Details

### Credential Callback Pattern

```python
import os
import pygit2

def _get_credentials(url, username_from_url, allowed_types):
    """Credential callback for pygit2 remote operations."""
    token = os.environ.get("TORVALDS_GITHUB_TOKEN")
    if not token:
        return None
    if pygit2.CREDTYPE_USER_PASS in allowed_types:
        return pygit2.CredCredential("oauth2", token)
    return None
```

### Repository Opening Helper

```python
def _open_repo(path: str) -> pygit2.Repository:
    """Open a repository at the given path."""
    try:
        return pygit2.Repository(path)
    except pygit2.GitError as e:
        raise ValueError(f"Not a valid git repository: {path}") from e
```

### Status Conversion Helper

pygit2 returns status as a dict of `{path: status_flags}`. We need to convert these to the porcelain-equivalent format:

```python
STATUS_MAP = {
    pygit2.GIT_STATUS_CURRENT: "",
    pygit2.GIT_STATUS_INDEX_NEW: "A",
    pygit2.GIT_STATUS_INDEX_MODIFIED: "M",
    pygit2.GIT_STATUS_INDEX_DELETED: "D",
    pygit2.GIT_STATUS_INDEX_RENAMED: "R",
    pygit2.GIT_STATUS_INDEX_COPIED: "C",
    pygit2.GIT_STATUS_WT_NEW: "?",
    pygit2.GIT_STATUS_WT_MODIFIED: "M",
    pygit2.GIT_STATUS_WT_DELETED: "D",
    pygit2.GIT_STATUS_WT_RENAMED: "R",
    pygit2.GIT_STATUS_WT_COPIED: "C",
}
```

---

## Files to Modify

| File | Change | Scope |
|------|--------|-------|
| `agent_git_toolkit.py` | Replace all subprocess calls with pygit2 | Major refactor (~900 lines) |
| `requirements.txt` | Add `pygit2` | 1 line |

---

## Benefits

- **Performance** — In-process Git operations are significantly faster than subprocess calls
- **Reliability** — No fragile string parsing of CLI output
- **Maintainability** — Clean Python API instead of shell command strings
- **Security** — No subprocess spawning, reduced injection surface
- **Cross-platform** — pygit2 bundles libgit2, works without Git CLI installed
- **Error handling** — Structured exceptions with meaningful error messages

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| pygit2 API differences cause return format changes | High | Extensive testing against current behavior; maintain identical return structures |
| `git_rebase` not fully supported by pygit2 | High | Use subprocess fallback for rebase only; wrap in pygit2-style interface |
| Authentication breaks for existing SSH setups | Medium | Graceful fallback; only use token for HTTPS URLs |
| Missing pygit2 on deployment systems | Medium | Add to requirements.txt; CI check |
| pygit2 version incompatibility | Low | Pin minimum version in requirements.txt |

---

## Acceptance Criteria

- [ ] All Git tools operate using pygit2 internally
- [ ] No subprocess calls to `git` remain in `agent_git_toolkit.py`
- [ ] The FunctionalAgent continues to work without any changes
- [ ] Tool signatures, names, and return formats remain unchanged
- [ ] No new functionality is added
- [ ] The agent cannot detect any behavioral difference except improved reliability
- [ ] The environment variable `TORVALDS_GITHUB_TOKEN` is used internally for authentication where applicable
- [ ] All existing tests pass
- [ ] Error messages and error behavior remain consistent with the current implementation

---

## Timeline

| Phase | Duration |
|-------|----------|
| Infrastructure & Dependencies | 1 day |
| Basic Operations (Tier 1) | 2 days |
| Remote Operations (Tier 2) | 2 days |
| Branch Management (Tier 3) | 1 day |
| Diff & Sync Operations (Tier 4) | 2 days |
| Testing & Validation | 2 days |
| **Total** | **~10 days** |

---

## Next Steps

1. Review and approve this proposal
2. Begin implementation in `feature/pygit2-refactor` branch under the self-development directory
3. Implement in phases (Tier 1 → Tier 4) with testing at each phase
4. Create pull request for review after all phases complete

---

*Proposal complete. Ready for implementation.*
