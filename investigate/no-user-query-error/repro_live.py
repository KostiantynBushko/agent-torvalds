"""
Live reproduction of the "No user query found in messages." failure.

Runs the REAL agent (real Ollama model, real Excel toolkit) against a
throw-away copy of the user's workspace and records, for every LLM call, the
exact message list that was put on the wire.

The recorder wraps ``Ollama.astream_chat`` so nothing is lost: the message
list is written to a JSONL file *before* the request is sent, so even the
failing call is captured.

Usage:
    python investigate/no-user-query-error/repro_live.py [--workspace DIR]
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from llama_index.core.base.llms.types import ChatMessage
from llama_index.llms.ollama.base import Ollama

# The workspace of the operator, on the external drive.  The name of
# the account comes from the environment — the Python equivalent of
# $USER — and it is never written down.
SOURCE_WORKSPACE = os.environ.get(
    "SOURCE_WORKSPACE",
    os.path.join(
        "/media",
        os.environ.get("USER", "operator"),
        "HP P500",
        "IKS",
        "inventory",
        "output_by_unit",
        "mytlushko",
    ),
)

REQUEST = (
    "in project folder: take a file A = OV_2026_10.xlsx file B = shtab.xlsx "
    "for person 'Митлушко Андрій Романович' merge entities from column 'D' in "
    "file A and column C in file B, the result must be in copy of file B in "
    "the project directory, the source of truth is file A. Original files "
    "must be untoched."
)

RECORD_PATH = "/tmp/no-user-query-requests.jsonl"


def has_user_query(messages) -> bool:
    """Mirror of the model's Jinja template check."""
    for m in reversed(list(messages)):
        if m.role != "user":
            continue
        content = (m.content or "").strip()
        if not (
            content.startswith("<tool_response>")
            and content.endswith("</tool_response>")
        ):
            return True
    return False


def install_recorder() -> None:
    """Wrap Ollama.astream_chat so every request is written to disk."""
    original = Ollama.astream_chat

    async def patched(self, messages, **kwargs):
        from components.context_guard import count_tokens

        record = {
            "roles": [m.role for m in messages],
            "ollama_messages": self._convert_to_ollama_messages(messages),
            "has_user_query": has_user_query(messages),
            "tokens": count_tokens(messages),
            "texts": [
                (m.content or "")[:200] for m in messages
            ],
        }
        with open(RECORD_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return await original(self, messages, **kwargs)

    Ollama.astream_chat = patched


async def main() -> int:
    workspace = None
    for i, arg in enumerate(sys.argv):
        if arg == "--workspace" and i + 1 < len(sys.argv):
            workspace = sys.argv[i + 1]

    if workspace is None:
        workspace = tempfile.mkdtemp(prefix="nuq-ws-")
        for name in ("OV_2026_10.xlsx", "shtab.xlsx", ".agentworkspace.json"):
            src = os.path.join(SOURCE_WORKSPACE, name)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(workspace, name))
        print(f"workspace: {workspace} (copy of {SOURCE_WORKSPACE})")
    else:
        print(f"workspace: {workspace}")

    os.chdir(workspace)
    if os.path.exists(RECORD_PATH):
        os.remove(RECORD_PATH)

    install_recorder()

    from toolkits.xlsx_toolkit.agent_xlsx_toolkit import get_all_tools as get_xlsx_tools
    from components.hitl_agent import HITLFunctionAgent
    from components.ollama_config import apply_context_window
    from llama_index.core.memory import ChatMemoryBuffer

    # The model must be pinned: the environment may point at a different one
    # (a cloud model with a 1M context window, for instance), and the bug
    # this reproduces is specific to the local qwen3.6 model whose server
    # runs with an 8k window.
    model = os.environ.get(
        "NUQ_TEST_MODEL", "richardyoung/qwen3.6-27b-abliterated:Q4_K_M"
    )
    llm = Ollama(
        model=model,
        base_url="http://localhost:11434",
        request_timeout=600.0,
        temperature=0.0,
    )
    window = apply_context_window(llm)
    print(f"context window in use: {window}")

    memory = ChatMemoryBuffer.from_defaults(token_limit=5000)

    agent = HITLFunctionAgent(
        tools=get_xlsx_tools(),
        llm=llm,
        max_iterations=20,
        memory=memory,
        system_prompt=(
            "You are Torvalds, a helpful assistant. Use the Excel tools to "
            "read and write .xlsx files in the project folder."
        ),
    )
    agent.hitl_enabled = False

    # Mirror prompt_handler(): project context goes in as a USER message.
    memory.put(
        ChatMessage(
            content=(
                "CONTEXT: ### Registered Projects\n"
                "- **mytlushko** (Unknown): ."
            )
        )
    )

    print("running agent ...", flush=True)
    handler = agent.run(REQUEST, memory=memory, max_iterations=20)
    try:
        result = await handler
        print("\nagent finished:", str(result)[:500])
    except Exception as exc:  # noqa: BLE001
        print(f"\n!! agent raised {type(exc).__name__}: {exc}")
        traceback.print_exc()

    print(f"\nrecorded requests -> {RECORD_PATH}")
    with open(RECORD_PATH, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            rec = json.loads(line)
            flag = "  <== NO USER QUERY (template will 500)" if not rec["has_user_query"] else ""
            over = "  <== OVER THE CONTEXT WINDOW" if rec["tokens"] > (window or 0) else ""
            print(f"  call {i}: {rec['tokens']} tokens, {len(rec['roles'])} msgs{flag}{over}")
            if not rec["has_user_query"]:
                for role, text in zip(rec["roles"], rec["texts"]):
                    print(f"      {role}: {text!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
