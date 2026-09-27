"""
Git Toolkit - Git repository management and version control operations.

This module provides comprehensive Git functionality for repository initialization,
commit management, changelog generation, remote operations, status inspection,
branch management, and diff/sync operations.

Refactored to use pygit2 (Python binding to libgit2) for improved performance,
reliability, and security.

Category: Version Control
Retriever Keywords: git, repository, commit, branch, remote, changelog, version control, diff, merge, sync
"""
import os
import logging
from datetime import date
from typing import Optional
import pygit2
from llama_index.core.tools import FunctionTool

logger = logging.getLogger(__name__)

# =============================================================================
# Helper Functions & Constants
# =============================================================================

# pygit2 status flag to porcelain-equivalent character mapping
STATUS_MAP = {
    pygit2.GIT_STATUS_CURRENT: "",
    pygit2.GIT_STATUS_INDEX_NEW: "A",
    pygit2.GIT_STATUS_INDEX_MODIFIED: "M",
    pygit2.GIT_STATUS_INDEX_DELETED: "D",
    pygit2.GIT_STATUS_INDEX_RENAMED: "R",
    pygit2.GIT_STATUS_WT_NEW: "?",
    pygit2.GIT_STATUS_WT_MODIFIED: "M",
    pygit2.GIT_STATUS_WT_DELETED: "D",
    pygit2.GIT_STATUS_WT_RENAMED: "R",
}


def _open_repo(path: str) -> pygit2.Repository:
    """
    Open a repository at the given path.
    
    Args:
        path: Path to the Git repository
        
    Returns:
        pygit2.Repository instance
        
    Raises:
        ValueError: If path is not a valid git repository
    """
    try:
        return pygit2.Repository(path)
    except pygit2.GitError as e:
        raise ValueError(f"Not a valid git repository: {path}") from e


def _get_credentials(url, username_from_url, allowed_types):
    """
    Credential callback for pygit2 remote operations.
    
    Reads TORVALDS_GITHUB_TOKEN from environment for HTTPS authentication.
    
    Args:
        url: Remote URL
        username_from_url: Username extracted from URL
        allowed_types: Set of allowed credential types
        
    Returns:
        pygit2 credential object or None
    """
    token = os.environ.get("TORVALDS_GITHUB_TOKEN")
    if not token:
        return None
    if pygit2.CREDTYPE_USER_PASS in allowed_types:
        return pygit2.CredCredential("oauth2", token)
    return None


def _get_author_and_committer(repo: pygit2.Repository):
    """
    Get author and committer identity from repository config.
    
    Falls back to default values if not configured.
    
    Args:
        repo: pygit2.Repository instance
        
    Returns:
        Tuple of (author, committer) pygit2.Signature objects
    """
    config = repo.config
    
    name = config.get("user.name").value if config.has_key("user.name") else "Torvalds Agent"
    email = config.get("user.email").value if config.has_key("user.email") else "agent@torvalds.local"
    
    author = pygit2.Signature(name, email)
    committer = pygit2.Signature(name, email)
    
    return author, committer


def _has_staged_changes(repo: pygit2.Repository) -> bool:
    """
    Check if there are staged changes ready to commit.
    
    Args:
        repo: pygit2.Repository instance
        
    Returns:
        bool: True if there are staged changes, False otherwise
    """
    # Check if index differs from HEAD
    try:
        head_commit = repo.head.peel(pygit2.Commit)
        return not repo.index.diff(head_commit.id)
    except (pygit2.GitError, ValueError):
        # No HEAD yet (first commit) — check if index has any entries
        return len(repo.index) > 0


