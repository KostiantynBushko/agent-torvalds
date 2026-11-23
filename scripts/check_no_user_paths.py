#!/usr/bin/env python3
"""
The check that no user path leaves the machine.

Rule 7 of ``DEVELOPMENT_RULES.md`` says it: a path of the machine of the
operator — the home, the account, the working copy, any directory that
carries the name of the account — is private, and it must never reach
anything outside the machine.  Not the source, not a commit message, not
the body of a pull request, not an issue, not a comment.

A path is found in two ways.

**The shape.**  ``/home/<account>``, ``/Users/<account>`` and
``C:\\Users\\<account>`` are the shapes a home has.  The shape is known
everywhere, so the check works in a CI that has never seen the machine of
the operator — which is where the body of a pull request is read.

**The identity.**  The account, the home and the folders of the working
copy of the machine the check runs on.  They are **computed**, never
written down: a rule that names the private folder in order to forbid it
has already published it.

The names that only the machine knows can also be given through the
environment, in ``TORVALDS_PRIVATE_NAMES`` — a comma-separated list.  It
is how the operator teaches a CI the names a shape cannot carry.

The placeholders a documentation writes — ``/home/user/...`` — are not a
path of anybody, and are left alone.

Usage::

    python scripts/check_no_user_paths.py files
    python scripts/check_no_user_paths.py commits origin/master..HEAD
    python scripts/check_no_user_paths.py text body.md
    cat body.md | python scripts/check_no_user_paths.py text -

The whole history carries the leaks of the past, and a gate that reads it
is red before anyone writes a line of code — the same reason the test
gate has a baseline.  The gate therefore reads the commits that are
**new**: a range, not ``--all``.

Exit codes:
    0  no user path was found
    1  a user path was found — the build must not proceed
    2  the check itself could not run

Category: CI / Tooling
Retriever Keywords: user path, private, home, account, leak, pull request
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The shapes a home directory has.  ``/home/<account>`` is the Linux one,
#: ``/Users/<account>`` the macOS one; the Windows one is spelled with
#: backslashes, which is why it has a pattern of its own.
HOME_PATTERNS = (
    re.compile(r"/home/([A-Za-z0-9._<>-]+)"),
    re.compile(r"/Users/([A-Za-z0-9._<>-]+)"),
    re.compile(r"[A-Za-z]:\\Users\\([A-Za-z0-9._<>-]+)"),
)

#: The generic placeholders.  They are not the home of anybody: they are
#: the way a documentation writes an example.  ``the-operator`` is one of
#: them — it is the published form of the name of the account.
PLACEHOLDERS = frozenset({
    "user",
    "<user>",
    "<account>",
    "account",
    "agent",
    "username",
    "name",
    "example",
    "someone",
    "operator",
    "the-operator",
})

#: The accounts that belong to nobody in particular — the account of a CI
#: runner, the account of a container, the account of a placeholder.  A
#: machine that has one of them tells the check nothing about the
#: operator, so the identity check stays silent on it.
GENERIC_ACCOUNTS = frozenset(PLACEHOLDERS) | frozenset({
    "runner",
    "root",
    "nobody",
    "daemon",
    "github",
    "circleci",
    "ubuntu",
})

#: The directories that are everybody's.  A folder of the machine that
#: carries one of these names says nothing about the operator.
GENERIC_DIRECTORIES = frozenset({
    "bin", "boot", "code", "data", "dev", "dist", "doc", "docs", "downloads",
    "etc", "home", "lib", "lib32", "lib64", "media", "mnt", "opt", "proc",
    "public", "repos", "repo", "run", "sbin", "srv", "src", "sys", "tmp",
    "usr", "var", "work", "workspace",
    "documents", "desktop", "projects", "project", "build", "node_modules",
})

#: A part of a path is a name of a folder only when it looks like one.
A_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

#: The environment variable that carries the names only the machine knows.
PRIVATE_NAMES_ENV = "TORVALDS_PRIVATE_NAMES"

#: A file bigger than this is not read — a repository does not carry a
#: path in a hundred megabytes of binary.
MAX_BYTES = 4 * 1024 * 1024

#: A finding: where it was found, what it is, and the text of it.
Finding = Tuple[str, str, str]


class Identity:
    """What names the operator on this machine — computed, never written down.

    The account of the machine and the private folders of the working copy
    are **read from the machine**, never written in this file: a rule that
    names the private folder in order to forbid it has already published
    it.

    The identity is inert on a machine that belongs to nobody in
    particular — the runner of a CI, for instance — because there the
    names carry no information about the operator.
    """

    def __init__(
        self,
        home: Optional[Path] = None,
        working_copy: Optional[Path] = None,
        extra_names: Sequence[str] = (),
    ) -> None:
        self.home = home if home is not None else Path.home()
        self.working_copy = working_copy if working_copy is not None else Path.cwd()

        self.account = self.home.name if str(self.home) not in ("", "/") else ""
        # A name that is a common directory is not the name of an account:
        # "/home" is a directory, and treating it as an account would make
        # the check find "/home" in every path of a machine.
        self.private = (
            bool(self.account)
            and self.account not in GENERIC_ACCOUNTS
            and self.account not in GENERIC_DIRECTORIES
        )

        #: The names that must not leave the machine: the account of this
        #: machine, and the ones the operator gave through the
        #: environment.
        self.names: List[str] = []
        if self.private:
            self.names.append(self.account)
        for name in extra_names:
            name = name.strip()
            if (
                name
                and name not in GENERIC_ACCOUNTS
                and name not in GENERIC_DIRECTORIES
                and name not in self.names
            ):
                self.names.append(name)

        #: The private folders of the working copy — the folders of the
        #: machine that carry a name of their own.  The name of the
        #: repository itself is public, and is left out.
        self.folders: List[str] = []
        if self.private:
            for part in self.working_copy.parts:
                if not A_NAME.match(part):
                    continue
                if part in GENERIC_DIRECTORIES or part.startswith("."):
                    continue
                if part == self.account or part == self.working_copy.name:
                    continue
                if part not in self.folders:
                    self.folders.append(part)

    def path_patterns(self) -> List[Tuple[str, "re.Pattern[str]"]]:
        """The patterns that find the names of the operator inside a path."""
        patterns: List[Tuple[str, "re.Pattern[str]"]] = []
        for name in self.names:
            escaped = re.escape(name)
            patterns.append((
                "the account of this machine in a path",
                re.compile(r"(?<![\w.-])/" + escaped + r"(?![\w.-])"),
            ))
            patterns.append((
                "the account of this machine in a path",
                re.compile(r"(?<![\w.-])[A-Za-z]:\\Users\\" + escaped + r"(?![\w.-])"),
            ))
        for folder in self.folders:
            escaped = re.escape(folder)
            patterns.append((
                "a private folder of this machine in a path",
                re.compile(r"(?<![\w.-])/" + escaped + r"(?![\w.-])"),
            ))
        return patterns

    def word_patterns(self) -> List[Tuple[str, "re.Pattern[str]"]]:
        """The patterns that find the names of the operator on their own."""
        patterns: List[Tuple[str, "re.Pattern[str]"]] = []
        for name in self.names:
            escaped = re.escape(name)
            patterns.append((
                "the name of the account of this machine",
                re.compile(r"(?<![\w.-])" + escaped + r"(?![\w.-])"),
            ))
        return patterns


def identity_from_environment() -> Identity:
    """The identity of this machine, with the names of the environment."""
    raw = os.environ.get(PRIVATE_NAMES_ENV, "")
    names = [part for part in raw.split(",") if part.strip()]
    return Identity(extra_names=names)


def find_user_paths(
    text: str,
    identity: Optional[Identity] = None,
    words: bool = True,
) -> List[Finding]:
    """The user paths in the text: (kind, the path, the line it is on).

    ``words`` says whether the name of the account **on its own** counts
    as a finding.  It does: the name of the account is private even
    without a path in front of it — it is what tells a reader whose
    machine this is.
    """
    identity = identity if identity is not None else Identity()
    findings: List[Finding] = []

    for pattern in HOME_PATTERNS:
        for match in pattern.finditer(text):
            if match.group(1) in PLACEHOLDERS:
                continue
            findings.append((
                "the shape of a home",
                match.group(0),
                _line_of(text, match.start()),
            ))

    for kind, pattern in identity.path_patterns():
        for match in pattern.finditer(text):
            findings.append((kind, match.group(0), _line_of(text, match.start())))

    if words:
        for kind, pattern in identity.word_patterns():
            for match in pattern.finditer(text):
                findings.append((kind, match.group(0), _line_of(text, match.start())))

    return findings


def _line_of(text: str, offset: int) -> int:
    """The number of the line the offset is on."""
    return text.count("\n", 0, offset) + 1


def read_text(path: Path) -> str:
    """The text of the file, or nothing when it is not text."""
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    if len(data) > MAX_BYTES:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return ""


def tracked_files(root: Path = REPO_ROOT) -> List[Path]:
    """The tracked files of the repository, as absolute paths."""
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git ls-files failed: {result.stderr.strip()}")
    files: List[Path] = []
    for name in result.stdout.split("\0"):
        if not name:
            continue
        path = root / name
        if path.is_file():
            files.append(path)
    return files


def commit_messages(root: Path = REPO_ROOT, revision: str = "--all") -> List[Tuple[str, str]]:
    """The messages of the commits, as (commit, message) pairs."""
    result = subprocess.run(
        ["git", "log", "--format=%H%x1f%B%x1e", revision],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git log failed: {result.stderr.strip()}")
    pairs: List[Tuple[str, str]] = []
    for chunk in result.stdout.split("\x1e"):
        chunk = chunk.strip("\n")
        if not chunk.strip():
            continue
        commit, _, message = chunk.partition("\x1f")
        pairs.append((commit.strip(), message))
    return pairs


def check_files(
    root: Path = REPO_ROOT,
    identity: Optional[Identity] = None,
    words: bool = True,
) -> List[Finding]:
    """The user paths in the tracked files of the repository."""
    identity = identity if identity is not None else Identity()
    findings: List[Finding] = []
    for path in tracked_files(root):
        text = read_text(path)
        if not text:
            continue
        try:
            name = str(path.relative_to(root))
        except ValueError:
            name = str(path)
        for kind, found, line in find_user_paths(text, identity, words=words):
            findings.append((f"{name}:{line}", kind, found))
    return findings


def check_commits(
    root: Path = REPO_ROOT,
    revision: str = "--all",
    identity: Optional[Identity] = None,
) -> List[Finding]:
    """The user paths in the messages of the commits."""
    identity = identity if identity is not None else Identity()
    findings: List[Finding] = []
    for commit, message in commit_messages(root, revision):
        for kind, found, line in find_user_paths(message, identity, words=True):
            findings.append((f"{commit[:12]}:{line}", kind, found))
    return findings


def check_texts(
    texts: Sequence[Tuple[str, str]],
    identity: Optional[Identity] = None,
) -> List[Finding]:
    """The user paths in free text — a pull request body, an issue, a comment."""
    identity = identity if identity is not None else Identity()
    findings: List[Finding] = []
    for name, text in texts:
        for kind, found, line in find_user_paths(text, identity, words=True):
            findings.append((f"{name}:{line}", kind, found))
    return findings


def report(findings: Sequence[Finding], stream=sys.stderr) -> None:
    """The findings, written where the operator reads them."""
    if not findings:
        return
    print("a user path of the machine must not leave it:", file=stream)
    for where, kind, found in findings:
        print(f"  {where}  {kind}: {found}", file=stream)
    print(
        f"{len(findings)} finding(s).  Write the path the way a "
        f"documentation writes it: ~, /home/<user>, <user>@example.com.",
        file=stream,
    )


def _text_arguments(paths: Sequence[str]) -> List[Tuple[str, str]]:
    """The (name, text) pairs of the files given, or of the standard input."""
    if not paths or list(paths) == ["-"]:
        return [("stdin", sys.stdin.read())]
    pairs: List[Tuple[str, str]] = []
    for name in paths:
        path = Path(name)
        pairs.append((name, read_text(path)))
    return pairs


def main(argv: Optional[Sequence[str]] = None) -> int:
    """The command line of the check."""
    parser = argparse.ArgumentParser(
        description="Fail when a user path of this machine is about to leave it.",
    )
    sub = parser.add_subparsers(dest="scope", required=True)

    sub.add_parser("files", help="the tracked files of the repository")
    commits = sub.add_parser("commits", help="the messages of the commits")
    commits.add_argument(
        "revision",
        nargs="?",
        default="--all",
        help="the commits to read — a range, or --all for the whole history",
    )
    text = sub.add_parser("text", help="free text: a pull request body, an issue")
    text.add_argument("paths", nargs="*", help="the files to read; - is the standard input")

    args = parser.parse_args(argv)
    identity = identity_from_environment()

    try:
        if args.scope == "files":
            findings = check_files(REPO_ROOT, identity)
        elif args.scope == "commits":
            findings = check_commits(REPO_ROOT, args.revision, identity)
        else:
            findings = check_texts(_text_arguments(args.paths), identity)
    except Exception as error:  # noqa: BLE001 — the check reports and stops
        print(f"the check could not run: {error}", file=sys.stderr)
        return 2

    if findings:
        report(findings)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
