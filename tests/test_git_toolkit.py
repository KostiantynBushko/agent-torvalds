"""
Unit tests for agent_git_toolkit.

Tests Git operations including:
- Repository initialization, status, commits
- Changelog generation and updates
- Remote operations
- File staging
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


if __name__ == "__main__":
    unittest.main()
