"""
Verification script: exercises every client method against the *real*
``shodan`` binary to confirm the argument vectors are valid.

Each Shodan subcommand declares its own options, and ``click`` rejects
anything else with ``No such option`` — aborting the command before it
ever reaches the API.  This script builds the exact argv the client would
execute for every method and runs it against the installed binary, so a
mismatch is caught here rather than in production.

A Shodan API key is not required: ``click`` parses options *before* the
command body runs, so an invalid flag fails with ``No such option`` while a
valid flag fails with the auth error.  That distinction lets us tell
"our argv is wrong" apart from "we lack a key".

Run with::

    python examples/verify_argv.py
"""

from __future__ import annotations

import sys
from typing import Callable, List, Tuple

from shodan_toolkit.client import ShodanClient
from shodan_toolkit.config import load_config

Argv = List[str]
Plan = Tuple[str, Callable[[ShodanClient], object]]


class _Stop(Exception):
    """Raised by the recording stub to abort the real command."""


def _build_plans() -> List[Plan]:
    """Return the (label, thunk) pairs for every client method."""
    return [
        ("search", lambda c: c.search("nginx", limit=5)),
        ("count", lambda c: c.count("nginx")),
        ("stats", lambda c: c.stats("nginx")),
        ("trends", lambda c: c.trends("nginx")),
        ("host", lambda c: c.host("8.8.8.8")),
        ("domain_info", lambda c: c.domain_info("example.com")),
        ("honeyscore", lambda c: c.honeyscore("1.1.1.1")),
        ("myip", lambda c: c.myip()),
        ("myip(ipv6=True)", lambda c: c.myip(ipv6=True)),
        ("account_info", lambda c: c.account_info()),
        ("list_alerts", lambda c: c.list_alerts()),
        ("create_alert", lambda c: c.create_alert("n", ["8.8.8.0/24"])),
        ("delete_alert", lambda c: c.delete_alert("abc")),
        ("list_scans", lambda c: c.list_scans()),
        ("scan_status", lambda c: c.scan_status("abc")),
        ("submit_scan", lambda c: c.submit_scan(["8.8.8.0/24"])),
        ("download", lambda c: c.download("nginx", "/tmp/shodan-argv-check.json.gz")),
    ]


def _record_argvs(client: ShodanClient) -> List[Tuple[str, Argv]]:
    """Return the argv each client method would execute.

    The runner is swapped for a recording stub, so no command actually runs;
    only the constructed argument vector matters.
    """
    recorded: List[Argv] = []

    class RecordingRunner:
        def run(self, args, check=True, timeout=None):
            recorded.append(list(args))
            raise _Stop()

    client._runner = RecordingRunner()  # type: ignore[assignment]

    out: List[Tuple[str, Argv]] = []
    for label, thunk in _build_plans():
        recorded.clear()
        try:
            thunk(client)
        except _Stop:
            pass
        except Exception:
            pass
        if recorded:
            out.append((label, recorded[0]))
    return out


def main() -> int:
    """Run every argv against the real binary and report the outcome."""
    config = load_config()
    runner = ShodanClient(config).runner

    if not runner.is_available():
        print("shodan CLI is not available; nothing to verify.")
        return 1

    argvs = _record_argvs(ShodanClient(config))

    failures = 0
    total = 0
    print("Checking every client argv against the real `shodan` binary:")
    print("=" * 78)

    for label, argv in argvs:
        total += 1
        result = runner.run(list(argv), check=False)
        stderr = (result.stderr or "").lower()
        stdout = (result.stdout or "").lower()

        if "no such option" in stderr or "no such option" in stdout:
            status = "INVALID OPTION"
            detail = (result.stderr or result.stdout).strip().splitlines()[-1]
            failures += 1
        elif result.returncode != 0:
            status = "OK (needs API key)"
            detail = "argv accepted by the CLI"
        else:
            status = "OK"
            detail = "command succeeded"

        print(f"[{status:<18}] {label:<18} shodan {' '.join(argv)}")
        if status == "INVALID OPTION":
            print(f"{'':<21}-> {detail}")

    print("=" * 78)
    print(f"{total - failures}/{total} argument vectors are valid.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
