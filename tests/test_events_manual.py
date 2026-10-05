#!/usr/bin/env python3
"""
Manual Event Testing Script

This script allows you to manually test the EventConsumer and related components
(StateHandler, SpinnerController) by simulating LlamaIndex workflow events.

Usage:
    # Run all tests:
    python test_events_manual.py
    
    # Run specific test:
    python test_events_manual.py --test test_tool_call_events
    
    # Run with verbose output:
    python test_events_manual.py --verbose
    
    # Interactive mode (press Enter to trigger each event):
    python test_events_manual.py --interactive
"""
import asyncio
import argparse
import sys
from pathlib import Path

# Add parent directory to path so we can import components
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from rich.console import Console
from components.spinner_controller import SpinnerController
from components.state_handler import StateHandler
from components.event_consumer import (
    EventConsumer,
    DEFAULT_INTERACTIVE_TOOLS,
    WORKFLOW_EVENTS_AVAILABLE,
)

# Import event classes (real or fallback)
try:
    from llama_index.core.workflow import Event, StopEvent
    from llama_index.core.agent.workflow import (
        AgentInput, AgentSetup, AgentOutput, AgentStream, ToolCall, ToolCallResult,
    )
except ImportError:
    print("[WARN] LlamaIndex not installed. Using fallback event classes.")
    from components.event_consumer import (
        Event, StopEvent, AgentInput, AgentSetup, AgentOutput,
        AgentStream, ToolCall, ToolCallResult,
    )

console = Console()


# ─── Helper Functions ──────────────────────────────────────────────────────────

def create_test_consumer(verbose=False):
    """Create a fresh EventConsumer for testing."""
    spinner = SpinnerController(
        console=console,
        status_text="[yellow]Processing...[/yellow]",
        spinner_style="dots",
    )
    state = StateHandler()
    consumer = EventConsumer(
        spinner_controller=spinner,
        state_handler=state,
        console=console,
        verbose=verbose,
    )
    return consumer, spinner, state


def print_section(title: str):
    """Print a section header."""
    console.print(f"\n{'─'*60}")
    console.print(f"[bold cyan]{title}[/bold cyan]")
    console.print(f"{'─'*60}\n")


def print_state_summary(state: StateHandler):
    """Print current state summary."""
    console.print("[dim]Current State:[/dim]")
    console.print(f"  workflow_running: {state.get('workflow_running')}")
    console.print(f"  workflow_paused:  {state.get('workflow_paused')}")
    console.print(f"  current_tool:     {state.get('current_tool')}")
    console.print(f"  tool_calls:       {state.get('tool_calls')}")
    console.print(f"  errors:           {len(state.get('errors', []))}")
    console.print(f"  tool_history:     {len(state.get('tool_history', []))}")
    console.print()


# ─── Test Cases ────────────────────────────────────────────────────────────────

async def test_basic_event_routing():
    """Test 1: Basic event routing - events go to correct handlers."""
    print_section("Test 1: Basic Event Routing")
    consumer, spinner, state = create_test_consumer(verbose=True)
    
    # Track which handlers were called
    called_handlers = []
    
    async def on_tool_call(event):
        called_handlers.append("ToolCall")
        console.print(f"[green]✓ ToolCall handler called for: {event.tool_name}[/green]")
    
    async def on_tool_result(event):
        called_handlers.append("ToolCallResult")
        console.print(f"[green]✓ ToolCallResult handler called for: {event.tool_name}[/green]")
    
    consumer.register_callback("ToolCall", on_tool_call)
    consumer.register_callback("ToolCallResult", on_tool_result)
    
    # Simulate events by calling handlers directly
    tool_call = ToolCall(
        tool_name="execute_shell_command",
        tool_kwargs={"command": "ls -la"},
        tool_id="tc_123",
    )
    await consumer._handle_event(tool_call)
    
    tool_result = ToolCallResult(
        tool_name="execute_shell_command",
        tool_output=type("MockOutput", (), {"content": "file1.py\nfile2.py"})(),
        tool_id="tc_123",
    )
    await consumer._handle_event(tool_result)
    
    # Verify
    assert "ToolCall" in called_handlers, "ToolCall handler should have been called"
    assert "ToolCallResult" in called_handlers, "ToolCallResult handler should have been called"
    console.print("[bold green]✓ PASS: Basic event routing works![/bold green]")
    print_state_summary(state)


