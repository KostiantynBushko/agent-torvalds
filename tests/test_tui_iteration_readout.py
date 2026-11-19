"""
The iteration of the workflow on the screen of the multi-window console.

The progress panel of the multi-window console shows the iteration of the
run — ``Workflow Iteration: [░░░░░░░░░░░░] 3/500 (0%)`` — and the number
stayed at zero from the day the panel was written.  Nothing published it:
the state of the TUI carried a number that nobody ever wrote.

The agent counts the requests it makes to the model, and tells whoever is
watching.  The console puts that number into the state of the TUI, and
the panel renders it.

The investigation is in ``investigate/workflow-iteration-counter/``.

Run with:
    pytest tests/test_tui_iteration_readout.py -v
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
from llama_index.core.base.llms.types import (
    ChatMessage,
    ChatResponse,
    MessageRole,
    TextBlock,
    ToolCallBlock,
)
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.tools import FunctionTool
from llama_index.llms.ollama.base import Ollama
from pydantic import PrivateAttr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent

from components.hitl_agent import HITLFunctionAgent  # noqa: E402
from components.tui.progress_view import ProgressView  # noqa: E402
from components.tui.state_bridge import TuiState  # noqa: E402


# ---------------------------------------------------------------------------
# The fixtures
# ---------------------------------------------------------------------------


def noop() -> str:
    """A tool that does nothing."""
    return "nothing to do"


class ScriptedOllama(Ollama):
    """An Ollama LLM that plays a script: two tool calls, then the answer.

    Every turn of the script is one request to the model, and one
    iteration of the workflow.
    """

    _turn: int = PrivateAttr(default=0)

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("model", "fake/model")
        kwargs.setdefault("base_url", "http://localhost:11434")
        kwargs.setdefault("context_window", 1_000_000)
        super().__init__(*args, **kwargs)

    def _response(self) -> ChatResponse:
        self._turn += 1
        if self._turn <= 2:
            return ChatResponse(
                message=ChatMessage(
                    role=MessageRole.ASSISTANT,
                    blocks=[
                        TextBlock(text="working"),
                        ToolCallBlock(
                            block_type="tool_call",
                            tool_name="noop",
                            tool_kwargs={},
                            tool_call_id=f"call-{self._turn}",
                        ),
                    ],
                )
            )
        return ChatResponse(
            message=ChatMessage(role=MessageRole.ASSISTANT, content="The work is done.")
        )

    async def astream_chat(self, messages, **kwargs):
        async def gen():
            yield self._response()

        return gen()

    async def achat(self, messages, **kwargs):
        return self._response()

    def restart(self) -> None:
        """The script starts again from the first tool call."""
        self._turn = 0


@pytest.fixture
def llm():
    return ScriptedOllama()


@pytest.fixture
def memory():
    return ChatMemoryBuffer.from_defaults(token_limit=5000)


@pytest.fixture
def agent(llm, memory):
    agent = HITLFunctionAgent(
        tools=[FunctionTool.from_defaults(fn=noop, name="noop")],
        llm=llm,
        max_iterations=10,
        memory=memory,
        system_prompt="You are Torvalds.",
    )
    agent.hitl_enabled = False
    return agent


def _run(agent, memory, request="count the iterations", max_iterations=10):
    """Run the agent and return what the workflow answered."""

    async def _drive():
        handler = agent.run(request, memory=memory, max_iterations=max_iterations)
        try:
            return await handler
        except Exception:  # noqa: BLE001 - the run may end early
            return None

    return asyncio.run(_drive())


# ---------------------------------------------------------------------------
# The rendering of the panel
# ---------------------------------------------------------------------------


def _render_text(state, width: int = 80) -> str:
    """Render the progress panel and return it as plain text."""
    from rich.console import Console

    console = Console(width=width, color_system=None)
    panel = ProgressView().render(state)
    lines = console.render_lines(panel, console.options.update(width=width))
    return "\n".join("".join(segment.text for segment in line) for line in lines)


# ---------------------------------------------------------------------------
# The observer
# ---------------------------------------------------------------------------


class TestTheObserver:
    """The agent tells whoever is watching which iteration it is on."""

    def test_the_observer_is_called_during_a_run(self, agent, memory):
        """The number reaches the observer."""
        seen = []
        agent.iteration_observer = lambda it, budget: seen.append((it, budget))

        _run(agent, memory)

        assert seen, "the observer was never called"

    def test_the_number_counts_the_requests_to_the_model(self, agent, memory):
        """One iteration is one request to the model.

        The operator reported on 2026-11-19 that the number in the panel
        never moved.  The run of the script makes three requests to the
        model, and the observer is told about all three of them.
        """
        seen = []
        agent.iteration_observer = lambda it, budget: seen.append(it)

        _run(agent, memory)

        assert seen == [1, 2, 3], f"the iterations are not the requests: {seen}"

    def test_the_observer_is_told_the_budget_of_the_run(self, agent, memory):
        """The number comes with the budget it is a share of."""
        seen = []
        agent.iteration_observer = lambda it, budget: seen.append(budget)

        _run(agent, memory, max_iterations=7)

        assert seen, "the observer was never called"
        assert set(seen) == {7}, (
            f"the budget of the run is not what the observer was told: {seen}"
        )

    def test_the_number_starts_again_with_every_run(self, agent, llm, memory):
        """The counter belongs to the run, not to the agent."""
        seen = []
        agent.iteration_observer = lambda it, budget: seen.append(it)

        _run(agent, memory)
        llm.restart()
        _run(agent, memory)

        assert seen == [1, 2, 3, 1, 2, 3], (
            f"the second run did not start at one: {seen}"
        )

    def test_a_failing_observer_does_not_take_the_run_down(self, agent, memory):
        """A number is never worth a run."""

        def broken(iteration, budget):
            raise RuntimeError("the observer is broken")

        agent.iteration_observer = broken

        result = _run(agent, memory)

        assert result is not None, "the run died because of the observer"

    def test_no_observer_is_no_problem(self, agent, memory):
        """Nobody is watching — the agent does not care."""
        assert agent.iteration_observer is None

        result = _run(agent, memory)

        assert result is not None


# ---------------------------------------------------------------------------
# The state of the TUI
# ---------------------------------------------------------------------------


class TestTheState:
    """The state carries the number to the panel."""

    def test_it_holds_the_iteration_and_the_budget(self):
        """The numbers arrive in the state."""
        state = TuiState()
        state.update_workflow_iteration(3, 500)

        assert state.workflow_iteration == 3
        assert state.max_iterations == 500

    def test_a_fresh_state_knows_no_budget(self):
        """The state does not carry a budget that nobody gave it.

        It used to carry ten — a number that was never measured and
        never true: the agent of the multi-window console runs with a
        budget of five hundred.
        """
        state = TuiState()

        assert state.max_iterations == 0
        assert state.workflow_iteration == 0

    def test_a_budget_of_zero_does_not_replace_a_known_budget(self):
        """The absence of a budget is not a budget."""
        state = TuiState()
        state.update_workflow_iteration(1, 500)
        state.update_workflow_iteration(2, 0)

        assert state.max_iterations == 500

    def test_a_new_request_starts_the_iteration_again(self):
        """A new request is a new run."""
        state = TuiState()
        state.update_workflow_iteration(7, 500)

        state.set_busy(True, "a new question")

        assert state.workflow_iteration == 0
        assert state.max_iterations == 500, "the budget of the run is still known"

    def test_a_negative_number_is_not_a_number(self):
        """The state does not hold a negative iteration."""
        state = TuiState()
        state.update_workflow_iteration(-5, -1)

        assert state.workflow_iteration == 0
        assert state.max_iterations == 0


# ---------------------------------------------------------------------------
# The readout
# ---------------------------------------------------------------------------


class TestTheReadout:
    """What the panel shows."""

    def test_it_shows_the_iteration_and_the_budget(self):
        """The number of the panel is the number of the run."""
        state = TuiState()
        state.update_workflow_iteration(3, 500)

        text = _render_text(state)

        assert "3/500" in text

    def test_it_shows_the_budget_and_not_a_made_up_one(self):
        """The denominator is the budget of the run.

        The panel used to say "0/10" — ten was the number the state
        carried when nobody had told it anything, and the agent of the
        multi-window console runs with a budget of five hundred.
        """
        state = TuiState()
        state.update_workflow_iteration(0, 500)

        text = _render_text(state)

        assert "0/500" in text
        assert "/10 " not in text, "the panel still shows the made-up budget"

    def test_it_shows_no_budget_that_nobody_gave(self):
        """A state that knows no budget shows no budget.

        The panel used to divide the iteration by one when the budget
        was not known - a budget nobody gave, and a bar that was full
        because of it.
        """
        state = TuiState()
        state.update_workflow_iteration(3, 0)

        text = _render_text(state)

        assert "Workflow Iteration: 3" in text
        assert "/1" not in text, "the panel shows a budget nobody gave"

    def test_the_bar_moves_with_the_iteration(self):
        """The bar is the share of the budget that is spent."""
        empty = TuiState()
        empty.update_workflow_iteration(0, 500)
        spent = TuiState()
        spent.update_workflow_iteration(250, 500)

        assert "█" in _render_text(spent)
        assert "█" not in _render_text(empty)

    def test_it_shows_the_iteration_of_the_run_that_is_running(self, agent, memory):
        """The panel shows what the agent did while it worked."""
        state = TuiState()
        agent.iteration_observer = (
            lambda it, budget: state.update_workflow_iteration(it, budget)
        )

        _run(agent, memory)

        text = _render_text(state)
        assert "3/10" in text, f"the panel does not show the iteration: {text!r}"
