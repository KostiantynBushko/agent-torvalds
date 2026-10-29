#!/usr/bin/env python3
"""Replay the operator's own log through the new rendering.

The log the operator sent with the request is the best evidence there
is: it is a real prompt, with the real system prompt of the agent, as
it was written to the log before the empty lines were removed.

    .venv/bin/python investigate/context-window-proof/replay_the_operator_log.py

The log is outside the repository, so the script says so and stops when
it is not there.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from llama_index.core.base.llms.types import ChatMessage, MessageRole

from components.chat_message import to_string

LOG = Path.home() / "torvald-log" / "chat-message.md"

if not LOG.exists():
    print(f"The log {LOG} is not there — nothing to replay.")
    sys.exit(2)

raw = LOG.read_text()

# The system message of the operator's run: everything between
# "[0] system: " and the next "[1] user: " line.
match = re.search(
    r"\[0\] system: (.*?)\n\d{4}-\d{2}-\d{2}.*?\[1\] user:", raw, re.S
)
if not match:
    print("The log does not hold a system message — nothing to replay.")
    sys.exit(2)

content = match.group(1)

message = ChatMessage(role=MessageRole.SYSTEM, content=content)
rendered = to_string(message)

before = content.splitlines()
after = rendered.splitlines()

print("=" * 70)
print("The operator's own log, replayed through the new rendering")
print("=" * 70)
print(f"  the message as it was logged : {len(before)} lines")
print(f"  the message as it is now     : {len(after)} lines")
print(f"  empty lines before           : {sum(1 for l in before if not l.strip())}")
print(f"  empty lines after            : {sum(1 for l in after if not l.strip())}")
print("=" * 70)
print()
print("--- the whole rendered message, as it goes into the log ---")
print(rendered)
print("=" * 70)

# The checks are not asserts.  Under ``python -O`` the assert
# statements are removed, and the script would print "OK" for a
# rendering that is broken — a proof that lies about its own result.
problems = []
if rendered.endswith("\n"):
    problems.append("the message still ends with a newline")
if "\n\n\n" in rendered:
    problems.append("the message still holds a run of empty lines")

if problems:
    for problem in problems:
        print(f"FAIL — {problem}")
    sys.exit(1)

print("OK — no trailing empty lines, no run of empty lines.")
