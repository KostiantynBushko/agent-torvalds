#!/usr/bin/env python3
"""
The CI test gate — a ratchet on the known test failures.

The suite does not pass yet: it carries a set of known failures (the git
toolkit against the current pygit2 API, the math toolkit's error
contracts, the runtime-toggle command parsing, …).  A plain ``pytest`` run
therefore always exits non-zero, which would make a CI workflow useless —
it would be red before anyone wrote a line of code.

This gate turns that into a useful signal.  It runs pytest, compares the
failures with a committed baseline, and fails **only when a failure
appears that is not in the baseline**.  A new regression breaks the build;
the known failures do not.  Every time a known failure is fixed, the gate
reports it, and the baseline is tightened with ``--write-baseline``.

Usage::

    python scripts/ci_test_gate.py                    # run the gate
    python scripts/ci_test_gate.py --write-baseline   # regenerate the baseline
    python scripts/ci_test_gate.py -k hitl            # only the HITL tests

Exit codes:
    0  no new failures — the build may proceed
    1  a new failure appeared — the build must not proceed
    2  the gate itself could not run

Category: CI / Tooling
Retriever Keywords: ci, gate, pytest, baseline, ratchet, workflow
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO_ROOT / "tests" / "ci_baseline.txt"

#: The default pytest arguments — the same ones the project uses locally.
DEFAULT_PYTEST_ARGS = ("-q", "--tb=short", "-p", "no:cacheprovider")


class _Collector:
    """Collects the node id of every failing test.

    A plugin is used instead of parsing pytest's output: the summary text
    is not a stable interface, the report objects are.
    """

    def __init__(self) -> None:
        self.failures: List[str] = []

    def pytest_runtest_logreport(self, report) -> None:
        if report.failed:
            self.failures.append(report.nodeid)

    def pytest_collectreport(self, report) -> None:
        # A collection error (a test module that cannot even be imported)
        # is a failure of the build as well.
        if report.failed:
            self.failures.append(report.nodeid)


def read_baseline(path: Path = BASELINE_PATH) -> Set[str]:
    """Return the known failures recorded in *path*."""
    if not path.exists():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def write_baseline(failures: Sequence[str], path: Path = BASELINE_PATH) -> None:
    """Write *failures* to *path* as the new baseline."""
    header = (
        "# The known test failures — the CI gate (scripts/ci_test_gate.py)\n"
        "# fails the build when a failure appears that is NOT listed here.\n"
        "#\n"
        "# Regenerate with:\n"
        "#     python scripts/ci_test_gate.py --write-baseline\n"
        "#\n"
        "# One node id per line.  Remove the lines whose tests have been\n"
        "# fixed — the gate reports them as \"fixed\" and the baseline can be\n"
        "# tightened.\n"
    )
    body = "\n".join(sorted(failures))
    path.write_text(f"{header}\n{body}\n", encoding="utf-8")
    print(f"Baseline written: {len(failures)} known failure(s) -> {path}")


def collect_failures(args: Sequence[str]) -> Tuple[Set[str], int]:
    """Run pytest and return the failing node ids and pytest's exit code."""
    try:
        import pytest
    except ImportError:  # pragma: no cover - the gate cannot run at all
        print(
            "pytest is not installed — the gate cannot run.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    collector = _Collector()
    exit_code = int(pytest.main([*args], plugins=[collector]))
    return set(collector.failures), exit_code


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail the build when a test failure appears that is not "
        "in the known-failure baseline."
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="regenerate the baseline from the current run and exit",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=BASELINE_PATH,
        help=f"the baseline file (default: {BASELINE_PATH.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/ci-gate-failures.txt"),
        help="where the failure list of this run is written",
    )
    # Everything the gate does not know is passed on to pytest, so that
    # "ci_test_gate.py -k hitl" does the obvious thing.
    options, pytest_args = parser.parse_known_args(argv)

    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]
    if not pytest_args:
        pytest_args = list(DEFAULT_PYTEST_ARGS)

    print("=" * 78)
    print("CI TEST GATE — a new failure breaks the build, a known one does not")
    print("=" * 78)
    print(f"pytest      : {' '.join(pytest_args)}")
    print(f"baseline    : {options.baseline}")
    print()

    failures, _exit_code = collect_failures(pytest_args)
    baseline = read_baseline(options.baseline)

    if options.write_baseline:
        write_baseline(sorted(failures), options.baseline)
        return 0

    new_failures = failures - baseline
    fixed = baseline - failures

    # The failure list is written out so that a CI run can upload it as an
    # artifact — it is the first thing anyone wants to see when the build
    # is red.
    try:
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(
            "\n".join(sorted(failures)) + "\n", encoding="utf-8"
        )
        print(f"failure list written to {options.output}")
    except OSError as exc:  # pragma: no cover - the gate must not fail here
        print(f"could not write the failure list: {exc}", file=sys.stderr)

    print()
    print("=" * 78)
    print("CI TEST GATE — result")
    print("=" * 78)
    print(f"known failures in the baseline : {len(baseline)}")
    print(f"failures in this run            : {len(failures)}")
    print(f"new failures                    : {len(new_failures)}")
    print(f"fixed since the baseline        : {len(fixed)}")

    if fixed:
        print()
        print("Fixed — these no longer fail, so the baseline can be tightened:")
        for nodeid in sorted(fixed):
            print(f"  - {nodeid}")
        print()
        print("  Run: python scripts/ci_test_gate.py --write-baseline")

    if new_failures:
        print()
        print("NEW FAILURES — the build must not proceed:")
        for nodeid in sorted(new_failures):
            print(f"  ! {nodeid}")
        print()
        print(
            "  Either fix them, or — if they are known and intended — record\n"
            "  them with: python scripts/ci_test_gate.py --write-baseline"
        )
        print("=" * 78)
        return 1

    print()
    print("No new failures. The build may proceed.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
