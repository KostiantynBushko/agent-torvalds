"""
The proof that the file-logging harness catches deliberate drifts.

A check that has never failed proves nothing.  This script copies the
prototype and the harness into a temporary directory, breaks the
prototype **one drift at a time**, runs the harness against the broken
copy, and restores the file afterwards.

Every drift must make the harness fail, and it must fail on the
invariant the drift attacks.

Run it:

    self-development/.venv/bin/python \\
        self-development/investigate/logging-to-file/verify_harness_catches_regressions.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROTOTYPE = HERE / "prototype_file_logging.py"
HARNESS = HERE / "verify_logging_to_file.py"


# ---------------------------------------------------------------------------
# The drifts
# ---------------------------------------------------------------------------

# (name, invariant, the original text, the broken text)
DRIFTS: list[tuple[str, str, str, str]] = [
    (
        "D1 — the symlink points at the rotated file, not at the live one",
        "L3",
        "        target = os.path.abspath(self.baseFilename)",
        "        target = os.path.abspath(self.baseFilename + '.1')",
    ),
    (
        "D2 — the symlink is not refreshed after a rollover",
        "L3",
        "        super().doRollover()\n        self.refresh_symlink()",
        "        super().doRollover()",
    ),
    (
        "D3 — the rotation is disabled",
        "L2",
        "        max_bytes=max_bytes,",
        "        max_bytes=0,",
    ),
    (
        "D4 — the log file is truncated instead of appended to",
        "L6",
        "        stream = super()._open()",
        "        self.mode = 'w'\n        stream = super()._open()",
    ),
    (
        "D5 — a symlink that cannot be created takes the agent down",
        "L5",
        "        except (OSError, NotImplementedError):\n            return False",
        "        except (OSError, NotImplementedError):\n"
        "            if 'no-such-dir' in link:\n"
        "                raise\n"
        "            return False",
    ),
    (
        "D6 — the log file is left readable by every account",
        "L6",
        "            os.chmod(self.baseFilename, self.FILE_MODE)",
        "            pass",
    ),
    (
        "D7 — the records are swallowed and never reach the file",
        "L1",
        "        super().emit(record)",
        "        return  # drift: the record is swallowed",
    ),
]


def run_drift(name: str, invariant: str, old: str, new: str) -> bool:
    """Apply one drift, run the harness, and report whether it was caught."""
    work = Path(tempfile.mkdtemp(prefix="torvalds-log-drift-"))
    try:
        prototype = work / PROTOTYPE.name
        harness = work / HARNESS.name
        shutil.copy2(PROTOTYPE, prototype)
        shutil.copy2(HARNESS, harness)

        source = prototype.read_text(encoding="utf-8")
        if old not in source:
            print(f"[FAIL] {name}")
            print(f"       the original text is not in the prototype any more:")
            print(f"       {old!r}")
            return False

        prototype.write_text(source.replace(old, new, 1), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(harness)],
            capture_output=True,
            text=True,
            cwd=str(work),
            timeout=120,
        )
        output = result.stdout + result.stderr

        if result.returncode == 0:
            print(f"[FAIL] {name}")
            print("       the harness still passed — the drift was NOT caught")
            return False

        if invariant not in output:
            print(f"[FAIL] {name}")
            print(f"       the harness failed, but not on {invariant}")
            return False

        # Which invariants failed, for the record.
        failed = []
        for line in output.splitlines():
            if line.startswith("FAILED:"):
                failed = line.split(":", 1)[1].strip().split(", ")
        only = "only" if failed == [invariant] else "also"
        print(f"[OK  ] {name}")
        print(f"       caught by {invariant} (failed: {', '.join(failed) or 'none'}; {only} that one)")
        return True
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    print("Does the harness catch the deliberate drifts?")
    print("=" * 70)
    print()

    caught = 0
    for name, invariant, old, new in DRIFTS:
        if run_drift(name, invariant, old, new):
            caught += 1
        print()

    print(f"{caught}/{len(DRIFTS)} drifts caught")
    return 0 if caught == len(DRIFTS) else 1


if __name__ == "__main__":
    sys.exit(main())
