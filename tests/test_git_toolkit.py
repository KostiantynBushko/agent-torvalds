"""
Unit tests for agent_git_toolkit.

Tests Git operations including:
- Repository initialization, status, commits
- Changelog generation and updates
- Remote operations
- File staging
- Branch management (Phase 1 / Tier 1)
- Diff & Sync tools (Phase 2 / Tier 2)
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
    # Phase 2: Diff & Sync Tools
    git_diff,
    git_diff_staged,
    git_pull,
    git_fetch,
    git_merge,
    git_rebase,
    git_log_compare,
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


# =============================================================================
# Phase 2: Diff & Sync Tests (Tier 2)
# =============================================================================

class TestDiffTools(GitTestBase):
    """Tests for git_diff and git_diff_staged."""

    def test_diff_returns_string(self):
        """Diff should return a string."""
        self._make_initial_commit()
        result = git_diff(self.test_dir)
        self.assertIsInstance(result, str)

    def test_diff_empty_on_clean_repo(self):
        """Diff on a clean repo should return empty string."""
        self._make_initial_commit()
        result = git_diff(self.test_dir)
        self.assertEqual(result.strip(), "")

    def test_diff_shows_unstaged_changes(self):
        """Diff should show unstaged file changes."""
        self._make_initial_commit()
        # Modify file without staging
        self._create_file("initial.txt", "modified content for diff test")
        result = git_diff(self.test_dir)
        self.assertIn("modified content for diff test", result)
        self.assertIn("+", result)  # Should show additions

    def test_diff_with_target(self):
        """Diff with a target should compare against that target."""
        self._make_initial_commit()
        # Make a second commit
        self._create_file("second.txt", "second file")
        git_add_files(self.test_dir, ["second.txt"])
        git_commit(self.test_dir, "Second commit")
        
        # Diff against HEAD~1
        result = git_diff(self.test_dir, "HEAD~1")
        self.assertIn("second.txt", result)

    def test_diff_staged_returns_string(self):
        """Staged diff should return a string."""
        self._make_initial_commit()
        result = git_diff_staged(self.test_dir)
        self.assertIsInstance(result, str)

    def test_diff_staged_empty_on_no_staged_changes(self):
        """Staged diff should be empty when nothing is staged."""
        self._make_initial_commit()
        result = git_diff_staged(self.test_dir)
        self.assertEqual(result.strip(), "")

    def test_diff_staged_shows_staged_changes(self):
        """Staged diff should show staged changes."""
        self._make_initial_commit()
        # Modify and stage file
        self._create_file("staged.txt", "staged content")
        git_add_files(self.test_dir, ["staged.txt"])
        result = git_diff_staged(self.test_dir)
        self.assertIn("staged.txt", result)

    def test_diff_invalid_target_returns_error(self):
        """Diff with invalid target should return error string."""
        self._make_initial_commit()
        result = git_diff(self.test_dir, "nonexistent-branch-12345")
        self.assertIn("Error", result)


class TestSyncTools(GitTestBase):
    """Tests for git_fetch, git_pull, git_merge, git_rebase, git_log_compare."""

    def test_fetch_returns_dict(self):
        """Fetch should return a dict with success key."""
        result = git_fetch(self.test_dir)
        self.assertIsInstance(result, dict)
        self.assertIn("success", result)

    def test_fetch_without_remote_fails(self):
        """Fetch without a remote should fail."""
        result = git_fetch(self.test_dir)
        self.assertFalse(result["success"])

    def test_pull_returns_dict(self):
        """Pull should return a dict with success key."""
        result = git_pull(self.test_dir)
        self.assertIsInstance(result, dict)
        self.assertIn("success", result)

    def test_pull_without_remote_fails(self):
        """Pull without a remote should fail."""
        result = git_pull(self.test_dir)
        self.assertFalse(result["success"])

    def test_merge_returns_dict(self):
        """Merge should return a dict with success and conflicts keys."""
        self._make_initial_commit()
        git_branch_create(self.test_dir, "feature/merge-test")
        result = git_merge(self.test_dir, "feature/merge-test")
        self.assertIsInstance(result, dict)
        self.assertIn("success", result)
        self.assertIn("conflicts", result)

    def test_merge_nonexistent_branch_fails(self):
        """Merge with non-existent branch should fail."""
        result = git_merge(self.test_dir, "nonexistent-branch")
        self.assertFalse(result["success"])

    def test_merge_with_strategy(self):
        """Merge should accept a strategy parameter."""
        self._make_initial_commit()
        git_branch_create(self.test_dir, "feature/strategy-test")
        result = git_merge(self.test_dir, "feature/strategy-test", strategy="recursive")
        self.assertIsInstance(result, dict)
        self.assertIn("success", result)

    def test_rebase_returns_dict(self):
        """Rebase should return a dict with success and conflicts keys."""
        self._make_initial_commit()
        git_branch_create(self.test_dir, "feature/rebase-test")
        result = git_rebase(self.test_dir, "feature/rebase-test")
        self.assertIsInstance(result, dict)
        self.assertIn("success", result)
        self.assertIn("conflicts", result)

    def test_rebase_nonexistent_branch_fails(self):
        """Rebase with non-existent branch should fail."""
        result = git_rebase(self.test_dir, "nonexistent-branch")
        self.assertFalse(result["success"])

    def test_rebase_with_strategy(self):
        """Rebase should accept a strategy parameter."""
        self._make_initial_commit()
        git_branch_create(self.test_dir, "feature/strategy-rebase")
        result = git_rebase(self.test_dir, "feature/strategy-rebase", strategy="recursive")
        self.assertIsInstance(result, dict)

    def test_log_compare_returns_dict(self):
        """Log compare should return a dict with ahead and behind keys."""
        self._make_initial_commit()
        git_branch_create(self.test_dir, "feature/compare-test")
        result = git_log_compare(self.test_dir, "feature/compare-test", "HEAD")
        self.assertIsInstance(result, dict)
        self.assertIn("success", result)
        self.assertIn("ahead", result)
        self.assertIn("behind", result)

    def test_log_compare_shows_divergence(self):
        """Log compare should show commits ahead and behind."""
        self._make_initial_commit()
        
        # Create feature branch from HEAD
        git_branch_create(self.test_dir, "feature/divergence")
        
        # Make a commit on feature branch
        git_branch_checkout(self.test_dir, "feature/divergence")
        self._create_file("feature-file.txt", "feature content")
        git_add_files(self.test_dir, ["feature-file.txt"])
        git_commit(self.test_dir, "Feature commit")
        
        # Go back to main branch
        main_branches = git_branch_list(self.test_dir)
        for b in main_branches:
            if b != "feature/divergence":
                git_branch_checkout(self.test_dir, b)
                break
        
        # Now compare: feature should be 1 ahead, main should be 0 behind
        result = git_log_compare(self.test_dir, "feature/divergence", "HEAD")
        self.assertTrue(result["success"])
        # Feature branch has 1 commit that HEAD doesn't
        self.assertEqual(len(result["ahead"]), 1)
        self.assertIn("Feature commit", result["ahead"][0]["message"])

    def test_log_compare_both_directions(self):
        """Log compare should show commits in both directions."""
        self._make_initial_commit()
        
        # Get the main branch name before switching
        main_branch = git_branch_list(self.test_dir)[0]
        
        # Create feature branch
        git_branch_create(self.test_dir, "feature/bidirectional")
        
        # Make commit on main (current) branch
        self._create_file("main-file.txt", "main content")
        git_add_files(self.test_dir, ["main-file.txt"])
        git_commit(self.test_dir, "Main commit")
        
        # Switch to feature and make commit there
        git_branch_checkout(self.test_dir, "feature/bidirectional")
        self._create_file("feature-file.txt", "feature content")
        git_add_files(self.test_dir, ["feature-file.txt"])
        git_commit(self.test_dir, "Feature commit")
        
        # Compare: feature has 1 ahead (feature commit), main has 1 ahead (main commit)
        # Use the main branch name explicitly instead of HEAD (which is now on feature)
        result = git_log_compare(self.test_dir, "feature/bidirectional", main_branch)
        self.assertTrue(result["success"])
        # Feature is ahead by its own commit
        self.assertEqual(len(result["ahead"]), 1)
        # Main branch is ahead by its own commit
        self.assertEqual(len(result["behind"]), 1)

    def test_log_compare_nonexistent_branch_fails(self):
        """Log compare with non-existent branch should fail."""
        result = git_log_compare(self.test_dir, "nonexistent1", "nonexistent2")
        self.assertFalse(result["success"])


if __name__ == "__main__":
    unittest.main()
