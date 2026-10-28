#!/usr/bin/env python3
"""The proof that the deployment folder's harness catches deliberate drifts.

A harness that has never failed proves nothing.  This script breaks the
contract on purpose, eleven times - once for every invariant - and
shows that the harness notices each one.

The breakages are made in a *copy* of the repository, never in the
checkout: the real tree is never touched.

Run it directly::

    python3 deploy/tests/verify_harness_catches_regressions.py
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

#: The repository root, two levels up from this file.
REPO_ROOT = Path(__file__).resolve().parents[2]

#: The harness under test.
HARNESS = Path(__file__).resolve().with_name("verify_deploy_layout.py")

#: The paths that are not copied into the scratch tree.
IGNORED = shutil.ignore_patterns(
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "wiki",
    "node_modules",
    "site-packages",
    "*.pyc",
)

#: The script, relative to the repository root.
SCRIPT_REL = Path("deploy") / "deploy-torvalds.sh"


# ---------------------------------------------------------------------------
# The drifts
# ---------------------------------------------------------------------------


@dataclass
class Drift:
    """One deliberate breakage of the contract."""

    name: str
    invariant: str
    description: str
    apply: object


def _script(root: Path) -> Path:
    return root / SCRIPT_REL


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def drift_the_script_leaves_the_folder(root: Path) -> None:
    """Move the script back into the investigation folder."""
    script = _script(root)
    old = root / "investigate" / "deployment-script" / SCRIPT_REL.name
    old.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(script), str(old))


def drift_the_script_loses_its_executable_bit(root: Path) -> None:
    """Make the script unreadable as a program."""
    os.chmod(_script(root), 0o644)


def drift_the_script_stops_parsing(root: Path) -> None:
    """Introduce a syntax error."""
    path = _script(root)
    _write(path, _read(path) + "\nif then fi\n")


def drift_help_goes_back_to_stderr(root: Path) -> None:
    """Send --help back to stderr."""
    path = _script(root)
    text = _read(path)
    text = text.replace(
        '    local code="${1:-0}"\n    cat <<EOF',
        '    local code="${1:-0}"\n    cat >&2 <<EOF',
        1,
    )
    _write(path, text)


def drift_an_unknown_option_succeeds(root: Path) -> None:
    """Make a bad flag exit 0 again."""
    path = _script(root)
    text = _read(path)
    text = text.replace("                print_help 2\n", "                print_help 0\n", 1)
    _write(path, text)


def drift_sudo_stops_bootstrapping(root: Path) -> None:
    """Remove the bootstrap from run_sudo."""
    path = _script(root)
    text = _read(path)
    text = text.replace(
        """    if ! sudo -n true 2>/dev/null; then
        bootstrap_sudo || true
    fi
""",
        "",
        1,
    )
    _write(path, text)


def drift_the_sudo_env_var_form_returns(root: Path) -> None:
    """Use the `sudo VAR=value` form again."""
    path = _script(root)
    text = _read(path)
    text = text.replace(
        "run_sudo env DEBIAN_FRONTEND=noninteractive apt-get install",
        "run_sudo DEBIAN_FRONTEND=noninteractive apt-get install",
    )
    _write(path, text)


def drift_the_env_names_the_wrong_variable(root: Path) -> None:
    """Write the variable the agent does not read."""
    path = _script(root)
    text = _read(path)
    text = text.replace("TORVALDS_MODEL=${CHAT_MODEL}", "TORVALDS_CHAT_MODEL=${CHAT_MODEL}", 1)
    _write(path, text)


def drift_a_document_points_at_the_old_path(root: Path) -> None:
    """Put a stale reference back into a document."""
    path = root / "DEPLOYMENT.md"
    text = _read(path)
    _write(
        path,
        text
        + "\n<!-- stale -->\n"
        + "Run `investigate/deployment-script/deploy-torvalds.sh` to deploy.\n",
    )


def drift_the_log_file_is_resolved_too_late(root: Path) -> None:
    """Resolve the log file after the packages are installed."""
    path = _script(root)
    text = _read(path)
    text = text.replace(
        """    # Before anything is logged, and before anything is redirected to
    # the log file.
    resolve_log_file

""",
        "",
        1,
    )
    text = text.replace(
        """    # The interpreter the packages just installed - this is the one the
    # virtual environment is built with.
    resolve_python3
""",
        """    # The interpreter the packages just installed - this is the one the
    # virtual environment is built with.
    resolve_python3

    # Too late: everything above was already redirected to a log file
    # that may not exist.
    resolve_log_file
