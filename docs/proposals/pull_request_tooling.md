# Pull Request Tooling Investigation

## Date
2025-01-25

## Objective
Investigate what additional Git/GitHub tools are needed to enable the Torvalds AI agent to create and manage Pull Requests against the GitHub repository (`git@github.com:KostiantynBushko/agent-torvalds.git`).

---

## Current State Analysis

### Existing Git Toolkit (`agent_git_toolkit.py`)

The current implementation provides **14 tools** for Git repository management:

| Tool | Function | Purpose |
|------|----------|---------|
| `git_get_latest_commit` | Get latest commit hash | Track current revision |
| `git_init_repo` | Initialize new repo | Create fresh repos |
| `git_add_files` | Add files to staging | Prepare commits |
| `git_commit` | Create a commit | Save staged changes |
| `git_get_status` | Get repo status | Inspect changes |
| `git_generate_changelog` | Generate changelog | Release notes |
| `git_get_recent_changes` | Get recent commits | Inspect history |
| `git_update_changelog` | Update changelog | Manual changelog mgmt |
| `git_get_email` | Get user email | Identity inspection |
| `git_init_and_commit` | Init + first commit | Quick bootstrap |
| `git_remote_add` | Add remote | Configure push/pull URLs |
| `git_push` | Push to remote | Upload commits |
| `git_remote_get` | List remotes | Inspect remote URLs |
| `git_set_upstream` | Set upstream tracking | Link local to remote |

### Current Architecture
- **Toolkit Module**: `agent_git_toolkit.py`
- **Agent Framework**: LlamaIndex FunctionAgent with on-demand tool retrieval
- **Remote**: `origin` → `git@github.com:KostiantynBushko/agent-torvalds.git`
- **Branch Model**: Standard Git workflow (main branch detected)

---

## Missing Tools for PR Workflow

### Tier 1: Essential Branch Management

| Tool | Function | Description |
|------|----------|-------------|
| `git_branch_list` | List all branches | Show local and remote branches |
| `git_branch_create` | Create a new branch | Create feature/fix branches |
| `git_branch_checkout` | Switch to a branch | Change working branch |
| `git_branch_delete` | Delete a branch | Clean up merged branches |
| `git_branch_rename` | Rename a branch | Fix branch naming |

### Tier 2: Branch Comparison & Sync

| Tool | Function | Description |
|------|----------|-------------|
| `git_diff` | Show file differences | Compare working tree, branches, commits |
| `git_diff_staged` | Show staged differences | Review before commit |
| `git_pull` | Pull from remote | Fetch and merge changes |
| `git_fetch` | Fetch from remote | Update remote refs without merging |
| `git_merge` | Merge branches | Integrate feature branches |
| `git_rebase` | Rebase commits | Clean up commit history |
| `git_log_compare` | Compare branch logs | See what's diverged |

### Tier 3: GitHub PR Operations (API/CLI)

| Tool | Function | Description |
|------|----------|-------------|
| `git_create_pull_request` | Create PR via API | Submit PR to GitHub |
| `git_list_pull_requests` | List open PRs | Inspect existing PRs |
| `git_get_pull_request` | Get PR details | View specific PR info |
| `git_update_pull_request` | Update PR title/desc | Modify PR metadata |
| `git_close_pull_request` | Close a PR | Close without merging |
| `git_merge_pull_request` | Merge a PR | Complete the PR workflow |
| `git_comment_on_pull_request` | Add PR comment | Review feedback |
| `git_review_file_changes` | Review diff in PR | Line-by-line comments |

### Tier 4: Authentication & Configuration

| Tool | Function | Description |
|------|----------|-------------|
| `git_check_auth` | Verify GitHub auth | Check SSH/GitHub token access |
| `git_get_user_info` | Get GitHub user info | Verify identity |
| `git_configure_credentials` | Set up credentials | Configure auth helpers |

---

## Implementation Approaches

### Option A: GitHub CLI (`gh`)
**Pros:**
- Official GitHub tooling
- Handles authentication automatically
- Rich PR lifecycle support
- Already available on many systems

**Cons:**
- Requires `gh` binary installation
- Adds external dependency

**Example Commands:**
```bash
# Create PR
gh pr create --title "Feature: Add X" --body "Description..." --base main --head feature-branch

# List PRs
gh pr list --state open

# Comment on PR
gh pr comment 123 --body "LGTM"
```