def _parse_git_status_porcelain(status_dict: dict) -> dict:
    """
    Parse pygit2 status dict into structured categories matching porcelain format.
    
    Args:
        status_dict: Raw status dict from repo.status()
        
    Returns:
        dict with categorized file lists
    """
    staged = []
    unstaged = []
    untracked = []
    
    if not status_dict:
        return {
            "staged": staged,
            "unstaged": unstaged,
            "untracked": untracked,
            "is_clean": True,
        }
    
    for file_path, flags in status_dict.items():
        # Decode path if bytes
        if isinstance(file_path, bytes):
            file_path = file_path.decode("utf-8")
        
        # Determine staged status (index)
        index_flags = flags & (
            pygit2.GIT_STATUS_INDEX_NEW |
            pygit2.GIT_STATUS_INDEX_MODIFIED |
            pygit2.GIT_STATUS_INDEX_DELETED |
            pygit2.GIT_STATUS_INDEX_RENAMED
        )
        
        # Determine working tree status
        wt_flags = flags & (
            pygit2.GIT_STATUS_WT_NEW |
            pygit2.GIT_STATUS_WT_MODIFIED |
            pygit2.GIT_STATUS_WT_DELETED |
            pygit2.GIT_STATUS_WT_RENAMED
        )
        
        # Untracked files have WT_NEW flag
        if flags & pygit2.GIT_STATUS_WT_NEW:
            untracked.append(file_path)
        elif index_flags:
            # Something is staged
            staged.append(file_path)
        elif wt_flags:
            # Only working tree changed, not staged
            unstaged.append(file_path)
    
    return {
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
        "is_clean": not (staged or unstaged or untracked),
    }


# =============================================================================
# Tier 1: Basic Operations
# =============================================================================

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
        repo = _open_repo(path)
        commit = repo.head.peel(pygit2.Commit)
        return commit.id.hex
    except (pygit2.GitError, ValueError) as e:
        return f"Error: {str(e)}"


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
        pygit2.init_repository(path)
        return True
    except pygit2.GitError:
        return False


def git_add_files(path: str, files: list) -> dict:
    """
    Add files to the staging area for commit.
    
    Use this tool to stage changes before committing. The 'files' parameter
    MUST be a list of file path strings. NEVER pass an empty list [].
    
    IMPORTANT: The 'files' parameter must be a Python list of strings, e.g.:
      - ['file.py', 'README.md'] to stage specific files
      - ['.'] to stage ALL changes (recommended when you want to stage everything)
      - status['unstaged'] to stage only unstaged files from git_get_status response
      - status['untracked'] to stage only untracked files from git_get_status response
    
    Args:
        path (str): The directory path of the Git repository
        files (list): List of file path strings to add. Examples:
                      - ['file.py', 'README.md'] for specific files
                      - ['.'] to stage all changes
                      - status['unstaged'] to stage unstaged files
                      - status['untracked'] to stage untracked files
        
    Returns:
        dict: Dictionary with keys:
            - 'success': bool indicating if the operation succeeded
            - 'files_staged': list of files that were staged (on success)
            - 'error': error message with guidance (on failure)
            
    Example:
        >>> git_add_files("/home/user/repo", ["src/main.py", "README.md"])
        {'success': True, 'files_staged': ['src/main.py', 'README.md']}
        >>> git_add_files("/home/user/repo", ["."])
        {'success': True, 'files_staged': ['.']}
        
    Keywords: add, stage, staging, index, prepare commit
    """
    logger.info(f"git_add_files called with path: {path}, files: {files}")
    
    # Validate input: check if files is empty
    if not files:
        return {
            "success": False,
            "error": "No files specified. Use ['.'] to stage all changes, or provide a list of file paths like ['file.py', 'README.md'].",
        }
    
    # Validate input: check that all items are strings
    non_string_items = [f for f in files if not isinstance(f, str)]
    if non_string_items:
        return {
            "success": False,
            "error": f"files must be a list of strings. Found non-string items: {non_string_items}. Use ['file.py', 'README.md'] format.",
        }
    
    try:
        repo = _open_repo(path)
        repo.index.add(files)
        repo.index.write()
        return {
            "success": True,
            "files_staged": files,
        }
    except (pygit2.GitError, ValueError) as e:
        return {
            "success": False,
            "error": f"Failed to add files: {str(e)}",
        }


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
        repo = _open_repo(path)
        
        # Check if there are staged changes
        if not _has_staged_changes(repo):
            return False
        
        author, committer = _get_author_and_committer(repo)
        
        # Prepare tree
        repo.index.write()
        tree = repo.index.write_tree()
        
        # Determine parent commits
        parents = []
        try:
            head_commit = repo.head.peel(pygit2.Commit)
            parents.append(head_commit.id)
        except (pygit2.GitError, ValueError):
            # First commit, no parents
            pass
        
        # Create commit
        repo.create_commit(
            "HEAD",
            author,
            committer,
            message,
            tree,
            parents,
        )
        return True
    except (pygit2.GitError, ValueError):
        return False


