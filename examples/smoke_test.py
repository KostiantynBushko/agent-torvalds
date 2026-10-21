"""
End-to-end smoke test against the *real* ``shodan`` CLI.

This exercises the full stack — subprocess execution, environment
neutralisation, output capture and parsing — without needing an API key for
the commands that do not require one.

Run with::

    python examples/smoke_test.py
"""

from __future__ import annotations

import sys

from shodan_toolkit import ShodanClient
from shodan_toolkit.runner import ShodanError


def main() -> int:
    """Run the smoke test and report the outcome."""
    client = ShodanClient()
    failures = 0

    print("Shodan Toolkit — End-to-End Smoke Test")
    print("=" * 60)

    # 1. CLI availability
    if client.is_available():
        print("[PASS] shodan CLI is available")
    else:
        print("[FAIL] shodan CLI is NOT available")
        return 1

    # 2. Version
    try:
        version = client.version()
        print(f"[PASS] CLI version: {version}")
    except ShodanError as exc:
        print(f"[FAIL] could not read CLI version: {exc}")
        failures += 1

    # 3. API key presence
    if client.has_api_key():
        print(f"[PASS] API key found at {client.api_key_path()}")
    else:
        print("[SKIP] no API key configured — network commands skipped")
        print("       run: shodan-toolkit init <api-key>")

    # 4. Commands that do not need a key still exercise the plumbing.
    try:
        result = client.run_raw(["--help"], check=True)
        if "--help" in result.stdout:
            print("[PASS] subprocess execution + output capture")
        else:
            print("[FAIL] unexpected --help output")
            failures += 1
    except ShodanError as exc:
        print(f"[FAIL] subprocess execution failed: {exc}")
        failures += 1

    # 5. An authenticated command, only if a key is present.
    if client.has_api_key():
        try:
            info = client.account_info()
            print(f"[PASS] account info: {info}")
        except ShodanError as exc:
            print(f"[FAIL] account info failed: {exc}")
            failures += 1

        try:
            total = client.count("nginx")
            print(f"[PASS] count('nginx') = {total}")
        except ShodanError as exc:
            print(f"[FAIL] count failed: {exc}")
            failures += 1

        try:
            results = client.search("nginx", limit=3)
            print(f"[PASS] search('nginx') returned {len(results)} record(s)")
            for record in results:
                print(f"         {record.get('ip_str')}:{record.get('port')}")
        except ShodanError as exc:
            print(f"[FAIL] search failed: {exc}")
            failures += 1
    else:
        print("[SKIP] search/count skipped (no API key)")

    print("=" * 60)
    if failures:
        print(f"Result: {failures} failure(s)")
        return 1

    print("Result: all executed checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
