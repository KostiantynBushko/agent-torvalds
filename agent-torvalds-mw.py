"""
Torvalds AI Agent - Multi-Window Console Orchestrator (agent-torvalds-mw.py)

This is the next-generation multi-window terminal interface for Torvalds AI Agent.
It combines all orchestrator capabilities from agent-torvalds.py with a persistent,
responsive Multi-Window Terminal User Interface (TUI):
  - Persistent Markdown Document Viewer with syntax highlighting & buffer pagination (PgUp/PgDn)
  - Dedicated Background Worker & Tool Progress monitor with iteration progress bar
  - Real-time Agent Telemetry & State inspector (token usage, cache hits, model info)
  - Non-blocking Interactive Command Bar with integrated Human-in-the-Loop (HITL) dialogs
  - Seamless fallback to classic linear REPL mode via --no-tui or in headless/piped environments

Usage:
    python agent-torvalds-mw.py                # Multi-Window TUI mode (default)
    python agent-torvalds-mw.py --no-tui       # Classic linear REPL mode
    python agent-torvalds-mw.py --full         # Load all tools upfront
    python agent-torvalds-mw.py --top-k 10     # Adjust retrieval count
    python agent-torvalds-mw.py --log-level DEBUG  # Enable debug logging
    python agent-torvalds-mw.py --tui-fps 20   # Custom TUI render refresh rate

Environment Variables:
    TORVALDS_TUI_ENABLED        Enable/disable multi-window TUI (default: true)
    TORVALDS_TUI_FPS            Render refresh rate for TUI (default: 15)
    TORVALDS_TUI_PAGING         Enable scroll buffer pagination (default: true)
    TORVALDS_HITL_ENABLED       Enable/disable HITL (default: true)
    TORVALDS_HITL_METHOD        Input method: 'console' or 'whiptail' (default: console)
    TORVALDS_HITL_TIMEOUT       Timeout in seconds for HITL prompts (default: 30)
    TORVALDS_HITL_DEFAULT_ANSWER Default answer on timeout (default: empty)
    TORVALDS_HITL_RUNTIME_TOGGLE Enable/disable runtime toggle commands (default: true)
"""
import asyncio
import argparse
import io
import json
import logging
import os
import signal
import sys
import uuid
import platform
from pathlib import Path
from typing import Optional, Tuple

from llama_index.core.callbacks import CallbackManager
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.llms.ollama import Ollama
from rich.console import Console
from rich.markdown import Markdown

# ---------------------------------------------------------------------------
# Import toolkits
# ---------------------------------------------------------------------------
from agent_git_toolkit import get_all_tools as get_git_tools
from agent_os_toolkit import get_all_tools as get_os_tools
from agent_db_toolkit import get_all_tools as get_db_tools
from agent_math_toolkit import get_all_tools as get_math_tools
from agent_linux_toolkit import get_all_tools as get_linux_tools
from agent_windows_toolkit import get_all_tools as get_windows_tools
from agent_github_toolkit import get_all_tools as get_github_tools
from agent_apt_toolkit import get_all_tools as get_apt_tools
from agent_cache_system import (
    get_all_tools as get_cache_tools,
    start_session,
    end_session,
    increment_session_commands,
    save_request_stats,
    get_stats_summary,
    log_error,
)

# ---------------------------------------------------------------------------
# Chat memory (PostgreSQL-backed with in-memory fallback)
# ---------------------------------------------------------------------------
import agent_chat_memory

# ---------------------------------------------------------------------------
# Stats handler
# ---------------------------------------------------------------------------
from components.stats_handler import (
    RequestStatsHandler,
    StatsRenderer,
    STATS_ENABLED,
    STATS_PERSIST,
    STATS_VERBOSE,
    STATS_FORMAT,
)

# ---------------------------------------------------------------------------
# Core Components
# ---------------------------------------------------------------------------
from components.spinner_controller import SpinnerController
from components.state_handler import StateHandler
from components.event_consumer import EventConsumer

