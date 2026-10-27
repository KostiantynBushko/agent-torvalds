#!/usr/bin/env python3
"""Refresh the commit SHAs that the history rewrite made stale.

On 2026-10-27 the repository's history was rewritten to remove the
`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
trailer from the root commit of the shodan-toolkit subtree.  A rewrite
changes the SHA of every descendant, so the SHAs that the documentation
records — in `SELF_DEVELOPMENT_RULES.md` and in the investigation reports —
now name commits that no longer exist.

`git filter-repo` leaves the mapping behind, in `filter-repo/commit-map`:
one `old new` pair per rewritten commit.  This script reads that mapping and
substitutes every reference in the tracked text files.

**What it changes:** hexadecimal tokens that are a prefix of an old SHA
**whose replacement actually exists in the repository**.  Nothing else.

That second condition is the important one.  The rewrite changed the SHAs
of the 29 branches that carried the offending commit; the other 26 branches
kept theirs, because they never carried it.  `filter-repo` rewrote the
whole history in its scratch clone, so its commit map names a new SHA for
every commit — including the ones on the branches that were never pushed.
Substituting those would point the documentation at commits that do not
exist.  So a substitution is made only when the new SHA resolves to a
commit in the repository.

A token that matches no old SHA is left alone, and a token that matches
more than one is reported and left alone too — a guard that guesses is not
a guard.

**What it does not change:** tree hashes.  A rewrite does not change a
tree, so the tree IDs the documentation records are still correct.

Usage:
    python3 refresh_commit_shas.py --commit-map <path>            # dry run
    python3 refresh_commit_shas.py --commit-map <path> --apply

The commit map is produced by the purge:
    /tmp/agent-torvalds-claude-purge/filter-repo/commit-map
"""
from __future__ import annotations

import argparse
import collections
import os
import re
import subprocess
import sys

# A hexadecimal token that could be a SHA: 7 characters is git's shortest
# unambiguous abbreviation, 40 is a full SHA.  The look-arounds keep the
# token from being a slice of a longer hex string.
TOKEN = re.compile(rb"(?<![0-9a-fA-F])([0-9a-f]{7,40})(?![0-9a-fA-F])")

# The file types that can hold a SHA reference.  Binary files are skipped.
TEXT_SUFFIXES = (".md", ".txt", ".py", ".sh", ".yml", ".yaml", ".cfg",
                 ".ini", ".toml", ".sql", ".example")


def read_commit_map(path: str):
    """Return {old_sha: new_sha} from a filter-repo commit map."""
    mapping = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) == 2 and len(parts[0]) == 40 and len(parts[1]) == 40:
                mapping[parts[0]] = parts[1]
    return mapping


def tracked_files(repo: str):
    out = subprocess.run(
        ["git", "ls-files"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.split()
    return [f for f in out if f.endswith(TEXT_SUFFIXES)]


def commit_exists(repo: str, sha: str) -> bool:
    """Is this SHA a commit in the repository?"""
    return subprocess.run(
        ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
        cwd=repo, capture_output=True,
    ).returncode == 0


def usable_mapping(repo: str, mapping):
    """Keep only the pairs whose new SHA really exists in the repository.

    The rewrite changed the SHAs of the branches that carried the offending
    commit and left the others alone.  `filter-repo` rewrote every commit in
    its scratch clone, so its map names a new SHA for the commits of the
    branches that were never pushed — and those SHAs do not exist here.
    """
    usable, skipped = {}, []
    for old, new in mapping.items():
        if commit_exists(repo, new):
            usable[old] = new
        else:
            skipped.append((old, new))
    return usable, skipped


def plan(repo: str, mapping):
    """Work out every substitution, without touching a file.

    Returns (changes, ambiguous) where `changes` maps a file to a list of
    (old_token, new_token, count) and `ambiguous` maps a token to the number
    of places it was found.
    """
    olds = list(mapping)
    changes = collections.defaultdict(list)
    ambiguous = collections.Counter()
    seen = collections.defaultdict(set)

    for path in tracked_files(repo):
        try:
            data = open(os.path.join(repo, path), "rb").read()
        except (IsADirectoryError, FileNotFoundError):
            continue
        for match in TOKEN.finditer(data):
            token = match.group(1).decode()
            matches = [o for o in olds if o.startswith(token)]
            if len(matches) == 1:
                old = matches[0]
                new = mapping[old][: len(token)]
                if new != token:
                    seen[path].add((token, new))
            elif len(matches) > 1:
                ambiguous[token] += 1

    for path, pairs in seen.items():
        for token, new in pairs:
            count = sum(
                1 for m in TOKEN.finditer(open(os.path.join(repo, path), "rb").read())
                if m.group(1).decode() == token
            )
            changes[path].append((token, new, count))
    return changes, ambiguous


def apply_changes(repo: str, changes):
    total = 0
    for path, pairs in changes.items():
        full = os.path.join(repo, path)
        with open(full, "rb") as fh:
            data = fh.read()
        for token, new, _ in pairs:
            data = TOKEN.sub(
                lambda m, t=token, n=new: n.encode()
                if m.group(1).decode() == t else m.group(0),
                data,
            )
            total += 1
        with open(full, "wb") as fh:
            fh.write(data)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit-map", required=True,
                        help="filter-repo's commit-map file")
    parser.add_argument("--repo", default=".",
                        help="the repository to rewrite (default: .)")
    parser.add_argument("--apply", action="store_true",
                        help="write the changes (default: dry run)")
    args = parser.parse_args()

    if not os.path.exists(args.commit_map):
        sys.exit(f"missing commit map: {args.commit_map}")

    mapping = read_commit_map(args.commit_map)
    print(f"commit map: {len(mapping)} rewritten commit(s)")

    mapping, skipped = usable_mapping(args.repo, mapping)
    print(f"  {len(mapping)} of them exist in this repository and are "
          f"usable")
    print(f"  {len(skipped)} belong to branches that were not rewritten and "
          f"are left alone")

    changes, ambiguous = plan(args.repo, mapping)
    total = sum(c for pairs in changes.values() for _, _, c in pairs)
    print(f"{len(changes)} file(s), {total} reference(s) to refresh")
    for path in sorted(changes, key=lambda p: -sum(c for _, _, c in changes[p])):
        print(f"  {path}")
        for token, new, count in sorted(changes[path]):
            print(f"      {token} -> {new}  ({count})")

    if ambiguous:
        print(f"\n{len(ambiguous)} ambiguous token(s) left alone:")
        for token, count in ambiguous.items():
            print(f"      {token} ({count})")

    if not args.apply:
        print("\nDRY RUN — nothing was written.  Re-run with --apply.")
        return 0

    written = apply_changes(args.repo, changes)
    print(f"\nrefreshed {written} reference(s) in {len(changes)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
