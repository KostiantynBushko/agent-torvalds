"""Empirical prototype: asyncssh against a RouterOS-like interactive prompt.

Validates the core technical risk of the MikroTik SSH toolkit:
  1. Can asyncssh open a channel and drive an interactive CLI?
  2. How is the CLI prompt detected reliably (not fixed-length)?
  3. Is the RouterOS error text ("invalid command name X") on stdout or stderr?
  4. What are the CRLF / trailing-prompt details of the response?
"""
import asyncio
import re
import asyncssh

from _proto_config import (HARNESS_HOST, HARNESS_PORT_SESSION, HARNESS_USER, HARNESS_KEY)

HOST, PORT, USER, KEY = HARNESS_HOST, HARNESS_PORT_SESSION, HARNESS_USER, HARNESS_KEY

# RouterOS prompt examples:
#   "[admin@MikroTik] > "
#   "[admin@MikroTik] <admin@MikroTik>"  (inside a submenu)
#   "[admin@MikroTik] <admin@MikroTik> >"
PROMPT_RE = re.compile(rb"\[(?P<user>[^\]\r\n]+?)@(?P<host>[^\]\r\n]+?)\][^\r\n]{0,40}?[>\s]\s*$")


async def read_until_prompt(reader, buf: str, timeout: float) -> tuple[str, bool]:
    """Read from reader until the CLI prompt is seen at the end of the buffer."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            return buf, False
        try:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=min(remaining, 1.0))
        except asyncio.TimeoutError:
            continue
        if chunk in (None, ""):
            return buf, True
        buf += chunk
        if PROMPT_RE.search(buf.encode()):
            return buf, True


async def run_command(command: str, timeout: float = 10.0) -> dict:
    async with asyncssh.connect(
        HOST, port=PORT, username=USER, client_keys=[KEY],
        known_hosts=None,
    ) as conn:
        writer, reader, _ = await conn.open_session(
            term_type="vt100", term_size=(80, 24),
            encoding="utf-8", errors="replace",
        )

        banner, ok = await read_until_prompt(reader, "", timeout)
        buf = ""
        writer.write(command + "\n")
        await writer.drain()
        out, ok = await read_until_prompt(reader, buf, timeout)
        return {"banner": banner, "output": out, "clean": ok}


async def main():
    for cmd in ["/system/resource", "/interface/print", "/bogus/command"]:
        res = await run_command(cmd)
        print(f"### COMMAND: {cmd}")
        print(f"--- banner : {res['banner']!r}")
        print(f"--- output : {res['output']!r}")
        print(f"--- clean  : {res['clean']}")
        print()

asyncio.run(main())
