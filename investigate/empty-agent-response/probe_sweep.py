#!/usr/bin/env python3
"""
Probe: the prompt that outgrows the context window.

``probe_long_prompt.py`` asks the server the same question at several prompt
sizes.  This probe runs the same sweep in the background and writes the
result to a file, so a long sweep does not have to be watched.

Usage:
    python probe_long_prompt.py --repeats 0 80 160 200 240 280 320
"""
from __future__ import annotations

import sys

from probe_long_prompt import main

if __name__ == "__main__":
    sys.exit(main())
