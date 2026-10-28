#!/usr/bin/env python3
"""
The proof that the answer-of-a-run harness catches deliberate drifts.

A check that has never failed proves nothing.  This script copies the
``components`` package into a temporary directory, breaks it **one drift
at a time**, runs the harness against the broken copy, and throws the copy
away afterwards.

Every drift must make the harness fail, and it must fail on the invariant
the drift attacks.

Run it:

    self-development/.venv/bin/python \\
        self-development/investigate/empty-agent-response/verify_harness_catches_regressions.py
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
HARNESS = HERE / "verify_empty_response.py"


# ---------------------------------------------------------------------------
# The drifts
# ---------------------------------------------------------------------------

# (name, invariant, the file, the original text, the broken text)
DRIFTS: list[tuple[str, str, str, str, str]] = [
    (
        "D1 — the answer is read off the result again",
        "E1",
        "components/agent_answer.py",
        "    text = _answer_text(result)\n    if text.strip():\n        return text\n\n    logger.warning(\n        \"The model returned no answer — the answer section is filled with \"\n        \"what the run found instead of nothing.\"\n    )\n    return _fallback(result)",
        "    text = str(result) if not isinstance(result, dict) else result.get(\"output\", \"\")\n    if text.strip():\n        return text\n\n    return \"\"",
    ),
    (
        "D2 — the notice is not shown any more",
        "E2",
        "components/agent_answer.py",
        '    sections: List[str] = [NO_ANSWER_NOTICE]',
        "    sections: List[str] = []",
    ),
    (
        "D3 — the tool results of the run are not shown",
        "E3",
        "components/agent_answer.py",
        "    for call in _safe_getattr(result, \"tool_calls\", None) or []:",
        "    for call in []:",
    ),
    (
        "D4 — the answer is trimmed on the way out",
        "E4",
        "components/agent_answer.py",
        "    text = _answer_text(result)\n    if text.strip():\n        return text",
        "    text = _answer_text(result)\n    if text.strip():\n        return text.upper()",
    ),
    (
        "D5 — a payload that raises takes the run down",
        "E5",
        "components/agent_answer.py",
        "    try:\n        return getattr(obj, name, default)\n    except Exception:  # noqa: BLE001 — a payload must not break the run\n        return default",
        "    return getattr(obj, name, default)",
    ),
    (
        "D6 — the run is not given another turn",
        "E6",
        "components/hitl_agent.py",
        "        if attempts >= EMPTY_ANSWER_RETRIES:\n            logger.warning(",
        "        if attempts >= 0:\n            logger.warning(",
    ),
]


def run_drift(name: str, invariant: str, filename: str, old: str, new: str) -> bool:
    """Apply one drift to a copy of the code and run the harness on it."""
    work = Path(tempfile.mkdtemp(prefix="torvalds-answer-drift-"))
    try:
        # A copy of the package, so the real tree is never touched.
        shutil.copytree(
            REPO / "components",
            work / "components",
            ignore=shutil.ignore_patterns("__pycache__"),
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
            print(output[-1500:])
            return False

        failed = []
        for line in output.splitlines():
            if line.startswith("FAILED:"):
                failed = line.split(":", 1)[1].strip().split(", ")

        only = "only" if failed == [invariant] else "also"
        print(f"[OK  ] {name}")
        print(
            f"       caught by {invariant} "
            f"(failed: {', '.join(failed) or 'none'}; {only} that one)"
        )
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
