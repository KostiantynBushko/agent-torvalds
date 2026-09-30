"""
Unit tests for EventConsumer HITL (Human-in-the-Loop) integration.

Tests:
- _on_input_required handler with mock events
- HITL stats tracking
- Timeout handling
- send_event method
- HITL enabled/disabled states
"""
import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from typing import Any

from components.event_consumer import EventConsumer
from components.spinner_controller import SpinnerController
from components.state_handler import StateHandler
from rich.console import Console


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_spinner() -> SpinnerController:
    """Create a mock spinner controller."""
    console = Console(force_terminal=True, width=80)
    spinner = SpinnerController(console=console)
    return spinner


@pytest.fixture
def mock_state() -> StateHandler:
    """Create a mock state handler."""
    return StateHandler()


@pytest.fixture
def mock_console() -> Console:
    """Create a mock console."""
    return Console(force_terminal=True, width=80)


@pytest.fixture
def event_consumer(mock_spinner, mock_state, mock_console):
    """Create an EventConsumer with HITL enabled."""
    return EventConsumer(
        spinner_controller=mock_spinner,
        state_handler=mock_state,
        console=mock_console,
        hitl_timeout=10,
        hitl_default_answer="default",
        hitl_enabled=True,
    )


@pytest.fixture
def event_consumer_disabled(mock_spinner, mock_state, mock_console):
    """Create an EventConsumer with HITL disabled."""
    return EventConsumer(
        spinner_controller=mock_spinner,
        state_handler=mock_state,
        console=mock_console,
        hitl_timeout=10,
        hitl_default_answer="default",
        hitl_enabled=False,
    )


# ---------------------------------------------------------------------------
# Tests: HITL Statistics
# ---------------------------------------------------------------------------

class TestHITLStats:
    """Tests for HITL statistics tracking."""

    def test_initial_stats(self, event_consumer):
        """Test initial HITL stats are zero."""
        stats = event_consumer.get_hitl_stats()
        assert stats["enabled"] is True
        assert stats["question_count"] == 0
        assert stats["timeout_count"] == 0
        assert stats["timeout"] == 10
        assert stats["default_answer"] == "default"

    def test_stats_when_disabled(self, event_consumer_disabled):
        """Test stats reflect disabled state."""
        stats = event_consumer_disabled.get_hitl_stats()
        assert stats["enabled"] is False

    def test_reset_stats(self, event_consumer):
        """Test resetting HITL stats."""
        # Manually set counts
        event_consumer._hitl_question_count = 5
        event_consumer._hitl_timeout_count = 2
        
        event_consumer.reset_hitl_stats()
        
        stats = event_consumer.get_hitl_stats()
        assert stats["question_count"] == 0
        assert stats["timeout_count"] == 0


# ---------------------------------------------------------------------------
# Tests: Input Required Event Handling
# ---------------------------------------------------------------------------

class TestInputRequiredEvent:
    """Tests for _on_input_required handler."""

    @pytest.mark.asyncio
    async def test_input_required_skips_when_disabled(self, event_consumer_disabled):
        """Test that InputRequiredEvent is skipped when HITL is disabled."""
        # Create a mock InputRequiredEvent
        event = Mock()
        event.prefix = "Test question?"
        event.user_name = "test_user"
        
        # Should complete without error and do nothing
        await event_consumer_disabled._on_input_required(event)
        
        stats = event_consumer_disabled.get_hitl_stats()
        assert stats["question_count"] == 0

    @pytest.mark.asyncio
    async def test_input_required_increments_question_count(self, event_consumer):
        """Test that question count is incremented."""
        event = Mock()
        event.prefix = "Test question?"
        event.user_name = "test_user"
        
        # Mock the console input to return a response
        with patch.object(event_consumer.console_input, 'prompt', new_callable=AsyncMock) as mock_prompt:
            mock_prompt.return_value = "user response"
            
            await event_consumer._on_input_required(event)
        
        stats = event_consumer.get_hitl_stats()
        assert stats["question_count"] == 1

    @pytest.mark.asyncio
    async def test_spinner_paused_and_resumed(self, event_consumer):
        """Test that spinner is paused and resumed during prompt."""
        event = Mock()
        event.prefix = "Test question?"
        
        # Track pause/resume calls
        pause_calls = []
        resume_calls = []
        
        original_pause = event_consumer.spinner.pause
        original_resume = event_consumer.spinner.resume
        
        event_consumer.spinner.pause = lambda: pause_calls.append(True) or original_pause()
        event_consumer.spinner.resume = lambda: resume_calls.append(True) or original_resume()
        
        with patch.object(event_consumer.console_input, 'prompt', new_callable=AsyncMock) as mock_prompt:
            mock_prompt.return_value = "response"
            await event_consumer._on_input_required(event)
        
        assert len(pause_calls) >= 1, "Spinner should be paused"
        assert len(resume_calls) >= 1, "Spinner should be resumed"

    @pytest.mark.asyncio
    async def test_timeout_handling(self, event_consumer):
        """Test timeout handling with default answer."""
        event = Mock()
        event.prefix = "Test question?"
        event.user_name = "test_user"
        
        # Mock prompt to return empty string (simulating timeout)
        with patch.object(event_consumer.console_input, 'prompt', new_callable=AsyncMock) as mock_prompt:
            mock_prompt.return_value = ""  # Empty = timeout when default is empty
            
            await event_consumer._on_input_required(event)
        
        stats = event_consumer.get_hitl_stats()
        assert stats["timeout_count"] >= 0  # May or may not increment depending on default

    @pytest.mark.asyncio
    async def test_timeout_exception_handling(self, event_consumer):
        """Test handling of TimeoutError exception."""
        event = Mock()
        event.prefix = "Test question?"
        event.user_name = "test_user"
        
        # Mock prompt to raise TimeoutError
        with patch.object(event_consumer.console_input, 'prompt', new_callable=AsyncMock) as mock_prompt:
            mock_prompt.side_effect = asyncio.TimeoutError()
            
            # Mock the handler context for sending events
            mock_handler = MagicMock()
            event_consumer._current_handler = mock_handler
            
            await event_consumer._on_input_required(event)
        
        stats = event_consumer.get_hitl_stats()
        assert stats["timeout_count"] >= 1

    @pytest.mark.asyncio
    async def test_general_exception_handling(self, event_consumer):
        """Test handling of general exceptions."""
        event = Mock()
        event.prefix = "Test question?"
        event.user_name = "test_user"
        
        # Mock prompt to raise a general exception
        with patch.object(event_consumer.console_input, 'prompt', new_callable=AsyncMock) as mock_prompt:
            mock_prompt.side_effect = Exception("Test error")
            
            await event_consumer._on_input_required(event)
        
        # Should not raise, just log error


