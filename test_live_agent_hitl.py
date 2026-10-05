"""
Live Agent Test with HITL Integration
Tests the Torvalds agent with real LLM and interactive HITL support.
"""
import asyncio
import sys
import os
import importlib

# Add self-development to path
sys.path.insert(0, '/home/kbush/ai-agent-investiagte/agent-torvalds/self-development')

from rich.console import Console

# Import agent components
from agent_cache_system import start_session, end_session
from components.spinner_controller import SpinnerController
from components.state_handler import StateHandler
from components.event_consumer import EventConsumer
from components.human_loop_handler import HumanLoopHandler
from components.hitl_runtime_toggle import HITLRuntimeToggle
from components.console_input_module import ConsoleInputModule

# Import agent module (has hyphen in name)
agent_module = importlib.import_module("agent-torvalds")
create_agent = agent_module.create_agent
prompt_handler = agent_module.prompt_handler
SYSTEM_PROMPT = agent_module.SYSTEM_PROMPT
MAX_ITERATIONS = agent_module.MAX_ITERATIONS

console = Console()

async def test_agent():
    """Run live agent test with HITL."""
    console.print("[bold cyan]=== Torvalds Live Agent Test ===[/bold cyan]")
    console.print("[dim]Testing with real LLM and HITL integration[/dim]\n")
    
    # Start session
    start_session()
    
    # Create spinner and HITL components
    spinner = SpinnerController(console)
    state_handler = StateHandler()
    
    # HITL toggle
    hitl_toggle = HITLRuntimeToggle(initial_state=True, console=console)
    
    # HITL handler
    human_loop = HumanLoopHandler(
        input_method='console',
        default_timeout=15,
        default_answer='',
        console=console,
        spinner=spinner,
        enable_hitl=True,
        runtime_toggle=hitl_toggle,
    )
    
    # Event consumer
    event_consumer = EventConsumer(
        spinner_controller=spinner,
        state_handler=state_handler,
        console=console,
        verbose=False,
        hitl_timeout=15,
        hitl_default_answer='',
        hitl_enabled=True,
    )
    
    # Wire them together
    human_loop.event_consumer = event_consumer
    
    # Create agent (full mode for faster testing)
    console.print("[yellow]Creating agent with full tool loading...[/yellow]")
    agent = create_agent(use_retriever=False)
    console.print("[green]✓ Agent created successfully[/green]\n")
    
    # Test queries
    test_queries = [
        "What is the current working directory?",
        "Calculate 15 * 23 + 47",
    ]
    
    for i, query in enumerate(test_queries, 1):
        console.rule(f"[blue]Test {i}/{len(test_queries)}[/blue]")
        console.print(f"[cyan]Query: {query}[/cyan]\n")
        
        spinner.start()
        try:
            response, stats = await prompt_handler(
                query, 
                agent, 
                enable_stats=True, 
                event_consumer=event_consumer
            )
            console.print(f"\n[bold green]Response:[/bold green] {response}\n")
            
            if stats:
                console.print(f"[dim]Stats: {stats.total_tokens} tokens, {stats.llm_call_count} LLM calls, {stats.tool_call_count} tool calls[/dim]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            import traceback
            traceback.print_exc()
        finally:
            spinner.stop()
        
        console.print()
    
    # Summary
    console.rule("[green]Test Complete[/green]")
    console.print("[bold green]✓ All tests executed successfully![/bold green]")
    
    end_session()

if __name__ == "__main__":
    asyncio.run(test_agent())
