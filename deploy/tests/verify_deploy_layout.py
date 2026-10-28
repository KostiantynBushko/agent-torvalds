#!/usr/bin/env python3
"""The layout and behaviour contract of the ``deploy/`` folder.

The deployment script used to live in ``investigate/deployment-script/``,
which is the wrong home for it: ``investigate/`` holds the *record* of a
piece of work - the report, the requirements, the plan - and the
implementations that came out of it live in their own place (the
toolkits under ``toolkits/``, the chat manager under ``chat_manager/``).
A folder that is named for what it holds is a folder somebody can find
again.

This harness is the permanent guard for that rule.  It answers two
questions:

* does the ``deploy/`` folder hold what it is supposed to hold, and
* does the script still behave the way the documentation says it does.

Every check is an explicit test, never an ``assert``: under ``python
-O`` the assert statements are removed, and a harness that reports "OK"
for a broken contract is worse than no harness at all.  The failures are
collected and reported, and the exit code is 1 when any of them fired.

Run it directly::

    python3 deploy/tests/verify_deploy_layout.py

or against another tree, which is what the drift proof does::

    python3 deploy/tests/verify_deploy_layout.py --root /tmp/mutated
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

#: The repository root, two levels up from this file:
#: <root>/deploy/tests/verify_deploy_layout.py
DEFAULT_ROOT = Path(__file__).resolve().parents[2]

#: The folder the deployment scripts live in.
DEPLOY_DIRNAME = "deploy"

#: The deployment script itself.
SCRIPT_NAME = "deploy-torvalds.sh"

#: The example environment file that ships next to it.
ENV_EXAMPLE_NAME = "deploy-torvalds.sh.example.env"

#: Where the script used to live. Nothing may point at it any more.
OLD_SCRIPT_PATH = "investigate/deployment-script/deploy-torvalds.sh"

#: The files of the harness itself. They name the old path on purpose -
#: that is what they look for - so they are not held to D9.
HARNESS_FILES = {
    "deploy/tests/verify_deploy_layout.py",
    "deploy/tests/verify_harness_catches_regressions.py",
}

#: The directories that are never scanned for stale references.
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "wiki",
    "node_modules",
    "site-packages",
}

#: The suffixes of the files that are scanned for stale references.
TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".sh",
    ".yml",
    ".yaml",
    ".toml",
    ".cfg",
    ".ini",
    ".txt",
    ".example",
    ".env",
}


# ---------------------------------------------------------------------------
# The result of a check
# ---------------------------------------------------------------------------


@dataclass
class Result:
    """The outcome of one invariant."""

    name: str
    failures: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures

    def fail(self, message: str) -> None:
        self.failures.append(message)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def read(path: Path) -> str:
    """Read a file, or return an empty string when it does not exist."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def run_script(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the deployment script and capture both streams separately.

    The streams are captured separately on purpose: the contract is that
    ``--help`` and ``--version`` are *queries* and write to stdout, while
    the deployment itself logs to stderr.
    """
    script = root / DEPLOY_DIRNAME / SCRIPT_NAME
    return subprocess.run(
        ["bash", str(script), *args],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(root),
    )


def iter_text_files(root: Path):
    """Yield every text file of the tree, skipping the noisy directories."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if path.is_symlink() and not path.exists():
                continue
            yield path


# ---------------------------------------------------------------------------
# The invariants
# ---------------------------------------------------------------------------


def check_the_folder_holds_the_script(result: Result, root: Path) -> None:
    """D1 - the script lives in deploy/ and nowhere else."""
    deployed = root / DEPLOY_DIRNAME / SCRIPT_NAME
    if not deployed.is_file():
        result.fail(f"{DEPLOY_DIRNAME}/{SCRIPT_NAME} is missing")

    deployed_env = root / DEPLOY_DIRNAME / ENV_EXAMPLE_NAME
    if not deployed_env.is_file():
        result.fail(f"{DEPLOY_DIRNAME}/{ENV_EXAMPLE_NAME} is missing")

    # Nothing may be left behind in the investigation folder.
    old = root / OLD_SCRIPT_PATH
    if old.exists():
        result.fail(f"the script is still at {OLD_SCRIPT_PATH}")

    # And no other copy may exist anywhere in the tree.
    for path in root.rglob(SCRIPT_NAME):
        if path.is_file() and path != deployed:
            result.fail(f"a second copy of the script exists: {path}")


