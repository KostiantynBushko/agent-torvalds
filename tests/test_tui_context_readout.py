"""
The size of the context on the screen of the multi-window console.

The size of the prompt is logged with every request to the model since
2026-11-04.  The telemetry panel of the multi-window console shows the
state of the agent while it works, and the size of the context belongs
there: the operator should not have to look away from the agent to find
out how full the context is.

The number on the screen is the number in the log — the same
measurement, rendered in two lines instead of one.

The design is in ``investigate/tui-context-readout/``.

Run with:
    pytest tests/test_tui_context_readout.py -v
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.tools import FunctionTool
from llama_index.llms.ollama.base import Ollama

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent

from components.hitl_agent import HITLFunctionAgent  # noqa: E402
from components.tui.state_bridge import TuiState  # noqa: E402
from components.tui.telemetry_view import (  # noqa: E402
    TelemetryView,
    _compact_tokens,
    _share_style,
)


# ---------------------------------------------------------------------------
# The fixtures
# ---------------------------------------------------------------------------


def noop() -> str:
    """A tool that does nothing."""
    return "nothing to do"


class ScriptedOllama(Ollama):
    """An Ollama LLM that answers from a script."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("model", "fake/model")
        kwargs.setdefault("base_url", "http://localhost:11434")
        kwargs.setdefault("context_window", 1_000_000)
        super().__init__(*args, **kwargs)

    async def astream_chat(self, messages, **kwargs):
        async def gen():
            from llama_index.core.base.llms.types import (
                ChatMessage,
                ChatResponse,
                MessageRole,
            )

            yield ChatResponse(
                message=ChatMessage(
                    role=MessageRole.ASSISTANT, content="The work is done."
                )
            )

        return gen()

    async def achat(self, messages, **kwargs):
        from llama_index.core.base.llms.types import (
            ChatMessage,
            ChatResponse,
            MessageRole,
        )

        return ChatResponse(
            message=ChatMessage(
                role=MessageRole.ASSISTANT, content="The work is done."
            )
        )


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


def _run(agent, llm, memory, request="how big is the context?"):
    """Run the agent and return what the workflow answered."""

    async def _drive():
        handler = agent.run(request, memory=memory, max_iterations=10)
        try:
            return await handler
        except Exception:  # noqa: BLE001 - the run may end early
            return None

    return asyncio.run(_drive())


# ---------------------------------------------------------------------------
# The rendering of the panel
# ---------------------------------------------------------------------------


def _render_text(state, width: int = 80) -> str:
    """Render the telemetry panel and return it as plain text."""
    from rich.console import Console

    console = Console(width=width, color_system=None)
    panel = TelemetryView().render(state)
    lines = console.render_lines(panel, console.options.update(width=width))
    return "\n".join("".join(segment.text for segment in line) for line in lines)


def _styles_of(state, needle: str):
    """The styles of the segments that carry *needle*."""
    from rich.console import Console

    console = Console(width=80, color_system="standard")
    panel = TelemetryView().render(state)
    return [
        segment.style
        for segment in console.render(panel)
        if needle in segment.text
    ]


def _measured_state(**overrides) -> TuiState:
    """A state that carries a measurement of the prompt."""
    state = TuiState()
    state.update_context_size(
        tokens=39_691,
        messages=75,
        total_bytes=159_334,
        window=1_000_000,
    )
    for name, value in overrides.items():
        setattr(state, name, value)
    return state


# ---------------------------------------------------------------------------
# The observer
# ---------------------------------------------------------------------------


class TestTheObserver:
    """The agent tells whoever is watching how big the prompt is."""

    def test_the_observer_is_called_during_a_run(self, agent, llm, memory):
        """The measurement reaches the observer."""
        seen = []
        agent.context_observer = lambda size, window: seen.append((size, window))

        _run(agent, llm, memory)

        assert seen, "the observer was never called"
        size, window = seen[-1]
        assert size.messages > 0, "the measurement carries no messages"
        assert size.total_tokens > 0, "the measurement carries no tokens"
        assert window == llm.context_window, (
            "the observer was not told the window of the model"
        )

    def test_the_observer_is_called_when_the_logging_is_off(
        self, agent, llm, memory
    ):
        """--no-context-log turns the log off, not the readout off."""
        agent.context_logging_enabled = False
        seen = []
        agent.context_observer = lambda size, window: seen.append((size, window))

        _run(agent, llm, memory)

        assert seen, (
            "the observer was silenced by the logging flag — the flag "
            "turns the log off, not the panel"
        )

    def test_a_failing_observer_does_not_take_the_run_down(
        self, agent, llm, memory
    ):
        """A size is never worth a run."""

        def broken(size, window):
            raise RuntimeError("the observer is broken")

        agent.context_observer = broken

        result = _run(agent, llm, memory)

        assert result is not None, "the run died because of the observer"

    def test_no_observer_is_no_problem(self, agent, llm, memory):
        """Nobody is watching — the agent does not care."""
        assert agent.context_observer is None

        result = _run(agent, llm, memory)

        assert result is not None