async def test_interactive_tool_spinner_pause():
    """Test 2: Spinner pauses for interactive tools."""
    print_section("Test 2: Interactive Tool Spinner Pause/Resume")
    consumer, spinner, state = create_test_consumer()
    
    spinner.start()
    console.print(f"Spinner running: {spinner.is_running}")
    assert spinner.is_running, "Spinner should be running"
    
    # Simulate an interactive tool call (should pause spinner)
    interactive_tool = ToolCall(
        tool_name="install_package",
        tool_kwargs={"package_name": "ffmpeg"},
        tool_id="tc_456",
    )
    await consumer._handle_event(interactive_tool)
    
    console.print(f"Spinner paused: {spinner.is_paused}")
    assert spinner.is_paused, "Spinner should be paused for interactive tool"
    assert state.get("workflow_paused"), "State should show workflow_paused=True"
    
    # Simulate tool completion (should resume spinner)
    result = ToolCallResult(
        tool_name="install_package",
        tool_output=type("MockOutput", (), {"content": "Package installed"})(),
        tool_id="tc_456",
    )
    await consumer._handle_event(result)
    
    console.print(f"Spinner resumed: {not spinner.is_paused}")
    assert not spinner.is_paused, "Spinner should be resumed after tool completes"
    assert not state.get("workflow_paused"), "State should show workflow_paused=False"
    
    spinner.stop()
    console.print("[bold green]✓ PASS: Spinner pause/resume works for interactive tools![/bold green]")
    print_state_summary(state)


async def test_non_interactive_tool_no_pause():
    """Test 3: Non-interactive tools don't pause the spinner."""
    print_section("Test 3: Non-Interactive Tool (No Spinner Pause)")
    consumer, spinner, state = create_test_consumer()
    
    spinner.start()
    
    # Non-interactive tool
    normal_tool = ToolCall(
        tool_name="ls",
        tool_kwargs={"path": "/tmp"},
        tool_id="tc_789",
    )
    await consumer._handle_event(normal_tool)
    
    assert not spinner.is_paused, "Spinner should NOT pause for non-interactive tool"
    
    result = ToolCallResult(
        tool_name="ls",
        tool_output=type("MockOutput", (), {"content": "file1\nfile2"})(),
        tool_id="tc_789",
    )
    await consumer._handle_event(result)
    
    assert not spinner.is_paused, "Spinner should still be running"
    
    spinner.stop()
    console.print("[bold green]✓ PASS: Non-interactive tools don't pause spinner![/bold green]")
    print_state_summary(state)


async def test_state_tracking():
    """Test 4: State is properly tracked across events."""
    print_section("Test 4: State Tracking")
    consumer, spinner, state = create_test_consumer()
    
    # Simulate multiple tool calls
    for i, tool_name in enumerate(["pwd", "ls", "read_file", "execute_shell_command"]):
        tc = ToolCall(tool_name=tool_name, tool_kwargs={}, tool_id=f"tc_{i}")
        await consumer._handle_event(tc)
        
        result = ToolCallResult(
            tool_name=tool_name,
            tool_output=type("MockOutput", (), {"content": "result"})(),
            tool_id=f"tc_{i}",
        )
        await consumer._handle_event(result)
    
    # Verify state
    assert state.get("tool_calls") == 4, f"Expected 4 tool calls, got {state.get('tool_calls')}"
    assert len(state.get("tool_history")) == 4, "Should have 4 entries in tool history"
    assert state.get("current_tool") == "execute_shell_command", "Last tool should be execute_shell_command"
    
    console.print(f"Tool calls recorded: {state.get('tool_calls')}")
    console.print(f"Tool history entries: {len(state.get('tool_history'))}")
    console.print(f"Current tool: {state.get('current_tool')}")
    console.print("[bold green]✓ PASS: State tracking works correctly![/bold green]")
    print_state_summary(state)


async def test_error_handling():
    """Test 5: Errors are properly tracked."""
    print_section("Test 5: Error Tracking")
    consumer, spinner, state = create_test_consumer()
    
    # Simulate an error result
    error_result = ToolCallResult(
        tool_name="run_postgres_query",
        tool_output=type("MockOutput", (), {"content": "Error: connection refused"})(),
        tool_id="tc_err",
    )
    await consumer._handle_event(error_result)
    
    history = state.get("tool_history")
    last_call = history[-1]
    assert last_call["error"], "Should mark tool call as error"
    
    console.print(f"Error detected in tool call: {last_call['error']}")
    console.print("[bold green]✓ PASS: Errors are properly tracked![/bold green]")
    print_state_summary(state)