def check_the_script_is_runnable(result: Result, root: Path) -> None:
    """D2 - it is executable, it is bash, and it parses."""
    script = root / DEPLOY_DIRNAME / SCRIPT_NAME
    if not script.is_file():
        result.fail("the script does not exist")
        return

    mode = script.stat().st_mode
    if not mode & stat.S_IXUSR:
        result.fail("the script is not executable by its owner")

    first_line = read(script).splitlines()[:1]
    if not first_line or not first_line[0].startswith("#!") or "bash" not in first_line[0]:
        result.fail(f"the shebang is not bash: {first_line}")

    parsed = subprocess.run(
        ["bash", "-n", str(script)], capture_output=True, text=True, timeout=30
    )
    if parsed.returncode != 0:
        result.fail(f"the script does not parse: {parsed.stderr.strip()}")


def check_help_is_a_query(result: Result, root: Path) -> None:
    """D3 - --help writes to stdout, exits 0 and lists the options."""
    completed = run_script(root, "--help")

    if completed.returncode != 0:
        result.fail(f"--help exited with {completed.returncode}")
    if completed.stderr.strip():
        result.fail(f"--help wrote to stderr: {completed.stderr.strip()[:120]}")
    if not completed.stdout.strip():
        result.fail("--help wrote nothing to stdout")

    for option in (
        "--non-interactive",
        "--skip-ollama",
        "--skip-pip",
        "--with-postgres",
        "--model",
        "--embedding-model",
        "--log-file",
        "--deploy-dir",
    ):
        if option not in completed.stdout:
            result.fail(f"--help does not mention {option}")


def check_version_is_a_query(result: Result, root: Path) -> None:
    """D4 - --version writes to stdout and exits 0."""
    completed = run_script(root, "--version")

    if completed.returncode != 0:
        result.fail(f"--version exited with {completed.returncode}")
    if completed.stderr.strip():
        result.fail(f"--version wrote to stderr: {completed.stderr.strip()[:120]}")
    if "v" not in completed.stdout:
        result.fail("--version printed no version")


def check_an_unknown_option_fails(result: Result, root: Path) -> None:
    """D5 - a bad flag must not be reported as a success."""
    completed = run_script(root, "--this-option-does-not-exist")

    if completed.returncode == 0:
        result.fail("an unknown option exited with 0")
    if completed.returncode != 2:
        result.fail(f"an unknown option exited with {completed.returncode}, expected 2")
    if "Unknown option" not in completed.stderr:
        result.fail("an unknown option was not reported on stderr")


def check_the_script_bootstraps_its_own_sudo(result: Result, root: Path) -> None:
    """D6 - a non-interactive run can obtain sudo by itself.

    sudo keys its cached timestamp on the terminal, so a cache created
    by the calling shell is not visible to a script.  The script has to
    establish its own - that is what makes `--non-interactive` work.
    """
    script = root / DEPLOY_DIRNAME / SCRIPT_NAME
    if not script.is_file():
        result.fail("the script does not exist")
        return

    source = read(script)
    for function in ("bootstrap_sudo", "load_sudo_password", "run_sudo"):
        if not re.search(rf"^{function}\s*\(\)\s*\{{", source, re.MULTILINE):
            result.fail(f"the script has no {function}() function")

    # run_sudo must use the bootstrap, and check_root_or_sudo must too.
    run_sudo_body = _function_body(source, "run_sudo")
    if "bootstrap_sudo" not in run_sudo_body:
        result.fail("run_sudo() does not call bootstrap_sudo()")

    check_body = _function_body(source, "check_root_or_sudo")
    if "bootstrap_sudo" not in check_body:
        result.fail("check_root_or_sudo() does not call bootstrap_sudo()")

    if "SUDO_PASSWORD_FILE" not in source:
        result.fail("the script does not support SUDO_PASSWORD_FILE")


