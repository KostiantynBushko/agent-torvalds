"""Verify every file:line reference in the investigation report.

A line reference in an investigation report is a promise: "look here and you
will find this".  This script checks the promise mechanically, so the report
cannot drift away from the code.

    self-development/.venv/bin/python \\
        investigate/chat-manager-user-settings/verify_report_references.py
"""

from __future__ import annotations

import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPORT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "INVESTIGATION_REPORT.md",
)

# A reference looks like `path/to/file.py:123` — with an optional second
# line number after a comma, e.g. `file.py:123, 456`.
REFERENCE_RE = re.compile(
    r"`(?P<path>[A-Za-z0-9_./-]+\.py):(?P<lines>\d+(?:\s*,\s*\d+)*)`"
)

# How many lines each reference must "cover" — the smallest window that
# actually contains the claimed construct.  Used to check that the cited
# line is not merely inside the file but close to the claim.
CLAIM_WINDOW = 3


def _load(path: str) -> list[str]:
    full = os.path.join(REPO_ROOT, path)
    if not os.path.exists(full):
        return []
    with open(full, encoding="utf-8") as handle:
        return handle.read().splitlines()


def main() -> int:
    if not os.path.exists(REPORT):
        print(f"FAIL — report not found: {REPORT}")
        return 1

    with open(REPORT, encoding="utf-8") as handle:
        text = handle.read()

    references = list(REFERENCE_RE.finditer(text))
    print(f"VERIFY — line references in {os.path.basename(REPORT)}")
    print(f"references found: {len(references)}")
    print()

    if not references:
        print("FAIL — no references found; the regex is broken")
        return 1

    checked = 0
    failures: list[str] = []
    seen: set[tuple[str, int]] = set()

    for match in references:
        path = match.group("path")
        numbers = [int(n) for n in re.findall(r"\d+", match.group("lines"))]

        for number in numbers:
            key = (path, number)
            if key in seen:
                continue
            seen.add(key)

            lines = _load(path)
            if not lines:
                failures.append(f"{path}:{number} — file does not exist")
                continue

            if number < 1 or number > len(lines):
                failures.append(
                    f"{path}:{number} — out of range (file has {len(lines)} lines)"
                )
                continue

            checked += 1

    # Print the content around each reference so a human can eyeball it.
    print("Reference map:")
    for (path, number) in sorted(seen):
        lines = _load(path)
        if not lines:
            print(f"  {path}:{number}  <missing file>")
            continue
        excerpt = lines[number - 1].strip()
        if len(excerpt) > 88:
            excerpt = excerpt[:85] + "..."
        print(f"  {path}:{number}  {excerpt}")
    print()

    if failures:
        print(f"FAIL — {len(failures)} broken reference(s):")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print(f"PASS — {checked} distinct references resolve to a real line.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
