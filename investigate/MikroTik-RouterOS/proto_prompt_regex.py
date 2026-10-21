"""Prototype 4: validate the prompt-detection regex against ALL real RouterOS prompt forms.

Prompt forms documented by MikroTik:
  [admin@MikroTik] >                                  (root level)
  [admin@MikroTik] /interface>                        (submenu path)
  [admin@MikroTik] /ip/route>                         (deep submenu path)
  [admin@MikroTik] <admin@MikroTik>                   (safe-mode style bracket)
  [admin@MikroTik] ip route<SAFE>                     (safe mode, per docs)
  [admin@MikroTik] >                                  (dumb terminal)
  line 2 of 3>                                        (multiline continuation prompt)
  old password:                                       (value request prompt)

The regex must NOT match a prompt that is merely *contained* in the output
(e.g. a log line that quotes a prompt), so it must anchor at the end of buffer.
"""
import re

# Candidate: match a RouterOS prompt at the END of the buffer.
PROMPT_RE = re.compile(
    r"\[(?P<user>[^\]\r\n]{1,64})@(?P<host>[^\]\r\n]{1,64})\]"      # [user@host]
    r"(?:\s*<SAFE>)?"                                               # optional <SAFE> marker
    r"(?P<path>(?:\s*/[^\s<>\r\n]+)*"                              # optional /sub/path
    r"|(?:\s+[^\s<>\r\n]+(?:\s+[^\s<>\r\n]+)*)?)?"              #   or space-separated path
    r"(?:\s*<(?P<bracket>[^>\r\n]*)>)?"                              # optional <...> bracket
    r"(?:\s*>)?\s*$"                                               # optional final '>'
)

# Continuation / value-request prompts must be detected separately
CONTINUATION_RE = re.compile(r"line\s+\d+\s+of\s+\d+\s*>\s*$")
VALUE_REQUEST_RE = re.compile(r"^[A-Za-z0-9 _\-/()']+:\s*$")

CASES = [
    # (buffer, expected_match, description)
    ("[admin@MikroTik] > ", True, "root prompt"),
    ("[admin@MikroTik] >", True, "root prompt no trailing space"),
    ("[admin@MikroTik] /interface> ", True, "submenu prompt"),
    ("[admin@MikroTik] /ip/route> ", True, "deep submenu prompt"),
    ("[admin@MikroTik] <admin@MikroTik> ", True, "bracketed path form"),
    ("[admin@MikroTik] <admin@MikroTik> > ", True, "bracketed path + >"),
    ("[admin@MikroTik] ip route<SAFE> ", True, "safe mode marker"),
    ("[admin@MikroTik] > /interface set ether1 mtu=1500", False, "command typed after prompt"),
    ("Flags: R - RUNNING\n  0 R ether1 1500\n[admin@MikroTik] > ", True, "output + prompt"),
    ("invalid command name foo\n[admin@MikroTik] > ", True, "error + prompt"),
    ("[admin@MikroTik] > ", True, "bare"),
    # must NOT match - a prompt-like string in the middle of output
    ("[admin@MikroTik] > some trailing text", False, "prompt not at end"),
    ("log line [admin@MikroTik] > was seen\nmore output", False, "prompt quoted mid-output"),
    # other users / hostnames
    ("[netops@core-rtr-01] > ", True, "other user/hostname"),
    ("[admin@MikroTik] /ip/firewall/filter> ", True, "long path"),
]

print("=" * 78)
print("PROMPT REGEX VALIDATION")
print("=" * 78)
ok = True
for buf, expected, desc in CASES:
    m = PROMPT_RE.search(buf)
    got = m is not None
    status = "PASS" if got == expected else "FAIL"
    if got != expected:
        ok = False
    detail = ""
    if m:
        detail = f"  user={m.group('user')!r} host={m.group('host')!r} path={m.group('path')!r}"
    print(f"[{status}] {desc:32} expected={expected!s:5} got={got!s:5}{detail}")

print()
print("Continuation prompt :", bool(CONTINUATION_RE.search("line 2 of 3> ")))
print("Value request prompt:", bool(VALUE_REQUEST_RE.search("old password: ")))
print()
print("ALL PASS" if ok else "SOME FAILED")
