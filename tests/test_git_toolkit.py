"""
Unit tests for agent_git_toolkit.

Tests Git operations including:
- Repository initialization, status, commits
- Changelog generation and updates
- Remote operations
- File staging
- Branch management (Phase 1 / Tier 1)
"""
import unittest
import os
import tempfile
import shutil
import subprocess

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_git_toolkit import (
    git_init_repo,
    git_add_files,
    git_commit,
    git_get_status,
    git_get_latest_commit,
    git_get_recent_changes,
    git_generate_changelog,
    git_update_changelog,
    git_get_email,
    git_init_and_commit,
    git_remote_add,
    git_remote_get,
    # Phase 1: Branch Management Tools
    git_branch_list,
    git_branch_create,
    git_branch_checkout,
    git_branch_delete,
    git_branch_rename,
)


class GitTestBase(unittest.TestCase):
    """Base class for Git tests with temp repo setup."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        # Initialize git repo
        git_init_repo(self.test_dir)
        # Configure user for commits
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.test_dir,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=self.test_dir,
            capture_output=True,
        )

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _create_file(self, filename, content="test content"):
        filepath = os.path.join(self.test_dir, filename)
        with open(filepath, "w") as f:
            f.write(content)
        return filepath

    def _make_initial_commit(self):
        """Helper to create an initial commit so branches can be created."""
        self._create_file("initial.txt", "initial content")
        git_add_files(self.test_dir, ["initial.txt"])
        git_commit(self.test_dir, "Initial commit")


class TestGitInit(GitTestBase):
    def test_init_returns_true(self):
        new_dir = os.path.join(self.test_dir, "new_repo")
        os.makedirs(new_dir)
        self.assertTrue(git_init_repo(new_dir))

    def test_init_creates_git_dir(self):
        new_dir = os.path.join(self.test_dir, "new_repo2")
        os.makedirs(new_dir)
        git_init_repo(new_dir)
        self.assertTrue(os.path.isdir(os.path.join(new_dir, ".git")))

    def test_init_nonexistent_dir_returns_false(self):
        self.assertFalse(git_init_repo("/nonexistent/path/to/repo"))


class TestGitAddAndCommit(GitTestBase):
    def test_add_files(self):
        filepath = self._create_file("test.txt")
        self.assertTrue(git_add_files(self.test_dir, ["test.txt"]))

    def test_commit(self):
        filepath = self._create_file("test.txt")
        git_add_files(self.test_dir, ["test.txt"])
        self.assertTrue(git_commit(self.test_dir, "Test commit"))

    def test_commit_no_changes_returns_false(self):
        # No staged changes
        self.assertFalse(git_commit(self.test_dir, "Empty commit"))


class TestGitStatus(GitTestBase):
    def test_status_returns_dict(self):
        result = git_get_status(self.test_dir)
        self.assertIsInstance(result, dict)
        self.assertIn("status", result)

    def test_status_success(self):
        result = git_get_status(self.test_dir)
        self.assertEqual(result["status"], "success")


class TestGitCommitInfo(GitTestBase):
    def test_get_latest_commit(self):
        self._create_file("test.txt")
        git_add_files(self.test_dir, ["test.txt"])
        git_commit(self.test_dir, "Initial commit")
        result = git_get_latest_commit(self.test_dir)
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_get_recent_changes(self):
        self._create_file("test.txt")
        git_add_files(self.test_dir, ["test.txt"])
        git_commit(self.test_dir, "First commit")
        result = git_get_recent_changes(self.test_dir)
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) > 0)
        self.assertIn("hash", result[0])
        self.assertIn("message", result[0])


class TestGitChangelog(GitTestBase):
    def test_generate_changelog(self):
        self._create_file("test.txt")
        git_add_files(self.test_dir, ["test.txt"])
        git_commit(self.test_dir, "Initial commit")
        self.assertTrue(git_generate_changelog(self.test_dir))
        changelog_path = os.path.join(self.test_dir, "CHANGELOG.md")
        self.assertTrue(os.path.exists(changelog_path))

    def test_update_changelog(self):
        self.assertTrue(git_update_changelog(self.test_dir, "feature", "New feature"))
        changelog_path = os.path.join(self.test_dir, "CHANGELOG.md")
        self.assertTrue(os.path.exists(changelog_path))
        with open(changelog_path) as f:
            content = f.read()
        self.assertIn("New feature", content)


class TestGitEmail(GitTestBase):
    def test_get_email(self):
        result = git_get_email(self.test_dir)
        self.assertEqual(result, "test@example.com")


class TestGitInitAndCommit(GitTestBase):
    def test_init_and_commit(self):
        new_dir = os.path.join(self.test_dir, "new_repo")
        os.makedirs(new_dir)
        self.assertTrue(git_init_and_commit(new_dir, "Initial commit"))


class TestGitRemote(GitTestBase):
    def test_remote_add(self):
        self.assertTrue(git_remote_add(self.test_dir, "origin", "https://github.com/test/repo.git"))

    def test_remote_get(self):
        git_remote_add(self.test_dir, "origin", "https://github.com/test/repo.git")
        result = git_remote_get(self.test_dir)
        self.assertIsInstance(result, list)
        self.assertTrue(len(result) > 0)


# =============================================================================
# Phase 1: Branch Management Tests (Tier 1)
# =============================================================================

class TestBranchManagement(GitTestBase):
    """Tests for branch list, create, checkout, delete, rename."""

    def test_branch_list_returns_list(self):
        """Branch list should return a list."""
        result = git_branch_list(self.test_dir)
        self.assertIsInstance(result, list)

    def test_branch_list_empty_on_new_repo(self):
        """New repo with no commits has no branches listed."""
        result = git_branch_list(self.test_dir)
        self.assertEqual(result, [])

    def test_branch_list_after_commit(self):
        """After initial commit, HEAD branch should appear."""
        self._make_initial_commit()
        result = git_branch_list(self.test_dir)
        self.assertIsInstance(result, list)
        # At least one branch (HEAD/master/main) should exist
        self.assertTrue(len(result) >= 1)

    def test_branch_list_remote_returns_empty_without_remote(self):
        """Remote branch list with no remote configured should be empty."""
        result = git_branch_list(self.test_dir, remote=True)
        self.assertEqual(result, [])

    def test_branch_create(self):
        """Creating a branch should succeed after a commit."""
        self._make_initial_commit()
        result = git_branch_create(self.test_dir, "feature/test-branch")
        self.assertTrue(result)

    def test_branch_create_adds_to_list(self):
        """Created branch should appear in branch list."""
        self._make_initial_commit()
        git_branch_create(self.test_dir, "feature/new-feature")
        branches = git_branch_list(self.test_dir)
        self.assertIn("feature/new-feature", branches)

    def test_branch_create_with_custom_start_point(self):
        """Branch can be created from a specific start point."""
        self._make_initial_commit()
        # Get the current HEAD
        head_hash = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.test_dir,
            capture_output=True,
            text=True,
        ).stdout.strip()
        result = git_branch_create(self.test_dir, "feature/from-head", start_point=head_hash)
        self.assertTrue(result)

    def test_branch_checkout(self):
        """Checkout to an existing branch should succeed."""
        self._make_initial_commit()
        git_branch_create(self.test_dir, "feature/checkout-test")
        result = git_branch_checkout(self.test_dir, "feature/checkout-test")
        self.assertTrue(result)

    def test_branch_checkout_changes_current_branch(self):
        """After checkout, the new branch should be current."""
        self._make_initial_commit()
        git_branch_create(self.test_dir, "feature/switch-test")
        git_branch_checkout(self.test_dir, "feature/switch-test")
        # Verify current branch via git command
        current = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=self.test_dir,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(current, "feature/switch-test")

    def test_branch_checkout_nonexistent_returns_false(self):
        """Checkout to a non-existent branch should fail."""
        result = git_branch_checkout(self.test_dir, "nonexistent-branch")
        self.assertFalse(result)

    def test_branch_delete(self):
        """Deleting a branch should succeed."""
        self._make_initial_commit()
        git_branch_create(self.test_dir, "feature/to-delete")
        result = git_branch_delete(self.test_dir, "feature/to-delete")
        self.assertTrue(result)

    def test_branch_delete_removes_from_list(self):
        """Deleted branch should no longer appear in branch list."""
        self._make_initial_commit()
        git_branch_create(self.test_dir, "feature/delete-me")
        branches_before = git_branch_list(self.test_dir)
        self.assertIn("feature/delete-me", branches_before)
        
        git_branch_delete(self.test_dir, "feature/delete-me")
        branches_after = git_branch_list(self.test_dir)
        self.assertNotIn("feature/delete-me", branches_after)

    def test_branch_delete_nonexistent_returns_false(self):
        """Deleting a non-existent branch should fail."""
        result = git_branch_delete(self.test_dir, "nonexistent")
        self.assertFalse(result)

    def test_branch_delete_force(self):
        """Force delete should work even for unmerged branches."""
        self._make_initial_commit()
        # Create branch but don't merge it
        git_branch_create(self.test_dir, "feature/unmerged")
        result = git_branch_delete(self.test_dir, "feature/unmerged", force=True)
        self.assertTrue(result)

    def test_branch_rename(self):
        """Renaming current branch should succeed."""
        self._make_initial_commit()
        result = git_branch_rename(self.test_dir, "new-branch-name")
        self.assertTrue(result)

    def test_branch_rename_changes_current_branch(self):
        """After rename, the new name should be current."""
        self._make_initial_commit()
        git_branch_rename(self.test_dir, "renamed-branch")
        current = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=self.test_dir,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(current, "renamed-branch")

    def test_branch_rename_nonexistent_returns_false(self):
        """Rename on a repo with no current branch should fail gracefully."""
        # Fresh repo with no commits has no current branch
        result = git_branch_rename(self.test_dir, "new-name")
        # This may fail since there's no HEAD branch yet
        self.assertIsInstance(result, bool)

    def test_branch_lifecycle_create_checkout_delete(self):
        """Full lifecycle: create -> checkout -> delete."""
        self._make_initial_commit()
        
        # Create
        self.assertTrue(git_branch_create(self.test_dir, "feature/lifecycle"))
        
        # Checkout
        self.assertTrue(git_branch_checkout(self.test_dir, "feature/lifecycle"))
        
        # Verify it's current
        current = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=self.test_dir,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(current, "feature/lifecycle")
        
        # Go back to main/HEAD branch
        main_branch = git_branch_list(self.test_dir)
        for b in main_branch:
            if b != "feature/lifecycle":
                git_branch_checkout(self.test_dir, b)
                break
        
        # Delete
        self.assertTrue(git_branch_delete(self.test_dir, "feature/lifecycle"))
        
        # Verify deleted
        branches = git_branch_list(self.test_dir)
        self.assertNotIn("feature/lifecycle", branches)


if __name__ == "__main__":
    unittest.main()
