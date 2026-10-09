"""
Torvalds AI Agent - Main Orchestrator

This is the actual agent that coordinates all toolkits. It provides a unified
interface to all capabilities with support for three startup modes:
  1. Default: on-demand tool retrieval (top-8 tools per query)
  2. Full: --full loads all tools upfront
  3. Select: --select lets the user interactively choose which tools to load

Features:
  - Real-time event streaming from workflow
  - Spinner pause/resume during interactive tools
  - Agent state tracking and management
  - Whiptail password dialog integration
  - Dynamic logging level control via --log-level CLI argument
  - Graceful signal handling (SIGINT/SIGTERM) for clean shutdown
  - Human-in-the-Loop (HITL) support with runtime toggle
  - Interactive startup tool selection with --select

Usage:
    python agent-torvalds.py              # Default mode (retriever-based, INFO logging)
    python agent-torvalds.py --full       # Load all tools upfront
    python agent-torvalds.py --select     # Interactively select tools before starting
    python agent-torvalds.py --top-k 10   # Adjust retrieval count
    python agent-torvalds.py --no-stats   # Disable request statistics
    python agent-torvalds.py --log-level DEBUG  # Enable debug logging

Environment Variables:
    TORVALDS_HITL_ENABLED       Enable/disable HITL (default: true)
    TORVALDS_HITL_METHOD        Input method: 'console' or 'whiptail' (default: console)
    TORVALDS_HITL_TIMEOUT       Timeout in seconds for HITL prompts (default: 30)
    TORVALDS_HITL_DEFAULT_ANSWER Default answer on timeout (default: empty)
    TORVALDS_HITL_RUNTIME_TOGGLE  Enable/disable runtime toggle commands (default: true)
"""
import asyncio
import argparse
import json
import logging
import os
import signal
import sys
import uuid
import platform
from pathlib import Path
from typing import Optional, List

from llama_index.core.callbacks import CallbackManager
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.tools import FunctionTool
from llama_index.llms.ollama import Ollama
from rich import status
from rich.console import Console

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
    increment_session_commands,
    save_request_stats,
    get_stats_summary,
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
# Components
# ---------------------------------------------------------------------------
from components.spinner_controller import SpinnerController
from components.state_handler import StateHandler
from components.event_consumer import EventConsumer

# ---------------------------------------------------------------------------
# HITL Components (Step 8: Agent Integration)
# ---------------------------------------------------------------------------
from components.human_loop_handler import HumanLoopHandler
from components.timeout_manager import TimeoutManager
from components.hitl_runtime_toggle import HITLRuntimeToggle
from components.console_input_module import ConsoleInputModule
from components.whiptail_input_module import WhiptailInputModule

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REQUEST_TIMEOUT = int(os.environ.get("TORVALDS_REQUEST_TIMEOUT", "99999"))
MAX_ITERATIONS = int(os.environ.get("TORVALDS_MAX_ITERATIONS", "50"))
TOKEN_LIMITS = int(os.environ.get("TORVALDS_TOKEN_LIMIT", "400"))
MODEL = os.environ.get("TORVALDS_MODEL", "richardyoung/qwen3.6-27b-abliterated:Q4_K_M")
SIMILARITY_TOP_K = int(os.environ.get("TORVALDS_SIMILARITY_TOP_K", "8"))

# Feature flags for event streaming
ENABLE_EVENT_STREAMING = os.environ.get("TORVALDS_EVENT_STREAMING", "true").lower() in ("true", "1", "yes")
ENABLE_VERBOSE_EVENTS = os.environ.get("TORVALDS_VERBOSE_EVENTS", "false").lower() in ("true", "1", "yes")

# ---------------------------------------------------------------------------
# HITL Configuration via Environment Variables
# ---------------------------------------------------------------------------
HITL_ENABLED = os.environ.get("TORVALDS_HITL_ENABLED", "true").lower() == "true"
HITL_METHOD = os.environ.get("TORVALDS_HITL_METHOD", "console")  # "console" or "whiptail"
HITL_TIMEOUT = int(os.environ.get("TORVALDS_HITL_TIMEOUT", "30"))
HITL_DEFAULT_ANSWER = os.environ.get("TORVALDS_HITL_DEFAULT_ANSWER", "")
HITL_RUNTIME_TOGGLE = os.environ.get("TORVALDS_HITL_RUNTIME_TOGGLE", "true").lower() == "true"