# ---------------------------------------------------------------------------
# HITL Components
# ---------------------------------------------------------------------------
from components.human_loop_handler import HumanLoopHandler
from components.timeout_manager import TimeoutManager
from components.hitl_runtime_toggle import HITLRuntimeToggle
from components.console_input_module import ConsoleInputModule
from components.whiptail_input_module import WhiptailInputModule

# ---------------------------------------------------------------------------
# Multi-Window TUI Components
# ---------------------------------------------------------------------------
from components.tui import (
    build_torvalds_layout,
    TuiState,
    TuiEventAdapter,
    TuiInputModule,
    TuiApp,
)

# ---------------------------------------------------------------------------
# Configuration & Defaults
# ---------------------------------------------------------------------------
REQUEST_TIMEOUT = int(os.environ.get("TORVALDS_REQUEST_TIMEOUT", "99999"))
MAX_ITERATIONS = int(os.environ.get("TORVALDS_MAX_ITERATIONS", "500"))
TOKEN_LIMITS = int(os.environ.get("TORVALDS_TOKEN_LIMIT", "10000"))
MODEL = os.environ.get("TORVALDS_MODEL", "richardyoung/qwen3.6-27b-abliterated:Q4_K_M")
SIMILARITY_TOP_K = int(os.environ.get("TORVALDS_SIMILARITY_TOP_K", "8"))

ENABLE_EVENT_STREAMING = os.environ.get("TORVALDS_EVENT_STREAMING", "true").lower() in ("true", "1", "yes")
ENABLE_VERBOSE_EVENTS = os.environ.get("TORVALDS_VERBOSE_EVENTS", "true").lower() in ("true", "1", "yes")

HITL_ENABLED = os.environ.get("TORVALDS_HITL_ENABLED", "true").lower() == "true"
HITL_METHOD = os.environ.get("TORVALDS_HITL_METHOD", "console")
HITL_TIMEOUT = int(os.environ.get("TORVALDS_HITL_TIMEOUT", "30"))
HITL_DEFAULT_ANSWER = os.environ.get("TORVALDS_HITL_DEFAULT_ANSWER", "")
HITL_RUNTIME_TOGGLE = os.environ.get("TORVALDS_HITL_RUNTIME_TOGGLE", "true").lower() == "true"

# TUI Configuration
TUI_ENABLED_DEFAULT = os.environ.get("TORVALDS_TUI_ENABLED", "true").lower() in ("true", "1", "yes")
TUI_DEFAULT_FPS = int(os.environ.get("TORVALDS_TUI_FPS", "15"))

SYSTEM_PROMPT = (
    "You are Torvalds, a technical AI assistant that interacts with the operating system, "
    "supports software development, and assists with engineering and analytical tasks."
    "Capabilities:"
    "Work with the system environment: files, processes, commands, configurations."
    "Assist with development: code creation, refactoring, debugging, architectural guidance."
    "Support analytical and scientific workflows: computation, data handling, reasoning."
    "Help with operational tasks: automation, diagnostics, environment inspection."
    "Operating Principles:"
    "Use available system interfaces and tools when performing actions."
    "Request explicit confirmation before destructive or irreversible operations."
    "For version control: never commit or push without explicit approval; always show changes first."
    "Be clear about actions, reasoning, and expected outcomes."
    "Source:"
    "Repository: git@github.com:KostiantynBushko/agent-torvalds.git"
    "Self‑Development Rules:"
    "1. All self‑modifications must be placed in ./self-development."
    "2. Do not modify the main repository directly; use the self‑development clone."
    "3. Persist these rules for future interactions."
)

VALID_LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
DEFAULT_LOG_LEVEL = "INFO"


