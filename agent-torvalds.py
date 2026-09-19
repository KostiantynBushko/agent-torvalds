"""
Torvalds AI Agent - Main Orchestrator

This is the actual agent that coordinates all toolkits. It provides a unified
interface to all capabilities with support for both:
  - Full tool loading (all tools available at once)
  - On-demand tool retrieval (tools loaded semantically per query)

Usage:
    python agent-torvalds.py              # Default mode (retriever-based)
    python agent-torvalds.py --full       # Load all tools upfront
    python agent-torvalds.py --top-k 10   # Adjust retrieval count
    python agent-torvalds.py --no-stats   # Disable request statistics
"""
import asyncio
import argparse
import json
import logging
import os
import sys
import uuid
from pathlib import Path

from llama_index.core.callbacks import CallbackManager
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.llms.ollama import Ollama
from rich.console import Console

# ---------------------------------------------------------------------------
# Import toolkits
# ---------------------------------------------------------------------------
from agent_git_toolkit import get_all_tools as get_git_tools
from agent_os_toolkit import get_all_tools as get_os_tools
from agent_db_toolkit import get_all_tools as get_db_tools
from agent_math_toolkit import get_all_tools as get_math_tools
from agent_linux_toolkit import get_all_tools as get_linux_tools
from agent_github_toolkit import get_all_tools as get_github_tools
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
from agent_stats_handler import (
    RequestStatsHandler,
    StatsRenderer,
    STATS_ENABLED,
    STATS_PERSIST,
    STATS_VERBOSE,
    STATS_FORMAT,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REQUEST_TIMEOUT = int(os.environ.get("TORVALDS_REQUEST_TIMEOUT", "99999"))
MAX_ITERATIONS = int(os.environ.get("TORVALDS_MAX_ITERATIONS", "50"))
TOKEN_LIMITS = int(os.environ.get("TORVALDS_TOKEN_LIMIT", "400"))
MODEL = os.environ.get("TORVALDS_MODEL", "richardyoung/qwen3.6-27b-abliterated:Q4_K_M")
SIMILARITY_TOP_K = int(os.environ.get("TORVALDS_SIMILARITY_TOP_K", "8"))

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
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)

console = Console()
stats_renderer = StatsRenderer(console)


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

def create_agent(use_retriever: bool = True, top_k: int = SIMILARITY_TOP_K):
    """
    Create and configure the Torvalds agent.

    Args:
        use_retriever: If True, use on-demand tool retrieval.
                       If False, load all tools upfront.
        top_k: Number of tools to retrieve per query (only used with retriever mode).

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
        # ---- Full tool loading mode ----
        console.print("[dim]Loading ALL tools upfront (legacy mode)[/dim]")

        all_tools = (
            get_math_tools()
            + get_git_tools()
            + get_os_tools()
            + get_db_tools()
            + get_linux_tools()
            + get_cache_tools()
        )

        agent = FunctionAgent(
            tools=all_tools,
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
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------

async def prompt_handler(cmd: str, agent: FunctionAgent, enable_stats: bool = True):
    """
    Process a single command through the agent.

    Args:
        cmd: User input string
        agent: FunctionAgent instance
        enable_stats: Whether to collect and return statistics

    Returns:
        tuple: (response_text, stats) if enable_stats else (response_text, None)
    """
    handler = None

    if enable_stats:
        request_id = str(uuid.uuid4())[:8]
        handler = RequestStatsHandler(request_id=request_id, user_query=cmd)
        callback_manager = CallbackManager([handler])
    else:
        callback_manager = CallbackManager([])

    try:
        chat_memory = agent_chat_memory.get_chat_memory()
        increment_session_commands()

        result = await agent.run(
            cmd,
            memory=chat_memory,
            max_iterations=MAX_ITERATIONS,
            callback_manager=callback_manager,
        )

        response_text = (
            result.get("output")
            if isinstance(result, dict)
            else str(result)
        )

        if handler:
            stats = handler.finalize()
            return response_text, stats

        return response_text, None

    except Exception as e:
        import traceback
        from agent_cache_system import log_error
        log_error(str(e))

        if handler:
            stats = handler.finalize()
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
    args = parse_args()

    # Determine if stats are enabled (CLI flag overrides env var)
    stats_enabled = STATS_ENABLED and not args.no_stats

    console.print("[cyan]Torvalds AI Agent[/cyan]")
    console.print(f"[dim]Model: {MODEL} | Max iterations: {MAX_ITERATIONS}[/dim]")
    if stats_enabled:
        console.print(
            f"[dim]Stats: enabled (format={STATS_FORMAT}, verbose={'on' if STATS_VERBOSE else 'off'})[/dim]"
        )
    else:
        console.print("[dim]Stats: disabled[/dim]")
    console.print("[dim]Type '\\exit' or '\\quit' to terminate.[/dim]")
    console.print("[dim]Type '\\stats' to view statistics summary.[/dim]\n")

    # Start a cache session
    start_session()

    # Create agent
    agent = create_agent(use_retriever=not args.full, top_k=args.top_k)

    while True:
        cmd = console.input("[green]>>> [/green]").strip()
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

        if not cmd:
            continue

        with console.status("[yellow]Processing...[/yellow]", spinner="dots"):
            try:
                response, stats = await prompt_handler(
                    cmd, agent, enable_stats=stats_enabled
                )
            except Exception as e:
                response = f"[red]Error: {e}[/red]"
                stats = None

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
