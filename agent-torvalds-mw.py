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

Feature parity with agent-torvalds.py:
  - Startup tool selection (--select) with interactive category picker
  - Project Management: auto-scan, workspace config, project context injection
  - Chat History Manager: multi-user, multi-session chat history
  - Runtime Prompt Injection: dynamic system prompt based on the active project
  - Callback manager propagation for LLM-level event tracking

Usage:
    python agent-torvalds-mw.py                # Multi-Window TUI mode (default)
    python agent-torvalds-mw.py --no-tui       # Classic linear REPL mode
    python agent-torvalds-mw.py --full         # Load all tools upfront
    python agent-torvalds-mw.py --select       # Interactively select tools before starting
    python agent-torvalds-mw.py --top-k 10     # Adjust retrieval count
    python agent-torvalds-mw.py --log-level DEBUG  # Enable debug logging
    python agent-torvalds-mw.py --tui-fps 20   # Custom TUI render refresh rate
    python agent-torvalds-mw.py --auto-scan   # Auto-scan and configure projects on startup
    python agent-torvalds-mw.py --project-path /path/to/project  # Load a specific project
    python agent-torvalds-mw.py --context-guard-on  # Trim the prompt to the context window

TUI slash commands:
    \\tools              Open the interactive tool category selection menu
    \\tool-list          List every available tool
    \\projects           List registered projects in the workspace
    \\project-info <n>   Show details for a registered project
    \\project-status     Show the git status of the active project
    \\project-summary    Show a full workspace summary
    \\chat-sessions      List chat sessions
    \\chat-select <id>   Switch the active chat session
    \\chat-info          Show the active chat session
    \\chat-user          Show or change your own settings

Environment Variables:
    TORVALDS_TUI_ENABLED        Enable/disable multi-window TUI (default: true)
    TORVALDS_TUI_FPS            Render refresh rate for TUI (default: 15)
    TORVALDS_TUI_PAGING         Enable scroll buffer pagination (default: true)
    TORVALDS_HITL_ENABLED       Enable/disable HITL (default: true)
    TORVALDS_HITL_METHOD        Input method: 'console' or 'whiptail' (default: console)
    TORVALDS_HITL_TIMEOUT       Timeout in seconds for HITL prompts; -1 = wait
                                for the user forever, no timeout (default: -1)
    TORVALDS_HITL_DEFAULT_ANSWER Default answer on timeout (default: empty)
    TORVALDS_HITL_RUNTIME_TOGGLE Enable/disable runtime toggle commands (default: true)
    TORVALDS_PROMPT_INJECTION   Enable/disable runtime prompt injection (default: true)
    TORVALDS_PROMPT_TEMPLATE    Path to custom prompt template file
    TORVALDS_INCLUDE_RECOMMENDATIONS  Include tool recommendations in prompt (default: true)
    TORVALDS_CONTEXT_GUARD   Enable/disable the context guard (default: false)
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
from typing import List, Optional, Tuple

from llama_index.core.callbacks import CallbackManager
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.base.llms.types import ChatMessage
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.tools import FunctionTool
from llama_index.llms.ollama import Ollama
from rich.console import Console
from rich.markdown import Markdown

# ---------------------------------------------------------------------------
# Import toolkits
# ---------------------------------------------------------------------------
# The database toolkit lives in ``toolkits/`` and is optional.  It can
# fail to import for two reasons: the database drivers are not installed
# (``ImportError``), and its configuration file -
# ``db_toolkit_config.yaml``, which it reads at import time - is missing
# or malformed (``FileNotFoundError`` / ``yaml.YAMLError``).  Neither may
# take the agent down, so the adapter is imported behind a guard.
try:
    from toolkits.db_toolkit.agent_db_toolkit import (
        get_all_tools as get_db_tools,
    )
except Exception:  # pragma: no cover - the toolkit is optional

    def get_db_tools() -> list:
        """The DB toolkit is unavailable - expose no tools."""
        return []


# The math, Git, GitHub, MikroTik, Shodan, OS, Linux, APT and Windows
# toolkits live in ``toolkits/`` and are optional.  A missing or broken
# toolkit has to degrade to "no tools", never to a failed boot, so the
# adapters are imported behind a guard.
try:
    from toolkits.os_toolkit.agent_os_toolkit import (
        get_all_tools as get_os_tools,
    )
except ImportError:  # pragma: no cover - the toolkit is optional

    def get_os_tools() -> list:
        """The OS toolkit is unavailable - expose no tools."""
        return []


try:
    from toolkits.apt_toolkit.agent_apt_toolkit import (
        get_all_tools as get_apt_tools,
    )
except ImportError:  # pragma: no cover - the toolkit is optional

    def get_apt_tools() -> list:
        """The APT toolkit is unavailable - expose no tools."""
        return []


try:
    from toolkits.windows_toolkit.agent_windows_toolkit import (
        get_all_tools as get_windows_tools,
    )
except ImportError:  # pragma: no cover - the toolkit is optional

    def get_windows_tools() -> list:
        """The Windows toolkit is unavailable - expose no tools."""
        return []


