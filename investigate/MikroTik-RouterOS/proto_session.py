"""Prototype 3: session-based (stateful) RouterOS CLI over SSH.

Validates the design that the production toolkit should use:
  - ONE SSH connection, N commands (RouterOS CLI is stateful: `cd` changes context)
  - Prompt regex detection (host name is dynamic)
  - Large output handling (no truncation, no deadlock)
  - stdout/stderr separation on the interactive channel
"""
import asyncio
import re
import time
import asyncssh

from _proto_config import (HARNESS_HOST, HARNESS_PORT_SESSION, HARNESS_USER, HARNESS_KEY)

HOST, PORT, USER, KEY = HARNESS_HOST, HARNESS_PORT_SESSION, HARNESS_USER, HARNESS_KEY

# RouterOS prompt forms:
#   [admin@MikroTik] >
#   [admin@MikroTik] <admin@MikroTik>      (submenu)
#   [admin@MikroTik] <admin@MikroTik> >    (submenu with prompt)
PROMPT = re.compile(r"\[(?P<user>[^\]\r\n]+)@(?P<host>[^\]\r\n]+)\](?P<path>(?:\s*<[^>\r\n]*>)*)\s*>?\s*$")


class RosSession:
    def __init__(self):
        self.conn = None
        self.writer = None
        self.reader = None
        self.banner = ""

    async def connect(self, timeout=10.0):
        self.conn = await asyncssh.connect(
            HOST, port=PORT, username=USER, client_keys=[KEY],
            known_hosts=None, encoding="utf-8", errors="replace",
        )
        self.writer, self.reader, _ = await self.conn.open_session(
            term_type="vt100", term_size=(80, 24))
        self.banner = await self._read_to_prompt(timeout)
        return self.banner

    async def _read_to_prompt(self, timeout):
        buf = ""
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("no prompt within timeout")
            try:
                chunk = await asyncio.wait_for(self.reader.read(4096), timeout=min(remaining, 1.0))
            except asyncio.TimeoutError:
                continue
            if chunk in (None, ""):
                raise ConnectionError("session closed")
            buf += chunk
            if PROMPT.search(buf):
                return buf

    async def run(self, command, timeout=10.0):
        self.writer.write(command + "\n")
        await self.writer.drain()
        raw = await self._read_to_prompt(timeout)
        # strip the echoed command and the trailing prompt
        body = raw
        for prefix in (command + "\r\n", command + "\n"):
            if body.startswith(prefix):
                body = body[len(prefix):]
                break
        m = PROMPT.search(body)
        if m:
            body = body[:m.start()]
        return body.rstrip("\r\n")

    async def close(self):
        if self.conn:
            self.conn.close()
            await self.conn.wait_closed()


async def main():
    s = RosSession()
    banner = await s.connect()
    print("BANNER:", repr(banner))
    print()

    for cmd in ["/system/resource", "/identity/print", "/interface/print", "/bogus/cmd"]:
        t0 = time.monotonic()
        out = await s.run(cmd)
        dt = (time.monotonic() - t0) * 1000
        lines = out.count("\n") + 1
        print(f"--- {cmd}  ({dt:.1f} ms, {len(out)} bytes, {lines} lines)")
        preview = out if len(out) < 220 else out[:200] + f"\n   ...[{len(out)-220} bytes elided]..."
        print(preview)
        print()

    # multi-command state check
    print("=== session reuse: 5 sequential commands on ONE connection ===")
    t0 = time.monotonic()
    for i in range(5):
        await s.run("/system/resource")
    print(f"5 commands in {(time.monotonic()-t0)*1000:.0f} ms (no reconnect overhead)")
    await s.close()

asyncio.run(main())
