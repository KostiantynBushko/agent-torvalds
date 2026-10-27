#!/usr/bin/env python3
"""Verify that no Claude trace survives in the agent-torvalds repository.

The operator does not want a "claude Claude" contributor in the repository.
That entry is **not** made by a pull-request footer — GitHub builds it from a
``Co-Authored-By:`` trailer in a commit message, and renders it as a
contributor with ``login: "claude"`` and a display name taken from the
trailer.  A PR body never creates a contributor.

So the check has two halves, and it distinguishes three grades of finding:

The two contexts are graded differently, and the reason is the mechanism:
**GitHub parses co-author trailers in commit messages only.**  A PR body
that quotes the trailer is quoting it — it does not make anybody a
contributor.

**FAIL — in a commit message:**

* a ``Co-Authored-By:`` trailer naming Claude — this is what creates the
  contributor;
* a ``🤖 Generated with [Claude Code]`` footer.

**FAIL — in prose (a PR title, a PR body, a comment):**

* a ``🤖 Generated with [Claude Code]`` footer — the operator asked for the
  footers to be gone.

**INFO — everything else.**  A co-author trailer quoted in a PR body, and a
bare mention anywhere, create nothing.  The tooling that did the purge has
to name what it purged, so its own commits and its own pull-request body
mention it.  Those are reported and counted, but they do not fail the
check — otherwise the check would fail on its own work, and a guard that
cries wolf is no guard.

The bar the check holds: **no co-author trailer in a commit message and no
Claude Code footer anywhere.**  As of the purge, no PR title, PR body or
comment in the repository contains even a bare mention.

**PASS — nothing found.**

Usage:
    python3 verify_no_claude.py            # GitHub side + Git side
    python3 verify_no_claude.py --offline  # Git side only (no token needed)
    python3 verify_no_claude.py --clone /path/to/clone

Exit code 0 = clean, 1 = a Claude trace was found, 2 = the check could not
run (no token, no network).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

DEFAULT_REPO = "KostiantynBushko/agent-torvalds"

# The trailer that creates the contributor.  GitHub parses this spelling.
CO_AUTHOR = re.compile(r"co-authored-by:.*claude", re.IGNORECASE)

# The footer the operator asked to have removed, in either spelling.
FOOTER = re.compile(r"generated with\s*\[?\s*claude", re.IGNORECASE)

# A bare mention.  On the GitHub side it is a failure; in a commit message
# it is only a mention.
MENTION = re.compile(r"\bclaude\b", re.IGNORECASE)

API = "https://api.github.com"


def _headers() -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get(path: str):
    req = urllib.request.Request(f"{API}{path}", headers=_headers())
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def _paged(path: str):
    """Follow GitHub's pagination until the pages run out."""
    out = []
    page = 1
    while True:
        sep = "&" if "?" in path else "?"
        chunk = _get(f"{path}{sep}per_page=100&page={page}")
        if not chunk:
            return out
        out.extend(chunk)
        if len(chunk) < 100:
            return out
        page += 1


def classify(text: str | None, in_commit_message: bool = False) -> set:
    """Return the grades of finding a piece of text carries.

    `in_commit_message` decides whether a co-author trailer counts as a
    failure.  GitHub parses trailers in commit messages only, so a trailer
    quoted in a PR body is a quotation, not a co-author.
    """
    grades = set()
    if not text:
        return grades
    if FOOTER.search(text):
        grades.add("FAIL")
    elif CO_AUTHOR.search(text) and in_commit_message:
        grades.add("FAIL")
    elif CO_AUTHOR.search(text) or MENTION.search(text):
        grades.add("MENTION")
    return grades