try:
    from toolkits.linux_toolkit.agent_linux_toolkit import (
        get_all_tools as get_linux_tools,
    )
except ImportError:  # pragma: no cover - the toolkit is optional

    def get_linux_tools() -> list:
        """The Linux toolkit is unavailable - expose no tools."""
        return []


try:
    from toolkits.git_toolkit.agent_git_toolkit import (
        get_all_tools as get_git_tools,
    )
except ImportError:  # pragma: no cover - the toolkit is optional

    def get_git_tools() -> list:
        """The Git toolkit is unavailable - expose no tools."""
        return []


try:
    from toolkits.github_toolkit.agent_github_toolkit import (
        get_all_tools as get_github_tools,
    )
except ImportError:  # pragma: no cover - the toolkit is optional

    def get_github_tools() -> list:
        """The GitHub toolkit is unavailable - expose no tools."""
        return []


try:
    from toolkits.math_toolkit.agent_math_toolkit import (
        get_all_tools as get_math_tools,
    )
except ImportError:  # pragma: no cover - the toolkit is optional

    def get_math_tools() -> list:
        """The math toolkit is unavailable - expose no tools."""
        return []


try:
    from toolkits.mikrotik_routeros.agent_mikrotik_toolkit import (
        get_all_tools as get_mikrotik_tools,
    )
except ImportError:  # pragma: no cover - the toolkit is optional

    def get_mikrotik_tools() -> list:
        """The MikroTik toolkit is unavailable - expose no tools."""
        return []


try:
    from toolkits.shodan_toolkit.agent_shodan_toolkit import (
        get_all_tools as get_shodan_tools,
    )
except ImportError:  # pragma: no cover - the toolkit is optional

    def get_shodan_tools() -> list:
        """The Shodan toolkit is unavailable - expose no tools."""
        return []


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
# Chat History Manager (multi-user, multi-session chat history)
# ---------------------------------------------------------------------------
from chat_manager.startup import (
    initialize_chat_manager,
    get_chat_manager,
    get_memory_buffer,
    select_startup_session,
)
from chat_manager.commands.handler import is_chat_command, handle_chat_command

# ---------------------------------------------------------------------------
# Interactive command registry (powers the \help command)
# ---------------------------------------------------------------------------
from components.command_registry import (
    HelpOptions,
    build_help_text,
    is_help_command,
)

# ---------------------------------------------------------------------------
# Project Management (project detection, workspace config, git status)
# ---------------------------------------------------------------------------
from project_manager.agent_project_manager_toolkit import (
    get_all_tools as get_project_manager_tools,
    load_project,
    build_project_context,
    initialize_project_management,
)

# ---------------------------------------------------------------------------
# Runtime Prompt Injection
# ---------------------------------------------------------------------------
from project_manager.prompt_engine import PromptTemplateEngine

# ---------------------------------------------------------------------------
# Stats handler
# ---------------------------------------------------------------------------
from components.stats_handler import (
    RequestStatsHandler,
    StatsRenderer,
    bind_callback_manager,
    STATS_ENABLED,
    STATS_PERSIST,
    STATS_VERBOSE,
    STATS_FORMAT,
)

# ---------------------------------------------------------------------------
# Core Components
# ---------------------------------------------------------------------------
from components.ollama_config import apply_context_window, get_ollama_base_url
from components.spinner_controller import SpinnerController
from components.state_handler import StateHandler
from components.event_consumer import EventConsumer

# ---------------------------------------------------------------------------
# HITL Components
# ---------------------------------------------------------------------------
from components.human_loop_handler import HumanLoopHandler
from components.hitl_agent import HITLFunctionAgent
from components.timeout_manager import TimeoutManager
from components.hitl_timeout import describe_timeout
from components.hitl_runtime_toggle import HITLRuntimeToggle
from components.console_input_module import ConsoleInputModule
from components.whiptail_input_module import WhiptailInputModule

# ---------------------------------------------------------------------------
# Multi-Window TUI Components
# ---------------------------------------------------------------------------
from components.tui import (
    TuiState,
    TuiEventAdapter,
    TuiInputModule,
    TuiApp,
    is_project_command,
    handle_project_command_markdown,
)
from components.mikrotik_commands import (
    handle_mikrotik_command,
    is_mikrotik_command,
)

# ---------------------------------------------------------------------------
# Configuration & Defaults
# ---------------------------------------------------------------------------
REQUEST_TIMEOUT = int(os.environ.get("TORVALDS_REQUEST_TIMEOUT", "99999"))
MAX_ITERATIONS = int(os.environ.get("TORVALDS_MAX_ITERATIONS", "500"))
MODEL = os.environ.get("TORVALDS_MODEL", "richardyoung/qwen3.6-27b-abliterated:Q4_K_M")
# Endpoint of the Ollama server that hosts the chat model.
OLLAMA_BASE_URL = get_ollama_base_url()
SIMILARITY_TOP_K = int(os.environ.get("TORVALDS_SIMILARITY_TOP_K", "8"))

