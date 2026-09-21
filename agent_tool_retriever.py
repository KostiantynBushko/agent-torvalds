"""
Tool Retriever - On-demand tool loading for the Torvalds Agent.

This module implements lazy loading of tools using Llama Index's
ObjectIndex. Tools are indexed and retrieved semantically based
on the user's query, reducing context window pollution.

Category: Infrastructure
Retriever Keywords: retriever, tool loading, lazy, vector index, semantic
"""
from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.objects import ObjectIndex
from llama_index.core.tools import FunctionTool
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.embeddings.ollama import OllamaEmbedding

# Configure Ollama embedding model
Settings.embed_model = OllamaEmbedding(model_name="nomic-embed-text")


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

    if include_math_tools:
        from agent_math_toolkit import get_all_tools as _get_math
        all_tools.extend(_get_math())

    if include_git_tools:
        from agent_git_toolkit import get_all_tools as _get_git
        all_tools.extend(_get_git())

    if include_os_tools:
        from agent_os_toolkit import get_all_tools as _get_os
        all_tools.extend(_get_os())

    if include_linux_tools:
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

    # -----------------------------------------------------------------------
    # 2. Build ObjectIndex over tool objects for semantic retrieval
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
) -> FunctionAgent:
    """
    Create a FunctionAgent that uses on-demand tool retrieval.

    Args:
        llm: The LLM instance.
        memory: ChatMemoryBuffer instance.
        system_prompt: System prompt string.
        max_iterations: Max agent iterations per query.
        similarity_top_k: Tools retrieved per query.

    Returns:
        FunctionAgent configured with tool_retriever.
    """
    tool_retriever, _ = build_tool_retriever(
        llm,
        similarity_top_k=similarity_top_k,
    )

    agent = FunctionAgent(
        llm=llm,
        tool_retriever=tool_retriever,
        memory=memory,
        system_prompt=system_prompt,
        max_iterations=max_iterations,
    )

    return agent