SYSTEM_PROMPT = (
    "Your name is Torvalds an AI assistant that can directly interact with the host operating system and a wide range of technical tools."
    "Core capabilities"
    "OS‑level access: browse file systems, run shell commands, launch/manage processes, work with network shares, containers, VMs, etc."
    "Database work: execute SQL queries (PostgreSQL, MySQL, SQLite, Snowflake, BigQuery, …) and inspect schemas."
    "Technical & scientific tasks: math, statistics, data analysis (pandas/NumPy), plotting, physics/engineering calculations."
    "Software development & architecture: generate/refactor code (Python, JavaScript, Go, Java, …), run tests, linting, build automation, create diagrams, and provide architectural advice."
    ""
    "Operational guidelines"
    "Tool‑first: always use the provided functions/tools for calculations, file ops, SQL, etc. – never simulate results."
    "Safety first: before any destructive action (delete, drop, modify production data, etc.) ask for explicit confirmation and, when possible, offer a dry‑run preview."
    "Git Safety: Do not commit or push changes to any repository unless explicitly requested. Always preview changes (e.g., via git status or git diff) and wait for explicit user confirmation before executing git commit or git push."
    "Clarity & transparency: state what you're doing, why, and what the expected outcome is. Surface exact error messages and suggest remediation."
    "Context awareness: keep track of the current directory, active databases, running processes, and any in‑progress scripts to avoid repetitive prompts."
    "Documentation: when you create code or scripts, also generate a short README or comment block explaining purpose, usage, and prerequisites."
    ""
    "Optional output‑format comment – keep it concise unless the user asks for a specific style."
    ""
    "Source URL: git@github.com:KostiantynBushko/agent-torvalds.git"
    ""
    "Self-Development Rules:"
    "1. When asked to update source code, always perform the changes in the 'self-development' directory located at: ${PWD}/self-development"
    "2. Do not modify the main repository directly for development tasks; use the self-development clone."
    "3. Remember these rules for future interactions."
)

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------

VALID_LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
DEFAULT_LOG_LEVEL = "INFO"


def configure_logging(level_name: str = DEFAULT_LOG_LEVEL) -> None:
    """
    Centralized logging configuration.

    Sets up the root logger with the specified level, a consistent format
    including timestamps and module names, and outputs to stderr (best
    practice — keeps logs separate from stdout).

    Args:
        level_name: Logging level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).
                    Defaults to INFO.
    """
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
        force=True,  # Reconfigure even if basicConfig was already called
    )


# Apply default logging configuration at module level
configure_logging(DEFAULT_LOG_LEVEL)

console = Console()
stats_renderer = StatsRenderer(console)


# ---------------------------------------------------------------------------
# Global spinner controller instance (accessed by toolkit modules)
# ---------------------------------------------------------------------------
spinner_controller = SpinnerController(console)


# ---------------------------------------------------------------------------
# HITL Runtime Toggle (global instance)
# ---------------------------------------------------------------------------
hitl_toggle = HITLRuntimeToggle(
    initial_state=HITL_ENABLED,
    console=console,
)


# ---------------------------------------------------------------------------
# HITL Handler (global instance — wired into callback manager)
# ---------------------------------------------------------------------------
# Note: event_consumer is set later after it's created
human_loop_handler = HumanLoopHandler(
    input_method=HITL_METHOD,
    default_timeout=HITL_TIMEOUT,
    default_answer=HITL_DEFAULT_ANSWER,
    console=console,
    spinner=spinner_controller,
    enable_hitl=HITL_ENABLED,
    runtime_toggle=hitl_toggle,
)


# ---------------------------------------------------------------------------
# Signal handling for graceful shutdown
# ---------------------------------------------------------------------------

_shutdown_requested = False


