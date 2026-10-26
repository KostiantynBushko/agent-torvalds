"""
Tool Retriever - On-demand tool loading for the Torvalds Agent.

This module implements lazy loading of tools using Llama Index's
ObjectIndex. Tools are indexed and retrieved semantically based
on the user's query, reducing context window pollution.

Category: Infrastructure
Retriever Keywords: retriever, tool loading, lazy, vector index, semantic
"""
from typing import Optional

from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.callbacks import CallbackManager
from llama_index.core.objects import ObjectIndex
from llama_index.core.tools import FunctionTool
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.embeddings.ollama import OllamaEmbedding
import sys

from components.ollama_config import get_ollama_base_url

# Configure Ollama embedding model. The endpoint follows the same
# TORVALDS_OLLAMA_HOST / OLLAMA_HOST rules as the chat model.
Settings.embed_model = OllamaEmbedding(
    model_name="nomic-embed-text",
    base_url=get_ollama_base_url(),
)


def build_tool_retriever(
    llm,
    similarity_top_k: int = 8,
    include_cache_tools: bool = True,
    include_math_tools: bool = True,
    include_git_tools: bool = True,
    include_os_tools: bool = True,
    include_linux_tools: bool = True,
    include_github_tools: bool = True,
    include_db_tools: bool = True,
    include_apt_tools: bool = True,
    include_windows_tools: bool = True,
    include_xlsx_tools: bool = True,
    include_data_analysis_tools: bool = True,
    include_project_manager_tools: bool = True,  # NEW: Step 05
    include_mikrotik_tools: bool = True,  # NEW: MikroTik RouterOS toolkit
    include_shodan_tools: bool = True,  # NEW: Shodan internet-exposure toolkit
) -> tuple:
    """
    Build a tool retriever that loads tools on-demand based on query semantics.

    Args:
        llm: The LLM instance to use for embedding/retrieval.
        similarity_top_k: Number of top tools to retrieve per query.
        include_*_tools: Flags to enable/disable entire toolkit categories.

    Returns:
        tuple: (tool_retriever, all_tools_list)
    """
    # -----------------------------------------------------------------------
    # 1. Collect all tool definitions from each toolkit
    # -----------------------------------------------------------------------
    all_tools: list[FunctionTool] = []

    # The math toolkit lives in ``toolkits/`` and is optional.  It is
    # imported behind a guard so that a missing toolkit degrades
    # gracefully instead of breaking the agent boot.
    if include_math_tools:
        try:
            from toolkits.math_toolkit.agent_math_toolkit import (
                get_all_tools as _get_math,
            )
            all_tools.extend(_get_math())
        except ImportError:
            # The math toolkit is optional - skip it when it is not installed.
            pass

    if include_git_tools:
        from agent_git_toolkit import get_all_tools as _get_git
        all_tools.extend(_get_git())

    if include_os_tools:
        from agent_os_toolkit import get_all_tools as _get_os
        all_tools.extend(_get_os())

    if include_linux_tools and sys.platform.startswith("linux"):
        from agent_linux_toolkit import get_all_tools as _get_linux
        all_tools.extend(_get_linux())

    if include_github_tools:
        from agent_github_toolkit import get_all_tools as _get_github
        all_tools.extend(_get_github())

    if include_db_tools:
        from agent_db_toolkit import get_all_tools as _get_db
        all_tools.extend(_get_db())

    if include_apt_tools:
        from agent_apt_toolkit import get_all_tools as _get_apt
        all_tools.extend(_get_apt())

    if include_cache_tools:
        from agent_cache_system import get_all_tools as _get_cache
        all_tools.extend(_get_cache())

    if include_windows_tools and sys.platform.startswith("win"):
        from agent_windows_toolkit import get_all_tools as _get_windows
        all_tools.extend(_get_windows())

    # -----------------------------------------------------------------------
    # 2. Excel & Data Analysis toolkits
    # -----------------------------------------------------------------------
    if include_xlsx_tools:
        from agent_xlsx_toolkit import get_all_tools as _get_xlsx
        all_tools.extend(_get_xlsx())

    if include_data_analysis_tools:
        from agent_data_analysis_toolkit import get_all_tools as _get_analysis
        all_tools.extend(_get_analysis())

    # -----------------------------------------------------------------------
    # 3. Project Manager toolkit (Step 05)
    # -----------------------------------------------------------------------
    if include_project_manager_tools:
        try:
            from project_manager.agent_project_manager_toolkit import get_all_tools as _get_pm
            all_tools.extend(_get_pm())
        except ImportError:
            # Project manager toolkit not available — skip gracefully
            pass

    # -----------------------------------------------------------------------
    # 3b. MikroTik RouterOS toolkit
    # -----------------------------------------------------------------------
    # The toolkit needs the optional 'asyncssh' dependency.  It is imported
    # behind a guard so that a missing dependency degrades gracefully
    # instead of breaking the agent boot.
    if include_mikrotik_tools:
        try:
            from toolkits.mikrotik_routeros.agent_mikrotik_toolkit import (
                get_all_tools as _get_mikrotik,
            )
            all_tools.extend(_get_mikrotik())
        except ImportError:
            # MikroTik toolkit not available — skip gracefully
            pass

    # -----------------------------------------------------------------------
    # 3c. Shodan toolkit
    # -----------------------------------------------------------------------
    # The toolkit drives the external 'shodan' CLI.  It is imported behind a
    # guard so that a missing dependency degrades gracefully instead of
    # breaking the agent boot.  Only the read-only tools are exposed unless
    # TORVALDS_SHODAN_ALLOW_MUTATING is set.
    if include_shodan_tools:
        try:
            from toolkits.shodan_toolkit.agent_shodan_toolkit import (
                get_all_tools as _get_shodan,
            )
            all_tools.extend(_get_shodan())
        except ImportError:
            # Shodan toolkit not available - skip gracefully
            pass

    # -----------------------------------------------------------------------
    # 4. Build ObjectIndex over tool objects for semantic retrieval
    # -----------------------------------------------------------------------
    # ObjectIndex properly wraps tools and returns FunctionTool instances
    tool_index = ObjectIndex.from_objects(
        all_tools,
        index_cls=VectorStoreIndex,
    )

    tool_retriever = tool_index.as_retriever(similarity_top_k=similarity_top_k)

    return tool_retriever, all_tools


