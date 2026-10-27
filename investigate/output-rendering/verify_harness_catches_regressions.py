"""
The proof that the answer-rendering harness catches deliberate drifts.

A check that has never failed proves nothing.  This script copies the
``components`` package into a temporary directory, breaks it **one
drift at a time**, runs the harness against the broken copy, and throws
the copy away afterwards.

Every drift must make the harness fail, and it must fail on the
invariant the drift attacks.

Run it:

    self-development/.venv/bin/python \\
        self-development/investigate/output-rendering/verify_harness_catches_regressions.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
HARNESS = HERE / "verify_output_rendering.py"


# ---------------------------------------------------------------------------
# The drifts
# ---------------------------------------------------------------------------

# (name, invariant, the file, the original text, the broken text)
DRIFTS: list[tuple[str, str, str, str, str]] = [
    (
        "D1 — the handler reads the field the framework does not have again",
        "O1",
        "components/event_consumer.py",
        '        answer = to_output_string(event)\n        if answer:',
        '        answer = to_output_string(getattr(event, "output", None))\n        if answer:',
    ),
    (
        "D2 — the stop event logs the repr of the model again",
        "O5",
        "components/event_consumer.py",
        "        answer = to_output_string(result)\n        if answer:",
        "        answer = to_output_string(None)\n        if answer:",
    ),
    (
        "D3 — the tool calls of the answer are not rendered",
        "O2",
        "components/chat_message.py",
        "    for call in _safe_getattr(output, \"tool_calls\", None) or []:",
        "    for call in []:",
    ),
    (
        "D4 — the structured response is not rendered",
        "O3",
        "components/chat_message.py",
        '    structured = _safe_getattr(output, "structured_response", None)',
        "    structured = None",
    ),
    (
        "D5 — the retry messages are not rendered",
        "O4",
        "components/chat_message.py",
        '    for index, message in enumerate(_safe_getattr(output, "retry_messages", None) or []):',
        "    for index, message in enumerate([]):",
    ),
    (
        "D6 — a payload that raises is not survivable any more",
        "O6",
        "components/chat_message.py",
        "    try:\n        return getattr(obj, name, default)\n    except Exception:  # noqa: BLE001 — a payload must not break the log\n        return default",
        "    return getattr(obj, name, default)",
    ),
]


def run_drift(name: str, invariant: str, filename: str, old: str, new: str) -> bool:
    """Apply one drift to a copy of the code and run the harness on it."""
    work = Path(tempfile.mkdtemp(prefix="torvalds-output-drift-"))
    try:
        # A copy of the package, so the real tree is never touched.
        shutil.copytree(
            REPO / "components", work / "components", ignore=shutil.ignore_patterns("__pycache__")
        )
        shutil.copy2(HARNESS, work / HARNESS.name)

        target = work / filename
        source = target.read_text(encoding="utf-8")
        if old not in source:
            print(f"[FAIL] {name}")
            print(f"       the original text is not in {filename} any more:")
            print(f"       {old!r}")
            return False

        target.write_text(source.replace(old, new, 1), encoding="utf-8")

        env = dict(os.environ)
        env["TORVALDS_MODULE_ROOT"] = str(work)
        env["PYTHONPATH"] = str(work)

        result = subprocess.run(
            [sys.executable, str(work / HARNESS.name)],
            capture_output=True,
            text=True,
            cwd=str(work),
            env=env,
            timeout=180,
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
    for name, invariant, filename, old, new in DRIFTS:
        if run_drift(name, invariant, filename, old, new):
            caught += 1
        print()

    print(f"{caught}/{len(DRIFTS)} drifts caught")
    return 0 if caught == len(DRIFTS) else 1


if __name__ == "__main__":
    sys.exit(main())