def _signal_handler(signum, frame):
    """
    Handle SIGINT (Ctrl+C) and SIGTERM for graceful shutdown.

    Stops the spinner, ends the session, and exits cleanly.
    If called a second time, force-exits immediately.
    """
    global _shutdown_requested

    if _shutdown_requested:
        # Second signal — force exit without further cleanup
        console.print("\n[yellow]Force quitting...[/yellow]")
        spinner_controller.stop()
        try:
            from agent_cache_system import end_session
            end_session()
        except Exception:
            pass
        sys.exit(130 if signum == signal.SIGINT else 143)

    _shutdown_requested = True
    spinner_controller.stop()
    console.print("\n[yellow]Signal received, shutting down gracefully...[/yellow]")

    try:
        from agent_cache_system import end_session
        end_session()
    except Exception:
        pass

    console.print("[yellow]Goodbye![/yellow]")
    sys.exit(0 if signum == signal.SIGTERM else 0)


def _setup_signal_handlers():
    """Register signal handlers for graceful shutdown."""
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)


# ---------------------------------------------------------------------------
# Helper: collect all tools from every toolkit
# ---------------------------------------------------------------------------

def _collect_all_tools() -> List[FunctionTool]:
    """
    Gather every available tool from all toolkit modules.

    This mirrors the tool collection logic used in both the retriever
    and full-loading modes, so the --select mode sees the same set
    of tools that would otherwise be available.

    Returns:
        List of all FunctionTool instances.
    """
    all_tools = (
        get_math_tools()
        + get_git_tools()
        + get_github_tools()
        + get_os_tools()
        + get_db_tools()
        + get_apt_tools()
        + get_cache_tools()
    )

    os_name = platform.system()
    if os_name == "Windows":
        all_tools += get_windows_tools()
    elif os_name == "Linux":
        all_tools += get_linux_tools()

    return all_tools


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