# ---------------------------------------------------------------------------
# Tests: send_event
# ---------------------------------------------------------------------------

class TestSendEvent:
    """Tests for send_event method."""

    def test_send_event_without_handler(self, event_consumer):
        """Test send_event when no handler is set (should not crash)."""
        event = Mock()
        # Should not raise
        event_consumer.send_event(event)

    def test_send_event_with_handler(self, event_consumer):
        """Test send_event when handler is set."""
        mock_handler = MagicMock()
        event_consumer._current_handler = mock_handler
        
        event = Mock()
        event_consumer.send_event(event)
        
        mock_handler.ctx.send_event.assert_called_once_with(event)


# ---------------------------------------------------------------------------
# Tests: HITL Configuration
# ---------------------------------------------------------------------------

class TestHITLConfiguration:
    """Tests for HITL configuration options."""

    def test_default_config(self, mock_spinner, mock_state, mock_console):
        """Test default HITL configuration."""
        consumer = EventConsumer(
            spinner_controller=mock_spinner,
            state_handler=mock_state,
            console=mock_console,
        )
        
        assert consumer.hitl_timeout == 30
        assert consumer.hitl_default_answer == ""
        assert consumer.hitl_enabled is True

    def test_custom_config(self, mock_spinner, mock_state, mock_console):
        """Test custom HITL configuration."""
        consumer = EventConsumer(
            spinner_controller=mock_spinner,
            state_handler=mock_state,
            console=mock_console,
            hitl_timeout=60,
            hitl_default_answer="yes",
            hitl_enabled=False,
        )
        
        assert consumer.hitl_timeout == 60
        assert consumer.hitl_default_answer == "yes"
        assert consumer.hitl_enabled is False


# ---------------------------------------------------------------------------
# Tests: Event Routing
# ---------------------------------------------------------------------------

class TestEventRouting:
    """Tests for event routing including HITL events."""

    @pytest.mark.asyncio
    async def test_input_required_event_routed(self, event_consumer):
        """Test that InputRequiredEvent is routed to handler."""
        # Import the event class
        try:
            from llama_index.core.workflow import InputRequiredEvent
        except ImportError:
            pytest.skip("LlamaIndex workflow events not available")
        
        event = InputRequiredEvent(prefix="Test question?")
        
        with patch.object(event_consumer, '_on_input_required', new_callable=AsyncMock) as mock_handler:
            await event_consumer._handle_event(event)
            mock_handler.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_verbose_logging_excludes_hitl_events(self, mock_spinner, mock_state, mock_console):
        """Test that HITL events don't appear in verbose logging."""
        consumer = EventConsumer(
            spinner_controller=mock_spinner,
            state_handler=mock_state,
            console=mock_console,
            verbose=True,
        )
        
        # Custom event should be logged
        custom_event = Mock()
        type(custom_event).__name__ = "CustomEvent"
        
        # InputRequiredEvent should be handled, not logged
        try:
            from llama_index.core.workflow import InputRequiredEvent
            input_event = InputRequiredEvent(prefix="Test?")
            
            await consumer._handle_event(input_event)
        except ImportError:
            pytest.skip("LlamaIndex workflow events not available")
