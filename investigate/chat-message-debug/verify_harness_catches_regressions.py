#!/usr/bin/env python3
"""
Prove the verification harness catches regressions.

Each drift is introduced, the harness is run, and the file is restored.
A drift that the harness does not notice is a hole in the harness.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(".").resolve()
MESSAGE = ROOT / "components" / "chat_message.py"
CONSUMER = ROOT / "components" / "event_consumer.py"
HARNESS = ROOT / "investigate" / "chat-message-debug" / "verify_chat_message.py"

BACKUP = Path("/tmp/chat_message_backup.py")
shutil.copy(MESSAGE, BACKUP)

DRIFTS = [
    (
        "I3 — the tool call in additional_kwargs is dropped",
        MESSAGE,
        """    for rendered in _legacy_tool_calls(message):
        if rendered not in block_calls:
            parts.append(rendered)
""",
        """    for rendered in []:
        if rendered not in block_calls:
            parts.append(rendered)
""",
    ),
    (
        "I1 — the prompt is logged as a repr again",
        CONSUMER,
        """        lines = to_strings(input_val)
""",
        """        lines = to_strings(input_val)
        logger.debug("EventConsumer._on_agent_input: input=%r", input_val)
""",
    ),
    (
        "I2 — only the first message is logged",
        CONSUMER,
        """            for index, line in enumerate(lines):
                logger.debug(
                    "EventConsumer._on_agent_input:   [%d] %s", index, line
                )
""",
        """            for index, line in enumerate(lines[:1]):
                logger.debug(
                    "EventConsumer._on_agent_input:   [%d] %s", index, line
                )
""",
    ),
    (
        "I4 — the state holds the repr again",
        CONSUMER,
        """            self.state.set(
                "agent_input",
                "\\n".join(lines) if lines else str(input_val),
            )
""",
        """            self.state.set("agent_input", str(input_val))
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
    shutil.copy(BACKUP, MESSAGE)

    if holes:
        print(f"FAIL — {len(holes)} hole(s) in the harness: {holes}")
        return 1
    print("PASS — every deliberate drift is caught.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