ENABLE_EVENT_STREAMING = os.environ.get("TORVALDS_EVENT_STREAMING", "true").lower() in ("true", "1", "yes")
ENABLE_VERBOSE_EVENTS = os.environ.get("TORVALDS_VERBOSE_EVENTS", "true").lower() in ("true", "1", "yes")

HITL_ENABLED = os.environ.get("TORVALDS_HITL_ENABLED", "true").lower() == "true"
HITL_METHOD = os.environ.get("TORVALDS_HITL_METHOD", "console")
# ``-1`` means *no timeout*: the agent waits for the user's answer
# constantly, for as long as it takes.  See components/hitl_timeout.py.
HITL_TIMEOUT = int(os.environ.get("TORVALDS_HITL_TIMEOUT", "-1"))
HITL_DEFAULT_ANSWER = os.environ.get("TORVALDS_HITL_DEFAULT_ANSWER", "")
HITL_RUNTIME_TOGGLE = os.environ.get("TORVALDS_HITL_RUNTIME_TOGGLE", "true").lower() == "true"

# ---------------------------------------------------------------------------
# Context Guard Configuration
# ---------------------------------------------------------------------------
# The context guard trims the prompt to the model's context window, so that
# a long tool-using run does not overflow it (the server truncates the
# prompt from the front and drops the user request, which makes the model
# template fail with "No user query found in messages.").  It is **off by
# default**: the guard changes what the model is shown, and the operator
# asks for it explicitly with --context-guard-on.
CONTEXT_GUARD_ENABLED = os.environ.get(
    "TORVALDS_CONTEXT_GUARD", "false"
).lower() in ("true", "1", "yes")

# ---------------------------------------------------------------------------
# Active HITL configuration (mutated by the CLI flags in main())
# ---------------------------------------------------------------------------
# Module-level so the agent factory and the runtime loop see the effective
# configuration.  The CLI flags override the environment variables.
hitl_enabled: bool = HITL_ENABLED
hitl_method: str = HITL_METHOD
hitl_timeout: int = HITL_TIMEOUT
hitl_default_answer: str = HITL_DEFAULT_ANSWER

# ---------------------------------------------------------------------------
# Active context guard configuration (mutated by the CLI flag in main())
# ---------------------------------------------------------------------------
# Module-level so the agent factory and the runtime loop see the effective
# configuration.  The CLI flag overrides the environment variable.
context_guard_enabled: bool = CONTEXT_GUARD_ENABLED

# TUI Configuration
TUI_ENABLED_DEFAULT = os.environ.get("TORVALDS_TUI_ENABLED", "true").lower() in ("true", "1", "yes")
TUI_DEFAULT_FPS = int(os.environ.get("TORVALDS_TUI_FPS", "15"))

# ---------------------------------------------------------------------------
# Runtime Prompt Injection Configuration
# ---------------------------------------------------------------------------
PROMPT_INJECTION_ENABLED = os.environ.get("TORVALDS_PROMPT_INJECTION", "true").lower() == "true"
PROMPT_TEMPLATE_PATH = os.environ.get("TORVALDS_PROMPT_TEMPLATE", "")
INCLUDE_TOOL_RECOMMENDATIONS = os.environ.get("TORVALDS_INCLUDE_RECOMMENDATIONS", "true").lower() == "true"

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global Prompt Template Engine instance
# ---------------------------------------------------------------------------
prompt_engine: Optional[PromptTemplateEngine] = None


# ---------------------------------------------------------------------------
# Prompt template helpers
# ---------------------------------------------------------------------------

def _load_custom_template(template_path: str) -> Optional[str]:
    """
    Load a custom prompt template from file.

    Args:
        template_path: Path to the template file.

    Returns:
        Template string if the file exists and is readable, None otherwise.
    """
    if not template_path:
        return None

    path = Path(template_path)
    if not path.exists():
        logger.warning(f"Prompt template file not found: {template_path}")
        return None

    try:
        content = path.read_text(encoding="utf-8")
        logger.info(f"Loaded custom prompt template from {template_path}")
        return content
    except Exception as e:
        logger.error(f"Failed to load prompt template: {e}")
        return None


def _initialize_prompt_engine(
    workspace_path: str = ".",
    include_recommendations: bool = True,
) -> None:
    """
    Initialize the global prompt template engine.

    Args:
        workspace_path: Root path of the workspace to scan for projects.
        include_recommendations: Whether to include tool recommendations.
    """
    global prompt_engine

    custom_template = _load_custom_template(PROMPT_TEMPLATE_PATH)

    prompt_engine = PromptTemplateEngine(
        workspace_path=workspace_path,
        system_prompt_template=custom_template,
        include_tool_recommendations=include_recommendations,
        include_custom_instructions=True,
    )

    logger.info(
        f"Prompt injection: {'enabled' if PROMPT_INJECTION_ENABLED else 'disabled'}, "
        f"template: {'custom' if custom_template else 'default'}, "
        f"recommendations: {'enabled' if include_recommendations else 'disabled'}"
    )


