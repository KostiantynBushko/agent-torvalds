import asyncio
from llama_index.core.agent.workflow import FunctionAgent
from rich.console import Console

from chat_manager.startup import get_memory_buffer

from toolkits.os_toolkit.agent_os_toolkit import *

# The database toolkit is optional: the drivers may not be installed, and
# its configuration file - ``db_toolkit_config.yaml``, which it reads at
# import time - may be missing or malformed.  Neither may take the
# orchestrator down, so the star import is behind a guard.
try:
    from toolkits.db_toolkit.agent_db_toolkit import *
except Exception:  # pragma: no cover - the toolkit is optional
    pass

from toolkits.math_toolkit.agent_math_toolkit import *
from toolkits.git_toolkit.agent_git_toolkit import *

from components.agent_answer import extract_answer

# Path to your local GGUF model
MODEL_PATH = "${HOME}/ai-agent-investiagte/models/NVIDIA-Nemotron3-Nano-4B-Q4_K_M.gguf"

from llama_index.llms.llama_cpp import LlamaCPP
from llama_index.core.llms.function_calling import FunctionCallingLLM

# Base LlamaCPP model
base_llm = LlamaCPP(
    model_path=MODEL_PATH,
    temperature=0.7,
    max_new_tokens=1024,
    context_window=4096,
    model_kwargs={"n_threads": 8},
)

# Wrap it so FunctionAgent can use it
llm = FunctionCallingLLM.from_llm(base_llm)

agent = FunctionAgent(
    tools=[add, multiply, divide,
           git_get_latest_commit, git_init_repo,
           pwd, ls, touch, check_path_exists, mkdir, rm, cp, mv, read_file, write_file, get_system_info],
    llm=llm,
    memory=get_memory_buffer(),
    system_prompt=(
        "Your name is **Torvald** – an AI assistant that can directly interact with the host operating system and a wide range of technical tools."
        ""
        "Core capabilities"
        "- **OS‑level access**: browse file systems, run shell commands, launch/manage processes, work with network shares, containers, VMs, etc."
        "- **Database work**: execute SQL queries (PostgreSQL, MySQL, SQLite, Snowflake, BigQuery, …) and inspect schemas."
        "- **Technical & scientific tasks**: math, statistics, data analysis (pandas/NumPy), plotting, physics/engineering calculations."
        "- **Software development & architecture**: generate/refactor code (Python, JavaScript, Go, Java, …), run tests, linting, build automation, create diagrams, and provide architectural advice."
        ""
        "Operational guidelines"
        "- **Tool‑first**: always use the provided functions/tools for calculations, file ops, SQL, etc. – never simulate results."
        "- **Safety first**: before any destructive action (delete, drop, modify production data, etc.) ask for explicit confirmation and, when possible, offer a dry‑run preview."
        "- **Clarity & transparency**: state what you’re doing, why, and what the expected outcome is. Surface exact error messages and suggest remediation."
        "- **Context awareness**: keep track of the current directory, active databases, running processes, and any in‑progress scripts to avoid repetitive prompts."
        "- **Documentation**: when you create code or scripts, also generate a short README or comment block explaining purpose, usage, and prerequisites."
    ),
)

console = Console()

import logging, traceback
logging.basicConfig(level=logging.DEBUG)

async def prompt_handler(cmd: str) -> str:
    try:
        result = await agent.run(cmd, memory=get_memory_buffer())
        # The answer of the run.  ``extract_answer`` never returns an
        # empty string: when the model wrote nothing, the operator is told
        # so and shown what the run found (the last tool result and the
        # thinking of the model) instead of a blank section.
        return extract_answer(result)
    except Exception as e:
        logging.exception("Agent run failed")
        return f"Error: {e}\n{traceback.format_exc()}"

async def main():
    console.print("[cyan]Advanced Async Terminal[/cyan]. Type '\\exit' or '\\quit' to terminate.")
    while True:
        cmd = console.input("[green]>>> [/green]").strip()
        if cmd.lower() in ("\\exit", "\\quit"):
            break

        with console.status("[yellow]Processing...[/yellow]", spinner="dots"):
            try:
                response = await prompt_handler(cmd)
            except Exception as e:
                response = f"[red]Error: {e}[/red]"

        console.rule("[blue]Agent Response[/blue]")
        console.print(response, style="bold white")
        console.rule()

if __name__ == "__main__":
    asyncio.run(main())
