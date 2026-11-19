"""Read-only probe: the iteration of the workflow in the TUI.

The probe answers one question in four parts:

1. What the operator sees — the progress pane of a fresh state.
2. The wiring — who writes the number of the iteration, and who tells
   the panel about it.
3. What the framework knows — a real run of the real agent, with the
   counters of the workflow read at every request to the model.
4. The run, end to end — the agent, the observer, the state, and the
   pane, while the agent works.

The probe changes nothing: it renders, it reads the source, and it runs
the agent against a scripted model that lives in this file.  It writes
nothing, and it talks to no service.

Run it from the root of the repository::

    .venv/bin/python investigate/workflow-iteration-counter/probe_workflow_iteration.py
"""

from __future__ import annotations

import ast
import asyncio
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from llama_index.core.base.llms.types import (  # noqa: E402
    ChatMessage,
    ChatResponse,
    CompletionResponse,
    LLMMetadata,
    MessageRole,
    TextBlock,
    ToolCallBlock,
)
from llama_index.core.llms.function_calling import FunctionCallingLLM  # noqa: E402
from llama_index.core.llms.llm import ToolSelection  # noqa: E402
from llama_index.core.tools import FunctionTool  # noqa: E402
from pydantic import PrivateAttr  # noqa: E402

from components.hitl_agent import HITLFunctionAgent  # noqa: E402
from components.tui.progress_view import ProgressView  # noqa: E402
from components.tui.state_bridge import TuiState  # noqa: E402

#: The budget the multi-window console gives the agent — the value the
#: workflow is run with.
BUDGET = 500


# ---------------------------------------------------------------------------
# 1. What the operator sees
# ---------------------------------------------------------------------------

def show_the_pane(state: TuiState, title: str) -> None:
    """Print the row of the progress pane that carries the iteration."""
    from rich.console import Console

    console = Console(width=60, no_color=True, legacy_windows=False)
    with console.capture() as capture:
        console.print(ProgressView().render(state))
    printed = capture.get()

    print(f"  {title}")
    for line in printed.splitlines():
        if "Workflow Iteration" in line:
            print(f"    {line.strip()}")


# ---------------------------------------------------------------------------
# 2. The wiring
# ---------------------------------------------------------------------------

def _python_files() -> list[Path]:
    """Every source file of the repository, but not the virtualenv."""
    files = []
    for path in REPO.rglob("*.py"):
        parts = set(path.parts)
        if parts & {".venv", "site-packages", ".git", "__pycache__"}:
            continue
        files.append(path)
    return files


def _calls_in(path: Path) -> tuple[list[str], list[str]]:
    """Return the names called and the attributes assigned in *path*."""
    called: list[str] = []
    assigned: list[str] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return called, assigned

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called.append(func.id)
            elif isinstance(func, ast.Attribute):
                called.append(func.attr)
        elif isinstance(node, ast.Attribute):
            if isinstance(node.ctx, ast.Store):
                assigned.append(node.attr)
    return called, assigned


def show_the_wiring() -> None:
    """Show who writes the number of the iteration, and who tells it."""
    writers: dict[str, list[str]] = {}
    callers: dict[str, list[str]] = {}
    observers: dict[str, list[str]] = {}

    for path in _python_files():
        rel = str(path.relative_to(REPO))
        called, assigned = _calls_in(path)
        if "workflow_iteration" in assigned:
            writers.setdefault(rel, []).append("workflow_iteration")
        for name in ("update_workflow_iteration", "iteration_observer"):
            if name in called:
                callers.setdefault(name, []).append(rel)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "iteration_observer" in text:
            observers.setdefault(rel, []).append("iteration_observer")

    print("  who writes the attribute `workflow_iteration`:")
    for rel in sorted(writers):
        print(f"    {rel}")

    print("  who calls `TuiState.update_workflow_iteration`:")
    for rel in sorted(callers.get("update_workflow_iteration", [])):
        print(f"    {rel}")

    print("  who names the observer of the iteration:")
    for rel in sorted(observers):
        print(f"    {rel}")


