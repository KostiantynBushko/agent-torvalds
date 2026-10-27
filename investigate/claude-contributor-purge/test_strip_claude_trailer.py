#!/usr/bin/env python3
"""The test of the `git filter-repo` message callback.

`strip_claude_trailer.py` is a **snippet**, not a module: filter-repo execs
it with `message` in scope.  This suite loads it the same way filter-repo
does — by exec'ing the snippet inside a function whose only argument is
`message` — and drives it with the real offending message and with the
messages that must survive untouched.

    python3 test_strip_claude_trailer.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SNIPPET = os.path.join(HERE, "strip_claude_trailer.py")


def load_callback():
    """Exec the snippet exactly the way `git filter-repo` does."""
    source = open(SNIPPET, encoding="utf-8").read()
    body = source.split('"""', 2)[2]          # drop the module docstring
    namespace = {"re": re}
    exec("def callback(message):\n"
         + "\n".join("    " + line for line in body.splitlines()),
         namespace)
    return namespace["callback"]


# (name, input, expected output)
CASES = [
    (
        "the real trailer is removed and nothing else",
        b"Initial commit: shodan-toolkit\n"
        b"\n"
        b"A Python wrapper around the Shodan CLI.\n"
        b"\n"
        b"Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>\n",
        b"Initial commit: shodan-toolkit\n"
        b"\n"
        b"A Python wrapper around the Shodan CLI.\n",
    ),
    (
        "the Claude Code footer is removed",
        b"Subject\n\n---\n\n"
        b"\xe2\x9a\xa0 Generated with [Claude Code](https://claude.com/claude-code)\n",
        b"Subject\n\n---\n",
    ),
    (
        "a trailer in the middle of the body leaves no double blank line",
        b"Subject\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n\nMore body.\n",
        b"Subject\n\nMore body.\n",
    ),
    (
        "a co-author that is not Claude stays",
        b"Subject\n\nCo-Authored-By: Kostiantyn <k@example.com>\n",
        b"Subject\n\nCo-Authored-By: Kostiantyn <k@example.com>\n",
    ),
    (
        "the word Claude inside the body stays",
        b"Subject\n\nBody with the word Claude in it.\n",
        b"Subject\n\nBody with the word Claude in it.\n",
    ),
    (
        "a clean message is returned byte-for-byte",
        b"Subject\n\nBody.\n\nCo-Authored-By: Kostiantyn <k@example.com>\n\nMore.\n",
        b"Subject\n\nBody.\n\nCo-Authored-By: Kostiantyn <k@example.com>\n\nMore.\n",
    ),
    (
        "a message that is only a trailer collapses to the subject",
        b"Subject\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <x@y.z>\n",
        b"Subject\n",
    ),
]


def main() -> int:
    callback = load_callback()
    failures = 0
    for name, given, want in CASES:
        got = callback(given)
        if got == want:
            print(f"PASS  {name}")
        else:
            failures += 1
            print(f"FAIL  {name}")
            print(f"      want {want!r}")
            print(f"      got  {got!r}")
    total = len(CASES)
    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