def configure_logging(level_name: str = DEFAULT_LOG_LEVEL, to_file: Optional[str] = None) -> None:
    """Configure logging format and destination."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    handlers = [logging.StreamHandler(sys.stderr)]
    if to_file:
        handlers.append(logging.FileHandler(to_file, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


# Apply default logging configuration
configure_logging(DEFAULT_LOG_LEVEL)

console = Console()
stats_renderer = StatsRenderer(console)
spinner_controller = SpinnerController(console)

hitl_toggle = HITLRuntimeToggle(
    initial_state=HITL_ENABLED,
    console=console,
)

human_loop_handler = HumanLoopHandler(
    input_method=HITL_METHOD,
    default_timeout=HITL_TIMEOUT,
    default_answer=HITL_DEFAULT_ANSWER,
    console=console,
    spinner=spinner_controller,
    enable_hitl=HITL_ENABLED,
    runtime_toggle=hitl_toggle,
)

# Signal handling state
_shutdown_requested = False
_active_tui_app: Optional[TuiApp] = None


def _signal_handler(signum, frame):
    """Graceful SIGINT/SIGTERM handler."""
    global _shutdown_requested, _active_tui_app

    if _shutdown_requested:
        sys.exit(130 if signum == signal.SIGINT else 143)

    _shutdown_requested = True
    if _active_tui_app and hasattr(_active_tui_app, "state"):
        _active_tui_app.state.exit_requested = True

    spinner_controller.stop()
    try:
        end_session()
    except Exception:
        pass

    sys.exit(0)


def _setup_signal_handlers():
    """Register signal handlers."""
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

def create_agent(use_retriever: bool = True, top_k: int = SIMILARITY_TOP_K, is_tui: bool = False):
    """
    Create and configure the Torvalds FunctionAgent.
    """
    llm = Ollama(
        model=MODEL,
        request_timeout=REQUEST_TIMEOUT,
        temperature=0.0,
        top_p=0.1,
    )

    chat_memory = agent_chat_memory.get_chat_memory()

    if use_retriever:
        from agent_tool_retriever import create_agent_with_retriever
        if not is_tui:
            console.print(f"[dim]Using on-demand tool retrieval (top_k={top_k})[/dim]")

        agent = create_agent_with_retriever(
            llm=llm,
            memory=chat_memory,
            system_prompt=SYSTEM_PROMPT,
            max_iterations=MAX_ITERATIONS,
            similarity_top_k=top_k,
        )
    else:
        if not is_tui:
            console.print("[dim]Loading ALL tools upfront (legacy mode)[/dim]")

        os_name = platform.system()
        all_tools = (
            get_os_tools()
            + get_github_tools()
        )
        if os_name == "Windows":
            all_tools += get_windows_tools()
        elif os_name == "Linux":
            all_tools += get_linux_tools()
            all_tools += get_apt_tools()

        agent = FunctionAgent(
            tools=all_tools,
            llm=llm,
            max_iterations=MAX_ITERATIONS,
            memory=chat_memory,
            system_prompt=SYSTEM_PROMPT,
        )

    return agent


# ---------------------------------------------------------------------------
# CLI Argument Parser
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Torvalds AI Agent - Multi-Window Console")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Load all tools upfront instead of using on-demand retrieval",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=SIMILARITY_TOP_K,
        help="Number of tools to retrieve per query (default: %(default)s)",
    )
    parser.add_argument(
        "--no-stats",
        action="store_true",
        help="Disable request statistics display",
    )
    parser.add_argument(
        "--no-events",
        action="store_true",
        help="Disable event streaming",
    )
    parser.add_argument(
        "--verbose-events",
        action="store_true",
        help="Enable verbose event logging",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=VALID_LOG_LEVELS,
        default=DEFAULT_LOG_LEVEL,
        help="Set logging verbosity level (default: %(default)s)",
    )
    parser.add_argument(
        "--no-hitl",
        action="store_true",
        help="Disable Human-in-the-Loop (HITL) support",
    )
    parser.add_argument(
        "--hitl-method",
        type=str,
        choices=["console", "whiptail"],
        default=HITL_METHOD,
        help="HITL input method (default: %(default)s)",
    )
    parser.add_argument(
        "--hitl-timeout",
        type=int,
        default=HITL_TIMEOUT,
        help="HITL prompt timeout in seconds (default: %(default)s)",
    )
    parser.add_argument(
        "--hitl-default-answer",
        type=str,
        default=HITL_DEFAULT_ANSWER,
        help="Default fallback answer on HITL timeout (default: empty)",
    )
    parser.add_argument(
        "--hitl-no-runtime-toggle",
        action="store_true",
        help="Disable runtime HITL toggle commands",
    )
    # TUI Specific Arguments
    parser.add_argument(
        "--tui",
        action="store_true",
        default=TUI_ENABLED_DEFAULT,
        help="Launch interactive multi-window TUI workspace (default: True)",
    )
    parser.add_argument(
        "--no-tui",
        action="store_false",
        dest="tui",
        help="Disable multi-window TUI and use classic linear REPL loop",
    )
    parser.add_argument(
        "--tui-fps",
        type=int,
        default=TUI_DEFAULT_FPS,
        help="Target frames per second for TUI refresh loop (default: %(default)s)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# HITL Command Handler
# ---------------------------------------------------------------------------

async def handle_hitl_command(cmd: str) -> Optional[str]:
    """Handle HITL interactive slash commands."""
    if hitl_toggle.is_hitl_command(cmd):
        result = await hitl_toggle.process_command(cmd)
        if result:
            human_loop_handler.enable_hitl = hitl_toggle.is_enabled
            return result
    return None


# ---------------------------------------------------------------------------
# Core Prompt Handler
# ---------------------------------------------------------------------------

async def prompt_handler(
    cmd: str,
    agent: FunctionAgent,
    enable_stats: bool = True,
    event_consumer: Optional[EventConsumer] = None,
) -> Tuple[str, Optional[any]]:
    """
    Process a single command through the agent workflow.
    """
    stats_handler = None
    callback_handlers = []

    if enable_stats:
        request_id = str(uuid.uuid4())[:8]
        stats_handler = RequestStatsHandler(request_id=request_id, user_query=cmd)
        callback_handlers.append(stats_handler)

    callback_handlers.append(human_loop_handler)
    callback_manager = CallbackManager(callback_handlers)

    try:
        chat_memory = agent_chat_memory.get_chat_memory()
        increment_session_commands()

        workflow_handler = agent.run(
            cmd,
            memory=chat_memory,
            max_iterations=MAX_ITERATIONS,
            callback_manager=callback_manager,
        )

        if event_consumer is None:
            state_handler = StateHandler()
            event_consumer = EventConsumer(
                spinner_controller=spinner_controller,
                state_handler=state_handler,
                console=console,
                verbose=ENABLE_VERBOSE_EVENTS,
            )

        human_loop_handler.event_consumer = event_consumer
        result = await event_consumer.consume_events(workflow_handler, cmd)

        response_text = (
            result.get("output")
            if isinstance(result, dict)
            else str(result)
        )

        if stats_handler:
            stats = stats_handler.finalize()
            return response_text, stats

        return response_text, None

    except Exception as e:
        import traceback
        log_error(str(e))
        if stats_handler:
            stats = stats_handler.finalize()
            stats.errors.append(str(e))
            return f"Error: {e}\n{traceback.format_exc()}", stats
        return f"Error: {e}\n{traceback.format_exc()}", None


def render_stats_summary(summary: dict) -> None:
    """Render the stats summary table for classic linear mode."""
    if "message" in summary:
        console.print(f"[dim]{summary['message']}[/dim]")
        return

    from rich.table import Table
    from rich.panel import Panel

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Metric", style="dim cyan")
    table.add_column("Value", style="bold white")

    table.add_row("📊 Total Requests", str(summary.get("total_requests", 0)))
    table.add_row("🔢 Total Tokens", f"{summary.get('total_tokens', 0):,}")
    table.add_row("🔁 Total LLM Calls", f"{summary.get('total_llm_calls', 0):,}")
    table.add_row("🛠️ Total Tool Calls", f"{summary.get('total_tool_calls', 0):,}")
    table.add_row("📈 Avg Tokens/Request", f"{summary.get('avg_tokens_per_request', 0):,.1f}")
    table.add_row("⏱️ Avg Duration", f"{summary.get('avg_duration_ms', 0):,.1f}ms")
    table.add_row("🔁 Avg LLM Calls/Request", f"{summary.get('avg_llm_calls_per_request', 0):,.1f}")
    table.add_row("⚠️ Total Errors", str(summary.get("total_errors", 0)))

    panel = Panel(
        table,
        title="[bold yellow]📊 Request Statistics Summary[/bold yellow]",
        border_style="yellow",
        padding=(1, 1),
    )
    console.print(panel)


# ---------------------------------------------------------------------------
# Classic Linear REPL Mode
# ---------------------------------------------------------------------------

async def run_classic_repl(args, stats_enabled: bool, events_enabled: bool, verbose_events: bool, hitl_method: str, hitl_timeout: int, runtime_toggle_enabled: bool):
    """Run classic linear REPL loop matching agent-torvalds.py."""
    console.print("[cyan]Torvalds AI Agent (Classic Linear REPL)[/cyan]")
    console.print(f"[dim]Model: {MODEL} | Max iterations: {MAX_ITERATIONS}[/dim]")
    console.print(f"[dim]Logging: {args.log_level}[/dim]")
    console.print(f"[dim]Stats: {'enabled' if stats_enabled else 'disabled'}[/dim]")
    console.print(f"[dim]Event streaming: {'enabled' if events_enabled else 'disabled'}[/dim]")
    console.print(f"[dim]HITL: {'enabled' if human_loop_handler.enable_hitl else 'disabled'} (method={hitl_method}, timeout={hitl_timeout}s)[/dim]")
    console.print("[dim]Type '\\exit' or '\\quit' to terminate.[/dim]")
    console.print("[dim]Type '\\stats' to view statistics summary.[/dim]")
    if runtime_toggle_enabled:
        console.print("[dim]Type '\\hitl-status' to check HITL status.[/dim]")
        console.print("[dim]Type '\\toggle-hitl' to enable/disable HITL at runtime.[/dim]")
    console.print("[dim]Press Ctrl+C to exit gracefully.[/dim]\n")

    start_session()
    agent = create_agent(use_retriever=not args.full, top_k=args.top_k, is_tui=False)

    state_handler = StateHandler()
    event_consumer = EventConsumer(
        spinner_controller=spinner_controller,
        state_handler=state_handler,
        console=console,
        verbose=verbose_events,
        hitl_timeout=hitl_timeout,
        hitl_default_answer=args.hitl_default_answer,
        hitl_enabled=human_loop_handler.enable_hitl,
    )

    while True:
        try:
            cmd = console.input("[green]>>> [/green]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Shutting down... Goodbye![/yellow]")
            end_session()
            break

        if cmd.lower() in ("\\exit", "\\quit"):
            end_session()
            console.print("[yellow]Goodbye![/yellow]")
            break

        if cmd.lower() == "\\stats":
            summary = get_stats_summary()
            render_stats_summary(summary)
            continue

        if cmd.lower() == "\\hitl-status" and runtime_toggle_enabled:
            status_info = hitl_toggle.status_sync()
            hitl_stats = event_consumer.get_hitl_stats()
            console.print(f"\n[cyan]HITL Status:[/cyan]")
            console.print(f"  Enabled: {'🟢 YES' if status_info['enabled'] else '🔴 NO'}")
            console.print(f"  Method: {hitl_method}")
            console.print(f"  Timeout: {hitl_timeout}s")
            console.print(f"  Questions asked: {hitl_stats['question_count']}")
            console.print(f"  Timeouts: {hitl_stats['timeout_count']}")
            console.print(f"  Toggle count: {status_info['toggle_count']}")
            continue

        if not cmd:
            continue

        if runtime_toggle_enabled:
            hitl_response = await handle_hitl_command(cmd)
            if hitl_response:
                console.print(f"[cyan]{hitl_response}[/cyan]")
                continue

        spinner_controller.start()
        try:
            response, stats = await prompt_handler(
                cmd, agent, enable_stats=stats_enabled, event_consumer=event_consumer
            )
        except Exception as e:
            response = f"[red]Error: {e}[/red]"
            stats = None
        finally:
            spinner_controller.stop()

        console.rule("[blue]Agent Response[/blue]")
        console.print(Markdown(response))
        console.rule()

        if stats_enabled and stats:
            stats_renderer.render(stats)
            if STATS_PERSIST:
                save_request_stats(stats.to_dict())


# ---------------------------------------------------------------------------
# Main Orchestrator
# ---------------------------------------------------------------------------

async def main():
    global _active_tui_app
    _setup_signal_handlers()

    args = parse_args()
    configure_logging(args.log_level)

    stats_enabled = STATS_ENABLED and not args.no_stats
    events_enabled = ENABLE_EVENT_STREAMING and not args.no_events
    verbose_events = ENABLE_VERBOSE_EVENTS or args.verbose_events

    hitl_enabled = HITL_ENABLED and not args.no_hitl
    hitl_method = args.hitl_method
    hitl_timeout = args.hitl_timeout
    hitl_default_answer = args.hitl_default_answer
    runtime_toggle_enabled = HITL_RUNTIME_TOGGLE and not args.hitl_no_runtime_toggle

    hitl_toggle._enabled = hitl_enabled
    human_loop_handler.enable_hitl = hitl_enabled
    human_loop_handler.input_method = hitl_method
    human_loop_handler.default_timeout = hitl_timeout

    # Check whether TUI mode should be launched
    is_interactive_tty = sys.stdin.isatty() if hasattr(sys.stdin, "isatty") else False
    use_tui = args.tui and is_interactive_tty

    if not use_tui:
        # Re-initialize input modules for classic console
        if hitl_method == "whiptail":
            human_loop_handler.whiptail_input = WhiptailInputModule()
        else:
            human_loop_handler.console_input = ConsoleInputModule(console)

        await run_classic_repl(
            args=args,
            stats_enabled=stats_enabled,
            events_enabled=events_enabled,
            verbose_events=verbose_events,
            hitl_method=hitl_method,
            hitl_timeout=hitl_timeout,
            runtime_toggle_enabled=runtime_toggle_enabled,
        )
        return

    # ---- Launch Multi-Window TUI Mode ----
    start_session()

    # Create thread-safe TUI state
    tui_state = TuiState()
    tui_state.model_name = MODEL
    tui_state.mode = f"Retriever (top_k={args.top_k})" if not args.full else "Full upfront"
    tui_state.hitl_enabled = hitl_enabled
    tui_state.hitl_timeout = hitl_timeout
    tui_state.hitl_default_answer = hitl_default_answer
    tui_state.active_toolkits = ["Git", "OS", "DB", "Math"]

    # Provide silent console for background EventConsumer and SpinnerController
    # to prevent terminal scroll tearing while Live is active
    tui_silent_console = Console(file=io.StringIO())
    tui_spinner_controller = SpinnerController(tui_silent_console)

    # Wire TuiInputModule for non-blocking command bar HITL prompts
    tui_input_module = TuiInputModule(tui_state)
    human_loop_handler.console_input = tui_input_module
    human_loop_handler.spinner = tui_spinner_controller

    # Create EventConsumer with silent console and connect TuiEventAdapter
    state_handler = StateHandler()
    event_consumer = EventConsumer(
        spinner_controller=tui_spinner_controller,
        state_handler=state_handler,
        console=tui_silent_console,
        verbose=verbose_events,
        hitl_timeout=hitl_timeout,
        hitl_default_answer=hitl_default_answer,
        hitl_enabled=hitl_enabled,
    )
    event_consumer.console_input = tui_input_module

    # Connect adapter callbacks
    event_adapter = TuiEventAdapter(tui_state)
    event_adapter.register_with_event_consumer(event_consumer)

    # Create Agent
    agent = create_agent(use_retriever=not args.full, top_k=args.top_k, is_tui=True)

    # Count chat memory messages
    try:
        msgs = agent_chat_memory.get_chat_memory().get()
        tui_state.memory_msg_count = len(msgs)
    except Exception:
        pass

    # Create and run TUI App
    app = TuiApp(
        agent=agent,
        prompt_handler_fn=prompt_handler,
        state=tui_state,
        console=console,
        target_fps=args.tui_fps,
        hitl_toggle=hitl_toggle,
        event_consumer=event_consumer,
        stats_enabled=stats_enabled,
    )
    _active_tui_app = app

    try:
        await app.run()
    finally:
        end_session()
        console.print("[yellow]Torvalds AI Agent session terminated. Goodbye![/yellow]")


if __name__ == "__main__":
    asyncio.run(main())