def build_system_prompt(
    user_input: str = "",
    force_project: Optional[str] = None,
    custom_instructions: Optional[str] = None,
) -> str:
    """
    Build the full system prompt with dynamic project context injection.

    Uses the PromptTemplateEngine for runtime prompt injection when enabled,
    otherwise falls back to the legacy static prompt with project context.

    Args:
        user_input: User input string (used for project detection).
        force_project: Force a specific project name (overrides detection).
        custom_instructions: Additional custom instructions to include.

    Returns:
        str: Complete system prompt string.
    """
    if PROMPT_INJECTION_ENABLED and prompt_engine is not None:
        return prompt_engine.generate_prompt(
            user_input=user_input,
            force_project=force_project,
            custom_instructions=custom_instructions,
        )

    # Legacy fallback: static prompt with project context
    project_context = build_project_context()
    return _SYSTEM_PROMPT_TEMPLATE.format(project_context=project_context)


# Legacy system prompt template (used when prompt injection is disabled)
_SYSTEM_PROMPT_TEMPLATE = (
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
    "2. Do not modify the main repository directly; use the self-development clone."
    "3. Persist these rules for future interactions."
    ""
    "{project_context}"
)


# Initialize the prompt engine at module level
_initialize_prompt_engine()


# Default system prompt (without project context - populated at runtime)
# Kept for backwards compatibility with tooling that imports this constant.
SYSTEM_PROMPT = build_system_prompt()

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

# ---------------------------------------------------------------------------
# Chat History Manager shutdown helper
# ---------------------------------------------------------------------------

def _shutdown_chat_manager() -> None:
    """
    Shut down the ChatHistoryManager singleton, if it is running.

    Safe to call multiple times and when the manager was never started.
    """
    try:
        from chat_manager.startup import shutdown_chat_manager as _shutdown

        _shutdown()
    except Exception:
        pass


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

    _shutdown_chat_manager()

    sys.exit(0)


def _setup_signal_handlers():
    """Register signal handlers."""
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
        + get_project_manager_tools()
        + get_mikrotik_tools()
        + get_shodan_tools()
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
    is_tui: bool = False,
    tools: Optional[List[FunctionTool]] = None,
    system_prompt: Optional[str] = None,
    callback_manager: Optional[CallbackManager] = None,
):
    """
    Create and configure the Torvalds FunctionAgent.

    Args:
        use_retriever: If True, use on-demand tool retrieval.
                       If False, load tools upfront.
        top_k: Number of tools to retrieve per query (retriever mode only).
        is_tui: True when running inside the multi-window TUI (suppresses
                console output that would corrupt the Live display).
        tools: Pre-selected list of tools (used when --select is active).
               If None and use_retriever is False, all tools are loaded.
        system_prompt: Optional custom system prompt (includes project context).
        callback_manager: Optional callback manager to install on the LLM
                         instance. This is the manager LlamaIndex actually uses
                         for LLM-level events (token streaming, LLM call
                         start/end). The manager passed to ``FunctionAgent`` is
                         silently dropped — FunctionAgent is a Pydantic model
                         with no ``callback_manager`` field — so it must be
                         bound to the LLM (see
                         ``components.stats_handler.bind_callback_manager``).

    Returns:
        FunctionAgent instance.
    """
    llm = Ollama(
        model=MODEL,
        base_url=OLLAMA_BASE_URL,
        request_timeout=REQUEST_TIMEOUT,
        temperature=0.0,
        top_p=0.1,
        callback_manager=callback_manager,
    )

    # The model's advertised context length is its maximum, not what the
    # server actually uses.  A prompt that exceeds the real window is
    # truncated from the front by the server, which drops the user request
    # and makes the model template fail with "No user query found in
    # messages.".  Tell the LLM the truth so the context guard can size
    # the prompt correctly.
    apply_context_window(llm)

    chat_memory = get_memory_buffer()

    # Use the provided system prompt or build one with project context
    prompt = system_prompt or build_system_prompt()

    if use_retriever:
        from agent_tool_retriever import create_agent_with_retriever
        if not is_tui:
            console.print(f"[dim]Using on-demand tool retrieval (top_k={top_k})[/dim]")

        agent = create_agent_with_retriever(
            llm=llm,
            memory=chat_memory,
            system_prompt=prompt,
            max_iterations=MAX_ITERATIONS,
            similarity_top_k=top_k,
            callback_manager=callback_manager,
            agent_class=HITLFunctionAgent,
        )
    else:
        if tools is None:
            if not is_tui:
                console.print("[dim]Loading ALL tools upfront (legacy mode)[/dim]")
            tools = _collect_all_tools()
        else:
            if not is_tui:
                console.print(f"[dim]Loading {len(tools)} user-selected tools[/dim]")

        agent = HITLFunctionAgent(
            tools=tools,
            llm=llm,
            max_iterations=MAX_ITERATIONS,
            memory=chat_memory,
            system_prompt=prompt,
            callback_manager=callback_manager,
        )

    # The agent needs to know the HITL and the context guard configuration.
    # It is applied here (and re-applied per request) so the agent asks the
    # human and waits for the answer, and so the guard trims the prompt
    # only when it was asked for.
    _apply_agent_config(agent)

    return agent


