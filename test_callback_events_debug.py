#!/usr/bin/env python3
"""
Debug Callback Event Tester for Agent Torvalds

This script tests how the agent emits callbacks by:
1. Running the agent in debug mode with verbose event logging
2. Creating custom callback handlers to capture ALL events
3. Giving the agent a multi-tool prompt to trigger various event types
4. Verifying all events are properly handled and routed

Usage:
    cd self-development
    python test_callback_events_debug.py
    
    # Or with specific test:
    python test_callback_events_debug.py --test test_full_workflow
    
    # List available tests:
    python test_callback_events_debug.py --list
"""
import asyncio
import logging
import sys
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import defaultdict

# Add self-development to path
sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Import LlamaIndex components
from llama_index.core.callbacks import CallbackManager
from llama_index.core.callbacks.schema import CBEventType, EventPayload
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.tools import ToolOutput
from llama_index.llms.ollama import Ollama

# Import our components
from components.spinner_controller import SpinnerController
from components.state_handler import StateHandler
from components.event_consumer import EventConsumer
from components.human_loop_handler import HumanLoopHandler
from components.hitl_events import AgentQuestionEvent, AgentAnswerEvent

# Import toolkits
from agent_math_toolkit import get_all_tools as get_math_tools
from agent_os_toolkit import get_all_tools as get_os_tools
from agent_git_toolkit import get_all_tools as get_git_tools
from agent_cache_system import get_all_tools as get_cache_tools

console = Console()

# ---------------------------------------------------------------------------
# Debug Event Collector - Captures ALL callback events
# ---------------------------------------------------------------------------

