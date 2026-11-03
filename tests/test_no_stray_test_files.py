"""
The rule that a test file is never invisible to the CI gate.

pytest collects the directories listed in ``testpaths`` in ``pytest.ini``,
and nothing else.  A ``test_*.py`` file that lives anywhere else is
**never run**: the CI gate does not see it, and a break in it is
invisible until somebody runs it by hand.

That is not a hypothetical.  ``test_live_agent_hitl.py`` and
``test_callback_events_debug.py`` sat in the repository root for a month
— outside ``testpaths``, and therefore outside the suite — and when the
``spinner=`` argument of ``HumanLoopHandler`` was removed, the root
script broke and the gate reported no new failure.  Both are live
scripts that need a real LLM, so they are not unit tests and they do not
belong under ``tests/``; they live in ``scripts/`` now.

There is **no exemption**.  Nothing outside the collected directories may
carry the name of a test — not the repository root, and not
``investigate/`` either.  The scripts under ``investigate/`` are helpers
for one particular case, and they are named for what they are, so
nothing in that folder is mistaken for a test.

The directories that are **not part of this repository** are never
walked — ``.git``, ``.venv``, and the retired ``self-development``
clone.  The clone is a second checkout of the repository: it holds a
whole copy of the suite, and a rule about the files of this repository
must not read the files of the copy.

Run with:
    pytest tests/test_no_stray_test_files.py -v
"""
import configparser
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: The directories pytest collects, read from ``pytest.ini``.
TESTPATHS = (
    "tests chat_manager/tests deploy/tests "
    "toolkits/MikroTik-RouterOS/tests toolkits/shodan-toolkit/tests "
    "toolkits/math-toolkit/tests toolkits/git-toolkit/tests "
    "toolkits/github-toolkit/tests toolkits/os-toolkit/tests "
    "toolkits/linux-toolkit/tests toolkits/apt-toolkit/tests "
    "toolkits/windows-toolkit/tests toolkits/db-toolkit/tests "
    "toolkits/xlsx-toolkit/tests toolkits/data-analysis-toolkit/tests"
).split()

#: The directories that are never walked.
SKIP_DIRS = frozenset({
    ".git", ".venv", ".pytest_cache", "__pycache__", "node_modules",
    # The self-development clone: a second checkout of this
    # repository.  It is git-ignored, and it holds a whole copy of the
    # suite - which the rule must not read as the suite of this
    # repository.
    "self-development",
})


def the_test_files(root):
    """Every ``test_*.py`` under ``root``, outside the skipped dirs."""
    found = []
    for path in root.rglob("test_*.py"):
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        found.append(path.relative_to(root))
    return sorted(found)


def stray_test_files(root, collected):
    """The test files that no collected directory reaches.

    There is no exemption.  A file that pytest will never collect is a
    stray, wherever it is.
    """
    strays = []
    for rel in the_test_files(root):
        absolute = root / rel
        if not any(
            absolute == d or d in absolute.parents for d in collected
        ):
            strays.append(rel.as_posix())
    return strays


def root_test_files(root):
    """The test files that sit directly in the given root."""
    return [
        rel.as_posix() for rel in the_test_files(root) if len(rel.parts) == 1
    ]