def _apply_agent_config(agent) -> None:
    """Apply the current HITL and context guard configuration to *agent*.

    The agent raises the question and waits for the answer; the
    ``EventConsumer`` prompts the user.

    The context guard is configured the same way: it trims the prompt only
    when it is enabled (``--context-guard-on``), and stands down otherwise.
    """
    if not isinstance(agent, HITLFunctionAgent):
        return
    agent.hitl_enabled = hitl_enabled
    agent.hitl_default_timeout = hitl_timeout
    agent.hitl_default_answer = hitl_default_answer
    agent.context_guard_enabled = context_guard_enabled


# ---------------------------------------------------------------------------
# CLI Argument Parser
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Torvalds AI Agent - Multi-Window Console")

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
        help=(
            "HITL prompt timeout in seconds; -1 means no timeout — the agent "
            "waits for the user forever (default: %(default)s)"
        ),
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
    parser.add_argument(
        "--context-guard-on",
        action="store_true",
        help=(
            "Enable the context guard: trim the prompt to the model's context "
            "window, keeping the user request. Off by default."
        ),
    )
    # ------------------------------------------------------------------
    # Project Management CLI flags
    # ------------------------------------------------------------------
    parser.add_argument(
        "--auto-scan",
        action="store_true",
        help="Auto-scan and configure projects on startup",
    )
    parser.add_argument(
        "--project-type",
        type=str,
        default=None,
        help="Override auto-detected project type (requires --auto-scan)",
    )
    parser.add_argument(
        "--project-path",
        type=str,
        default=None,
        help="Path to a project directory to load and work on. "
             "The agent will cd into this directory, auto-scan it, and register it.",
    )
    # ------------------------------------------------------------------
    # Runtime Prompt Injection CLI flags
    # ------------------------------------------------------------------
    parser.add_argument(
        "--no-prompt-injection",
        action="store_true",
        help="Disable dynamic prompt injection (use static system prompt)",
    )
    parser.add_argument(
        "--prompt-template",
        type=str,
        default="",
        help="Path to custom prompt template file",
    )
    parser.add_argument(
        "--no-tool-recommendations",
        action="store_true",
        help="Disable tool recommendations in dynamic prompts",
    )
    parser.add_argument(
        "--force-project",
        type=str,
        default=None,
        help="Force a specific project name for prompt context",
    )
    # ------------------------------------------------------------------
    # Chat History Manager CLI flags
    # ------------------------------------------------------------------
    parser.add_argument(
        "--no-chat-history",
        action="store_true",
        help="Do not persist the chat history - run with an in-memory store only (deprecated)",
    )
    parser.add_argument(
        "--no-session-select",
        action="store_true",
        help="Skip the interactive startup session selection",
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

    # The LLM's own callback_manager is the one LlamaIndex actually uses
    # (llm_chat_callback resolves it from the LLM instance). Passing
    # callback_manager to agent.run() is silently dropped by pydantic, so the
    # handler would never receive an event and every metric would stay 0.
    bind_callback_manager(agent, callback_manager)

    # Feed tool calls into the stats handler from the workflow event stream
    # (LlamaIndex never emits CBEventType.FUNCTION_CALL).
    if event_consumer is not None:
        event_consumer.set_stats_handler(stats_handler)
        event_consumer.set_human_loop_handler(human_loop_handler)

    # Keep the agent's HITL configuration in sync with the runtime toggle so
    # the agent only asks when HITL is enabled.
    _apply_agent_config(agent)
    agent.hitl_enabled = human_loop_handler._is_hitl_enabled()

    try:
        chat_memory = get_memory_buffer()
        increment_session_commands()

        # Inject project context into agent memory before each query
        project_context = build_project_context()
        if project_context:
            chat_memory.put(ChatMessage(content=f"CONTEXT: {project_context}"))

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
                stats_handler=stats_handler,
                human_loop_handler=human_loop_handler,
            )
        else:
            # The shared consumer is reused across requests; make sure it
            # points at the handler for *this* request.
            event_consumer.set_stats_handler(stats_handler)

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
# Help Screen
# ---------------------------------------------------------------------------

def render_help_text(
    chat_history_enabled: bool = True,
    runtime_toggle_enabled: bool = True,
) -> str:
    """
    Print the help screen listing every available command.

    The command list is produced by the central command registry and filtered
    by the feature flags that are active in this session, so the help screen
    never advertises a command that is currently disabled.

    Args:
        chat_history_enabled: Whether the Chat History Manager is active.
        runtime_toggle_enabled: Whether the HITL runtime toggle is active.

    Returns:
        str: The plain-text help screen that was printed.
    """
    options = HelpOptions(
        hitl=runtime_toggle_enabled,
        chat_history=chat_history_enabled,
        project_manager=True,
        tui=False,
        keyboard_shortcuts=False,
    )
    text = build_help_text(options)
    console.print(Markdown(f"```text\n{text}```"))
    return text