### Option B: GitHub REST API (Python requests)
**Pros:**
- No external binary required
- Full control over API calls
- Better error handling in Python

**Cons:**
- Requires authentication token management
- More code to maintain
- Need to handle pagination, rate limits

**Example API Calls:**
```python
# Create PR via API
POST /repos/{owner}/{repo}/pulls
{
  "title": "Feature: Add X",
  "body": "Description...",
  "head": "feature-branch",
  "base": "main"
}
```

### Option C: Hybrid (Git + GitHub CLI fallback)
Use native Git for branch operations and `gh` CLI for PR-specific operations.

---

## Recommended Implementation Plan

### Phase 1: Branch Management Tools (Immediate)
Add to `agent_git_toolkit.py`:
```python
def git_branch_list(path: str, remote: bool = False) -> list
def git_branch_create(path: str, branch_name: str, start_point: str = "HEAD") -> bool
def git_branch_checkout(path: str, branch_name: str) -> bool
def git_branch_delete(path: str, branch_name: str, force: bool = False) -> bool
```

### Phase 2: Diff & Sync Tools (Short-term)
```python
def git_diff(path: str, target: str = None) -> str
def git_pull(path: str, remote: str = "origin", branch: str = None) -> bool
def git_fetch(path: str, remote: str = "origin") -> bool
def git_merge(path: str, branch: str, strategy: str = None) -> bool
```

### Phase 3: GitHub PR Integration (Medium-term)
Create new module `agent_github_toolkit.py`:
```python
def github_create_pull_request(
    owner: str, repo: str, 
    title: str, body: str,
    head: str, base: str
) -> dict
def github_list_pull_requests(owner: str, repo: str, state: str = "open") -> list
def github_comment_on_pr(owner: str, repo: str, pr_number: int, comment: str) -> bool
```

**Authentication Strategy:**
- Use GitHub CLI token if available
- Fall back to environment variable `GITHUB_TOKEN`
- Support SSH key authentication for Git operations

---

## Dependencies to Add

### For GitHub CLI approach:
```txt
# requirements.txt (no change - uses subprocess)
```

### For REST API approach:
```txt
# requirements.txt additions
requests>=2.31.0
PyGithub>=2.1.0  # Optional: higher-level GitHub API wrapper
```

---

## Security Considerations

1. **Credential Storage**: Never store tokens in source code; use environment variables or Git credential helpers
2. **PR Creation Confirmation**: Always require explicit user confirmation before creating/merging PRs
3. **Branch Protection**: Respect branch protection rules on target repository
4. **Audit Trail**: Log all PR operations for debugging

---

## Example PR Workflow (Post-Implementation)

```
User: "Create a PR for the new cache statistics feature"

Agent workflow:
1. git_get_status() → Check current changes
2. git_branch_create("feature/cache-stats") → Create feature branch
3. git_add_files(["agent_stats_handler.py", ...]) → Stage changes
4. git_commit("feat: Add request statistics tracking") → Commit
5. git_push("origin", "feature/cache-stats") → Push to remote
6. github_create_pull_request(
       title="feat: Add request statistics tracking",
       body="Automated PR description...",
       head="feature/cache-stats",
       base="main"
     ) → Create PR
7. Return PR URL and number to user
```

---

## Files to Modify

| File | Action |
|------|--------|
| `self-development/agent_git_toolkit.py` | Add branch/diff/sync functions |
| `self-development/agent-torvalds.py` | Import new GitHub toolkit |
| `self-development/agent_github_toolkit.py` | **New file** - GitHub API/CLI integration |
| `self-development/requirements.txt` | Add `requests` or `PyGithub` if using API |
| `self-development/docs/proposals/pull_request_tooling.md` | This document |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Broken auth flow | Medium | High | Test with SSH keys first |
| Accidental PR creation | Low | High | Require explicit confirmation |
| API rate limiting | Medium | Medium | Implement retry/backoff |
| Branch conflicts | Medium | Medium | Pre-flight diff checks |

---

## Next Steps

1. [ ] Implement Tier 1 branch management tools
2. [ ] Add unit tests for new Git functions
3. [ ] Test branch workflow in self-development repo
4. [ ] Implement Tier 2 diff/sync tools
5. [ ] Decide on GitHub CLI vs API approach
6. [ ] Implement Tier 3 PR operations
7. [ ] End-to-end PR workflow test
8. [ ] Update agent documentation

---

*Generated by Torvalds AI Agent - Self-Development Investigation*