def check_no_sudo_env_var_form(result: Result, root: Path) -> None:
    """D7 - no `sudo VAR=value cmd`.

    sudo only honours a variable set on the command line when the
    `setenv` option is set in sudoers, or when the variable survives
    `env_reset`.  Neither is guaranteed, and when the variable is
    refused sudo aborts the whole command.  `sudo env VAR=value cmd`
    always works, because env runs as root, after the environment has
    already been reset.
    """
    script = root / DEPLOY_DIRNAME / SCRIPT_NAME
    if not script.is_file():
        result.fail("the script does not exist")
        return

    # The word is matched as a command: anything that ends in "sudo" and
    # is followed by a variable assignment.  A plain "\bsudo" would not
    # match "run_sudo", because the underscore and the "s" are both word
    # characters and there is no boundary between them - and "run_sudo"
    # is the form this script actually uses.
    assignment = re.compile(r"\b\w*sudo\s+[A-Za-z_][A-Za-z0-9_]*=")

    for number, line in enumerate(read(script).splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if assignment.search(stripped):
            result.fail(
                f"line {number} uses the `sudo VAR=value` form, which the "
                f"sudoers policy may refuse: {stripped}"
            )


def check_the_environment_variables_are_the_ones_the_agent_reads(
    result: Result, root: Path
) -> None:
    """D8 - the generated .env names the variables the agent reads.

    The agent reads TORVALDS_MODEL and TORVALDS_OLLAMA_HOST.  It does
    not read TORVALDS_CHAT_MODEL or TORVALDS_OLLAMA_BASE_URL - the
    script used to write those two, so the .env it produced configured
    nothing.
    """
    script = root / DEPLOY_DIRNAME / SCRIPT_NAME
    if not script.is_file():
        result.fail("the script does not exist")
        return

    source = read(script)
    for wanted in ("TORVALDS_MODEL=", "TORVALDS_OLLAMA_HOST="):
        if wanted not in source:
            result.fail(f"the script does not write {wanted}")

    for unwanted in ("TORVALDS_CHAT_MODEL=", "TORVALDS_OLLAMA_BASE_URL="):
        if unwanted in source:
            result.fail(f"the script writes {unwanted}, which the agent does not read")


def check_nothing_points_at_the_old_path(result: Result, root: Path) -> None:
    """D9 - no document still points at the old location."""
    for path in iter_text_files(root):
        relative = path.relative_to(root).as_posix()
        if relative in HARNESS_FILES:
            continue
        if OLD_SCRIPT_PATH in read(path):
            result.fail(f"{relative} still points at {OLD_SCRIPT_PATH}")


def check_the_log_file_is_resolved_first(result: Result, root: Path) -> None:
    """D10 - the log file is made writable before anything uses it.

    The default is /var/log/torvalds-deploy.log, which only root may
    create.  Every `2>>"$LOG_FILE"` in the script is a redirection, and
    a redirection that cannot be opened means the command does not run
    at all - so an unwritable log file would have silently skipped
    every pip and apt call.
    """
    script = root / DEPLOY_DIRNAME / SCRIPT_NAME
    if not script.is_file():
        result.fail("the script does not exist")
        return

    source = read(script)
    if not re.search(r"^resolve_log_file\s*\(\)\s*\{", source, re.MULTILINE):
        result.fail("the script has no resolve_log_file() function")

    main_body = _function_body(source, "main")
    if "resolve_log_file" not in main_body:
        result.fail("main() does not call resolve_log_file()")
    elif "install_system_packages" in main_body:
        resolve_at = main_body.index("resolve_log_file")
        install_at = main_body.index("install_system_packages")
        if resolve_at > install_at:
            result.fail("resolve_log_file() runs after the packages are installed")


def check_a_query_is_not_reported_as_a_deployment(result: Result, root: Path) -> None:
    """D11 - --help does not print a deployment summary."""
    script = root / DEPLOY_DIRNAME / SCRIPT_NAME
    if not script.is_file():
        result.fail("the script does not exist")
        return

    source = read(script)
    if "DEPLOYMENT_STARTED" not in source:
        result.fail("the script has no DEPLOYMENT_STARTED guard")

    exit_body = _function_body(source, "trap_exit")
    if "DEPLOYMENT_STARTED" not in exit_body:
        result.fail("trap_exit() does not check DEPLOYMENT_STARTED")

    # And the behaviour itself: --help must not report a deployment.
    completed = run_script(root, "--help")
    if "Deployment completed" in (completed.stdout + completed.stderr):
        result.fail("--help reports a deployment summary")


# ---------------------------------------------------------------------------
# The harness
# ---------------------------------------------------------------------------

CHECKS = (
    ("D1", "the deployment script lives in deploy/ and nowhere else", check_the_folder_holds_the_script),
    ("D2", "the script is executable, is bash, and parses", check_the_script_is_runnable),
    ("D3", "--help is a query: stdout, exit 0, every option listed", check_help_is_a_query),
    ("D4", "--version is a query: stdout, exit 0", check_version_is_a_query),
    ("D5", "an unknown option fails instead of reporting success", check_an_unknown_option_fails),
    ("D6", "the script bootstraps its own sudo timestamp", check_the_script_bootstraps_its_own_sudo),
    ("D7", "no `sudo VAR=value` form, which the sudoers policy may refuse", check_no_sudo_env_var_form),
    ("D8", "the .env names the variables the agent actually reads", check_the_environment_variables_are_the_ones_the_agent_reads),
    ("D9", "no document still points at the old path", check_nothing_points_at_the_old_path),
    ("D10", "the log file is made writable before anything is redirected to it", check_the_log_file_is_resolved_first),
    ("D11", "a query is not reported as a deployment", check_a_query_is_not_reported_as_a_deployment),
)


def run_all(root: Path) -> list[Result]:
    """Run every invariant and return the results."""
    results = []
    for _name, _description, check in CHECKS:
        result = Result(_name)
        try:
            check(result, root)
        except Exception as exc:  # noqa: BLE001 - a broken check is a failure
            result.fail(f"the check itself raised: {exc!r}")
        results.append(result)
    return results


def _function_body(source: str, name: str) -> str:
    """Return the body of a shell function, as text.

    Used to assert on what a function *calls*, which is the part of a
    shell script that a regular expression over the whole file cannot
    tell apart from a comment or from another function.
    """
    match = re.search(rf"^{re.escape(name)}\s*\(\)\s*\{{", source, re.MULTILINE)
    if not match:
        return ""

    depth = 0
    start = match.end()
    for index in range(start - 1, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    return source[start:]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="the repository root to check (default: the checkout this file lives in)",
    )
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not root.is_dir():
        print(f"[FAIL] {root} is not a directory")
        return 1

    results = run_all(root)

    print(f"Deployment folder contract - {root}")
    print("=" * 72)

    failed = 0
    for result in results:
        description = next(d for _n, d, _c in CHECKS if _n == result.name)
        if result.ok:
            print(f"[PASS] {result.name}  {description}")
        else:
            failed += 1
            print(f"[FAIL] {result.name}  {description}")
            for failure in result.failures:
                print(f"         {failure}")

    print("=" * 72)
    if failed:
        print(f"FAILED - {failed} of {len(results)} invariants did not hold")
        return 1

    print(f"OK - {len(results)} invariants hold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
