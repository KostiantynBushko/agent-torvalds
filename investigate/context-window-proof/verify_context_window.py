#!/usr/bin/env python3
"""
Proof — the context window the agent reports is the one the server uses.

The model advertises its **maximum** context length.  The Ollama server
usually runs with a much smaller window (``PARAMETER num_ctx`` in the
Modelfile, or ``--ctx-size`` on the command line), and a prompt that
exceeds it is truncated from the front by the server — which drops the
user request and makes the model template fail with "No user query found
in messages.".

So the number the agent logs is not a detail: it is the number the
prompt is sized against.  This script proves that the number comes from
the **server** and not from the model's advertisement.

Run it against a live Ollama server:

    .venv/bin/python investigate/context-window-proof/verify_context_window.py

Exit code 0 = every invariant holds.  Exit code 1 = at least one is
broken.

Invariants
----------
P1  The number the agent reports is the number the **server** uses: the
    ``PARAMETER num_ctx`` of the model's Modelfile, and the
    ``context_length`` of the running model when it is loaded.
P2  The number the agent reports is **not** the model's advertised
    maximum — the number a naive implementation would report.
P3  The ``INFO`` log names the size **and** the source it came from.
P4  The number is **read** from the server, not baked into the code.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
_SELF_DEV = _HERE.parents[1]
if str(_SELF_DEV) not in sys.path:
    sys.path.insert(0, str(_SELF_DEV))

from components.ollama_config import (  # noqa: E402
    CONTEXT_LENGTH_ENV_VAR,
    SOURCE_ENVIRONMENT,
    SOURCE_MODEL_MAXIMUM,
    apply_context_window,
    resolve_context_window_with_source,
)

#: The model the agent talks to by default (see ``MODEL`` in
#: ``agent-torvalds.py``).
#:
#: ``TORVALDS_MODEL`` is deliberately **not** used here: it is often
#: pointed at a cloud model (``minimax-m3.1-flash:cloud``, for
#: instance), and the local Ollama server knows nothing about it.  The
#: proof is about the local server, so it names the local model.
DEFAULT_MODEL = "richardyoung/qwen3.6-27b-abliterated:Q4_K_M"

#: The model the proof runs against.
MODEL = os.environ.get("CONTEXT_WINDOW_PROOF_MODEL", DEFAULT_MODEL)

#: The Ollama server the agent talks to.
BASE_URL = os.environ.get(
    "TORVALDS_OLLAMA_HOST", "http://localhost:11434"
).rstrip("/")

LOGGER_NAME = "components.ollama_config"


# ---------------------------------------------------------------------------
# The server, asked directly
# ---------------------------------------------------------------------------


def _get(path: str, payload: Optional[dict] = None, timeout: int = 10) -> Any:
    """Return the JSON the server answers with, or ``None``."""
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except Exception:  # noqa: BLE001 - the server may be unreachable
        return None


def server_num_ctx(model: str = MODEL) -> Optional[int]:
    """Return the ``PARAMETER num_ctx`` of the model's Modelfile.

    This is the window the server was configured to run the model with.
    """
    info = _get("/api/show", {"name": model})
    if not info:
        return None
    for line in (info.get("modelfile") or "").splitlines():
        line = line.strip()
        if not line.upper().startswith("PARAMETER NUM_CTX"):
            continue
        try:
            return int(line.split("num_ctx")[-1].strip())
        except ValueError:
            return None
    return None


def server_advertised_maximum(model: str = MODEL) -> Optional[int]:
    """Return the context length the model *advertises*.

    This is the maximum the model was trained for — not the window the
    server runs it with.
    """
    tags = _get("/api/tags")
    if not tags:
        return None
    for entry in tags.get("models") or []:
        name = entry.get("model") or entry.get("name") or ""
        if name == model or model in name or name in model:
            return (entry.get("details") or {}).get("context_length")
    return None


def server_running_context_length(model: str = MODEL) -> Optional[int]:
    """Return the context length the server allocated for the model.

    ``/api/ps`` reports the window the *running* model was loaded with.
    While the model is loaded this is the authoritative answer.
    """
    running = _get("/api/ps")
    if not running:
        return None
    for entry in running.get("models") or []:
        name = entry.get("model") or entry.get("name") or ""
        if name == model or model in name or name in model:
            return entry.get("context_length")
    return None


# ---------------------------------------------------------------------------
# The agent's view
# ---------------------------------------------------------------------------


def agent_llm():
    """Return the LLM the agent uses, talking to the real server."""
    from llama_index.llms.ollama import Ollama

    return Ollama(
        model=MODEL,
        base_url=BASE_URL,
        request_timeout=30,
    )


def agent_reported(llm) -> Tuple[Optional[int], str]:
    """Return what the agent reports, and where it got it from."""
    length, source = resolve_context_window_with_source(llm)
    return length, source


def agent_advertised(llm) -> Optional[int]:
    """Return the context window the LLM *advertises* without any help.

    This is the number a naive implementation would log.
    """
    try:
        return int(llm.metadata.context_window)
    except Exception:  # noqa: BLE001
        return None


def capture_apply_log(llm) -> List[str]:
    """Return the log records ``apply_context_window()`` writes."""
    records: List[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    logger = logging.getLogger(LOGGER_NAME)
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        apply_context_window(llm)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)

    return [record.getMessage() for record in records]


# ---------------------------------------------------------------------------
# The invariants
# ---------------------------------------------------------------------------


def p1_the_number_is_the_servers() -> Tuple[bool, str, str]:
    """The number the agent reports is the number the server uses."""
    llm = agent_llm()
    reported, source = agent_reported(llm)

    num_ctx = server_num_ctx()
    running = server_running_context_length()

    problems = []
    if reported is None:
        problems.append("the agent reports no window at all")
    if num_ctx is None:
        problems.append("the server did not report a num_ctx")
    elif reported != num_ctx:
        problems.append(
            f"the agent reports {reported}, the server is configured "
            f"with num_ctx {num_ctx}"
        )
    if running is not None and reported != running:
        problems.append(
            f"the agent reports {reported}, the running model was "
            f"loaded with {running}"
        )

    if reported is not None and running is not None and reported == running:
        source_note = "the running model agrees"
    else:
        source_note = "the Modelfile agrees"

    detail = (
        f"reported {reported} ({source}); server num_ctx {num_ctx}; "
        f"running model {running} — {source_note}"
    )
    return (not problems, "; ".join(problems) or "the server's own number", detail)


def p2_it_is_not_the_advertised_maximum() -> Tuple[bool, str, str]:
    """The number the agent reports is not the advertised maximum."""
    llm = agent_llm()
    reported, _ = agent_reported(llm)
    advertised = agent_advertised(llm)

    problems = []
    if advertised is None:
        problems.append("the LLM does not advertise a context window")
    elif advertised == reported:
        problems.append(
            f"the agent reports the advertised maximum {advertised} — "
            "that is the number the server does not necessarily use"
        )

    if advertised is not None and reported is not None:
        detail = (
            f"advertised maximum {advertised}; the agent reports {reported} "
            f"({advertised - reported} tokens smaller)"
        )
    else:
        detail = f"advertised maximum {advertised}; the agent reports {reported}"
    return (not problems, "; ".join(problems) or "not the advertisement", detail)


def p3_the_log_names_the_size_and_the_source() -> Tuple[bool, str, str]:
    """The INFO log names the size and the source."""
    llm = agent_llm()
    reported, source = agent_reported(llm)
    messages = capture_apply_log(llm)

    problems = []
    if not messages:
        problems.append("apply_context_window() logged nothing at INFO")
    else:
        text = "\n".join(messages)
        if "Context window" not in text:
            problems.append("the log does not mention the context window")
        if reported is not None and str(reported) not in text:
            problems.append(f"the log does not carry the size {reported}")
        if source not in text:
            problems.append(f"the log does not name the source ({source})")

    detail = "; ".join(messages) or "nothing was logged"
    return (not problems, "; ".join(problems) or "the log is complete", detail)


def p4_the_number_is_read_not_baked_in() -> Tuple[bool, str, str]:
    """The number is read from the server, not baked into the code."""
    llm = agent_llm()
    reported, _ = agent_reported(llm)

    problems = []

    # (a) The environment override is followed.
    previous = os.environ.get(CONTEXT_LENGTH_ENV_VAR)
    os.environ[CONTEXT_LENGTH_ENV_VAR] = "12345"
    try:
        override, override_source = agent_reported(llm)
    finally:
        if previous is None:
            os.environ.pop(CONTEXT_LENGTH_ENV_VAR, None)
        else:
            os.environ[CONTEXT_LENGTH_ENV_VAR] = previous

    if override != 12345:
        problems.append(f"the override was ignored (got {override})")
    if override_source != SOURCE_ENVIRONMENT:
        problems.append(
            f"the override is not named as the source ({override_source})"
        )

    # (b) With the server's own probes disabled the number changes: the
    # number came from the server, not from a constant in the code.
    from unittest.mock import patch

    from components import ollama_config

    with patch.object(
        ollama_config, "_context_length_from_running_model", return_value=None
    ), patch.object(
        ollama_config, "_context_length_from_modelfile", return_value=None
    ):
        without_server, without_source = agent_reported(llm)

    if without_server == reported:
        problems.append(
            "the number did not change when the server was taken away — "
            "it is a constant"
        )
    if without_source != SOURCE_MODEL_MAXIMUM:
        problems.append(
            "without the server the source should be the advertised "
            f"maximum, not {without_source}"
        )

    detail = (
        f"with the server: {reported}; the override: {override} "
        f"({override_source}); without the server: {without_server} "
        f"({without_source})"
    )
    return (not problems, "; ".join(problems) or "the number is read", detail)


INVARIANTS = (
    ("P1  the number is the server's", p1_the_number_is_the_servers),
    ("P2  it is not the advertised maximum", p2_it_is_not_the_advertised_maximum),
    ("P3  the log names the size and the source", p3_the_log_names_the_size_and_the_source),
    ("P4  the number is read, not baked in", p4_the_number_is_read_not_baked_in),
)


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------


def print_evidence() -> None:
    """Print what the server says, next to what the agent says."""
    llm = agent_llm()
    reported, source = agent_reported(llm)

    print("The evidence")
    print("-" * 70)
    print(f"  model                       {MODEL}")
    print(f"  server                      {BASE_URL}")
    print(f"  the model advertises        {agent_advertised(llm)} tokens")
    print(f"  the server is configured    {server_num_ctx()} tokens (num_ctx)")
    print(f"  the running model has       {server_running_context_length()} tokens")
    print(f"  the agent reports           {reported} tokens ({source})")
    print("-" * 70)


def main() -> int:
    print("Context window — proof that the agent reports the server's window")
    print("=" * 70)

    if server_num_ctx() is None and server_running_context_length() is None:
        print(
            "  [SKIP] the Ollama server is not reachable — the live "
            "invariants cannot be checked."
        )
        print("         start the server and run this again.")
        return 2

    print_evidence()
    print()

    failures = 0
    for name, check in INVARIANTS:
        ok, problem, detail = check()
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}: {detail}")
        if not ok:
            print(f"           -> {problem}")
            failures += 1

    print("=" * 70)
    if failures:
        print(f"FAIL — {failures} of {len(INVARIANTS)} invariants are broken.")
        return 1

    print(f"PASS — all {len(INVARIANTS)} invariants hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
