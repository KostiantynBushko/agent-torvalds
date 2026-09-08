import asyncio
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.ollama import Ollama
from rich.console import Console

import agent_chat_memory

from agent_git_toolkit import *
from agent_os_toolkit import *
from agent_db_toolkit import *
from agent_math_toolkit import *

REQUEST_TIMEOUT = 99999
llm = Ollama(model="qwen3-coder:latest", request_timeout=99999)

agent = FunctionAgent(
    tools=[add, multiply, divide,
           git_get_latest_commit, git_init_repo, git_add_files, git_commit, git_get_status, git_generate_changelog,
           git_get_recent_changes, git_update_changelog, git_get_email, git_init_and_commit,
           git_remote_add, git_push, git_remote_get, git_set_upstream,
           pwd, ls, touch, check_path_exists, mkdir, rm, cp, mv, read_file, write_file, get_system_info,
           postgres_tool, mysql_tool],
    llm=llm,
    max_iterations=10000,
    memory=agent_chat_memory.chat_memory,
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
        ""
        "# Optional output‑format comment – keep it concise unless the user asks for a specific style."
    ),
)

console = Console()

import logging
logging.basicConfig(level=logging.INFO)

async def prompt_handler(cmd: str) -> str:
    try:
        result = await agent.run(cmd, memory=agent_chat_memory.chat_memory,
                                 max_iterations=10000,
                                 early_stopping_method="generate")
        if isinstance(result, dict):
            return result.get("output") or result.get("text") or str(result)
        return str(result)
    except Exception as e:
        import traceback
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