def check_github(repo: str):
    """Return (failures, mentions) on the GitHub side."""
    failures, mentions = [], []
    prs = _paged(f"/repos/{repo}/pulls?state=all")
    for pr in prs:
        for field, label in (("title", "title"), ("body", "body")):
            grades = classify(pr.get(field))
            if "FAIL" in grades:
                failures.append(
                    f"PR #{pr['number']} {label}: {str(pr.get(field))[:200]!r}"
                )
            elif "MENTION" in grades:
                mentions.append(f"PR #{pr['number']} {label}")
    for comment in _paged(f"/repos/{repo}/issues/comments"):
        if "FAIL" in classify(comment.get("body")):
            failures.append(f"comment {comment.get('html_url')}")
        elif "MENTION" in classify(comment.get("body")):
            mentions.append(f"comment {comment.get('html_url')}")
    for comment in _paged(f"/repos/{repo}/pulls/comments"):
        if "FAIL" in classify(comment.get("body")):
            failures.append(f"review comment {comment.get('html_url')}")
        elif "MENTION" in classify(comment.get("body")):
            mentions.append(f"review comment {comment.get('html_url')}")
    for commit in _paged(f"/repos/{repo}/commits"):
        message = commit.get("commit", {}).get("message")
        grades = classify(message, in_commit_message=True)
        if "FAIL" in grades:
            failures.append(f"commit {commit.get('sha')}")
        elif "MENTION" in grades:
            mentions.append(f"commit {commit.get('sha')}")
    return failures, mentions


def check_git(repo_dir: str):
    """Return (failures, mentions) on the Git side (commit messages)."""
    failures, mentions = [], []
    shas = subprocess.run(
        ["git", "log", "--all", "--format=%H"],
        cwd=repo_dir, capture_output=True, text=True, check=True,
    ).stdout.split()
    for sha in shas:
        message = subprocess.run(
            ["git", "show", "-s", "--format=%B", sha],
            cwd=repo_dir, capture_output=True, text=True, check=True,
        ).stdout
        grades = classify(message, in_commit_message=True)
        if "FAIL" in grades:
            subject = message.strip().splitlines()[0] if message.strip() else ""
            failures.append(f"commit {sha} ({subject})")
        elif "MENTION" in grades:
            subject = message.strip().splitlines()[0] if message.strip() else ""
            mentions.append(f"commit {sha} ({subject})")
    return failures, mentions


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify no Claude trace.")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="owner/name")
    parser.add_argument("--clone", default=None,
                        help="path to the git clone (default: auto)")
    parser.add_argument("--offline", action="store_true",
                        help="skip the GitHub side")
    args = parser.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    # .../self-development/investigate/<dir>/verify_no_claude.py
    clone = args.clone or os.path.dirname(os.path.dirname(os.path.dirname(here)))
    if not os.path.isdir(os.path.join(clone, ".git")):
        clone = os.path.dirname(clone)

    ok = True

    if not args.offline:
        try:
            failures, mentions = check_github(args.repo)
        except urllib.error.HTTPError as exc:
            print(f"GitHub check FAILED: {exc} (set GITHUB_TOKEN)",
                  file=sys.stderr)
            return 2
        if failures:
            ok = False
            print(f"GitHub side: FAIL ({len(failures)} finding(s))")
            for f in failures:
                print(f"  - {f}")
        else:
            print("GitHub side: PASS (no PR title, PR body, comment or "
                  "review comment carries a Claude co-author trailer or a "
                  "Claude Code footer)")
        if mentions:
            print(f"GitHub side: {len(mentions)} item(s) merely *mention* "
                  f"Claude (no trailer, no footer — so no contributor is "
                  f"created) — informational only:")
            for m in mentions:
                print(f"  · {m}")

    failures, mentions = check_git(clone)
    if failures:
        ok = False
        print(f"Git side: FAIL ({len(failures)} commit(s) carry a Claude "
              f"co-author trailer or footer)")
        for f in failures:
            print(f"  - {f}")
    else:
        print("Git side: PASS (no commit message of any ref carries a Claude "
              f"co-author trailer or footer) [{clone}]")

    if mentions:
        print(f"Git side: {len(mentions)} commit(s) merely *mention* Claude "
              f"(no co-author trailer, so no contributor is created) — "
              f"informational only:")
        for m in mentions:
            print(f"  · {m}")

    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
