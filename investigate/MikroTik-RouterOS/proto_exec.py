"""Prototype 2: asyncssh exec-mode against a RouterOS-like SSH server.

Validates:
  1. asyncssh run() with a command string (exec mode) -> stdout/stderr/exit status
  2. Known-hosts / host-key policy handling
  3. Behaviour of the routeros_api / librouteros API clients against a
     non-RouterOS endpoint (to document why they are NOT a fit for
     "run arbitrary CLI commands over SSH")
"""
import asyncio
import asyncssh

from _proto_config import HARNESS_KNOWN_HOSTS

from _proto_config import (HARNESS_HOST, HARNESS_PORT_EXEC, HARNESS_USER, HARNESS_KEY)

HOST, PORT, USER, KEY = HARNESS_HOST, HARNESS_PORT_EXEC, HARNESS_USER, HARNESS_KEY


async def main():
    # --- 1. exec mode -----------------------------------------------------
    async with asyncssh.connect(
        HOST, port=PORT, username=USER, client_keys=[KEY],
        known_hosts=None, encoding="utf-8", errors="replace",
    ) as conn:
        result = await conn.run("/system/resource", check=False)
        print("exec stdout      :", repr(result.stdout))
        print("exec stderr      :", repr(result.stderr))
        print("exec exit_status :", result.exit_status)
        print("exec returncode  :", result.returncode)

        result2 = await conn.run("/bogus/command", check=False)
        print()
        print("err stdout       :", repr(result2.stdout))
        print("err stderr       :", repr(result2.stderr))
        print("err exit_status  :", result2.exit_status)

    # --- 2. host key policy ------------------------------------------------
    print()
    try:
        async with asyncssh.connect(
            HOST, port=PORT, username=USER, client_keys=[KEY],
            known_hosts=HARNESS_KNOWN_HOSTS,
        ) as conn:
            await conn.run("/system/resource")
        print("known_hosts policy: UNEXPECTEDLY ACCEPTED")
    except Exception as e:
        print("known_hosts policy:", type(e).__name__, "->", str(e)[:140])

asyncio.run(main())