def show_the_budget_paths() -> None:
    """Show the turns of the agent that never reach the budget check.

    The workflow counts the iterations of the run and stops it when the
    budget is spent — in the base implementation of the step that
    parses the output of the model.  The override of the HITL agent
    answers a question itself and returns without calling that base
    implementation: such a turn is neither counted nor checked.

    The measurement is made on the source: the returns of the override
    are listed, and the ones that reach the base implementation are
    marked.
    """
    path = REPO / "components" / "hitl_agent.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    lines = path.read_text(encoding="utf-8").splitlines()

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "HITLFunctionAgent":
            continue
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if item.name != "parse_agent_output":
                continue

            print(f"  the returns of {item.name}():")
            for child in ast.walk(item):
                if not isinstance(child, ast.Return) or child.value is None:
                    continue
                reaches_base = any(
                    isinstance(node_, ast.Call)
                    and isinstance(node_.func, ast.Attribute)
                    and node_.func.attr == "parse_agent_output"
                    for node_ in ast.walk(child.value)
                )
                mark = "counts and checks the budget" if reaches_base else "does NOT"
                source = lines[child.lineno - 1].strip()
                print(f"    line {child.lineno:>4}  {mark:<28} {source[:58]}")


# ---------------------------------------------------------------------------
# 3. What the framework knows
# ---------------------------------------------------------------------------

class ScriptedModel(FunctionCallingLLM):
    """A model that plays a fixed script: two tool calls, then the answer.

    The model is the smallest thing that can drive the real agent: it
    returns a tool call, the agent runs the tool, and it comes back for
    the next turn.  Every turn is one request to the model, and one
    iteration of the workflow.
    """

    max_tokens: int = 512
    turns_before_the_answer: int = 2
    _turn: int = PrivateAttr(default=0)

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            num_output=self.max_tokens,
            is_chat_model=True,
            is_function_calling_model=True,
        )

    def _message(self) -> ChatMessage:
        turn = self._turn
        self._turn += 1
        if turn < self.turns_before_the_answer:
            return ChatMessage(
                role=MessageRole.ASSISTANT,
                blocks=[
                    TextBlock(text="working"),
                    ToolCallBlock(
                        block_type="tool_call",
                        tool_name="probe_tool",
                        tool_kwargs={"n": turn},
                        tool_call_id=f"call-{turn}",
                    ),
                ],
            )
        return ChatMessage(
            role=MessageRole.ASSISTANT, blocks=[TextBlock(text="the answer")]
        )

    def chat(self, messages, **kwargs) -> ChatResponse:
        message = self._message()
        return ChatResponse(message=message, raw={"content": message.content})

    def stream_chat(self, messages, **kwargs):
        yield self.chat(messages, **kwargs)

    async def achat(self, messages, **kwargs) -> ChatResponse:
        return self.chat(messages, **kwargs)

    async def astream_chat(self, messages, **kwargs):
        """The stream of the scripted turn: one response, and then silence."""

        async def gen():
            yield self.chat(messages, **kwargs)

        return gen()

    def complete(self, prompt, formatted=False, **kwargs) -> CompletionResponse:
        raise NotImplementedError("the probe talks to the model with chat()")

    def stream_complete(self, prompt, formatted=False, **kwargs):
        raise NotImplementedError("the probe talks to the model with chat()")

    async def acomplete(self, prompt, formatted=False, **kwargs) -> CompletionResponse:
        raise NotImplementedError("the probe talks to the model with chat()")

    async def astream_complete(self, prompt, formatted=False, **kwargs):
        raise NotImplementedError("the probe talks to the model with chat()")

    def _prepare_chat_with_tools(
        self,
        tools,
        user_msg=None,
        chat_history=None,
        verbose=False,
        allow_parallel_tool_calls=False,
        tool_required=False,
        **kwargs,
    ) -> dict:
        """The arguments of the chat: the history and the message of the user."""
        messages = list(chat_history or [])
        if user_msg is not None:
            messages.append(
                user_msg
                if isinstance(user_msg, ChatMessage)
                else ChatMessage(role=MessageRole.USER, content=user_msg)
            )
        return {"messages": messages}

    def get_tool_calls_from_response(self, response, error_on_no_tool_call=True, **kwargs):
        """The tool calls of the scripted turn."""
        selections = []
        for block in response.message.blocks or []:
            if getattr(block, "block_type", "") == "tool_call":
                selections.append(
                    ToolSelection(
                        tool_id=getattr(block, "tool_call_id", "") or "call",
                        tool_name=block.tool_name,
                        tool_kwargs=dict(block.tool_kwargs or {}),
                    )
                )
        if not selections and error_on_no_tool_call:
            raise ValueError("no tool call in the scripted response")
        return selections


