"""
Git Status Module - Check uncommitted and modified files in a project.

Provides git status checking capabilities for inspecting the current state
of a project's working tree, including modified, staged, and untracked files.

Category: Project Management
"""

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class GitFileStatus:
    """Status of a single file in the git working tree."""

    path: str
    status: str  # e.g., 'M', 'A', 'D', '??', 'M ', ' M', etc.
    staged: bool
    modified: bool
    untracked: bool
    deleted: bool
    renamed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "path": self.path,
            "status": self.status,
            "staged": self.staged,
            "modified": self.modified,
            "untracked": self.untracked,
            "deleted": self.deleted,
            "renamed": self.renamed,
        }


@dataclass
class GitStatusResult:
    """Result of a git status check."""

    path: str
    is_git_repo: bool
    branch: str
    commit_hash: str
    files: List[GitFileStatus] = field(default_factory=list)
    has_uncommitted: bool = False
    has_staged: bool = False
    has_untracked: bool = False
    has_modified: bool = False
    error: Optional[str] = None

    @property
    def uncommitted_count(self) -> int:
        """Count of uncommitted (modified + staged + untracked) files."""
        return len(self.files)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "path": self.path,
            "is_git_repo": self.is_git_repo,
            "branch": self.branch,
            "commit_hash": self.commit_hash,
            "has_uncommitted": self.has_uncommitted,
            "has_staged": self.has_staged,
            "has_untracked": self.has_untracked,
            "has_modified": self.has_modified,
            "uncommitted_count": self.uncommitted_count,
            "files": [f.to_dict() for f in self.files],
            "error": self.error,
        }


