"""
The rule that no user path of the machine leaves the machine.

The repository is public, and the machine of the operator is private.
**Every** path of that machine — the home, the name of the account, the
working copy, the folders of the disk — must never reach anything outside
it: not the source, not a commit message, not the body of a pull
request, not an issue, not a comment, not the text the agent writes.

The check that enforces it is `scripts/check_no_user_paths.py`.  It finds
a path in two ways: by the **shape** of a home (`/home/<account>`,
`/Users/<account>`, `C:\\Users\\<account>`), which is known everywhere, and
by the **identity** of the machine the check runs on — the account, the
home, the private folders of the working copy — which is computed and
never written down.

The placeholders a documentation writes (`/home/user/...`) are not a path
of anybody and are left alone.

The operator stated this on 2026-11-23, after finding a user path of the
machine in the text the agent generates.

Run with:
    pytest tests/test_no_user_paths.py -v
"""

import importlib.util
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKER_PATH = ROOT / "scripts" / "check_no_user_paths.py"
RULES_PATH = ROOT / "DEVELOPMENT_RULES.md"
PROMPT_ENGINE_PATH = ROOT / "project_manager" / "prompt_engine.py"
AGENT_PATH = ROOT / "agent-torvalds.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "user_paths.yml"

#: A name that is the account of nobody.  The examples of the tests are
#: built at runtime, with it: a path written down in this file would be a
#: path of a home, and the check of Rule 8 would — rightly — find it here.
FAKE_ACCOUNT = "account-of-the-test"


def load_checker():
    """The checker script, loaded the way the other tests load a module."""
    spec = importlib.util.spec_from_file_location("check_no_user_paths", CHECKER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = load_checker()


def git(*arguments):
    """The output of a git command, or nothing when it fails."""
    result = subprocess.run(
        ["git", *arguments],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def base_revision():
    """The revision the branch of the work starts from, or nothing."""
    for candidate in ("origin/master", "master", "origin/main", "main"):
        if git("rev-parse", "--verify", candidate).strip():
            return candidate
    return None


class TestNothingCarriesAUserPath(unittest.TestCase):
    """Nothing that leaves the machine carries a path of the machine."""

    def test_no_tracked_file_carries_a_user_path(self):
        """The tree of the repository is clean."""
        identity = checker.Identity()
        findings = checker.check_files(ROOT, identity)
        self.assertEqual(
            [f"{where}  {kind}: {found}" for where, kind, found in findings],
            [],
            "these files carry a user path:\n"
            + "\n".join(f"{where}  {kind}: {found}" for where, kind, found in findings),
        )

    def test_no_new_commit_carries_a_user_path(self):
        """The commits of the branch are clean.

        Only the commits that are **new** are read: the whole history
        carries the leaks of the past, and a gate that reads it would be
        red before anyone writes a line of code.
        """
        base = base_revision()
        if not base:
            self.skipTest("the base of the branch cannot be found")
        identity = checker.Identity()
        findings = checker.check_commits(ROOT, f"{base}..HEAD", identity)
        self.assertEqual(
            [f"{where}  {kind}: {found}" for where, kind, found in findings],
            [],
            "these commits carry a user path:\n"
            + "\n".join(f"{where}  {kind}: {found}" for where, kind, found in findings),
        )

    def test_the_check_finds_a_home_when_one_is_there(self):
        """A check that has never failed proves nothing."""
        identity = checker.Identity(home=Path("/nonexistent/home"))
        text = f"the file is in /home/{FAKE_ACCOUNT}/.config"
        findings = checker.find_user_paths(text, identity)
        self.assertTrue(findings, "the shape of a home was not found")

    def test_the_check_finds_the_account_of_this_machine(self):
        """The identity of the machine is found as well as the shape."""
        identity = checker.Identity(home=Path("/nonexistent") / FAKE_ACCOUNT)
        text = f"/srv/{FAKE_ACCOUNT}/data"
        findings = checker.find_user_paths(text, identity)
        self.assertTrue(findings, "the account of the machine was not found in a path")

    def test_the_name_of_the_account_on_its_own_is_a_finding(self):
        """The name of the account is private even without a path."""
        identity = checker.Identity(home=Path("/nonexistent") / FAKE_ACCOUNT)
        text = f"the account is {FAKE_ACCOUNT}"
        findings = checker.find_user_paths(text, identity)
        self.assertTrue(findings, "the name of the account was not found")

    def test_a_placeholder_is_not_a_finding(self):
        """The placeholders a documentation writes are left alone."""
        identity = checker.Identity(home=Path("/nonexistent/home"))
        text = "the file is in /home/user/.config and in ~/notes"
        self.assertEqual(checker.find_user_paths(text, identity), [])

    def test_the_check_does_not_find_its_own_source(self):
        """The file that defines the patterns is scanned like any other."""
        identity = checker.Identity()
        text = CHECKER_PATH.read_text(encoding="utf-8")
        findings = checker.find_user_paths(text, identity)
        self.assertEqual(
            [f"{kind}: {found}" for _, kind, found in findings],
            [],
            "the check matches its own source:\n"
            + "\n".join(f"{kind}: {found}" for _, kind, found in findings),
        )

    def test_the_rule_is_written_down(self):
        """The rule is in the rules of the development."""
        text = RULES_PATH.read_text(encoding="utf-8")
        self.assertIn("Rule 8", text)
        self.assertIn("user path", text)

    def test_the_agent_is_told_the_rule(self):
        """The operating instructions of the agent carry the rule.

        The agent that writes the text, the code and the commit message
        is the one that has to be told — the rule cannot live only in a
        file the agent reads once.
        """
        for path in (PROMPT_ENGINE_PATH, AGENT_PATH):
            with self.subTest(path=path.name):
                text = path.read_text(encoding="utf-8")
                self.assertIn(
                    "user path",
                    text,
                    f"{path.name} does not tell the agent about the user path",
                )

    def test_the_workflow_checks_the_text_outside_the_repository(self):
        """The body of a pull request, an issue and a comment is checked.

        The text that leaves the machine is not a file of the repository,
        so the check that reads it is a workflow of its own.
        """
        self.assertTrue(WORKFLOW_PATH.is_file(), "the workflow is missing")
        text = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("check_no_user_paths.py", text)
        for event in ("pull_request", "issues", "issue_comment"):
            self.assertIn(event, text, f"the workflow does not listen to {event}")


if __name__ == "__main__":
    unittest.main()