def probe_tool(n: int = 0) -> str:
    """A tool that does nothing at all, and says so."""
    return f"the tool ran, turn {n}"


async def run_the_agent(state: TuiState) -> list[tuple[int, int, int]]:
    """Run the real agent and read the counters at every request.

    The observer of the iteration is the one the console installs: it
    puts the number into the state of the TUI.

    Returns the list of ``(requests, num_iterations, max_iterations)``:
    the number of requests the model was asked for, the counter of the
    framework and the budget of the run.
    """
    model = ScriptedModel()
    tool = FunctionTool.from_defaults(fn=probe_tool)
    agent = HITLFunctionAgent(tools=[tool], llm=model, system_prompt="probe")
    agent.iteration_observer = (
        lambda iteration, budget: state.update_workflow_iteration(iteration, budget)
    )

    seen: list[tuple[int, int, int]] = []
    original = HITLFunctionAgent.take_step

    async def counting_take_step(self, ctx, llm_input, tools, memory):
        num = await ctx.store.get("num_iterations", default=0)
        mx = await ctx.store.get("max_iterations", default=0)
        seen.append((len(seen) + 1, num, mx))
        return await original(self, ctx, llm_input, tools, memory)

    HITLFunctionAgent.take_step = counting_take_step
    try:
        handler = agent.run("count the iterations", max_iterations=BUDGET)
        await handler
    finally:
        HITLFunctionAgent.take_step = original

    return seen


# ---------------------------------------------------------------------------
# The probe
# ---------------------------------------------------------------------------

async def main() -> int:
    print("=" * 72)
    print("1. What the operator sees")
    print("=" * 72)
    fresh = TuiState()
    print(f"  a fresh state carries: workflow_iteration={fresh.workflow_iteration}, "
          f"max_iterations={fresh.max_iterations}")
    show_the_pane(fresh, "the progress pane of a fresh state:")
    print(f"  the budget the agent is really run with: {BUDGET}")

    print()
    print("=" * 72)
    print("2. The wiring")
    print("=" * 72)
    show_the_wiring()

    print()
    print("=" * 72)
    print("3. What the framework knows")
    print("=" * 72)
    state = TuiState()
    seen = await run_the_agent(state)
    print(f"  the agent asked the model {len(seen)} times")
    print("  request | num_iterations | max_iterations")
    for request, num, mx in seen:
        print(f"      {request}    |        {num}      |       {mx}")

    print()
    print("=" * 72)
    print("4. The run, end to end")
    print("=" * 72)
    print("  the agent, the observer, the state of the TUI, and the pane:")
    print(f"    the state carries: workflow_iteration={state.workflow_iteration}, "
          f"max_iterations={state.max_iterations}")
    show_the_pane(state, "the progress pane after the run:")

    print()
    print("=" * 72)
    print("5. The budget and the turns that do not reach it")
    print("=" * 72)
    show_the_budget_paths()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