def create_agent_with_retriever(
    llm,
    memory,
    system_prompt: str,
    max_iterations: int = 50,
    similarity_top_k: int = 8,
    callback_manager: Optional[CallbackManager] = None,
    agent_class: type = FunctionAgent,
) -> FunctionAgent:
    """
    Create a FunctionAgent that uses on-demand tool retrieval.

    Args:
        llm: The LLM instance.
        memory: ChatMemoryBuffer instance.
        system_prompt: System prompt string.
        max_iterations: Max agent iterations per query.
        similarity_top_k: Tools retrieved per query.
        callback_manager: Optional callback manager to install on the LLM
                         instance for LLM-level event tracking (stats, HITL,
                         etc.). The manager passed to ``FunctionAgent`` is
                         silently dropped — FunctionAgent is a Pydantic model
                         with no ``callback_manager`` field — so it is bound to
                         the LLM here.

        agent_class: Agent class to instantiate.  Defaults to
                     ``FunctionAgent``; the HITL-aware orchestrator passes
                     ``components.hitl_agent.HITLFunctionAgent`` so the agent
                     can ask the human and wait for the answer.

    Returns:
        FunctionAgent configured with tool_retriever.
    """
    tool_retriever, _ = build_tool_retriever(
        llm,
        similarity_top_k=similarity_top_k,
    )

    agent = agent_class(
        llm=llm,
        tool_retriever=tool_retriever,
        memory=memory,
        system_prompt=system_prompt,
        max_iterations=max_iterations,
        # NOTE: FunctionAgent is a Pydantic model with no 'callback_manager'
        # field, so this argument is silently ignored. The callback manager
        # that actually receives LLM events is the one on the LLM instance —
        # it is bound per request by components.stats_handler.bind_callback_manager.
        callback_manager=callback_manager,
    )

    # Make sure the LLM carries the callback manager even if the agent was
    # created without one: llm_chat_callback resolves the manager from the
    # LLM instance, and an empty manager means no events are delivered.
    if callback_manager is not None:
        from components.stats_handler import bind_callback_manager

        bind_callback_manager(agent, callback_manager)

    return agent
