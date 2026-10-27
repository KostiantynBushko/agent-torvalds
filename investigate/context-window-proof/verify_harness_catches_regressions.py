#!/usr/bin/env python3
"""
Prove the verification harness catches regressions.

Each drift is introduced, the harness is run, and the file is restored.
A drift that the harness does not notice is a hole in the harness.

The harness talks to a live Ollama server, so this script needs one:

    .venv/bin/python investigate/context-window-proof/verify_harness_catches_regressions.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "components" / "ollama_config.py"
HARNESS = ROOT / "investigate" / "context-window-proof" / "verify_context_window.py"

BACKUP = Path("/tmp/ollama_config_backup.py")
shutil.copy(CONFIG, BACKUP)

DRIFTS = [
    (
        "P1/P2 — the server's probes are dropped and the advertised "
        "maximum is reported",
        CONFIG,
        """    for probe, source in (
        (_context_length_from_running_model, SOURCE_RUNNING_MODEL),
        (_context_length_from_modelfile, SOURCE_MODELFILE),
    ):
""",
        """    for probe, source in (
    ):
""",
    ),
    (
        "P3 — the log does not carry the size",
        CONFIG,
        """    logger.info("Context window: %d tokens — %s", length, source)
""",
        """    logger.info("Context window: unknown — %s", source)
""",
    ),
    (
        "P3 — the log does not name the source",
        CONFIG,
        """    logger.info("Context window: %d tokens — %s", length, source)
""",
        """    logger.info("Context window: %d tokens", length)
""",
    ),
    (
        "P4 — the number is hardcoded instead of read",
        CONFIG,
        """        length = int(llm.metadata.context_window)
        if length > 0:
            return length, SOURCE_MODEL_MAXIMUM
""",
        """        length = int(llm.metadata.context_window)
        if length > 0:
            return 8192, SOURCE_MODEL_MAXIMUM
""",
    ),
]


def run_harness() -> tuple:
    result = subprocess.run(
        [str(ROOT / ".venv" / "bin" / "python"), str(HARNESS)],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout


def main() -> int:
    print("Proving the harness fails when the behaviour drifts.")
    print("=" * 72)

    code, out = run_harness()
    if code != 0:
        print("The harness does not pass on the clean tree — fixing that first.")
        print(out)
        print("stdout of the clean run:")
        print(out)
        return 2
    print("  [OK] the harness passes on the clean tree")
    print("-" * 72)

    holes = []
    for name, path, old, new in DRIFTS:
        text = path.read_text()
        if text.count(old) != 1:
            print(f"  [SKIP] {name}: the anchor is not unique")
            holes.append(name)
            continue
        path.write_text(text.replace(old, new))
        try:
            code, out = run_harness()
        finally:
            path.write_text(text)

        if code == 0:
            print(f"  [HOLE] {name}: the harness still passes")
            holes.append(name)
        else:
            failed = [
                line.strip()
                for line in out.splitlines()
                if line.strip().startswith("[FAIL]")
            ]
            print(f"  [OK]   {name}: caught ({len(failed)} invariant(s))")

    print("=" * 72)
    shutil.copy(BACKUP, CONFIG)

    if holes:
        print(f"FAIL — {len(holes)} hole(s) in the harness: {holes}")
        return 1
    print("PASS — every deliberate drift is caught.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
