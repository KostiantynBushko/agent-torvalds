"""
The rule that the private folder of the operator is never published.

The repository is public.  The home directory of the operator is
**private**, and it must never appear in the source, in the
documentation, in a script, in a fixture or in a report — not the path
of the home, and not the name of the account.

The check looks for the **shape** of a home directory, and for the home
of the machine the test runs on.  It never names a home itself: the
placeholders it accepts are the generic ones, and the home of the
machine is **computed**, never written down.

The operator stated this on 2026-10-29, after finding the home
directory in the body of a pull request.

Run with:
    pytest tests/test_no_private_paths.py -v
"""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: The shapes of a home directory.  ``/home/<account>`` is the Linux one
#: and ``/Users/<account>`` the macOS one; the Windows one is spelled
#: with backslashes, which is why it has a pattern of its own.
HOME_PATTERNS = (
    re.compile(r"/home/([A-Za-z0-9._<>-]+)"),
    re.compile(r"/Users/([A-Za-z0-9._<>-]+)"),
    re.compile(r"[A-Za-z]:\\Users\\([A-Za-z0-9._<>-]+)"),
)

#: The generic placeholders.  They are not the home of anybody: they are
#: the way a documentation writes an example.
PLACEHOLDERS = frozenset({
    "user",
    "<user>",
    "agent",
    "username",
    "name",
    "example",
    "someone",
})

#: The tracked files that are text.
TEXT_SUFFIXES = frozenset({
    ".py", ".md", ".toml", ".yml", ".yaml", ".txt", ".json",
    ".cfg", ".ini", ".sh", ".bash", ".js", ".html", ".sql",
})


class TestNothingPublishesThePrivateFolder(unittest.TestCase):
    """Nothing in the repository names the home of the operator."""

    def the_files(self):
        """The tracked files that are text, as (name, path) pairs."""
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=180,
        )
        for name in result.stdout.splitlines():
            path = ROOT / name
            if path.suffix.lower() in TEXT_SUFFIXES and path.is_file():
                yield name, path

    def the_text(self, path: Path) -> str:
        """The text of the file, or nothing when it is not text."""
        try:
            return path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return ""

    def test_no_tracked_file_carries_a_home_directory(self):
        """The shape of a home is a leak, whoever the account belongs to."""
        offenders = []
        for name, path in self.the_files():
            text = self.the_text(path)
            if not text:
                continue
            for pattern in HOME_PATTERNS:
                for match in pattern.finditer(text):
                    if match.group(1) in PLACEHOLDERS:
                        continue
                    line = text.count("\n", 0, match.start()) + 1
                    offenders.append(f"{name}:{line}  {match.group(0)}")
        self.assertEqual(
            offenders,
            [],
            "these files name a home directory:\n" + "\n".join(offenders),
        )

    def test_no_tracked_file_carries_the_home_of_this_machine(self):
        """The home of the machine the test runs on — computed, never written down."""
        home = str(Path.home())
        if not home or home in ("/", "/root", "/nonexistent"):
            self.skipTest("the home of this machine cannot be determined")

        offenders = []
        for name, path in self.the_files():
            text = self.the_text(path)
            if not text or home not in text:
                continue
            for number, line in enumerate(text.splitlines(), start=1):
                if home in line:
                    offenders.append(f"{name}:{number}  {line.strip()[:100]}")
        self.assertEqual(
            offenders,
            [],
            "these files carry the home of this machine:\n" + "\n".join(offenders),
        )

    def test_the_check_finds_a_home_when_one_is_there(self):
        """A check that has never failed proves nothing."""
        pattern = HOME_PATTERNS[0]
        self.assertIsNotNone(pattern.search("/home/somebody/.config/x.toml"))
        self.assertIsNone(pattern.search("~/.config/x.toml"))

    def test_the_placeholder_is_recognised_as_a_placeholder(self):
        """The regex matches the shape; the allowlist decides who it is."""
        match = HOME_PATTERNS[0].search("/home/user/.config/x.toml")
        self.assertIsNotNone(match)
        self.assertIn(match.group(1), PLACEHOLDERS)


if __name__ == "__main__":
    unittest.main()