# ---------------------------------------------------------------------------
# The state of the TUI
# ---------------------------------------------------------------------------


class TestTheState:
    """The state carries the measurement to the panel."""

    def test_it_holds_the_measurement(self):
        """The numbers arrive in the state."""
        state = TuiState()
        state.update_context_size(
            tokens=39_691,
            messages=75,
            total_bytes=159_334,
            window=1_000_000,
        )

        assert state.context_measured is True
        assert state.context_tokens == 39_691
        assert state.context_messages == 75
        assert state.context_bytes == 159_334
        assert state.context_window == 1_000_000
        assert state.context_estimated is False

    def test_it_knows_that_nothing_was_measured_yet(self):
        """A fresh state has no measurement."""
        state = TuiState()

        assert state.context_measured is False
        assert state.context_tokens == 0

    def test_a_negative_number_is_not_a_number(self):
        """The state does not hold a negative size."""
        state = TuiState()
        state.update_context_size(tokens=-5, messages=-1, total_bytes=-2, window=-3)

        assert state.context_tokens == 0
        assert state.context_messages == 0
        assert state.context_bytes == 0
        assert state.context_window == 0


# ---------------------------------------------------------------------------
# The readout
# ---------------------------------------------------------------------------


class TestTheReadout:
    """What the panel shows."""

    def test_it_shows_the_tokens_and_the_share(self):
        """The tokens of the prompt and the share of the window."""
        text = _render_text(_measured_state())

        assert "39,691 tok" in text
        assert "4.0% of 1M" in text

    def test_it_shows_the_messages_and_the_size(self):
        """What the tokens are made of."""
        text = _render_text(_measured_state())

        assert "75 msgs" in text
        assert "155.6 KB" in text

    def test_it_is_one_row_of_the_table(self):
        """The readout sits in the panel, under the total tokens."""
        text = _render_text(_measured_state())

        assert "Context" in text
        assert text.index("Context") < text.index("Total Tokens") + 200

    def test_before_the_first_measurement_it_shows_a_dash(self):
        """A context of zero tokens would be a lie."""
        text = _render_text(TuiState())

        assert "—" in text
        assert "tok" not in text

    def test_an_estimated_number_says_so(self):
        """The operator is told that the number is an estimate."""
        text = _render_text(_measured_state(context_estimated=True))

        assert "≈39,691 tok" in text

    def test_without_a_window_there_is_no_share(self):
        """The share needs a window to be a share of."""
        text = _render_text(_measured_state(context_window=0))

        assert "39,691 tok" in text
        assert "%" not in text

    def test_the_share_is_coloured_by_the_threshold(self):
        """Green while the context has room, red when it does not."""
        assert _share_style(0.0) == "green"
        assert _share_style(49.9) == "green"
        assert _share_style(50.0) == "yellow"
        assert _share_style(79.9) == "yellow"
        assert _share_style(80.0) == "bold red"
        assert _share_style(99.0) == "bold red"

    def test_the_colour_reaches_the_screen(self):
        """The colour of the share is on the screen, not only in the code."""
        state = _measured_state()
        state.update_context_size(
            tokens=900_000,
            messages=75,
            total_bytes=159_334,
            window=1_000_000,
        )

        styles = _styles_of(state, "90.0%")

        assert styles, "the share is not on the screen"
        assert any("red" in str(style) for style in styles), (
            f"a context of 90% is not red: {styles}"
        )

    def test_the_window_is_shortened(self):
        """The panel has room for a few characters."""
        assert _compact_tokens(1_000_000) == "1M"
        assert _compact_tokens(131_072) == "131K"
        assert _compact_tokens(999) == "999"