class TestNoStrayTestFiles(unittest.TestCase):
    """Every test file is somewhere the CI gate can see it."""

    def setUp(self):
        self.collected = [ROOT / p for p in TESTPATHS]

    def test_the_repository_root_holds_no_test_file(self):
        """The root is the directory that made this worth a rule."""
        strays = root_test_files(ROOT)
        self.assertEqual(
            strays,
            [],
            f"a test file in the repository root is not collected by pytest: "
            f"{strays}.  pytest collects {TESTPATHS}.  Move it under one of "
            f"those, or rename it after what it is.",
        )

    def test_every_test_file_is_collected(self):
        """No test file sits where pytest will never look for it."""
        strays = stray_test_files(ROOT, self.collected)
        self.assertEqual(
            strays,
            [],
            f"these test files are outside every directory pytest collects: "
            f"{strays}.  pytest collects {TESTPATHS}.  Move them under one "
            f"of those, or rename them after what they are.",
        )

    def test_investigate_holds_no_test_file(self):
        """The helpers under investigate/ are named for what they are.

        They test one particular case, and they are not part of the
        suite.  Nothing in that folder may carry the name of a test.
        """
        strays = [
            rel.as_posix() for rel in the_test_files(ROOT)
            if rel.parts[0] == "investigate"
        ]
        self.assertEqual(
            strays,
            [],
            f"these files under investigate/ are named like tests: {strays}.  "
            f"They are helpers for one case - rename them after what they are.",
        )

    def test_the_check_reads_the_test_paths_of_pytest_ini(self):
        """The rule follows pytest.ini, and does not drift from it.

        If a directory is added to ``testpaths``, the rule has to know
        about it.  If it is removed, the files under it have to move.
        """
        parser = configparser.ConfigParser()
        parser.read(ROOT / "pytest.ini")
        configured = parser["pytest"]["testpaths"].split()
        self.assertEqual(
            sorted(configured),
            sorted(TESTPATHS),
            "the test paths in pytest.ini have changed - update TESTPATHS "
            "in this file, so that the rule follows pytest.",
        )

    def test_the_check_catches_a_test_file_in_the_root(self):
        """The rule is tested against a deliberate stray.

        A check that has never failed proves nothing, so the tree is
        built with a test file in the root, and the rule has to find it.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "test_stray.py").write_text("# a stray\n")
            (root / "tests").mkdir()
            (root / "tests" / "test_fine.py").write_text("# a real test\n")

            self.assertEqual(
                root_test_files(root),
                ["test_stray.py"],
                "the rule does not find a test file in the root",
            )
            self.assertEqual(
                stray_test_files(root, [root / "tests"]),
                ["test_stray.py"],
                "the rule does not report a test file in the root as a stray",
            )

    def test_the_check_catches_a_test_file_outside_the_collected_dirs(self):
        """A test file in an uncollected directory is a stray too."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "somewhere").mkdir()
            (root / "somewhere" / "test_stray.py").write_text("# a stray\n")
            (root / "tests").mkdir()
            (root / "tests" / "test_fine.py").write_text("# a real test\n")

            self.assertEqual(
                stray_test_files(root, [root / "tests"]),
                ["somewhere/test_stray.py"],
                "the rule does not report a test file outside the collected "
                "directories as a stray",
            )

    def test_the_check_catches_a_test_file_under_investigate(self):
        """There is no exemption for the record of a piece of work."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = root / "investigate"
            record.mkdir()
            (record / "test_stray.py").write_text("# a stray\n")
            (root / "tests").mkdir()
            (root / "tests" / "test_fine.py").write_text("# a real test\n")

            self.assertEqual(
                stray_test_files(root, [root / "tests"]),
                ["investigate/test_stray.py"],
                "the rule exempts a test file under investigate/",
            )

    def test_the_check_allows_a_test_file_in_a_collected_dir(self):
        """A test file where pytest looks for it is not a stray."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests").mkdir()
            (root / "tests" / "test_fine.py").write_text("# a real test\n")

            self.assertEqual(
                stray_test_files(root, [root / "tests"]),
                [],
                "the rule reports a test file in a collected directory as "
                "a stray",
            )

    def test_the_check_ignores_the_virtual_environment(self):
        """The environment holds thousands of files called ``test_*``."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            venv = root / ".venv" / "lib" / "python3.12" / "site-packages"
            venv.mkdir(parents=True)
            (venv / "test_whatever.py").write_text("# not ours\n")

            self.assertEqual(
                the_test_files(root),
                [],
                "the rule walks into the virtual environment",
            )

    def test_the_check_ignores_the_self_development_clone(self):
        """The clone is a second checkout of the repository, not part of it.

        The clone is retired - the agent works in this working copy now,
        see DEVELOPMENT_RULES.md - but the folder is still on disk until
        it is removed, and it holds a whole copy of the suite.  The rule
        reads the tree of **this** repository.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clone = root / "self-development" / "tests"
            clone.mkdir(parents=True)
            (clone / "test_whatever.py").write_text("# not ours\n")
            (root / "tests").mkdir()
            (root / "tests" / "test_fine.py").write_text("# a real test\n")

            self.assertEqual(
                the_test_files(root),
                [Path("tests/test_fine.py")],
                "the rule walks into the self-development clone",
            )
            self.assertEqual(
                stray_test_files(root, [root / "tests"]),
                [],
                "the rule reports the test files of the clone as strays",
            )

    def test_this_file_does_not_fail_the_check(self):
        """The check is not tripped by its own name."""
        strays = stray_test_files(ROOT, self.collected)
        self.assertEqual(
            strays,
            [],
            "the check matches its own file",
        )


if __name__ == "__main__":
    unittest.main()