async def test_custom_callback_registration():
    """Test 6: Custom callbacks can be registered."""
    print_section("Test 6: Custom Callback Registration")
    consumer, spinner, state = create_test_consumer()
    
    callback_called = []
    
    async def my_custom_callback(event):
        callback_called.append(event.tool_name)
        console.print(f"[magenta]Custom callback fired for: {event.tool_name}[/magenta]")
    
    consumer.register_callback("ToolCall", my_custom_callback)
    
    # Trigger event
    tc = ToolCall(tool_name="multiply", tool_kwargs={"a": 5, "b": 3}, tool_id="tc_cb")
    await consumer._handle_event(tc)
    
    assert "multiply" in callback_called, "Custom callback should have been called"
    console.print("[bold green]✓ PASS: Custom callbacks work![/bold green]")
    print_state_summary(state)


async def test_add_remove_interactive_tools():
    """Test 7: Dynamic management of interactive tool list."""
    print_section("Test 7: Dynamic Interactive Tool Management")
    consumer, spinner, state = create_test_consumer()
    
    spinner.start()
    
    # Initially, 'add' is not interactive
    tc1 = ToolCall(tool_name="add", tool_kwargs={"a": 1, "b": 2}, tool_id="tc_a")
    await consumer._handle_event(tc1)
    assert not spinner.is_paused, "add should not pause initially"
    console.print("[green]✓ 'add' did not pause spinner (correct)[/green]")
    
    # Add 'add' to interactive tools
    consumer.add_interactive_tools(["add"])
    tc2 = ToolCall(tool_name="add", tool_kwargs={"a": 3, "b": 4}, tool_id="tc_b")
    await consumer._handle_event(tc2)
    assert spinner.is_paused, "add should now pause spinner"
    console.print("[green]✓ 'add' now pauses spinner after adding to interactive list[/green]")
    
    consumer._handle_event(ToolCallResult(tool_name="add", tool_output=type("MO", (), {"content": "7"})(), tool_id="tc_b"))
    
    # Remove 'add' from interactive tools
    consumer.remove_interactive_tools(["add"])
    tc3 = ToolCall(tool_name="add", tool_kwargs={"a": 5, "b": 6}, tool_id="tc_c")
    await consumer._handle_event(tc3)
    assert not spinner.is_paused, "add should no longer pause spinner"
    console.print("[green]✓ 'add' no longer pauses spinner after removing from interactive list[/green]")
    
    spinner.stop()
    console.print("[bold green]✓ PASS: Dynamic interactive tool management works![/bold green]")
    print_state_summary(state)


async def test_agent_stream_event():
    """Test 8: AgentStream events are handled (no-op by default)."""
    print_section("Test 8: AgentStream Event Handling")
    consumer, spinner, state = create_test_consumer()
    
    # AgentStream events should be handled without errors
    stream_events = [
        AgentStream(delta="Hello", prefix=True, suffix=False),
        AgentStream(delta=" world", prefix=False, suffix=False),
        AgentStream(delta="!", prefix=False, suffix=True),
    ]
    
    for event in stream_events:
        await consumer._handle_event(event)
    
    console.print("[green]✓ AgentStream events handled without errors[/green]")
    console.print("[bold green]✓ PASS: AgentStream events work![/bold green]")
    print_state_summary(state)


async def test_stop_event():
    """Test 9: StopEvent marks workflow as complete."""
    print_section("Test 9: StopEvent Handling")
    consumer, spinner, state = create_test_consumer()
    
    state.set("workflow_running", True)
    
    stop_event = StopEvent(result="Workflow complete")
    await consumer._handle_event(stop_event)
    
    assert not state.get("workflow_running"), "Workflow should be marked as not running"
    console.print("[green]✓ StopEvent marked workflow as complete[/green]")
    console.print("[bold green]✓ PASS: StopEvent handling works![/bold green]")
    print_state_summary(state)