class DebugEventCollector:
    """
    Custom callback handler that captures ALL events for debugging.
    
    This tracks:
    - Event types and counts
    - Event payloads
    - Timing information
    - Tool call details
    - Errors
    """
    
    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.events: List[Dict[str, Any]] = []
        self.event_counts: Dict[str, int] = defaultdict(int)
        self.tool_calls: List[Dict[str, Any]] = []
        self.tool_results: List[Dict[str, Any]] = []
        self.errors: List[str] = []
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        
        # Track event timing
        self.event_timeline: List[Dict[str, Any]] = []
        
    def on_event_start(
        self,
        event_type: CBEventType,
        payload: Optional[Dict[str, Any]] = None,
        event_id: str = "",
        parent_id: str = "",
        **kwargs: Any,
    ) -> str:
        """Capture event start."""
        timestamp = datetime.now().isoformat()
        event_info = {
            "type": "start",
            "event_type": event_type.value if hasattr(event_type, 'value') else str(event_type),
            "event_id": event_id,
            "parent_id": parent_id,
            "timestamp": timestamp,
            "payload_keys": list(payload.keys()) if payload else [],
        }
        
        self.events.append(event_info)
        self.event_counts[f"{event_info['event_type']}_start"] += 1
        self.event_timeline.append({
            "time": timestamp,
            "action": "EVENT_START",
            "type": event_info["event_type"],
        })
        
        if self.verbose:
            console.print(
                f"[dim][{timestamp}][/dim] [cyan]▶ EVENT_START[/cyan] "
                f"[yellow]{event_info['event_type']}[/yellow] "
                f"[dim]id={event_id[:8] if event_id else 'none'}[/dim]"
            )
        
        return event_id
    
    def on_event_end(
        self,
        event_type: CBEventType,
        payload: Optional[Dict[str, Any]] = None,
        event_id: str = "",
        **kwargs: Any,
    ) -> None:
        """Capture event end."""
        timestamp = datetime.now().isoformat()
        event_info = {
            "type": "end",
            "event_type": event_type.value if hasattr(event_type, 'value') else str(event_type),
            "event_id": event_id,
            "timestamp": timestamp,
            "payload_keys": list(payload.keys()) if payload else [],
        }
        
        self.events.append(event_info)
        self.event_counts[f"{event_info['event_type']}_end"] += 1
        self.event_timeline.append({
            "time": timestamp,
            "action": "EVENT_END",
            "type": event_info["event_type"],
        })
        
        if self.verbose:
            console.print(
                f"[dim][{timestamp}][/dim] [green]◀ EVENT_END[/green] "
                f"[yellow]{event_info['event_type']}[/yellow] "
                f"[dim]id={event_id[:8] if event_id else 'none'}[/dim]"
            )
    
    def on_error(self, error: Exception, **kwargs: Any) -> None:
        """Capture errors."""
        self.errors.append(str(error))
        if self.verbose:
            console.print(f"[red]⚠ ERROR: {error}[/red]")
    
    def start_trace(self, trace_id: Optional[str] = None) -> None:
        """Capture trace start."""
        self.start_time = datetime.now().timestamp()
        self.event_timeline.append({
            "time": datetime.now().isoformat(),
            "action": "TRACE_START",
            "trace_id": trace_id,
        })
        if self.verbose:
            console.print(f"[magenta]🔍 TRACE_START[/magenta] [dim]id={trace_id}[/dim]")
    
    def end_trace(
        self,
        trace_id: Optional[str] = None,
        trace_map: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        """Capture trace end."""
        self.end_time = datetime.now().timestamp()
        self.event_timeline.append({
            "time": datetime.now().isoformat(),
            "action": "TRACE_END",
            "trace_id": trace_id,
        })
        if self.verbose:
            console.print(f"[magenta]🔍 TRACE_END[/magenta] [dim]id={trace_id}[/dim]")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all captured events."""
        duration = 0
        if self.start_time and self.end_time:
            duration = self.end_time - self.start_time
        
        return {
            "total_events": len(self.events),
            "event_counts": dict(self.event_counts),
            "tool_calls": len(self.tool_calls),
            "tool_results": len(self.tool_results),
            "errors": len(self.errors),
            "duration_seconds": round(duration, 2),
            "unique_event_types": list(set(
                e["event_type"] for e in self.events
            )),
        }


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

async def test_event_consumer_basic():
    """Test 1: EventConsumer basic event handling."""
    console.print("\n" + "═" * 60)
    console.print("[bold cyan]Test 1: EventConsumer Basic Event Handling[/bold cyan]")
    console.print("═" * 60 + "\n")
    
    # Create components
    spinner = SpinnerController(console, "[yellow]Processing...[/yellow]")
    state = StateHandler()
    consumer = EventConsumer(
        spinner_controller=spinner,
        state_handler=state,
        console=console,
        verbose=True,
    )
    
    # Track events
    captured_events = []
    
    async def capture_callback(event):
        event_type = type(event).__name__
        captured_events.append({
            "type": event_type,
            "timestamp": datetime.now().isoformat(),
        })
        console.print(f"[dim]Captured: {event_type}[/dim]")
    
    # Register callback for ToolCall events
    consumer.register_callback("ToolCall", capture_callback)
    consumer.register_callback("ToolCallResult", capture_callback)
    
    # Import event classes
    try:
        from llama_index.core.agent.workflow import ToolCall, ToolCallResult
        from llama_index.core.workflow import StopEvent
        
        # Simulate events
        console.print("\n[yellow]Simulating events...[/yellow]\n")
        
        # Event 1: ToolCall
        tc = ToolCall(
            tool_name="pwd",
            tool_kwargs={},
            tool_id="test_001",
        )
        await consumer._handle_event(tc)
        
        # Event 2: ToolCallResult - Fixed with proper ToolOutput and required fields
        tool_output = ToolOutput(
            tool_name="pwd",
            content="/home/user",
            raw_input={},
        )
        tcr = ToolCallResult(
            tool_name="pwd",
            tool_kwargs={},
            tool_output=tool_output,
            tool_id="test_001",
            return_direct=False,
        )
        await consumer._handle_event(tcr)
        
        # Event 3: StopEvent
        stop = StopEvent(result="Done")
        await consumer._handle_event(stop)
        
        # Verify
        console.print(f"\n[green]✓ Captured {len(captured_events)} events[/green]")
        console.print(f"  Tool calls in state: {state.get('tool_calls')}")
        console.print(f"  Tool history entries: {len(state.get('tool_history', []))}")
        console.print(f"  Workflow running: {state.get('workflow_running')}")
        
        assert len(captured_events) == 4, f"Expected 4 events, got {len(captured_events)}"
        assert state.get('tool_calls') == 1, "Should have 1 tool call"
        assert not state.get('workflow_running'), "Workflow should be stopped"
        
        console.print("[bold green]✓ PASS: EventConsumer basic handling works![/bold green]")
        return True
        
    except ImportError as e:
        console.print(f"[yellow]⚠ Skipping - LlamaIndex events not available: {e}[/yellow]")
        return True


async def test_callback_manager_integration():
    """Test 2: CallbackManager integration with custom handlers."""
    console.print("\n" + "═" * 60)
    console.print("[bold cyan]Test 2: CallbackManager Integration[/bold cyan]")
    console.print("═" * 60 + "\n")
    
    # Create debug collector
    debug_collector = DebugEventCollector(verbose=True)
    
    # Create callback manager with our handler
    callback_manager = CallbackManager([debug_collector])
    
    console.print("\n[yellow]Testing callback manager event routing...[/yellow]\n")
    
    # Simulate some events through the callback manager
    # Fixed: Use valid CBEventType values and valid EventPayload keys
    test_event_types = [
        CBEventType.LLM,
        CBEventType.AGENT_STEP,
        CBEventType.FUNCTION_CALL,
    ]
    
    for event_type in test_event_types:
        event_id = f"test_{event_type.value}"
        
        # Start event - use QUERY_STR instead of BLOCK_TEXT
        callback_manager.on_event_start(
            event_type=event_type,
            payload={EventPayload.QUERY_STR: "test payload"},
            event_id=event_id,
        )
        
        # End event
        callback_manager.on_event_end(
            event_type=event_type,
            payload={EventPayload.RESPONSE: "test result"},
            event_id=event_id,
        )
    
    # Trigger trace events
    callback_manager.start_trace("test_trace_001")
    callback_manager.end_trace("test_trace_001")
    
    # Verify
    summary = debug_collector.get_summary()
    
    console.print(f"\n[green]✓ Captured {summary['total_events']} events[/green]")
    console.print(f"  Unique event types: {len(summary['unique_event_types'])}")
    console.print(f"  Errors: {summary['errors']}")
    
    # Print event counts table
    table = Table(title="Event Counts")
    table.add_column("Event Type", style="cyan")
    table.add_column("Count", justify="right", style="green")
    
    for event_type, count in sorted(summary['event_counts'].items()):
        table.add_row(event_type, str(count))
    
    console.print(table)
    
    assert summary['total_events'] >= 6, f"Expected at least 6 events, got {summary['total_events']}"
    
    console.print("[bold green]✓ PASS: CallbackManager integration works![/bold green]")
    return True


async def test_hitl_events():
    """Test 3: HITL event emission and handling."""
    console.print("\n" + "═" * 60)
    console.print("[bold cyan]Test 3: HITL Event Emission[/bold cyan]")
    console.print("═" * 60 + "\n")
    
    # Create components
    spinner = SpinnerController(console, "[yellow]Processing...[/yellow]")
    state = StateHandler()
    consumer = EventConsumer(
        spinner_controller=spinner,
        state_handler=state,
        console=console,
        verbose=True,
        hitl_enabled=False,  # Disable for testing (no actual prompts)
    )
    
    console.print("\n[yellow]Testing HITL event classes...[/yellow]\n")
    
    # Test AgentQuestionEvent
    question_event = AgentQuestionEvent(
        question="Should I install nginx?",
        question_id="q-001",
        timeout=30,
        default_answer="yes",
        input_type="yesno",
    )
    
    console.print(f"[cyan]Created AgentQuestionEvent:[/cyan]")
    console.print(f"  Question: {question_event.question}")
    console.print(f"  ID: {question_event.question_id}")
    console.print(f"  Type: {question_event.input_type}")
    console.print(f"  Timeout: {question_event.timeout}s")
    
    # Validate
    question_event.validate()
    console.print("[green]✓ Question event validated[/green]")
    
    # Test AgentAnswerEvent
    answer_event = AgentAnswerEvent(
        question_id="q-001",
        answer="yes",
        was_timeout=False,
    )
    
    console.print(f"\n[cyan]Created AgentAnswerEvent:[/cyan]")
    console.print(f"  Question ID: {answer_event.question_id}")
    console.print(f"  Answer: {answer_event.answer}")
    console.print(f"  Timeout: {answer_event.was_timeout}")
    
    # Validate
    answer_event.validate()
    console.print("[green]✓ Answer event validated[/green]")
    
    # Test HITL stats
    hitl_stats = consumer.get_hitl_stats()
    console.print(f"\n[cyan]HITL Stats:[/cyan]")
    console.print(f"  Enabled: {hitl_stats['enabled']}")
    console.print(f"  Questions: {hitl_stats['question_count']}")
    console.print(f"  Timeouts: {hitl_stats['timeout_count']}")
    
    console.print("[bold green]✓ PASS: HITL events work correctly![/bold green]")
    return True


async def test_spinner_pause_resume():
    """Test 4: Spinner pause/resume during interactive tools."""
    console.print("\n" + "═" * 60)
    console.print("[bold cyan]Test 4: Spinner Pause/Resume for Interactive Tools[/bold cyan]")
    console.print("═" * 60 + "\n")
    
    spinner = SpinnerController(console, "[yellow]Processing...[/yellow]")
    state = StateHandler()
    consumer = EventConsumer(
        spinner_controller=spinner,
        state_handler=state,
        console=console,
        verbose=True,
    )
    
    console.print("\n[yellow]Testing spinner pause/resume...[/yellow]\n")
    
    spinner.start()
    console.print(f"Spinner started: {spinner.is_running}")
    assert spinner.is_running, "Spinner should be running"
    
    # Test interactive tool (should pause)
    try:
        from llama_index.core.agent.workflow import ToolCall, ToolCallResult
        
        interactive_tool = ToolCall(
            tool_name="install_package",
            tool_kwargs={"package_name": "test-pkg"},
            tool_id="tc_interactive",
        )
        await consumer._handle_event(interactive_tool)
        
        console.print(f"Spinner paused after interactive tool: {spinner.is_paused}")
        assert spinner.is_paused, "Spinner should be paused for interactive tool"
        
        # Complete the tool - Fixed with proper ToolOutput and required fields
        tool_output = ToolOutput(
            tool_name="install_package",
            content="Package installed",
            raw_input={},
        )
        result = ToolCallResult(
            tool_name="install_package",
            tool_kwargs={"package_name": "test-pkg"},
            tool_output=tool_output,
            tool_id="tc_interactive",
            return_direct=False,
        )
        await consumer._handle_event(result)
        
        console.print(f"Spinner resumed after tool completion: {not spinner.is_paused}")
        assert not spinner.is_paused, "Spinner should resume after tool completes"
        
        # Test non-interactive tool (should NOT pause)
        normal_tool = ToolCall(
            tool_name="pwd",
            tool_kwargs={},
            tool_id="tc_normal",
        )
        await consumer._handle_event(normal_tool)
        
        console.print(f"Spinner NOT paused for normal tool: {not spinner.is_paused}")
        assert not spinner.is_paused, "Spinner should NOT pause for non-interactive tool"
        
        spinner.stop()
        console.print("[bold green]✓ PASS: Spinner pause/resume works![/bold green]")
        return True
        
    except ImportError:
        console.print("[yellow]⚠ Skipping - LlamaIndex events not available[/yellow]")
        return True


async def test_state_tracking():
    """Test 5: State tracking across multiple tool calls."""
    console.print("\n" + "═" * 60)
    console.print("[bold cyan]Test 5: State Tracking Across Tool Calls[/bold cyan]")
    console.print("═" * 60 + "\n")
    
    spinner = SpinnerController(console)
    state = StateHandler()
    consumer = EventConsumer(
        spinner_controller=spinner,
        state_handler=state,
        console=console,
        verbose=True,
    )
    
    console.print("\n[yellow]Testing state tracking...[/yellow]\n")
    
    try:
        from llama_index.core.agent.workflow import ToolCall, ToolCallResult
        
        tools = ["pwd", "ls", "check_path_exists", "read_file"]
        
        for i, tool_name in enumerate(tools):
            # Tool call
            tc = ToolCall(
                tool_name=tool_name,
                tool_kwargs={"path": "/tmp"} if tool_name in ["ls", "check_path_exists", "read_file"] else {},
                tool_id=f"tc_{i}",
            )
            await consumer._handle_event(tc)
            
            # Tool result - Fixed with proper ToolOutput and required fields
            tool_output = ToolOutput(
                tool_name=tool_name,
                content=f"Result from {tool_name}",
                raw_input={},
            )
            tcr = ToolCallResult(
                tool_name=tool_name,
                tool_kwargs={"path": "/tmp"} if tool_name in ["ls", "check_path_exists", "read_file"] else {},
                tool_output=tool_output,
                tool_id=f"tc_{i}",
                return_direct=False,
            )
            await consumer._handle_event(tcr)
            
            console.print(f"[dim]Processed: {tool_name}[/dim]")
        
        # Verify state
        console.print(f"\n[cyan]Final State:[/cyan]")
        console.print(f"  Tool calls: {state.get('tool_calls')}")
        console.print(f"  Tool history entries: {len(state.get('tool_history', []))}")
        console.print(f"  Current tool: {state.get('current_tool')}")
        
        tool_summary = state.get_tool_summary()
        console.print(f"  Summary: {tool_summary}")
        
        assert state.get('tool_calls') == len(tools), f"Expected {len(tools)} tool calls"
        assert len(state.get('tool_history')) == len(tools), "Should have matching history"
        
        console.print("[bold green]✓ PASS: State tracking works![/bold green]")
        return True
        
    except ImportError:
        console.print("[yellow]⚠ Skipping - LlamaIndex events not available[/yellow]")
        return True


async def test_full_workflow():
    """Test 6: Full workflow with actual agent (requires Ollama)."""
    console.print("\n" + "═" * 60)
    console.print("[bold cyan]Test 6: Full Workflow with Agent (requires Ollama)[/bold cyan]")
    console.print("═" * 60 + "\n")
    
    # Check if Ollama is available
    import subprocess
    try:
        result = subprocess.run(
            ["curl", "-s", "http://localhost:11434/api/version"],
            capture_output=True, timeout=5
        )
        if result.returncode != 0:
            console.print("[yellow]⚠ Ollama not running - skipping full workflow test[/yellow]")
            return True
    except (subprocess.SubprocessError, FileNotFoundError):
        console.print("[yellow]⚠ Ollama not available - skipping full workflow test[/yellow]")
        return True
    
    console.print("[green]Ollama detected - running full workflow test[/green]\n")
    
    # Create debug collector
    debug_collector = DebugEventCollector(verbose=True)
    
    # Create callback manager
    callback_manager = CallbackManager([debug_collector])
    
    # Create agent with minimal tools
    console.print("[yellow]Creating agent with test tools...[/yellow]\n")
    
    try:
        from llama_index.core.memory import ChatMemoryBuffer
        
        MODEL = os.environ.get("TORVALDS_MODEL", "richardyoung/qwen3.6-27b-abliterated:Q4_K_M")
        llm = Ollama(model=MODEL, request_timeout=30)
        
        # Use just math tools for quick test
        all_tools = get_math_tools()
        
        console.print(f"Loaded {len(all_tools)} tools")
        
        agent = FunctionAgent(
            tools=all_tools,
            llm=llm,
            max_iterations=5,
            memory=ChatMemoryBuffer.from_defaults(),
            system_prompt="You are a helpful assistant. Use tools to answer questions.",
        )
        
        # Run agent with a simple math question
        test_query = "What is 42 multiplied by 7?"
        console.print(f"\n[yellow]Running agent with query: '{test_query}'[/yellow]\n")
        
        workflow_handler = agent.run(
            test_query,
            callback_manager=callback_manager,
        )
        
        # Create event consumer
        spinner = SpinnerController(console, "[yellow]Thinking...[/yellow]")
        state = StateHandler()
        consumer = EventConsumer(
            spinner_controller=spinner,
            state_handler=state,
            console=console,
            verbose=True,
        )
        
        spinner.start()
        try:
            result = await consumer.consume_events(workflow_handler, test_query)
        finally:
            spinner.stop()
        
        # Print results
        console.print("\n" + "═" * 60)
        console.print("[bold cyan]Results[/bold cyan]")
        console.print("═" * 60 + "\n")
        
        console.print(f"[green]Agent Response:[/green]")
        if isinstance(result, dict):
            console.print(result.get('output', str(result)))
        else:
            console.print(str(result))
        
        console.print(f"\n[cyan]Event Summary:[/cyan]")
        summary = debug_collector.get_summary()
        console.print(f"  Total events captured: {summary['total_events']}")
        console.print(f"  Duration: {summary['duration_seconds']}s")
        console.print(f"  Tool calls: {summary['tool_calls']}")
        console.print(f"  Errors: {summary['errors']}")
        
        # Print state summary
        console.print(f"\n[cyan]State Summary:[/cyan]")
        console.print(f"  Tool calls tracked: {state.get('tool_calls')}")
        console.print(f"  Tool history: {len(state.get('tool_history', []))}")
        
        if state.get('tool_history'):
            console.print(f"\n[cyan]Tool History:[/cyan]")
            for entry in state.get('tool_history'):
                status = "[red]ERROR[/red]" if entry.get('error') else "[green]OK[/green]"
                console.print(f"  {status} {entry['tool']}")
        
        console.print("[bold green]✓ PASS: Full workflow test completed![/bold green]")
        return True
        
    except Exception as e:
        console.print(f"[red]✗ Full workflow test failed: {e}[/red]")
        import traceback
        console.print(traceback.format_exc())
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

TESTS = {
    "test_event_consumer_basic": test_event_consumer_basic,
    "test_callback_manager_integration": test_callback_manager_integration,
    "test_hitl_events": test_hitl_events,
    "test_spinner_pause_resume": test_spinner_pause_resume,
    "test_state_tracking": test_state_tracking,
    "test_full_workflow": test_full_workflow,
}


async def run_tests(test_names: List[str] = None, verbose: bool = True):
    """Run specified tests or all tests."""
    if test_names is None:
        test_names = list(TESTS.keys())
    
    console.print("\n" + "█" * 60)
    console.print("[bold yellow]Agent Torvalds - Callback Event Debug Tests[/bold yellow]")
    console.print(f"[dim]Running {len(test_names)} test(s)[/dim]")
    console.print("█" * 60)
    
    passed = 0
    failed = 0
    errors = []
    
    for test_name in test_names:
        try:
            result = await TESTS[test_name]()
            if result:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            console.print(f"\n[bold red]✗ ERROR in {test_name}: {e}[/bold red]")
            import traceback
            console.print(traceback.format_exc())
            failed += 1
            errors.append((test_name, str(e)))
    
    # Final summary
    console.print("\n" + "█" * 60)
    console.print("[bold yellow]Test Summary[/bold yellow]")
    console.print("█" * 60)
    
    summary_table = Table(show_header=False, box=None, padding=(0, 2))
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", justify="right", style="bold")
    
    summary_table.add_row("Tests Passed", f"[green]{passed}[/green]")
    summary_table.add_row("Tests Failed", f"[red]{failed}[/red]" if failed else "[green]0[/green]")
    summary_table.add_row("Total Tests", str(passed + failed))
    
    panel = Panel(
        summary_table,
        title="[bold]🧪 Callback Event Tests Complete[/bold]",
        border_style="yellow",
    )
    console.print(panel)
    
    if errors:
        console.print("\n[yellow]Errors:[/yellow]")
        for test_name, error in errors:
            console.print(f"  [red]• {test_name}[/red]: {error}")
    
    return failed == 0


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Debug Callback Event Tests for Agent Torvalds"
    )
    parser.add_argument(
        "--test", type=str, help="Run a specific test by name"
    )
    parser.add_argument(
        "--verbose", action="store_true", default=True, help="Enable verbose output"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Disable verbose output"
    )
    parser.add_argument(
        "--list", action="store_true", help="List available tests"
    )
    
    args = parser.parse_args()
    
    if args.list:
        console.print("[bold]Available tests:[/bold]")
        for name in TESTS:
            console.print(f"  - {name}")
        return
    
    verbose = args.verbose and not args.quiet
    
    # Configure logging
    log_level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )
    
    success = asyncio.run(run_tests(test_names=None if not args.test else [args.test], verbose=verbose))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()