""",
        1,
    )
    _write(path, text)


def drift_the_deployment_started_guard_is_removed(root: Path) -> None:
    """Let a query report a deployment."""
    path = _script(root)
    text = _read(path)
    text = text.replace(
        """    if [[ "$DEPLOYMENT_STARTED" != "true" ]]; then
        return 0
    fi

""",
        "",
        1,
    )
    _write(path, text)


DRIFTS = [
    Drift(
        "the script leaves the deploy/ folder",
        "D1",
        "the script is moved back into investigate/deployment-script/",
        drift_the_script_leaves_the_folder,
    ),
    Drift(
        "the script loses its executable bit",
        "D2",
        "chmod 644 on the script",
        drift_the_script_loses_its_executable_bit,
    ),
    Drift(
        "the script stops parsing",
        "D2",
        "a syntax error is introduced",
        drift_the_script_stops_parsing,
    ),
    Drift(
        "--help goes back to stderr",
        "D3",
        "the help output is redirected to stderr",
        drift_help_goes_back_to_stderr,
    ),
    Drift(
        "an unknown option succeeds",
        "D5",
        "the unknown-option branch exits 0",
        drift_an_unknown_option_succeeds,
    ),
    Drift(
        "sudo stops bootstrapping",
        "D6",
        "run_sudo() no longer calls bootstrap_sudo()",
        drift_sudo_stops_bootstrapping,
    ),
    Drift(
        "the sudo VAR=value form returns",
        "D7",
        "`sudo env DEBIAN_FRONTEND=...` becomes `sudo DEBIAN_FRONTEND=...`",
        drift_the_sudo_env_var_form_returns,
    ),
    Drift(
        "the .env names the wrong variable",
        "D8",
        "TORVALDS_MODEL becomes TORVALDS_CHAT_MODEL",
        drift_the_env_names_the_wrong_variable,
    ),
    Drift(
        "a document points at the old path",
        "D9",
        "a stale reference is put back into DEPLOYMENT.md",
        drift_a_document_points_at_the_old_path,
    ),
    Drift(
        "the log file is resolved too late",
        "D10",
        "resolve_log_file() moves after the package installation",
        drift_the_log_file_is_resolved_too_late,
    ),
    Drift(
        "the deployment-started guard is removed",
        "D11",
        "trap_exit() no longer checks DEPLOYMENT_STARTED",
        drift_the_deployment_started_guard_is_removed,
    ),
]


# ---------------------------------------------------------------------------
# The proof
# ---------------------------------------------------------------------------


def _run_harness(root: Path) -> tuple[int, str]:
    """Run the harness against a tree and return (exit code, output)."""
    completed = subprocess.run(
        [sys.executable, str(root / HARNESS.relative_to(REPO_ROOT)), "--root", str(root)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    return completed.returncode, completed.stdout + completed.stderr


def _failed_invariants(output: str) -> set[str]:
    """The invariants the harness reported as failed."""
    return set(re.findall(r"^\[FAIL\] (D\d+)", output, re.MULTILINE))


def main() -> int:
    print("The drift proof - every deliberate breakage, caught")
    print("=" * 72)
    print(f"Repository: {REPO_ROOT}")
    print(f"Drifts:     {len(DRIFTS)}")
    print()

    caught = 0
    missed: list[Drift] = []

    for index, drift in enumerate(DRIFTS, start=1):
        with tempfile.TemporaryDirectory(prefix="deploy-drift-") as tmp:
            root = Path(tmp) / "tree"
            shutil.copytree(REPO_ROOT, root, ignore=IGNORED)

            try:
                drift.apply(root)
            except Exception as exc:  # noqa: BLE001
                print(f"[FAIL] {drift.name}: the drift itself raised: {exc!r}")
                missed.append(drift)
                continue

            code, output = _run_harness(root)
            failed = _failed_invariants(output)

            if code != 0 and drift.invariant in failed:
                caught += 1
                others = sorted(failed - {drift.invariant})
                extra = f" (and {', '.join(others)})" if others else ""
                print(f"[PASS] {drift.invariant} caught: {drift.name}{extra}")
            else:
                missed.append(drift)
                print(f"[FAIL] {drift.invariant} NOT caught: {drift.name}")
                print(f"         the harness exited with {code}")
                for line in output.splitlines()[:12]:
                    print(f"         {line}")

    print("=" * 72)
    if missed:
        print(f"FAILED - {len(missed)} of {len(DRIFTS)} drifts were not caught")
        for drift in missed:
            print(f"  - {drift.invariant}: {drift.name}")
        return 1

    print(f"OK - {caught} of {len(DRIFTS)} deliberate drifts are caught")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