async def test_cancel_workflow():
    """Test 10: Workflow can be cancelled."""
    print_section("Test 10: Workflow Cancellation")
    consumer, spinner, state = create_test_consumer()
    
    consumer._running = True
    assert consumer.is_running
    
    consumer.cancel()
    assert not consumer.is_running
    console.print("[green]✓ Workflow cancelled successfully[/green]")
    console.print("[bold green]✓ PASS: Cancellation works![/bold green]")


# ─── Interactive Mode ──────────────────────────────────────────────────────────

async def run_interactive_mode():
    """Interactive mode: manually trigger events one by one."""
    print_section("Interactive Event Testing Mode")
    console.print("[yellow]Press Enter to trigger the next event. Type 'quit' to exit.[/yellow]")
    
    consumer, spinner, state = create_test_consumer(verbose=True)
    spinner.start()
    
    events = [
        ("ToolCall: pwd", ToolCall(tool_name="pwd", tool_kwargs={}, tool_id="tc1")),
        ("ToolCallResult: pwd", ToolCallResult(tool_name="pwd", tool_output=type("MO", (), {"content": "/home/user"})(), tool_id="tc1")),
        ("ToolCall: install_package (interactive)", ToolCall(tool_name="install_package", tool_kwargs={"package_name": "git"}, tool_id="tc2")),
        ("ToolCallResult: install_package", ToolCallResult(tool_name="install_package", tool_output=type("MO", (), {"content": "OK"})(), tool_id="tc2")),
        ("ToolCall: ls", ToolCall(tool_name="ls", tool_kwargs={"path": "."}, tool_id="tc3")),
        ("ToolCallResult: ls", ToolCallResult(tool_name="ls", tool_output=type("MO", (), {"content": "file1\nfile2"})(), tool_id="tc3")),
        ("StopEvent", StopEvent(result="Done")),
    ]
    
    for name, event in events:
        console.print(f"\n[dim]Next event: {name}[/dim]")
        try:
            input("[dim]Press Enter to trigger... (or type 'quit')[/dim]")
        except EOFError:
            break
        await consumer._handle_event(event)
        print_state_summary(state)
    
    spinner.stop()
    console.print("[bold green]Interactive test complete![/bold green]")


# ─── Main ──────────────────────────────────────────────────────────────────────

TESTS = {
    "test_basic_event_routing": test_basic_event_routing,
    "test_interactive_tool_spinner_pause": test_interactive_tool_spinner_pause,
    "test_non_interactive_tool_no_pause": test_non_interactive_tool_no_pause,
    "test_state_tracking": test_state_tracking,
    "test_error_handling": test_error_handling,
    "test_custom_callback_registration": test_custom_callback_registration,
    "test_add_remove_interactive_tools": test_add_remove_interactive_tools,
    "test_agent_stream_event": test_agent_stream_event,
    "test_stop_event": test_stop_event,
    "test_cancel_workflow": test_cancel_workflow,
}


async def run_tests(test_names: list = None, verbose: bool = False):
    """Run specified tests or all tests."""
    if test_names is None:
        test_names = list(TESTS.keys())
    
    console.print(f"[bold]Running {len(test_names)} test(s)...[/bold]")
    
    passed = 0
    failed = 0
    for test_name in test_names:
        try:
            await TESTS[test_name]()
            passed += 1
        except AssertionError as e:
            console.print(f"[bold red]✗ FAIL: {test_name} - {e}[/bold red]")
            failed += 1
        except Exception as e:
            console.print(f"[bold red]✗ ERROR: {test_name} - {e}[/bold red]")
            failed += 1
    
    console.print(f"\n[bold]Results: {passed} passed, {failed} failed[/bold]")
    return failed == 0


def main():
    parser = argparse.ArgumentParser(description="Manual Event Testing for EventConsumer")
    parser.add_argument("--test", type=str, help="Run a specific test by name")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("--interactive", action="store_true", help="Run in interactive mode")
    parser.add_argument("--list", action="store_true", help="List available tests")
    
    args = parser.parse_args()
    
    if args.list:
        console.print("[bold]Available tests:[/bold]")
        for name in TESTS:
            console.print(f"  - {name}")
        return
    
    if args.interactive:
        asyncio.run(run_interactive_mode())
        return
    
    test_names = [args.test] if args.test else None
    asyncio.run(run_tests(test_names, verbose=args.verbose))


if __name__ == "__main__":
    main()