class GitStatusChecker:
    """
    Checks git status of a project directory.

    Provides detailed information about uncommitted changes, staged files,
    untracked files, and the overall git state of a project.

    Args:
        default_timeout: Default timeout in seconds for git commands (default: 10)
    """

    def __init__(self, default_timeout: int = 10):
        self.default_timeout = default_timeout

    def check_status(
        self,
        path: str,
        include_untracked: bool = True,
        timeout: Optional[int] = None,
    ) -> GitStatusResult:
        """
        Check git status of a directory.

        Args:
            path: Directory path to check
            include_untracked: Whether to include untracked files (default: True)
            timeout: Timeout in seconds for git commands

        Returns:
            GitStatusResult with detailed status information
        """
        effective_timeout = timeout or self.default_timeout
        project_path = Path(path).resolve()

        if not project_path.is_dir():
            return GitStatusResult(
                path=str(project_path),
                is_git_repo=False,
                branch="",
                commit_hash="",
                error=f"Path is not a directory: {project_path}",
            )

        try:
            # Check if it's a git repo
            is_repo = self._is_git_repo(str(project_path), effective_timeout)

            if not is_repo:
                return GitStatusResult(
                    path=str(project_path),
                    is_git_repo=False,
                    branch="",
                    commit_hash="",
                )

            # Get branch name
            branch = self._get_branch(str(project_path), effective_timeout)

            # Get commit hash
            commit_hash = self._get_commit_hash(str(project_path), effective_timeout)

            # Get file statuses
            files = self._get_file_statuses(
                str(project_path),
                include_untracked=include_untracked,
                timeout=effective_timeout,
            )

            # Determine overall status flags
            has_staged = any(f.staged for f in files)
            has_modified = any(f.modified for f in files)
            has_untracked = any(f.untracked for f in files)
            has_uncommitted = has_staged or has_modified or has_untracked

            return GitStatusResult(
                path=str(project_path),
                is_git_repo=True,
                branch=branch,
                commit_hash=commit_hash,
                files=files,
                has_uncommitted=has_uncommitted,
                has_staged=has_staged,
                has_untracked=has_untracked,
                has_modified=has_modified,
            )

        except Exception as e:
            logger.error(f"Git status check failed for {project_path}: {e}")
            return GitStatusResult(
                path=str(project_path),
                is_git_repo=True,
                branch="",
                commit_hash="",
                error=str(e),
            )

    def _run_git_command(
        self,
        path: str,
        args: List[str],
        timeout: int,
    ) -> subprocess.CompletedProcess:
        """Run a git command with timeout."""
        return subprocess.run(
            ["git", "-C", path] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def _is_git_repo(self, path: str, timeout: int) -> bool:
        """Check if path is inside a git repository."""
        try:
            result = self._run_git_command(
                path,
                ["rev-parse", "--is-inside-work-tree"],
                timeout,
            )
            return result.returncode == 0 and result.stdout.strip() == "true"
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    def _get_branch(self, path: str, timeout: int) -> str:
        """Get current branch name."""
        try:
            result = self._run_git_command(
                path,
                ["branch", "--show-current"],
                timeout,
            )
            return result.stdout.strip() if result.returncode == 0 else ""
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return ""

    def _get_commit_hash(self, path: str, timeout: int) -> str:
        """Get current commit hash (short)."""
        try:
            result = self._run_git_command(
                path,
                ["rev-parse", "--short", "HEAD"],
                timeout,
            )
            return result.stdout.strip() if result.returncode == 0 else ""
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return ""

    def _get_file_statuses(
        self,
        path: str,
        include_untracked: bool = True,
        timeout: int = 10,
    ) -> List[GitFileStatus]:
        """
        Get detailed file statuses from git status.

        Uses 'git status --porcelain' for machine-readable output.
        """
        files: List[GitFileStatus] = []

        try:
            # Build porcelain command
            args = ["status", "--porcelain"]
            if not include_untracked:
                args.append("--untracked-files=no")

            result = self._run_git_command(path, args, timeout)

            if result.returncode != 0:
                logger.warning(f"git status failed: {result.stderr}")
                return files

            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue

                file_status = self._parse_porcelain_line(line)
                if file_status:
                    files.append(file_status)

        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            logger.warning(f"Failed to get file statuses: {e}")

        return files

    @staticmethod
    def _parse_porcelain_line(line: str) -> Optional[GitFileStatus]:
        """
        Parse a single line from 'git status --porcelain' output.

        The porcelain format uses a 2-character status code:
        - First character: staged area (index)
        - Second character: working tree
        - Common codes: M (modified), A (added), D (deleted), ?? (untracked), R (renamed)
        """
        if len(line) < 3:
            return None

        # Status codes are first 2-3 characters, followed by space, then path
        status_part = line[:3].rstrip()
        path_part = line[3:].strip() if len(line) > 3 else line[2:].strip()

        # Handle rename format: "R100\told_path -> new_path"
        if "\t" in path_part and status_part[0] in ("R", "T"):
            path_part = path_part.split("\t")[-1].strip()

        staged_char = status_part[0] if len(status_part) >= 1 else " "
        working_char = status_part[1] if len(status_part) >= 2 else " "

        # Determine flags
        is_staged = staged_char not in (" ", "?")
        is_modified = (staged_char == "M" or working_char == "M")
        is_untracked = (staged_char == "?" or working_char == "?")
        is_deleted = (staged_char == "D" or working_char == "D")
        is_renamed = (staged_char == "R" or working_char == "R")

        return GitFileStatus(
            path=path_part,
            status=status_part,
            staged=is_staged,
            modified=is_modified,
            untracked=is_untracked,
            deleted=is_deleted,
            renamed=is_renamed,
        )

    def get_summary(self, path: str, include_untracked: bool = True) -> Dict[str, Any]:
        """
        Get a summary of git status without detailed file list.

        Args:
            path: Directory path to check
            include_untracked: Whether to include untracked files

        Returns:
            Dictionary with summary information
        """
        result = self.check_status(path, include_untracked=include_untracked)

        return {
            "path": result.path,
            "is_git_repo": result.is_git_repo,
            "branch": result.branch,
            "commit_hash": result.commit_hash,
            "has_uncommitted": result.has_uncommitted,
            "has_staged": result.has_staged,
            "has_untracked": result.has_untracked,
            "has_modified": result.has_modified,
            "uncommitted_count": result.uncommitted_count,
            "error": result.error,
        }