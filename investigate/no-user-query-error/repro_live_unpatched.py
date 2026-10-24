"""
The "before" case, with the real agent: run the real Excel task with the
context guard bypassed and watch the original failure happen.

The guard is removed by pointing ``HITLFunctionAgent.take_step`` back at the
framework implementation, which is exactly how the agent behaved before the
fix.  Everything else — the real model, the real Excel toolkit, the real
workspace — stays the same.

The run is expected to fail with

    "No user query found in messages."

which is the error from ``/home/kbush/torvald-log/exel.txt``.

Usage:
    python investigate/no-user-query-error/repro_live_unpatched.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.base.llms.types import ChatMessage
from llama_index.llms.ollama.base import Ollama

from components.hitl_agent import HITLFunctionAgent

# Bypass the context guard: go back to the framework implementation.
HITLFunctionAgent.take_step = FunctionAgent.take_step

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "nuq_repro_live",
    os.path.join(os.path.dirname(__file__), "repro_live.py"),
)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
run_live = _mod.main

if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_live()))