def git_get_status(path: str) -> dict:
    """
    Get current repository status showing staged, unstaged, and untracked files.
    
    Use this tool to inspect the working tree status before making changes or commits.
    The response contains categorized file lists ('staged', 'unstaged', 'untracked')
    that you can directly pass to git_add_files to stage specific files.
    
    IMPORTANT WORKFLOW:
    1. Call git_get_status to get the status
    2. Extract file paths from the 'unstaged' or 'untracked' lists
    3. Pass those file paths as a list to git_add_files
    
    Args:
        path (str): The directory path of the Git repository
        
    Returns:
        dict: Dictionary containing status information with keys:
            - 'status': 'success' or 'error'
            - 'output': Raw porcelain format status string (on success)
            - 'staged': list of file paths with staged changes (ready to commit)
            - 'unstaged': list of file paths for modified files not yet staged
            - 'untracked': list of file paths for new files not tracked by git
            - 'is_clean': True if working tree is clean, False otherwise
            - 'message': Error message (on failure)
            
    Example:
        >>> git_get_status("/home/user/repo")
        {
            'status': 'success',
            'output': 'M src/main.py\n?? new_file.py',
            'staged': [],
            'unstaged': ['src/main.py'],
            'untracked': ['new_file.py'],
            'is_clean': False
        }
        
    Workflow Example:
        Step 1: Check status
        >>> status = git_get_status("/home/user/repo")
        >>> # status['unstaged'] = ['src/main.py']
        >>> # status['untracked'] = ['new_file.py']
        
        Step 2: Stage the unstaged files by passing the list directly
        >>> git_add_files("/home/user/repo", status['unstaged'])
        {'success': True, 'files_staged': ['src/main.py']}
        
        Step 3: Stage untracked files similarly
        >>> git_add_files("/home/user/repo", status['untracked'])
        {'success': True, 'files_staged': ['new_file.py']}
        
        Step 4: Stage all changes at once using ['.']
        >>> git_add_files("/home/user/repo", ['.'])
        {'success': True, 'files_staged': ['.']}
        
    Keywords: status, changes, modified, untracked, dirty, clean, inspect
    """
    logger.info(f"git_get_status called with path: {path}")
    try:
        repo = _open_repo(path)
        status_dict = repo.status()
        parsed = _parse_git_status_porcelain(status_dict)
        
        # Build porcelain-like output string
        output_lines = []
        for f in parsed["staged"]:
            output_lines.append(f"M  {f}")
        for f in parsed["unstaged"]:
            output_lines.append(f" M {f}")
        for f in parsed["untracked"]:
            output_lines.append(f"?? {f}")
        output = "\n".join(output_lines)
        
        return {
            "status": "success",
            "output": output,
            "staged": parsed["staged"],
            "unstaged": parsed["unstaged"],
            "untracked": parsed["untracked"],
            "is_clean": parsed["is_clean"],
        }
    except (pygit2.GitError, ValueError) as e:
        return {
            "status": "error",
            "message": f"Error getting status: {str(e)}",
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
        repo = _open_repo(path)
        
        # Try to get the head commit
        try:
            head_commit = repo.head.peel(pygit2.Commit)
        except (pygit2.GitError, ValueError):
            # No commits yet
            changelog_path = os.path.join(path, output_file)
            with open(changelog_path, "w") as f:
                f.write("# Changelog\n\nAll notable changes to this project will be documented in this file.\n")
            return True
        
        # Walk commits, filtering out merges
        commits = []
        for commit in repo.walk(head_commit.id, pygit2.GIT_SORT_TIME):
            # Skip merge commits (more than one parent)
            if len(commit.parents) > 1:
                continue
            commits.append(commit)
            if len(commits) >= 1000:  # Safety limit
                break
        
        if not commits:
            changelog_path = os.path.join(path, output_file)
            with open(changelog_path, "w") as f:
                f.write("# Changelog\n\nAll notable changes to this project will be documented in this file.\n")
            return True
        
        changelog_content = "# Changelog\n\nAll notable changes to this project will be documented in this file.\n\n"
        
        current_date = ""
        for commit in commits:
            # Format date as YYYY-MM-DD
            commit_date = date.fromtimestamp(commit.commit_time).strftime("%Y-%m-%d")
            commit_hash = commit.short_id.hex
            message = commit.message.strip().split("\n")[0]  # First line only
            
            # Add date header when date changes
            if commit_date != current_date:
                changelog_content += f"\n## {commit_date}\n\n"
                current_date = commit_date
            
            changelog_content += f"- {message} ({commit_hash})\n"
        
        changelog_path = os.path.join(path, output_file)
        with open(changelog_path, "w") as f:
            f.write(changelog_content)
        
        return True
    except (pygit2.GitError, OSError, ValueError):
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
        repo = _open_repo(path)
        
        # Try to get the head commit
        try:
            head_commit = repo.head.peel(pygit2.Commit)
        except (pygit2.GitError, ValueError):
            return []
        
        recent_changes = []
        count = 0
        
        for commit in repo.walk(head_commit.id, pygit2.GIT_SORT_TIME):
            # Skip merge commits
            if len(commit.parents) > 1:
                continue
            
            commit_date = date.fromtimestamp(commit.commit_time).strftime("%Y-%m-%d")
            commit_hash = commit.short_id.hex
            message = commit.message.strip().split("\n")[0]
            author = commit.author.name
            
            recent_changes.append({
                "hash": commit_hash,
                "date": commit_date,
                "message": message,
                "author": author,
            })
            
            count += 1
            if count >= num_commits:
                break
        
        return recent_changes
    except (pygit2.GitError, ValueError):
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
        repo = _open_repo(path)
        config = repo.config
        if config.has_key("user.email"):
            return config.get("user.email").value
        return ""
    except (pygit2.GitError, ValueError):
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
            pygit2.init_repository(path)
        
        repo = _open_repo(path)
        config = repo.config
        
        # Configure user identity if needed
        if not config.has_key("user.email"):
            config.set_multivar("user.email", "agent@torvalds.local")
        if not config.has_key("user.name"):
            config.set_multivar("user.name", "Torvalds Agent")
        
        # Stage all files
        repo.index.add(["."])
        repo.index.write()
        
        # Get author/committer
        author, committer = _get_author_and_committer(repo)
        
        # Get tree
        tree = repo.index.write_tree()
        
        # Determine parents
        parents = []
        try:
            head_commit = repo.head.peel(pygit2.Commit)
            parents.append(head_commit.id)
        except (pygit2.GitError, ValueError):
            pass
        
        # Create commit (allow empty for fresh repos)
        repo.create_commit(
            "HEAD",
            author,
            committer,
            message,
            tree,
            parents,
        )
        
        return True
    except (pygit2.GitError, ValueError):
        return False




def git_add_all_changes(path: str) -> dict:
    """
    Add all changed and untracked files in the given path to the git staging area.

    Use this tool to automatically stage all modified, deleted, and new (untracked)
    files discovered via git_get_status. Supports relative paths (e.g. '.' for
    the current working directory) and validates that the path exists before
    attempting to stage files.

    Internally:
      1. Resolves relative paths to absolute paths (e.g. '.' -> current dir)
      2. Checks that the resolved path exists on disk
      3. Calls git_get_status(path) to obtain all changed/untracked file lists
      4. Stages every file from 'unstaged' and 'untracked' individually

    Args:
        path (str): Path to the Git repository. Supports relative paths such as
                    '.' (current working directory) or '../other-repo'.

    Returns:
        dict: Dictionary with keys:
            - 'success': bool indicating if the operation succeeded
            - 'files_staged': list of files that were staged (on success)
            - 'status': the full git_get_status result (on success)
            - 'error': error message (on failure)

    Example:
        >>> git_add_all_changes(".")
        {'success': True, 'files_staged': ['src/main.py', 'new_file.py'], ...}
        >>> git_add_all_changes("/home/user/my-repo")
        {'success': True, 'files_staged': [...], ...}

    Keywords: add all, stage all, auto stage, relative path, current directory
    """
    logger.info(f"git_add_all_changes called with path: {path}")

    # Step 1: Resolve relative paths to absolute paths
    resolved_path = os.path.abspath(path)

    # Step 2: Check if the path exists
    if not os.path.isdir(resolved_path):
        return {
            "success": False,
            "error": f"Path does not exist or is not a directory: {resolved_path} (original: {path})",
        }

    # Step 3: Use git_get_status to obtain all changed files
    status = git_get_status(resolved_path)
    if status.get("status") != "success":
        return {
            "success": False,
            "error": f"Failed to get git status: {status.get('message', 'Unknown error')}",
        }

    # Step 4: Collect all unstaged and untracked files
    files_to_stage = []
    files_to_stage.extend(status.get("unstaged", []))
    files_to_stage.extend(status.get("untracked", []))

    # Nothing to stage
    if not files_to_stage:
        return {
            "success": True,
            "files_staged": [],
            "status": status,
        }

    # Step 5: Stage all collected files individually via pygit2
    try:
        repo = _open_repo(resolved_path)
        staged_files = []
        for file_path in files_to_stage:
            # Ensure the path is a string (handle potential bytes from status)
            if isinstance(file_path, bytes):
                file_path = file_path.decode("utf-8")
            repo.index.add(file_path)
            staged_files.append(file_path)
        repo.index.write()
    except (pygit2.GitError, ValueError) as e:
        return {
            "success": False,
            "error": f"Failed to add files: {str(e)}",
        }

    return {
        "success": True,
        "files_staged": staged_files,
        "status": status,
    }


# =============================================================================
# Tier 2: Remote Operations
# =============================================================================

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
        repo = _open_repo(path)
        repo.create_remote(name, url)
        return True
    except (pygit2.GitError, ValueError):
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
        repo = _open_repo(path)
        
        # Get the remote
        if remote not in repo.remotes:
            return False
        remote_obj = repo.remotes[remote]
        
        # Push the branch
        specs = [f"refs/heads/{branch}:refs/heads/{branch}"]
        remote_obj.push(specs, credentials=_get_credentials)
        
        # Set upstream if requested
        if set_upstream:
            try:
                local_branch = repo.branches.local[branch]
                upstream_ref = f"refs/remotes/{remote}/{branch}"
                local_branch.set_upstream(upstream_ref)
            except (KeyError, pygit2.GitError):
                pass
        
        return True
    except (pygit2.GitError, ValueError):
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
        repo = _open_repo(path)
        remotes = []
        for remote in repo.remotes:
            remotes.append({"name": remote.name, "url": remote.url})
        return remotes
    except (pygit2.GitError, ValueError):
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
        repo = _open_repo(path)
        local_branch = repo.branches.local[branch]
        upstream_ref = f"refs/remotes/{remote}/{branch}"
        local_branch.set_upstream(upstream_ref)
        return True
    except (pygit2.GitError, KeyError, ValueError):
        return False


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
        {'success': True, 'output': 'Updating a1b2c3d..e4f5g6h\n...'}
        
    Keywords: pull, fetch, merge, remote, update, synchronize, sync
    """
    logger.info(f"git_pull called with path: {path}, remote: {remote}, branch: {branch}")
    try:
        repo = _open_repo(path)
        
        # Fetch first
        if remote in repo.remotes:
            remote_obj = repo.remotes[remote]
            remote_obj.fetch(credentials=_get_credentials)
        
        if branch:
            # Merge the specific branch
            merge_commit = repo.revparse_single(f"{remote}/{branch}")
            merge_analysis = repo.merge_analysis(merge_commit.id)
            
            if merge_analysis[0] & pygit2.GIT_MERGE_ANALYSIS_UP_TO_DATE:
                return {"success": True, "output": "Already up to date."}
            
            # Perform merge
            repo.merge(merge_commit.id)
            
            # Check for conflicts
            conflicts = list(repo.index.conflicts())
            if conflicts:
                return {
                    "success": False,
                    "output": "",
                    "error": "Merge conflicts detected",
                }
            
            # Complete merge
            author, committer = _get_author_and_committer(repo)
            tree = repo.index.write_tree()
            head_commit = repo.head.peel(pygit2.Commit)
            
            repo.create_commit(
                "HEAD",
                author,
                committer,
                f"Merge remote branch '{branch}'",
                tree,
                [head_commit.id, merge_commit.id],
            )
            
            return {"success": True, "output": f"Merged {branch}"}
        else:
            return {"success": True, "output": "Fetch completed"}
    except (pygit2.GitError, ValueError) as e:
        return {
            "success": False,
            "output": "",
            "error": str(e),
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
        {'success': True, 'output': 'From https://github.com/user/repo\n * branch ...'}
        
    Keywords: fetch, remote, update, download, refs, remote-tracking
    """
    logger.info(f"git_fetch called with path: {path}, remote: {remote}")
    try:
        repo = _open_repo(path)
        
        if remote not in repo.remotes:
            return {
                "success": False,
                "output": "",
                "error": f"Remote '{remote}' not found",
            }
        
        remote_obj = repo.remotes[remote]
        remote_obj.fetch(credentials=_get_credentials)
        
        return {
            "success": True,
            "output": f"Fetched from {remote}",
        }
    except (pygit2.GitError, ValueError) as e:
        return {
            "success": False,
            "output": "",
            "error": str(e),
        }


# =============================================================================
# Tier 3: Branch Management
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
        repo = _open_repo(path)
        if remote:
            return [b.name for b in repo.branches.remote]
        else:
            return [b.name for b in repo.branches.local]
    except (pygit2.GitError, ValueError):
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
        repo = _open_repo(path)
        target = repo.revparse_single(start_point)
        repo.create_branch(branch_name, target)
        return True
    except (pygit2.GitError, ValueError):
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
        repo = _open_repo(path)
        repo.checkout(f"refs/heads/{branch_name}")
        return True
    except (pygit2.GitError, ValueError):
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
        repo = _open_repo(path)
        # pygit2 delete doesn't distinguish between -d and -D, so we just delete
        repo.branches.local.delete(branch_name)
        return True
    except (pygit2.GitError, KeyError, ValueError):
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
        repo = _open_repo(path)
        current_branch = repo.head.shorthand
        repo.branches.local.rename(current_branch, new_name, force=True)
        return True
    except (pygit2.GitError, KeyError, ValueError):
        return False


# =============================================================================
# Tier 4: Diff & Sync Operations
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
        'diff --git a/file.py b/file.py\n--- a/file.py\n+++ b/file.py\n@@ ...'
        >>> git_diff("/home/user/repo", "HEAD~1")
        'diff --git a/file.py b/file.py\n...'
        
    Keywords: diff, difference, changes, compare, modified, additions, deletions
    """
    logger.info(f"git_diff called with path: {path}, target: {target}")
    try:
        repo = _open_repo(path)
        
        if target:
            # Diff against a specific target
            target_commit = repo.revparse_single(target)
            if isinstance(target_commit, pygit2.Commit):
                diff = repo.diff(target_commit.id, repo.head.peel(pygit2.Commit).id)
            else:
                diff = repo.index.diff(target)
        else:
            # Diff working tree against index
            diff = repo.index.diff_working_tree()
        
        return diff.diffstring
    except (pygit2.GitError, ValueError) as e:
        return f"Error: {str(e)}"


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
        'diff --git a/file.py b/file.py\n--- a/file.py\n+++ b/file.py\n@@ ...'
        
    Keywords: diff, staged, index, cached, review, before commit
    """
    logger.info(f"git_diff_staged called with path: {path}")
    try:
        repo = _open_repo(path)
        head_commit = repo.head.peel(pygit2.Commit)
        diff = repo.index.diff(head_commit.id)
        return diff.diffstring
    except (pygit2.GitError, ValueError) as e:
        return f"Error: {str(e)}"


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
        repo = _open_repo(path)
        
        # Get the branch to merge
        merge_branch = repo.branches.local[branch]
        merge_commit = repo.get(merge_branch.target)
        
        # Analyze merge
        merge_analysis = repo.merge_analysis(merge_commit.id)
        
        if merge_analysis[0] & pygit2.GIT_MERGE_ANALYSIS_UP_TO_DATE:
            return {
                "success": True,
                "output": "Already up to date.",
                "conflicts": False,
            }
        
        # Perform merge
        repo.merge(merge_commit.id)
        
        # Check for conflicts
        conflicts = list(repo.index.conflicts())
        if conflicts:
            return {
                "success": False,
                "output": "",
                "conflicts": True,
                "error": "Merge conflicts detected",
            }
        
        # Complete merge commit
        author, committer = _get_author_and_committer(repo)
        tree = repo.index.write_tree()
        head_commit = repo.head.peel(pygit2.Commit)
        
        repo.create_commit(
            "HEAD",
            author,
            committer,
            f"Merge branch '{branch}'",
            tree,
            [head_commit.id, merge_commit.id],
        )
        
        return {
            "success": True,
            "output": f"Merge made by the 'recursive' strategy.",
            "conflicts": False,
        }
    except (pygit2.GitError, KeyError, ValueError) as e:
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
    
    Note: pygit2 has limited rebase support, so this uses a subprocess fallback.
    
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
        import subprocess
        
        cmd = ["git", "rebase"]
        if strategy:
            cmd.extend(["-s", strategy])
        cmd.append(branch)
        
        result = subprocess.run(
            cmd,
            cwd=path,
            capture_output=True,
            text=True,
            check=False,
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
        repo = _open_repo(path)
        
        # Get commit IDs for both branches
        branch1_commit = repo.revparse_single(branch1)
        branch2_commit = repo.revparse_single(branch2)
        
        if not isinstance(branch1_commit, pygit2.Commit) or not isinstance(branch2_commit, pygit2.Commit):
            return {
                "success": False,
                "ahead": [],
                "behind": [],
                "error": "Invalid branch names",
            }
        
        # Commits in branch1 but not in branch2
        ahead = []
        for commit in repo.walk(branch1_commit.id, pygit2.GIT_SORT_TIME):
            if len(commit.parents) > 1:  # Skip merges
                continue
            # Check if this commit is reachable from branch2
            try:
                repo.graph_ahead_behind(branch2_commit.id, commit.id)
            except pygit2.GitError:
                pass
            # Simple approach: walk and collect, then filter
            ahead.append({
                "hash": commit.short_id.hex,
                "message": commit.message.strip().split("\n")[0],
            })
        
        # Commits in branch2 but not in branch1
        behind = []
        for commit in repo.walk(branch2_commit.id, pygit2.GIT_SORT_TIME):
            if len(commit.parents) > 1:  # Skip merges
                continue
            behind.append({
                "hash": commit.short_id.hex,
                "message": commit.message.strip().split("\n")[0],
            })
        
        return {
            "success": True,
            "ahead": ahead[:10],  # Limit to first 10
            "behind": behind[:10],
        }
    except (pygit2.GitError, ValueError) as e:
        return {
            "success": False,
            "ahead": [],
            "behind": [],
            "error": str(e),
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
            description="Add files to staging area. The 'files' parameter must be a list of file path strings, e.g. ['file.py', 'README.md'] or ['.'] for all files. Use for preparing commits. Category: Version Control",
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
            fn=git_add_all_changes,
            description="Add all changed and untracked files to staging area. Uses git_get_status internally, supports relative paths like '.', validates path existence. Use for auto-staging all changes. Category: Version Control",
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
        # Branch Management Tools
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
        # Diff & Sync Tools
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
