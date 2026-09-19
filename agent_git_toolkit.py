"""
Git Toolkit - Git repository management and version control operations.

This module provides comprehensive Git functionality for repository initialization,
commit management, changelog generation, remote operations, status inspection,
branch management, and diff/sync operations.

Category: Version Control
Retriever Keywords: git, repository, commit, branch, remote, changelog, version control, diff, merge, sync
"""
import os
import subprocess
import logging
from datetime import date
from typing import Optional
from llama_index.core.tools import FunctionTool

logger = logging.getLogger(__name__)


def git_get_latest_commit(path: str) -> str:
    """
    Get the latest commit hash in a Git repository.
    
    Use this tool to retrieve the most recent commit SHA for tracking or logging.
    
    Args:
        path (str): Path to the Git repository
        
    Returns:
        str: The full commit hash of the latest commit, or an error message if failed
        
    Example:
        >>> git_get_latest_commit("/home/user/my-repo")
        'a1b2c3d4e5f6789012345678901234567890abcd'
        
    Keywords: commit, hash, latest, head, revision
    """
    logger.info(f"git_get_latest_commit called with path: {path}")
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"Error: {e.stderr.strip() if e.stderr else str(e)}"


def git_init_repo(path: str) -> bool:
    """
    Initialize a new Git repository at the given path.
    
    Use this tool to create a fresh Git repository in an existing directory.
    Parent directories are NOT created automatically; the path must exist.
    
    Args:
        path (str): The directory path where the Git repository should be initialized
        
    Returns:
        bool: True if initialization was successful, False otherwise
        
    Example:
        >>> git_init_repo("/home/user/new-project")
        True
        
    Keywords: init, initialize, repository, new repo, setup
    """
    logger.info(f"git_init_repo called with path: {path}")
    try:
        if not os.path.isdir(path):
            return False
        subprocess.run(
            ["git", "init"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def git_add_files(path: str, files: list) -> bool:
    """
    Add files to the staging area for commit.
    
    Use this tool to stage changes before committing. Pass a list of file paths
    relative to the repository root, or use ['.'] to stage everything.
    
    Args:
        path (str): The directory path of the Git repository
        files (list): List of file paths to add (e.g., ['file.py', 'README.md'])
        
    Returns:
        bool: True if successful, False otherwise
        
    Example:
        >>> git_add_files("/home/user/repo", ["src/main.py", "README.md"])
        True
        
    Keywords: add, stage, staging, index, prepare commit
    """
    logger.info(f"git_add_files called with path: {path}, files: {files}")
    try:
        subprocess.run(
            ["git", "add"] + files,
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def _has_staged_changes(path: str) -> bool:
    """
    Check if there are staged changes ready to commit.
    
    Handles both the case where HEAD exists (normal commits) and where it doesn't
    (first commit in a new repository).
    
    Args:
        path (str): The directory path of the Git repository
        
    Returns:
        bool: True if there are staged changes, False otherwise
    """
    logger.info(f"_has_staged_changes called with path: {path}")
    # Check if HEAD exists
    head_check = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        capture_output=True,
        text=True,
    )
    
    if head_check.returncode != 0:
        # No HEAD yet (first commit) — check if anything is staged
        result = subprocess.run(
            ["git", "diff-index", "--cached", "--quiet", "HEAD"],
            cwd=path,
            capture_output=True,
            text=True,
        )
        return result.returncode != 0
    
    # HEAD exists — normal staged changes check
    result = subprocess.run(
        ["git", "diff-index", "--cached", "--quiet", "HEAD"],
        cwd=path,
        capture_output=True,
        text=True,
    )
    return result.returncode != 0


def git_commit(path: str, message: str) -> bool:
    """
    Create a commit with the given message.
    
    Use this tool to commit staged changes to the repository.
    Returns False if there are no staged changes to commit.
    
    Args:
        path (str): The directory path of the Git repository
        message (str): Commit message describing the changes
        
    Returns:
        bool: True if commit was created successfully, False otherwise
        
    Example:
        >>> git_commit("/home/user/repo", "Fix bug in authentication module")
        True
        
    Keywords: commit, save, snapshot, message, changes
    """
    logger.info(f"git_commit called with path: {path}, message: {message}")
    try:
        # Check if there are staged changes
        if not _has_staged_changes(path):
            return False
        
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def git_get_status(path: str) -> dict:
    """
    Get current repository status showing staged, unstaged, and untracked files.
    
    Use this tool to inspect the working tree status before making changes or commits.
    
    Args:
        path (str): The directory path of the Git repository
        
    Returns:
        dict: Dictionary containing status information with keys:
            - 'status': 'success' or 'error'
            - 'output': Porcelain format status string (on success)
            - 'message': Error message (on failure)
            
    Example:
        >>> git_get_status("/home/user/repo")
        {'status': 'success', 'output': 'M src/main.py\n?? new_file.py'}
        
    Keywords: status, changes, modified, untracked, dirty, clean
    """
    logger.info(f"git_get_status called with path: {path}")
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        return {
            "status": "success",
            "output": result.stdout.strip(),
        }
    except subprocess.CalledProcessError as e:
        return {
            "status": "error",
            "message": f"Error getting status: {e.stderr.strip() if e.stderr else str(e)}",
        }


def git_generate_changelog(path: str, output_file: str = "CHANGELOG.md") -> bool:
    """
    Generate a changelog file from Git commit history.
    
    Use this tool to automatically create a formatted changelog from commit messages,
    grouped by date. This is useful for release notes and project documentation.
    
    Args:
        path (str): The directory path of the Git repository
        output_file (str): Name of the changelog file to create (default: 'CHANGELOG.md')
        
    Returns:
        bool: True if changelog was generated successfully, False otherwise
        
    Example:
        >>> git_generate_changelog("/home/user/repo")
        True
        
    Keywords: changelog, history, release notes, commits, documentation, log
    """
    logger.info(f"git_generate_changelog called with path: {path}, output_file: {output_file}")
    try:
        result = subprocess.run(
            ["git", "log", "--pretty=format:%h|%ad|%s", "--date=short", "--no-merges"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        
        if not result.stdout.strip():
            # No commits yet - create empty changelog
            changelog_path = os.path.join(path, output_file)
            with open(changelog_path, "w") as f:
                f.write("# Changelog\n\nAll notable changes to this project will be documented in this file.\n")
            return True
        
        commits = result.stdout.strip().split("\n")
        changelog_content = "# Changelog\n\nAll notable changes to this project will be documented in this file.\n\n"
        
        current_date = ""
        for commit in commits:
            if not commit:
                continue
            try:
                parts = commit.split("|", 2)
                if len(parts) != 3:
                    continue
                commit_hash, commit_date, message = parts
                
                # Add date header when date changes
                if commit_date != current_date:
                    changelog_content += f"\n## {commit_date}\n\n"
                    current_date = commit_date
                
                changelog_content += f"- {message} ({commit_hash})\n"
            except (ValueError, IndexError):
                continue
        
        changelog_path = os.path.join(path, output_file)
        with open(changelog_path, "w") as f:
            f.write(changelog_content)
        
        return True
    except (subprocess.CalledProcessError, OSError):
        return False


def git_get_recent_changes(path: str, num_commits: int = 10) -> list:
    """
    Get recent commits from the Git repository.
    
    Use this tool to inspect recent commit history, including author, date, and message.
    
    Args:
        path (str): The directory path of the Git repository
        num_commits (int): Number of recent commits to retrieve (default: 10)
        
    Returns:
        list: List of dictionaries containing commit information with keys:
            - 'hash': Short commit hash
            - 'date': Commit date (YYYY-MM-DD)
            - 'message': Commit message
            - 'author': Author name
            
    Example:
        >>> git_get_recent_changes("/home/user/repo", 5)
        [{'hash': 'a1b2c3d', 'date': '2024-01-15', 'message': 'Fix login bug', 'author': 'Alice'}, ...]
        
    Keywords: recent, history, log, commits, author, changes
    """
    logger.info(f"git_get_recent_changes called with path: {path}, num_commits: {num_commits}")
    try:
        result = subprocess.run(
            ["git", "log", f"-{num_commits}", "--pretty=format:%h|%ad|%s|%an", "--date=short", "--no-merges"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        
        if not result.stdout.strip():
            return []
        
        commits = result.stdout.strip().split("\n")
        recent_changes = []
        
        for commit in commits:
            if not commit:
                continue
            try:
                parts = commit.split("|", 3)
                if len(parts) != 4:
                    continue
                commit_hash, commit_date, message, author = parts
                recent_changes.append({
                    "hash": commit_hash,
                    "date": commit_date,
                    "message": message,
                    "author": author,
                })
            except (ValueError, IndexError):
                continue
        
        return recent_changes
    except subprocess.CalledProcessError:
        return []


def git_update_changelog(path: str, change_type: str, description: str) -> bool:
    """
    Update the changelog with a new entry.
    
    Use this tool to manually add a changelog entry with a specific change type
    (feature, fix, docs, etc.) and description.
    
    Args:
        path (str): The directory path of the Git repository
        change_type (str): Type of change (feature, fix, docs, refactor, chore, etc.)
        description (str): Description of the change
        
    Returns:
        bool: True if changelog was updated successfully, False otherwise
        
    Example:
        >>> git_update_changelog("/home/user/repo", "fix", "Resolve null pointer in parser")
        True
        
    Keywords: update, changelog, entry, change type, feature, fix, docs
    """
    logger.info(f"git_update_changelog called with path: {path}, change_type: {change_type}, description: {description}")
    try:
        today = date.today().strftime("%Y-%m-%d")
        changelog_path = os.path.join(path, "CHANGELOG.md")
        
        # Read existing changelog or create new one
        changelog_content = ""
        if os.path.exists(changelog_path):
            with open(changelog_path, "r") as f:
                changelog_content = f.read()
        
        # Create new entry
        new_entry = f"- [{change_type}] {description} ({today})\n"
        
        # Initialize if empty
        if not changelog_content.strip():
            changelog_content = (
                "# Changelog\n\n"
                "All notable changes to this project will be documented in this file.\n\n"
            )
        
        # Try to insert under today's date header, or create new date section
        date_header = f"## {today}\n"
        if date_header in changelog_content:
            # Insert after existing date header
            idx = changelog_content.index(date_header) + len(date_header)
            # Skip any newlines after the header
            while idx < len(changelog_content) and changelog_content[idx] in ("\n", " "):
                idx += 1
            updated_content = changelog_content[:idx] + new_entry + changelog_content[idx:]
        else:
            # Insert after the intro paragraph
            insert_marker = "documented in this file.\n"
            if insert_marker in changelog_content:
                idx = changelog_content.index(insert_marker) + len(insert_marker)
                updated_content = (
                    changelog_content[:idx]
                    + f"\n## {today}\n\n{new_entry}\n"
                    + changelog_content[idx:]
                )
            else:
                # Append to end
                updated_content = changelog_content + f"\n## {today}\n\n{new_entry}\n"
        
        with open(changelog_path, "w") as f:
            f.write(updated_content)
        
        return True
    except Exception:
        return False


def git_get_email(path: str) -> str:
    """
    Get the user's email from Git configuration.
    
    Use this tool to retrieve the configured user email for the repository.
    Returns an empty string if not configured.
    
    Args:
        path (str): The directory path of the Git repository
        
    Returns:
        str: User's email address or empty string if not found
        
    Example:
        >>> git_get_email("/home/user/repo")
        'developer@example.com'
        
    Keywords: email, config, user, identity, author
    """
    logger.info(f"git_get_email called with path: {path}")
    try:
        result = subprocess.run(
            ["git", "config", "--get", "user.email"],
            cwd=path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return ""
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return ""


def git_init_and_commit(path: str, message: str) -> bool:
    """
    Initialize a Git repository and make the first commit.
    
    Use this tool to quickly set up a new repository with an initial commit.
    If the repo already exists, it will just stage and commit all files.
    Auto-configures user identity if not already set.
    
    Args:
        path (str): The directory path where the Git repository should be initialized
        message (str): Commit message for the initial commit
        
    Returns:
        bool: True if successful, False otherwise
        
    Example:
        >>> git_init_and_commit("/home/user/new-project", "Initial commit")
        True
        
    Keywords: init, first commit, setup, bootstrap, initialize
    """
    logger.info(f"git_init_and_commit called with path: {path}, message: {message}")
    try:
        # Initialize if not already a git repo
        if not os.path.isdir(os.path.join(path, ".git")):
            subprocess.run(["git", "init"], cwd=path, capture_output=True, text=True, check=True)
        
        # Configure user identity if needed
        email = git_get_email(path)
        if not email:
            subprocess.run(["git", "config", "user.email", "agent@torvalds.local"], cwd=path, capture_output=True, text=True)
            subprocess.run(["git", "config", "user.name", "Torvalds Agent"], cwd=path, capture_output=True, text=True)
        
        # Stage all files
        subprocess.run(["git", "add", "."], cwd=path, capture_output=True, text=True)
        
        # Commit (allow empty commits for fresh repos with no files)
        subprocess.run(["git", "commit", "--allow-empty", "-m", message], cwd=path, capture_output=True, text=True, check=True)
        
        return True
    except subprocess.CalledProcessError:
        return False


def git_remote_add(path: str, name: str, url: str) -> bool:
    """
    Add a remote repository.
    
    Use this tool to configure a remote URL for pushing/pulling changes.
    
    Args:
        path (str): The directory path of the Git repository
        name (str): Name of the remote (e.g., 'origin', 'upstream')
        url (str): URL of the remote repository
        
    Returns:
        bool: True if successful, False otherwise
        
    Example:
        >>> git_remote_add("/home/user/repo", "origin", "https://github.com/user/repo.git")
        True
        
    Keywords: remote, add, url, origin, upstream, push, pull
    """
    logger.info(f"git_remote_add called with path: {path}, name: {name}, url: {url}")
    try:
        subprocess.run(
            ["git", "remote", "add", name, url],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def git_push(
    path: str,
    remote: str = "origin",
    branch: str = "main",
    set_upstream: bool = False,
) -> bool:
    """
    Push changes to a remote repository.
    
    Use this tool to upload local commits to a remote repository.
    Requires the remote to be configured and proper authentication.
    
    Args:
        path (str): The directory path of the Git repository
        remote (str): Name of the remote repository (default: 'origin')
        branch (str): Branch name to push (default: 'main')
        set_upstream (bool): Whether to set upstream tracking (default: False)
        
    Returns:
        bool: True if successful, False otherwise
        
    Example:
        >>> git_push("/home/user/repo", "origin", "main")
        True
        
    Keywords: push, upload, remote, branch, upstream, sync
    """
    logger.info(f"git_push called with path: {path}, remote: {remote}, branch: {branch}, set_upstream: {set_upstream}")
    try:
        if set_upstream:
            subprocess.run(
                ["git", "push", "--set-upstream", remote, branch],
                cwd=path,
                capture_output=True,
                text=True,
                check=True,
            )
        else:
            subprocess.run(
                ["git", "push", remote, branch],
                cwd=path,
                capture_output=True,
                text=True,
                check=True,
            )
        return True
    except subprocess.CalledProcessError:
        return False


def git_remote_get(path: str) -> list[dict]:
    """
    Get list of configured remotes.
    
    Use this tool to inspect which remotes are configured for the repository.
    
    Args:
        path (str): The directory path of the Git repository
        
    Returns:
        list[dict]: List of dictionaries containing remote information with keys:
            - 'name': Remote name
            - 'url': Remote URL
            
    Example:
        >>> git_remote_get("/home/user/repo")
        [{'name': 'origin', 'url': 'https://github.com/user/repo.git'}]
        
    Keywords: remote, list, configured, url, fetch, push
    """
    logger.info(f"git_remote_get called with path: {path}")
    try:
        result = subprocess.run(
            ["git", "remote", "-v"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        
        if not result.stdout.strip():
            return []
        
        remotes = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                remotes.append({"name": parts[0], "url": parts[1]})
        
        return remotes
    except subprocess.CalledProcessError:
        return []


def git_set_upstream(path: str, remote: str, branch: str) -> bool:
    """
    Set upstream tracking for a branch.
    
    Use this tool to link a local branch to a remote branch for simpler push/pull operations.
    
    Args:
        path (str): The directory path of the Git repository
        remote (str): Name of the remote repository
        branch (str): Branch name to set upstream for
        
    Returns:
        bool: True if successful, False otherwise
        
    Example:
        >>> git_set_upstream("/home/user/repo", "origin", "main")
        True
        
    Keywords: upstream, tracking, branch, remote, link, configure
    """
    logger.info(f"git_set_upstream called with path: {path}, remote: {remote}, branch: {branch}")
    try:
        subprocess.run(
            ["git", "branch", "--set-upstream-to", f"{remote}/{branch}"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


# =============================================================================
# Phase 1: Branch Management Tools (Tier 1)
# =============================================================================

def git_branch_list(path: str, remote: bool = False) -> list[str]:
    """
    List all branches in a Git repository.
    
    Use this tool to inspect available local or remote branches before
    switching, creating, or deleting branches.
    
    Args:
        path (str): The directory path of the Git repository
        remote (bool): If True, list remote-tracking branches instead of local ones.
                      Default: False (list local branches).
        
    Returns:
        list[str]: List of branch names. Returns empty list on error or no branches.
        
    Example:
        >>> git_branch_list("/home/user/repo")
        ['main', 'feature/auth', 'develop']
        >>> git_branch_list("/home/user/repo", remote=True)
        ['origin/main', 'origin/develop']
        
    Keywords: branch, list, branches, remote branches, local branches
    """
    logger.info(f"git_branch_list called with path: {path}, remote: {remote}")
    try:
        if remote:
            result = subprocess.run(
                ["git", "branch", "-r"],
                cwd=path,
                capture_output=True,
                text=True,
                check=True,
            )
        else:
            result = subprocess.run(
                ["git", "branch"],
                cwd=path,
                capture_output=True,
                text=True,
                check=True,
            )
        
        if not result.stdout.strip():
            return []
        
        branches = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            # Strip leading whitespace and asterisk (current branch marker)
            branch_name = line.strip().lstrip("* ").strip()
            if branch_name:
                branches.append(branch_name)
        return branches
    except subprocess.CalledProcessError:
        return []


def git_branch_create(path: str, branch_name: str, start_point: str = "HEAD") -> bool:
    """
    Create a new branch in the Git repository.
    
    Use this tool to create feature, fix, or experiment branches before
    making isolated changes.
    
    Args:
        path (str): The directory path of the Git repository
        branch_name (str): Name for the new branch (e.g., 'feature/new-login')
        start_point (str): The commit/branch to start from (default: 'HEAD')
        
    Returns:
        bool: True if branch was created successfully, False otherwise
        
    Example:
        >>> git_branch_create("/home/user/repo", "feature/auth")
        True
        >>> git_branch_create("/home/user/repo", "bugfix/typo", "main")
        True
        
    Keywords: branch, create, new branch, feature branch, start point
    """
    logger.info(f"git_branch_create called with path: {path}, branch_name: {branch_name}, start_point: {start_point}")
    try:
        subprocess.run(
            ["git", "branch", branch_name, start_point],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def git_branch_checkout(path: str, branch_name: str) -> bool:
    """
    Switch to an existing branch.
    
    Use this tool to change the working directory to a different branch.
    Be cautious: uncommitted changes may cause conflicts.
    
    Args:
        path (str): The directory path of the Git repository
        branch_name (str): Name of the branch to switch to
        
    Returns:
        bool: True if checkout was successful, False otherwise
        
    Example:
        >>> git_branch_checkout("/home/user/repo", "feature/auth")
        True
        
    Keywords: branch, checkout, switch, change branch, working branch
    """
    logger.info(f"git_branch_checkout called with path: {path}, branch_name: {branch_name}")
    try:
        subprocess.run(
            ["git", "checkout", branch_name],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def git_branch_delete(path: str, branch_name: str, force: bool = False) -> bool:
    """
    Delete a branch from the repository.
    
    Use this tool to clean up merged or abandoned branches.
    By default, uses safe delete (prevents deleting unmerged branches).
    Set force=True to delete regardless of merge status.
    
    Args:
        path (str): The directory path of the Git repository
        branch_name (str): Name of the branch to delete
        force (bool): If True, force-delete even if unmerged. Default: False.
        
    Returns:
        bool: True if branch was deleted successfully, False otherwise
        
    Example:
        >>> git_branch_delete("/home/user/repo", "feature/old-feature")
        True
        >>> git_branch_delete("/home/user/repo", "feature/unmerged", force=True)
        True
        
    Keywords: branch, delete, remove, cleanup, force delete
    """
    logger.info(f"git_branch_delete called with path: {path}, branch_name: {branch_name}, force: {force}")
    try:
        flag = "-D" if force else "-d"
        subprocess.run(
            ["git", "branch", flag, branch_name],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def git_branch_rename(path: str, new_name: str) -> bool:
    """
    Rename the current branch.
    
    Use this tool to fix branch naming mistakes or standardize branch naming.
    Only renames the currently checked-out branch.
    
    Args:
        path (str): The directory path of the Git repository
        new_name (str): The new name for the current branch
        
    Returns:
        bool: True if rename was successful, False otherwise
        
    Example:
        >>> git_branch_rename("/home/user/repo", "feature/authentication")
        True
        
    Keywords: branch, rename, current branch, rename branch
    """
    logger.info(f"git_branch_rename called with path: {path}, new_name: {new_name}")
    try:
        subprocess.run(
            ["git", "branch", "-m", new_name],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


# =============================================================================
# Phase 2: Diff & Sync Tools (Tier 2)
# =============================================================================

def git_diff(path: str, target: str = None) -> str:
    """
    Show differences between the working tree, index, or commits.
    
    Use this tool to inspect what has changed in files compared to a target
    (commit, branch, or the index). Without a target, shows unstaged changes.
    
    Args:
        path (str): The directory path of the Git repository
        target (str, optional): Target commit/branch to compare against.
                               If None, shows unstaged working tree changes.
                               Examples: 'HEAD', 'main', 'feature/branch', commit hash
        
    Returns:
        str: Unified diff output showing additions (+) and deletions (-),
             or an error message if the operation failed.
        
    Example:
        >>> git_diff("/home/user/repo")
        'diff --git a/file.py b/file.py\\n--- a/file.py\\n+++ b/file.py\\n@@ ...'
        >>> git_diff("/home/user/repo", "HEAD~1")
        'diff --git a/file.py b/file.py\\n...'
        
    Keywords: diff, difference, changes, compare, modified, additions, deletions
    """
    logger.info(f"git_diff called with path: {path}, target: {target}")
    try:
        if target:
            result = subprocess.run(
                ["git", "diff", target],
                cwd=path,
                capture_output=True,
                text=True,
                check=True,
            )
        else:
            result = subprocess.run(
                ["git", "diff"],
                cwd=path,
                capture_output=True,
                text=True,
                check=True,
            )
        return result.stdout
    except subprocess.CalledProcessError as e:
        return f"Error: {e.stderr.strip() if e.stderr else str(e)}"


def git_diff_staged(path: str) -> str:
    """
    Show staged differences (changes in the index compared to HEAD).
    
    Use this tool to review what will be committed before creating a commit.
    This shows the difference between the staging area and the last commit.
    
    Args:
        path (str): The directory path of the Git repository
        
    Returns:
        str: Unified diff output of staged changes,
             or an error message if the operation failed.
        
    Example:
        >>> git_diff_staged("/home/user/repo")
        'diff --git a/file.py b/file.py\\n--- a/file.py\\n+++ b/file.py\\n@@ ...'
        
    Keywords: diff, staged, index, cached, review, before commit
    """
    logger.info(f"git_diff_staged called with path: {path}")
    try:
        result = subprocess.run(
            ["git", "diff", "--staged"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        return f"Error: {e.stderr.strip() if e.stderr else str(e)}"


def git_pull(path: str, remote: str = "origin", branch: str = None) -> dict:
    """
    Pull changes from a remote repository and merge into the current branch.
    
    Use this tool to fetch and integrate changes from a remote repository.
    Equivalent to git fetch followed by git merge.
    
    Args:
        path (str): The directory path of the Git repository
        remote (str): Name of the remote repository (default: 'origin')
        branch (str, optional): Branch name to pull. If None, pulls the
                               upstream branch for the current branch.
        
    Returns:
        dict: Dictionary containing:
            - 'success': bool indicating if the pull succeeded
            - 'output': stdout from the pull command
            - 'error': error message if failed (on failure)
            
    Example:
        >>> git_pull("/home/user/repo")
        {'success': True, 'output': 'Already up to date.'}
        >>> git_pull("/home/user/repo", "origin", "main")
        {'success': True, 'output': 'Updating a1b2c3d..e4f5g6h\\n...'}
        
    Keywords: pull, fetch, merge, remote, update, synchronize, sync
    """
    logger.info(f"git_pull called with path: {path}, remote: {remote}, branch: {branch}")
    try:
        if branch:
            result = subprocess.run(
                ["git", "pull", remote, branch],
                cwd=path,
                capture_output=True,
                text=True,
                check=True,
            )
        else:
            result = subprocess.run(
                ["git", "pull"],
                cwd=path,
                capture_output=True,
                text=True,
                check=True,
            )
        return {
            "success": True,
            "output": result.stdout.strip(),
        }
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "output": result.stdout.strip() if 'result' in locals() else "",
            "error": e.stderr.strip() if e.stderr else str(e),
        }


def git_fetch(path: str, remote: str = "origin") -> dict:
    """
    Fetch objects and refs from a remote repository without merging.
    
    Use this tool to update remote-tracking branches without modifying
    the working tree or current branch. Safer than pull for inspecting
    what's available before merging.
    
    Args:
        path (str): The directory path of the Git repository
        remote (str): Name of the remote repository (default: 'origin')
        
    Returns:
        dict: Dictionary containing:
            - 'success': bool indicating if the fetch succeeded
            - 'output': stdout from the fetch command
            - 'error': error message if failed (on failure)
            
    Example:
        >>> git_fetch("/home/user/repo")
        {'success': True, 'output': 'From https://github.com/user/repo\\n * branch ...'}
        
    Keywords: fetch, remote, update, download, refs, remote-tracking
    """
    logger.info(f"git_fetch called with path: {path}, remote: {remote}")
    try:
        result = subprocess.run(
            ["git", "fetch", remote],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        return {
            "success": True,
            "output": result.stdout.strip(),
        }
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "output": result.stdout.strip() if 'result' in locals() else "",
            "error": e.stderr.strip() if e.stderr else str(e),
        }


def git_merge(path: str, branch: str, strategy: str = None) -> dict:
    """
    Merge the specified branch into the current branch.
    
    Use this tool to integrate changes from a feature branch into the
    current branch. Supports custom merge strategies.
    
    Args:
        path (str): The directory path of the Git repository
        branch (str): Name of the branch to merge into the current branch
        strategy (str, optional): Merge strategy to use (e.g., 'ours', 'theirs', 'recursive').
                                 If None, uses the default merge strategy.
        
    Returns:
        dict: Dictionary containing:
            - 'success': bool indicating if the merge succeeded
            - 'output': stdout from the merge command
            - 'conflicts': bool indicating if there were merge conflicts
            - 'error': error message if failed (on failure)
            
    Example:
        >>> git_merge("/home/user/repo", "feature/new-feature")
        {'success': True, 'output': 'Merge made by the \'recursive\' strategy.', 'conflicts': False}
        >>> git_merge("/home/user/repo", "feature/conflict", strategy="theirs")
        {'success': True, 'output': '...', 'conflicts': False}
        
    Keywords: merge, integrate, combine, strategy, conflicts, feature branch
    """
    logger.info(f"git_merge called with path: {path}, branch: {branch}, strategy: {strategy}")
    try:
        cmd = ["git", "merge"]
        if strategy:
            cmd.extend(["-s", strategy])
        cmd.append(branch)
        
        result = subprocess.run(
            cmd,
            cwd=path,
            capture_output=True,
            text=True,
            check=False,  # Merge can return non-zero for conflicts
        )
        
        has_conflicts = result.returncode != 0 and "CONFLICT" in (result.stderr or "")
        
        return {
            "success": result.returncode == 0,
            "output": result.stdout.strip(),
            "conflicts": has_conflicts,
            "error": result.stderr.strip() if result.returncode != 0 else None,
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "conflicts": False,
            "error": str(e),
        }


def git_rebase(path: str, branch: str, strategy: str = None) -> dict:
    """
    Rebase the current branch onto the specified branch.
    
    Use this tool to replay commits on top of another branch, creating
    a linear history. Useful for cleaning up commit history before merging.
    
    Args:
        path (str): The directory path of the Git repository
        branch (str): Name of the branch to rebase onto
        strategy (str, optional): Rebase strategy/strategy option.
                                 If None, uses default rebase behavior.
        
    Returns:
        dict: Dictionary containing:
            - 'success': bool indicating if the rebase succeeded
            - 'output': stdout from the rebase command
            - 'conflicts': bool indicating if there were rebase conflicts
            - 'error': error message if failed (on failure)
            
    Example:
        >>> git_rebase("/home/user/repo", "main")
        {'success': True, 'output': 'Successfully rebased and updated refs/heads/feature.', 'conflicts': False}
        
    Keywords: rebase, replay, linear, history, cleanup, onto
    """
    logger.info(f"git_rebase called with path: {path}, branch: {branch}, strategy: {strategy}")
    try:
        cmd = ["git", "rebase"]
        if strategy:
            cmd.extend(["-s", strategy])
        cmd.append(branch)
        
        result = subprocess.run(
            cmd,
            cwd=path,
            capture_output=True,
            text=True,
            check=False,  # Rebase can return non-zero for conflicts
        )
        
        has_conflicts = result.returncode != 0 and "CONFLICT" in (result.stderr or "")
        
        return {
            "success": result.returncode == 0,
            "output": result.stdout.strip(),
            "conflicts": has_conflicts,
            "error": result.stderr.strip() if result.returncode != 0 else None,
        }
    except Exception as e:
        return {
            "success": False,
            "output": "",
            "conflicts": False,
            "error": str(e),
        }


def git_log_compare(path: str, branch1: str, branch2: str) -> dict:
    """
    Compare commit logs between two branches.
    
    Use this tool to see which commits are unique to each branch and
    which are shared. Useful for understanding divergence before merging.
    
    Args:
        path (str): The directory path of the Git repository
        branch1 (str): First branch name
        branch2 (str): Second branch name
        
    Returns:
        dict: Dictionary containing:
            - 'success': bool indicating if the comparison succeeded
            - 'ahead': list of commits in branch1 but not in branch2
            - 'behind': list of commits in branch2 but not in branch1
            - 'error': error message if failed (on failure)
            
    Example:
        >>> git_log_compare("/home/user/repo", "feature", "main")
        {
            'success': True,
            'ahead': [{'hash': 'a1b2c3d', 'message': 'Add feature X'}],
            'behind': [{'hash': 'e4f5g6h', 'message': 'Fix bug Y'}]
        }
        
    Keywords: compare, compare branches, divergence, ahead, behind, log, difference
    """
    logger.info(f"git_log_compare called with path: {path}, branch1: {branch1}, branch2: {branch2}")
    try:
        # Commits in branch1 but not in branch2 (branch1 is ahead)
        ahead_result = subprocess.run(
            ["git", "log", f"{branch2}..{branch1}", "--pretty=format:%h|%s", "--no-merges"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        
        # Commits in branch2 but not in branch1 (branch1 is behind)
        behind_result = subprocess.run(
            ["git", "log", f"{branch1}..{branch2}", "--pretty=format:%h|%s", "--no-merges"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        
        def parse_commits(output: str) -> list[dict]:
            commits = []
            if output.strip():
                for line in output.strip().split("\n"):
                    if not line:
                        continue
                    parts = line.split("|", 1)
                    if len(parts) == 2:
                        commits.append({"hash": parts[0], "message": parts[1]})
                    else:
                        commits.append({"hash": parts[0] if parts else "", "message": line})
            return commits
        
        return {
            "success": True,
            "ahead": parse_commits(ahead_result.stdout),
            "behind": parse_commits(behind_result.stdout),
        }
    except subprocess.CalledProcessError as e:
        return {
            "success": False,
            "ahead": [],
            "behind": [],
            "error": e.stderr.strip() if e.stderr else str(e),
        }


def get_all_tools() -> list[FunctionTool]:
    """
    Return all Git tools as FunctionTool objects for on-demand loading.
    
    Each tool includes category metadata for better retrieval.
    
    Returns:
        list[FunctionTool]: List of Git FunctionTool objects
    """
    logger.info("get_all_tools called")
    return [
        FunctionTool.from_defaults(
            fn=git_get_latest_commit,
            description="Get the latest commit hash. Use for tracking current revision. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_init_repo,
            description="Initialize a new Git repository. Use for creating fresh repos. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_add_files,
            description="Add files to staging area. Use for preparing commits. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_commit,
            description="Create a commit with a message. Use for saving staged changes. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_get_status,
            description="Get repository status. Use for inspecting changes and untracked files. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_generate_changelog,
            description="Generate changelog from commit history. Use for release notes and documentation. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_get_recent_changes,
            description="Get recent commits with author and date. Use for inspecting history. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_update_changelog,
            description="Update changelog with a new entry. Use for manual changelog management. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_get_email,
            description="Get user email from Git config. Use for identity inspection. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_init_and_commit,
            description="Initialize repo and make first commit. Use for quick bootstrap. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_remote_add,
            description="Add a remote repository. Use for configuring push/pull URLs. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_push,
            description="Push changes to remote. Use for uploading commits. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_remote_get,
            description="List configured remotes. Use for inspecting remote URLs. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_set_upstream,
            description="Set upstream tracking for a branch. Use for linking local to remote branches. Category: Version Control",
        ),
        # Phase 1: Branch Management Tools
        FunctionTool.from_defaults(
            fn=git_branch_list,
            description="List all branches (local or remote). Use for inspecting available branches. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_branch_create,
            description="Create a new branch. Use for creating feature/fix branches. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_branch_checkout,
            description="Switch to a branch. Use for changing the working branch. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_branch_delete,
            description="Delete a branch. Use for cleaning up merged/abandoned branches. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_branch_rename,
            description="Rename the current branch. Use for fixing branch naming. Category: Version Control",
        ),
        # Phase 2: Diff & Sync Tools
        FunctionTool.from_defaults(
            fn=git_diff,
            description="Show file differences. Use for comparing working tree, branches, or commits. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_diff_staged,
            description="Show staged differences. Use for reviewing changes before commit. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_pull,
            description="Pull from remote. Use for fetching and merging changes. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_fetch,
            description="Fetch from remote. Use for updating remote refs without merging. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_merge,
            description="Merge branches. Use for integrating feature branches. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_rebase,
            description="Rebase commits. Use for cleaning up commit history. Category: Version Control",
        ),
        FunctionTool.from_defaults(
            fn=git_log_compare,
            description="Compare branch logs. Use for seeing what's diverged between branches. Category: Version Control",
        ),
    ]
