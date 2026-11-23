#!/usr/bin/env python3
"""
The probe of the exposure of the user paths.

It answers three questions.

**1. Where can a path of the machine leave?**  The surfaces are not the
same: a file of the repository is read by the test gate, while the body
of a pull request, the body of an issue, the body of a comment and the
answer the agent gives to the operator are not files at all — they are
the text that leaves the machine.

**2. What does the check catch?**  The checker is run against a body
that leaks and against a body that is written the generic way.

**3. What is already out there?**  The history is read, and the paths it
carries are counted.

The probe writes **no path of the machine** into its own output: the
examples are built at runtime, from the machine itself, and everything
that is printed is masked — the account becomes ``<account>``, the home
becomes ``~``.  A probe that leaks what it investigates proves nothing.

Run with:
    python investigate/user-path-exposure/probe_user_paths.py

Category: Investigation / Tooling
Retriever Keywords: user path, privacy, probe, exposure, history
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = ROOT / "scripts" / "check_no_user_paths.py"


def load_checker():
    """The checker script, loaded by its path."""
    spec = importlib.util.spec_from_file_location("check_no_user_paths", CHECKER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = load_checker()


def git(*arguments: str) -> str:
    """The output of a git command, or nothing when it fails."""
    result = subprocess.run(
        ["git", *arguments],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def mask(text: str, identity) -> str:
    """The text with the names of the machine taken out of it."""
    masked = text
    for name in identity.names:
        masked = masked.replace(name, "<account>")
    if identity.home and str(identity.home) not in ("", "/"):
        masked = masked.replace(str(identity.home), "~")
    return masked


def the_surfaces() -> List[Tuple[str, str, str]]:
    """The surfaces a path can leave through, with a leaking and a clean text.

    The texts are built at runtime: the probe carries no path of the
    machine in its own source.
    """
    identity = checker.Identity()
    home = str(identity.home)
    folder = identity.folders[0] if identity.folders else "<folder>"

    leaking = (
        f"The fix lives in {home}/{folder}/the-project.\n"
        f"The configuration is in {home}/.config/torvalds/config.toml.\n"
    )
    clean = (
        "The fix lives in ~/the-project.\n"
        "The configuration is in /home/<user>/.config/torvalds/config.toml.\n"
    )
    return [
        ("a file of the repository", leaking, clean),
        ("the message of a commit", leaking, clean),
        ("the body of a pull request", leaking, clean),
        ("the body of an issue", leaking, clean),
        ("the body of a comment", leaking, clean),
        ("the answer of the agent", leaking, clean),
    ]


def what_the_check_catches(identity) -> None:
    """The result of the check on every surface, leaking and clean."""
    print("2. What the check catches")
    print("-" * 72)
    for name, leaking, clean in the_surfaces():
        found_leaking = checker.find_user_paths(leaking, identity)
        found_clean = checker.find_user_paths(clean, identity)
        verdict_leaking = "CAUGHT" if found_leaking else "MISSED"
        verdict_clean = "CAUGHT" if found_clean else "clean"
        print(f"  {name:<32} leaking: {verdict_leaking:<7} clean: {verdict_clean}")
        for kind, found, _ in found_leaking:
            print(f"      {kind}: {mask(found, identity)}")
    print()


def what_is_already_there(identity) -> None:
    """The audit of the history: the paths that are already published."""
    print("3. What is already out there")
    print("-" * 72)
    if not identity.names:
        print("  the machine carries no name that identifies the operator — nothing to audit")
        print()
        return

    account = identity.names[0]
    commits = git("rev-list", "--all").split()
    carrying: List[str] = []
    if commits:
        output = git("grep", "-l", "-I", account, *commits)
        carrying = sorted({line.split(":", 1)[0] for line in output.splitlines() if line})

    messages = git("log", "--all", "--format=%H%x1f%B%x1e")
    dirty_messages = [
        chunk.split("\x1f", 1)[0]
        for chunk in messages.split("\x1e")
        if account in chunk
    ]

    print(f"  commits of the history                  : {len(commits)}")
    print(f"  commits whose tree carries the name     : {len(carrying)}")
    print(f"  commit messages that carry the name     : {len(dirty_messages)}")

    blobs = git("log", "--all", "-p")
    shapes = sorted({
        line.replace(account, "<account>").strip()
        for line in blobs.splitlines()
        if account in line
    })
    if shapes:
        print("  the shapes that were published:")
        for shape in shapes[:12]:
            print(f"      {mask(shape, identity)[:96]}")
        if len(shapes) > 12:
            print(f"      ... and {len(shapes) - 12} more")
    print()


def main() -> int:
    """The probe."""
    identity = checker.Identity()

    print("The exposure of the user paths")
    print("=" * 72)
    print("  the machine is read, not written: the account is computed at runtime")
    print(f"  the check reads: {CHECKER_PATH.relative_to(ROOT)}")
    print()

    print("1. Where a path can leave")
    print("-" * 72)
    for name, _, _ in the_surfaces():
        print(f"  {name}")
    print()

    what_the_check_catches(identity)
    what_is_already_there(identity)

    print("The probe writes no path of the machine: everything above is masked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