def create_agent(
    use_retriever: bool = True,
    top_k: int = SIMILARITY_TOP_K,
    tools: Optional[List[FunctionTool]] = None,
):
    """
    Create and configure the Torvalds agent.

    Args:
        use_retriever: If True, use on-demand tool retrieval.
                       If False, load tools upfront.
        top_k: Number of tools to retrieve per query (only used with retriever mode).
        tools: Pre-selected list of tools (used when --select is active).
               If None and use_retriever is False, all tools are loaded.

    Returns:
        FunctionAgent instance
    """
    llm = Ollama(model=MODEL, request_timeout=REQUEST_TIMEOUT)
    chat_memory = agent_chat_memory.get_chat_memory()

    if use_retriever:
        # ---- On-demand tool retrieval mode ----
        from agent_tool_retriever import create_agent_with_retriever

        console.print(f"[dim]Using on-demand tool retrieval (top_k={top_k})[/dim]")

        agent = create_agent_with_retriever(
            llm=llm,
            memory=chat_memory,
            system_prompt=SYSTEM_PROMPT,
            max_iterations=MAX_ITERATIONS,
            similarity_top_k=top_k,
        )
    else:
        # ---- Full / selected tool loading mode ----
        if tools is None:
            console.print("[dim]Loading ALL tools upfront (legacy mode)[/dim]")
            tools = _collect_all_tools()
        else:
            console.print(f"[dim]Loading {len(tools)} user-selected tools[/dim]")

        agent = FunctionAgent(
            tools=tools,
            llm=llm,
            max_iterations=MAX_ITERATIONS,
            memory=chat_memory,
            system_prompt=SYSTEM_PROMPT,
        )

    return agent


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Torvalds AI Agent")

    # Mutually exclusive group for startup mode selection
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--full",
        action="store_true",
        help="Load all tools upfront instead of using on-demand retrieval",
    )
    mode.add_argument(
        "--select",
        action="store_true",
        help="Interactively select which tools to load before starting the agent",
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
        help="Disable event streaming (legacy behavior)",
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
        help="Set logging verbosity level (default: %(default)s). "
             "Options: DEBUG, INFO, WARNING, ERROR, CRITICAL",
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
        help="Disable runtime HITL toggle commands (toggle-hitl, hitl-status, etc.)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# HITL Command Handler
# ---------------------------------------------------------------------------

async def handle_hitl_command(cmd: str) -> Optional[str]:
    """
    Handle HITL interactive commands.

    Args:
        cmd: The command string to process.

    Returns:
        Response message if it was a HITL command, None otherwise.
    """
    if hitl_toggle.is_hitl_command(cmd):
        result = await hitl_toggle.process_command(cmd)
        if result:
            # Also update the human_loop_handler's enable_hitl flag
            human_loop_handler.enable_hitl = hitl_toggle.is_enabled
            return result
    return None


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------

async def prompt_handler(cmd: str, agent: FunctionAgent, enable_stats: bool = True, event_consumer: Optional[EventConsumer] = None):
    """
    Process a single command through the agent.

    Uses event streaming to provide real-time feedback and spinner control.

    Args:
        cmd: User input string
        agent: FunctionAgent instance
        enable_stats: Whether to collect and return statistics
        event_consumer: Optional pre-configured EventConsumer (for HITL integration)

    Returns:
        tuple: (response_text, stats) if enable_stats else (response_text, None)
    """
    stats_handler = None

    # Build callback manager with HITL handler
    callback_handlers = []

    if enable_stats:
        request_id = str(uuid.uuid4())[:8]
        stats_handler = RequestStatsHandler(request_id=request_id, user_query=cmd)
        callback_handlers.append(stats_handler)

    # Add HITL handler to callback manager
    callback_handlers.append(human_loop_handler)

    callback_manager = CallbackManager(callback_handlers)

    try:
        chat_memory = agent_chat_memory.get_chat_memory()
        increment_session_commands()

        # Create workflow handler
        workflow_handler = agent.run(
            cmd,
            memory=chat_memory,
            max_iterations=MAX_ITERATIONS,
            callback_manager=callback_manager,
        )

        # Use event consumer for real-time feedback
        if event_consumer is None:
            state_handler = StateHandler()
            event_consumer = EventConsumer(
                spinner_controller=spinner_controller,
                state_handler=state_handler,
                console=console,
                verbose=ENABLE_VERBOSE_EVENTS,
            )

        # Wire event consumer into human loop handler
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
        from agent_cache_system import log_error
        log_error(str(e))

        if stats_handler:
            stats = stats_handler.finalize()
            stats.errors.append(str(e))
            return f"Error: {e}\n{traceback.format_exc()}", stats

        return f"Error: {e}\n{traceback.format_exc()}", None


def render_stats_summary(summary: dict) -> None:
    """Render the stats summary table."""
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
    table.add_row(
        "📈 Avg Tokens/Request",
        f"{summary.get('avg_tokens_per_request', 0):,.1f}",
    )
    table.add_row(
        "⏱️ Avg Duration",
        f"{summary.get('avg_duration_ms', 0):,.1f}ms",
    )
    table.add_row(
        "🔁 Avg LLM Calls/Request",
        f"{summary.get('avg_llm_calls_per_request', 0):,.1f}",
    )
    table.add_row("⚠️ Total Errors", str(summary.get("total_errors", 0)))

    panel = Panel(
        table,
        title="[bold yellow]📊 Request Statistics Summary[/bold yellow]",
        border_style="yellow",
        padding=(1, 1),
    )
    console.print(panel)


async def main():
    # Set up signal handlers before anything else
    _setup_signal_handlers()

    args = parse_args()

    # Apply logging configuration from CLI argument (reconfigures if different from default)
    configure_logging(args.log_level)

    # Determine if stats are enabled (CLI flag overrides env var)
    stats_enabled = STATS_ENABLED and not args.no_stats

    # Determine if event streaming is enabled
    events_enabled = ENABLE_EVENT_STREAMING and not args.no_events
    verbose_events = ENABLE_VERBOSE_EVENTS or args.verbose_events

    # HITL configuration (CLI overrides env vars)
    hitl_enabled = HITL_ENABLED and not args.no_hitl
    hitl_method = args.hitl_method
    hitl_timeout = args.hitl_timeout
    hitl_default_answer = args.hitl_default_answer
    runtime_toggle_enabled = HITL_RUNTIME_TOGGLE and not args.hitl_no_runtime_toggle

    # Update global HITL components with CLI values
    hitl_toggle._enabled = hitl_enabled
    human_loop_handler.enable_hitl = hitl_enabled
    human_loop_handler.input_method = hitl_method
    human_loop_handler.default_timeout = hitl_timeout

    # Re-initialize input modules based on method
    if hitl_method == "whiptail":
        human_loop_handler.whiptail_input = WhiptailInputModule()
    else:
        human_loop_handler.console_input = ConsoleInputModule(console)

    console.print("[cyan]Torvalds AI Agent[/cyan]")
    console.print(f"[dim]Model: {MODEL} | Max iterations: {MAX_ITERATIONS}[/dim]")
    console.print(f"[dim]Logging: {args.log_level}[/dim]")
    if stats_enabled:
        console.print(
            f"[dim]Stats: enabled (format={STATS_FORMAT}, verbose={'on' if STATS_VERBOSE else 'off'})[/dim]"
        )
    else:
        console.print("[dim]Stats: disabled[/dim]")
    console.print(
        f"[dim]Event streaming: {'enabled' if events_enabled else 'disabled'}[/dim]"
    )
    console.print(
        f"[dim]HITL: {'enabled' if hitl_enabled else 'disabled'} (method={hitl_method}, timeout={hitl_timeout}s)[/dim]"
    )
    console.print("[dim]Type '\\exit' or '\\quit' to terminate.[/dim]")
    console.print("[dim]Type '\\stats' to view statistics summary.[/dim]")
    if runtime_toggle_enabled:
        console.print("[dim]Type '\\hitl-status' to check HITL status.[/dim]")
        console.print("[dim]Type 'toggle-hitl' to enable/disable HITL at runtime.[/dim]")
    console.print("[dim]Press Ctrl+C to exit gracefully.[/dim]\n")

    # Start a cache session
    start_session()

    # -----------------------------------------------------------------------
    # Startup mode decision: default (retriever) | --full | --select
    # -----------------------------------------------------------------------
    selected_tools: Optional[List[FunctionTool]] = None

    if args.select:
        # ---- Interactive tool selection mode ----
        from agent_tool_selection import select_tools_interactively

        selected_tools = select_tools_interactively()

        if not selected_tools:
            console.print("[yellow]No tools selected. Exiting.[/yellow]")
            from agent_cache_system import end_session
            end_session()
            console.print("[yellow]Goodbye![/yellow]")
            return

        console.print(
            f"[green]Starting agent with {len(selected_tools)} selected tool(s)...[/green]"
        )

    # Create agent
    agent = create_agent(
        use_retriever=not args.full and not args.select,
        top_k=args.top_k,
        tools=selected_tools,
    )

    # Create shared EventConsumer instance
    state_handler = StateHandler()
    event_consumer = EventConsumer(
        spinner_controller=spinner_controller,
        state_handler=state_handler,
        console=console,
        verbose=verbose_events,
        hitl_timeout=hitl_timeout,
        hitl_default_answer=hitl_default_answer,
        hitl_enabled=hitl_enabled,
    )

    while True:
        try:
            cmd = console.input("[green]>>> [/green]").strip()
        except EOFError:
            # Handle EOF (e.g., piped input ends)
            console.print("\n[yellow]EOF received, shutting down...[/yellow]")
            from agent_cache_system import end_session
            end_session()
            console.print("[yellow]Goodbye![/yellow]")
            break
        except KeyboardInterrupt:
            # Handle Ctrl+C during input
            console.print("\n[yellow]Interrupted, shutting down...[/yellow]")
            from agent_cache_system import end_session
            end_session()
            console.print("[yellow]Goodbye![/yellow]")
            break

        if cmd.lower() in ("\\exit", "\\quit"):
            from agent_cache_system import end_session
            end_session()
            console.print("[yellow]Goodbye![/yellow]")
            break

        if cmd.lower() == "\\stats":
            # Show statistics summary
            summary = get_stats_summary()
            render_stats_summary(summary)
            continue

        if cmd.lower() == "\\hitl-status" and runtime_toggle_enabled:
            # Show HITL status
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

        # Check for HITL commands (only if runtime toggle is enabled)
        if runtime_toggle_enabled:
            hitl_response = await handle_hitl_command(cmd)
        if hitl_response:
            console.print(f"[cyan]{hitl_response}[/cyan]")
            continue

        # Use the global spinner controller
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
        console.print(response, style="bold white")
        console.rule()

        # Render stats if enabled and available
        if stats_enabled and stats:
            stats_renderer.render(stats)

            # Persist stats to cache if configured
            if STATS_PERSIST:
                save_request_stats(stats.to_dict())


if __name__ == "__main__":
    asyncio.run(main())