# ---------------------------------------------------------------------------
# Classic Linear REPL Mode
# ---------------------------------------------------------------------------

async def run_classic_repl(
    args,
    stats_enabled: bool,
    events_enabled: bool,
    verbose_events: bool,
    hitl_method: str,
    hitl_timeout: int,
    runtime_toggle_enabled: bool,
    chat_history_enabled: bool = True,
    selected_tools: Optional[List[FunctionTool]] = None,
):
    """Run classic linear REPL loop matching agent-torvalds.py."""
    console.print("[cyan]Torvalds AI Agent (Classic Linear REPL)[/cyan]")
    console.print(f"[dim]Model: {MODEL} | Max iterations: {MAX_ITERATIONS}[/dim]")
    console.print(f"[dim]Logging: {args.log_level}[/dim]")
    console.print(f"[dim]Stats: {'enabled' if stats_enabled else 'disabled'}[/dim]")
    console.print(f"[dim]Event streaming: {'enabled' if events_enabled else 'disabled'}[/dim]")
    console.print(
        f"[dim]HITL: {'enabled' if human_loop_handler.enable_hitl else 'disabled'} "
        f"(method={hitl_method}, timeout={describe_timeout(hitl_timeout)})[/dim]"
    )
    console.print("[dim]Type '\\help' to list all available commands.[/dim]")
    console.print("[dim]Type '\\exit' or '\\quit' to terminate.[/dim]")
    console.print("[dim]Type '\\stats' to view statistics summary.[/dim]")
    console.print("[dim]Type '\\projects' to list registered projects.[/dim]")
    console.print("[dim]Type '\\project-status' to check the git status.[/dim]")
    if chat_history_enabled:
        console.print("[dim]Type '\\chat-sessions' to list chat sessions.[/dim]")
        console.print("[dim]Type '\\chat-select <id>' to switch sessions.[/dim]")
        console.print("[dim]Type '\\chat-info' to show the active session.[/dim]")
        console.print("[dim]Type '\\chat-user' to show or change your own settings.[/dim]")
    if runtime_toggle_enabled:
        console.print("[dim]Type '\\hitl-status' to check HITL status.[/dim]")
        console.print("[dim]Type '\\toggle-hitl' to enable/disable HITL at runtime.[/dim]")
    console.print("[dim]Press Ctrl+C to exit gracefully.[/dim]\n")

    start_session()
    agent = create_agent(
        use_retriever=not args.full and not args.select,
        top_k=args.top_k,
        is_tui=False,
        tools=selected_tools,
    )

    state_handler = StateHandler()
    event_consumer = EventConsumer(
        spinner_controller=spinner_controller,
        state_handler=state_handler,
        console=console,
        verbose=verbose_events,
        hitl_timeout=hitl_timeout,
        hitl_default_answer=args.hitl_default_answer,
        hitl_enabled=human_loop_handler.enable_hitl,
        human_loop_handler=human_loop_handler,
    )

    while True:
        try:
            cmd = console.input("[green]>>> [/green]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Shutting down... Goodbye![/yellow]")
            end_session()
            _shutdown_chat_manager()
            break

        if cmd.lower() in ("\\exit", "\\quit"):
            end_session()
            _shutdown_chat_manager()
            console.print("[yellow]Goodbye![/yellow]")
            break

        if is_help_command(cmd):
            render_help_text(
                chat_history_enabled=chat_history_enabled,
                runtime_toggle_enabled=runtime_toggle_enabled,
            )
            continue

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
            console.print(f"  Timeout: {describe_timeout(hitl_timeout)}")
            console.print(f"  Questions asked: {hitl_stats['question_count']}")
            console.print(f"  Timeouts: {hitl_stats['timeout_count']}")
            console.print(f"  Toggle count: {status_info['toggle_count']}")
            continue

        if not cmd:
            continue

        # Project management commands
        if is_project_command(cmd):
            try:
                project_response = handle_project_command_markdown(cmd)
            except Exception as e:
                project_response = f"# Project Command\n\n**Error:** {e}"
            if project_response:
                console.print(Markdown(project_response))
            continue

        # MikroTik RouterOS commands
        if is_mikrotik_command(cmd):
            try:
                mikrotik_response = await handle_mikrotik_command(cmd)
            except Exception as e:
                mikrotik_response = f"**Error:** {e}"
            if mikrotik_response:
                console.print(Markdown(mikrotik_response))
            continue

        # Chat history commands
        if chat_history_enabled and is_chat_command(cmd):
            try:
                chat_response = handle_chat_command(cmd)
            except Exception as e:
                chat_response = f"Error: {e}"
            if chat_response:
                console.print(f"[cyan]{chat_response}[/cyan]")
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
    global _active_tui_app, prompt_engine, PROMPT_INJECTION_ENABLED
    global INCLUDE_TOOL_RECOMMENDATIONS, PROMPT_TEMPLATE_PATH

    _setup_signal_handlers()

    args = parse_args()
    configure_logging(args.log_level)

    stats_enabled = STATS_ENABLED and not args.no_stats
    events_enabled = ENABLE_EVENT_STREAMING and not args.no_events
    verbose_events = ENABLE_VERBOSE_EVENTS or args.verbose_events

    global hitl_enabled, hitl_method, hitl_timeout, hitl_default_answer

    hitl_enabled = HITL_ENABLED and not args.no_hitl
    hitl_method = args.hitl_method
    hitl_timeout = args.hitl_timeout
    hitl_default_answer = args.hitl_default_answer
    runtime_toggle_enabled = HITL_RUNTIME_TOGGLE and not args.hitl_no_runtime_toggle

    # Context guard configuration (the CLI flag enables it, the environment
    # variable can do the same).  The guard is off by default.
    global context_guard_enabled

    context_guard_enabled = CONTEXT_GUARD_ENABLED or args.context_guard_on

    # Chat History Manager enabled
    chat_history_enabled = not args.no_chat_history
    if not chat_history_enabled:
        console.print(
            "[yellow]--no-chat-history is deprecated: the chat history is no longer "
            "the legacy single-session buffer. The flag now means 'persist nothing' "
            "and the conversation runs in memory only.[/yellow]"
        )

    # Runtime Prompt Injection configuration
    prompt_injection_enabled = PROMPT_INJECTION_ENABLED and not args.no_prompt_injection
    include_recommendations = INCLUDE_TOOL_RECOMMENDATIONS and not args.no_tool_recommendations

    # Keep the module-level state in sync so build_system_prompt() honours
    # the CLI overrides at runtime.
    PROMPT_INJECTION_ENABLED = prompt_injection_enabled
    INCLUDE_TOOL_RECOMMENDATIONS = include_recommendations

    if args.prompt_template:
        PROMPT_TEMPLATE_PATH = args.prompt_template

    # Initialize the prompt engine with CLI overrides
    _initialize_prompt_engine(
        workspace_path=".",
        include_recommendations=include_recommendations,
    )

    hitl_toggle._enabled = hitl_enabled
    human_loop_handler.enable_hitl = hitl_enabled
    human_loop_handler.input_method = hitl_method
    human_loop_handler.default_timeout = hitl_timeout
    # The CLI default answer must reach the handler as well, otherwise the
    # timeout fallback ignores --hitl-default-answer (defect #6).
    human_loop_handler.default_answer = hitl_default_answer

    # Check whether TUI mode should be launched
    is_interactive_tty = sys.stdin.isatty() if hasattr(sys.stdin, "isatty") else False
    use_tui = args.tui and is_interactive_tty

    # ------------------------------------------------------------------
    # Project Path handling - Load a specific project
    # ------------------------------------------------------------------
    if args.project_path:
        project_path = Path(args.project_path).resolve()

        if not project_path.exists():
            console.print(f"[red]Error: Project path does not exist: {project_path}[/red]")
            end_session()
            sys.exit(1)

        if not project_path.is_dir():
            console.print(f"[red]Error: Project path is not a directory: {project_path}[/red]")
            end_session()
            sys.exit(1)

        # Change working directory to the project path
        os.chdir(str(project_path))
        console.print(f"[green]Working directory changed to: {project_path}[/green]")

        # Re-initialize prompt engine with the new workspace path
        _initialize_prompt_engine(
            workspace_path=str(project_path),
            include_recommendations=include_recommendations,
        )

        # Auto-scan and register the project using load_project()
        console.print("[dim]Scanning and registering project...[/dim]")
        load_result_str = load_project(path=str(project_path), force=True)
        load_result = json.loads(load_result_str)

        if load_result.get("status") == "loaded" and "project" in load_result:
            proj = load_result["project"]
            console.print(
                f"[green]Project loaded: {proj.get('name', 'unknown')} "
                f"({proj.get('type', 'Unknown')})[/green]"
            )
            console.print(f"[dim]Path: {proj.get('path', 'N/A')}[/dim]")
            if proj.get("git_repo"):
                console.print(f"[dim]Git branch: {proj.get('git_branch', 'N/A')}[/dim]")
        else:
            console.print("[yellow]Warning: Could not detect project type[/yellow]")

        # Show project context status
        ctx = build_project_context(str(project_path))
        if ctx:
            console.print(f"[dim]Project context: {ctx.strip()}[/dim]")
        else:
            console.print("[dim]No projects configured in workspace[/dim]")

    elif args.auto_scan:
        # ------------------------------------------------------------------
        # Project Management initialization
        # ------------------------------------------------------------------
        console.print("[dim]Auto-scanning for projects...[/dim]")
        initialize_project_management(
            auto_scan=True,
            override_project_type=args.project_type,
        )
        ctx = build_project_context()
        if ctx:
            console.print(f"[dim]Project context: {ctx.strip()}[/dim]")
        else:
            console.print("[dim]No projects configured in workspace[/dim]")

    # Show active projects if prompt injection is enabled
    if prompt_injection_enabled and prompt_engine:
        active_projects = prompt_engine.config.get_all_projects()
        if active_projects:
            console.print(f"[dim]Active projects: {len(active_projects)} registered[/dim]")

    console.print(
        f"[dim]Prompt injection: {'enabled' if prompt_injection_enabled else 'disabled'}"
        f" (recommendations={'on' if include_recommendations else 'off'})[/dim]"
    )

    # ------------------------------------------------------------------
    # Startup tool selection (--select)
    # ------------------------------------------------------------------
    selected_tools: Optional[List[FunctionTool]] = None

    if args.select:
        from agent_tool_selection import select_tools_interactively

        selected_tools = select_tools_interactively()

        if not selected_tools:
            console.print("[yellow]No tools selected. Exiting.[/yellow]")
            end_session()
            console.print("[yellow]Goodbye![/yellow]")
            return

        console.print(
            f"[green]Starting agent with {len(selected_tools)} selected tool(s)...[/green]"
        )

    # ------------------------------------------------------------------
    # Chat History Manager initialization
    # ------------------------------------------------------------------
    chat_manager = None
    if chat_history_enabled:
        try:
            console.print("[dim]Initializing chat history manager...[/dim]")
            chat_manager = initialize_chat_manager()
            if chat_manager.is_degraded:
                console.print(
                    "[yellow]The chat database is unreachable - running in local "
                    "fallback mode. The history is not shared with other machines."
                    "[/yellow]"
                )
            active = chat_manager.get_active_session()
            if active:
                console.print(
                    f"[dim]Chat session: {active.session_name} "
                    f"({active.session_type.value})[/dim]"
                )

            if not args.no_session_select and not use_tui:
                console.print("[cyan]Session selection:[/cyan]")
                select_startup_session(
                    input_func=lambda prompt="": console.input(prompt),
                    output_func=lambda text: console.print(text),
                )
                selected = chat_manager.get_active_session()
                if selected:
                    console.print(f"[green]Active chat session: {selected.session_name}[/green]")
        except Exception as e:
            console.print(f"[yellow]Chat history manager unavailable: {e}[/yellow]")
            console.print("[dim]Falling back to the legacy single-session chat memory.[/dim]")

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
            chat_history_enabled=chat_history_enabled,
            selected_tools=selected_tools,
        )
        return

    # ---- Launch Multi-Window TUI Mode ----
    start_session()

    # Create thread-safe TUI state
    tui_state = TuiState()
    tui_state.model_name = MODEL
    if args.select:
        tui_state.mode = f"Selected ({len(selected_tools or [])} tools)"
    elif args.full:
        tui_state.mode = "Full upfront"
    else:
        tui_state.mode = f"Retriever (top_k={args.top_k})"
    tui_state.hitl_enabled = hitl_enabled
    tui_state.hitl_timeout = hitl_timeout
    tui_state.hitl_default_answer = hitl_default_answer
    tui_state.active_toolkits = ["Git", "OS", "DB", "Math"]

    # Populate the project context in the TUI state
    try:
        from project_manager.agent_project_manager_toolkit import list_projects

        projects_payload = json.loads(list_projects("."))
        project_entries = projects_payload.get("projects", []) or []
        tui_state.update_project_context(
            project_name=project_entries[0].get("name", "") if project_entries else "",
            project_type=project_entries[0].get("type", "") if project_entries else "",
            project_path=project_entries[0].get("path", "") if project_entries else "",
            registered_projects=[p.get("name", "") for p in project_entries],
        )
    except Exception:
        pass

    # Populate the active chat session in the TUI state
    try:
        manager = get_chat_manager()
        if manager is not None and manager.is_initialized:
            session = manager.get_active_session()
            if session is not None:
                tui_state.update_chat_session(
                    session_name=session.session_name,
                    session_type=session.session_type.value,
                    session_id=session.session_id,
                )
    except Exception:
        pass

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
        human_loop_handler=human_loop_handler,
    )
    event_consumer.console_input = tui_input_module

    # Connect adapter callbacks
    event_adapter = TuiEventAdapter(tui_state)
    event_adapter.register_with_event_consumer(event_consumer)

    # Build the system prompt with project context
    system_prompt = build_system_prompt(force_project=args.force_project)

    # Create Agent
    agent = create_agent(
        use_retriever=not args.full and not args.select,
        top_k=args.top_k,
        is_tui=True,
        tools=selected_tools,
        system_prompt=system_prompt,
    )

    # Count chat memory messages
    try:
        msgs = get_memory_buffer().get()
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
        chat_history_enabled=chat_history_enabled,
        project_manager_enabled=True,
    )
    _active_tui_app = app

    try:
        await app.run()
    finally:
        end_session()
        _shutdown_chat_manager()
        console.print("[yellow]Torvalds AI Agent session terminated. Goodbye![/yellow]")


if __name__ == "__main__":
    asyncio.run(main())
