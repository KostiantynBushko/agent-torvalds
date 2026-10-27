"""The message callback that `git filter-repo` executes for every commit.

It removes the two spellings of a Claude trace from a commit message:

    Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
    🤖 Generated with [Claude Code](https://claude.com/claude-code)

Only those lines go — the rest of the message is left byte-for-byte alone,
and the author, the committer and both dates are preserved by filter-repo
itself.  `message` arrives as **bytes** and must be returned as bytes.

The removal is **line-wise** rather than a single regex over the whole
message, because a trailer is a *line* and the blank line that separates it
from the body has to go with it.  A regex that only eats the trailer leaves
a double blank line behind; this does not.

The file is a snippet, not a module: `git filter-repo --message-callback`
execs its contents with `message` in scope, so the purge script passes it
with `$(cat strip_claude_trailer.py)`.
"""
import re

# A whole line that carries the trace, and nothing else.
_TRAILER_LINE = re.compile(rb"^[ \t]*Co-Authored-By:[ \t]*.*[Cc]laude[^\n]*$")
_FOOTER_LINE = re.compile(rb"^[ \t]*.*[Gg]enerated with[^\n]*[Cc]laude[^\n]*$")

_before = message

_kept = []
_removed = False
for _line in message.split(b"\n"):
    if _TRAILER_LINE.match(_line) or _FOOTER_LINE.match(_line):
        _removed = True
        # The blank line that separated the trailer from the body goes with
        # it, so no double blank line is left behind.
        if _kept and _kept[-1] == b"":
            _kept.pop()
        continue
    _kept.append(_line)

if _removed:
    message = b"\n".join(_kept).rstrip(b"\n") + b"\n"

# A message that carried no trace is returned byte-for-byte unchanged.
assert _removed or message == _before, "the callback changed a clean message"

# filter-repo execs this snippet as a function body and takes the value of
# the `return` statement as the new message.
return message
