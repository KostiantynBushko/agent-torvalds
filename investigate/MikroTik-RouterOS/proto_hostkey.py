"""
Prototype: host-key policy matrix for the MikroTik RouterOS toolkit.

Validates investigation hypothesis V7/V8:
  - strict known_hosts (empty file)  -> must REJECT
  - known_hosts with the correct key -> must ACCEPT
  - known_hosts=None                -> accepts (insecure; opt-in only)
  - TOFU callable (host, addr, port) -> accepts and can be persisted
  - TOFU returning a wrong key       -> must REJECT

The RouterOS SSH server auto-generates its host key on first connection and the
operator has no pre-seeded known_hosts, so TOFU is the practical default.

Usage (requires the local SSH harness on port 2223):
    python proto_hostkey.py
"""
import asyncio
import asyncssh

from _proto_config import (HARNESS_HOST, HARNESS_PORT_EXEC, HARNESS_USER, HARNESS_KEY,
                        HARNESS_KNOWN_HOSTS, HARNESS_KNOWN_HOSTS_OK, HARNESS_HOSTKEY_PUB)

HOST, PORT, USER, KEY = HARNESS_HOST, HARNESS_PORT_EXEC, HARNESS_USER, HARNESS_KEY


async def attempt(label: str, **kwargs) -> None:
    """Try to connect + run a command, reporting accept/reject and the reason."""
    try:
        async with asyncssh.connect(
            HOST, port=PORT, username=USER, client_keys=[KEY],
            encoding="utf-8", **kwargs
        ) as conn:
            await conn.run("/system/resource", check=False)
        print(f"{label:42} -> ACCEPTED")
    except Exception as exc:  # noqa: BLE001 - we want to report every failure mode
        print(f"{label:42} -> {type(exc).__name__}: {str(exc)[:90]}")


async def main() -> None:
    # 1. Strict policy: empty known_hosts file -> the key is not trusted
    await attempt("known_hosts=<empty file>", known_hosts=HARNESS_KNOWN_HOSTS)

    # 2. Strict policy: file containing the correct key -> accepted
    await attempt("known_hosts=<correct key>", known_hosts=HARNESS_KNOWN_HOSTS_OK)

    # 3. No verification at all (insecure, must be opt-in)
    await attempt("known_hosts=None (no verify)", known_hosts=None)

    # 4. TOFU: the callable receives (host, addr, port) and must return
    #    (trusted, trusted_ca, revoked) where the key lists hold BYTES of an
    #    OpenSSH public key line.
    pub = open(HARNESS_HOSTKEY_PUB, "rb").read().strip()
    seen: list[tuple] = []

    def tofu(host, addr, port):
        seen.append((host, addr, port))
        return ([pub], [], [])

    await attempt("known_hosts=<callable TOFU>", known_hosts=tofu)
    print(f"{'   callback invoked with':42} -> {seen}")

    # 5. TOFU with the WRONG key must be rejected
    def tofu_bad(host, addr, port):
        return ([b"ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC7badkeyforhostAAAA"], [], [])

    await attempt("TOFU with wrong key", known_hosts=tofu_bad)


if __name__ == "__main__":
    asyncio.run(main())
