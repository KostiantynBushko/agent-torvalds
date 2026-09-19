# Proposal: On-Demand Tool Loading for Torvalds Agent

## 1. Problem Statement
Currently, the `agent-torvalds.py` script loads **all** available tools (Math, Git, OS, DB, Linux) into the agent's context at startup.

**Drawbacks:**
*   **Context Window Pollution:** Tool descriptions consume a significant portion of the LLM's context window, leaving less room for conversation history and complex reasoning.
*   **Cognitive Overload:** The LLM must consider all tools for every single decision, which can lead to "analysis paralysis" or selection of irrelevant tools.
*   **Memory Usage:** Instantiating all tool wrappers and associated modules increases the initial memory footprint.
*   **Latency:** Initial agent setup takes longer as it processes every tool definition.

## 2. Goal
Implement a **Lazy Loading** mechanism where tools are loaded into the agent's active context **only when they are needed**.

## 3. Proposed Architecture (Updated: Native Llama Index Approach)

Llama Index's `FunctionAgent` (via `BaseWorkflowAgent`) natively supports a `tool_retriever` parameter. This is the most robust and "Llama-native" way to implement on-demand tool loading without complex custom state management.

### 3.1. How `tool_retriever` Works
Instead of passing a static list of `tools` to the agent, we pass a `tool_retriever`.
*   On every turn, the agent takes the user's input (or the current query) and passes it to the `tool_retriever`.
*   The retriever searches its index (e.g., a vector store of tool descriptions) and returns only the **most relevant** tools for that specific query.
*   The agent then uses *only* those retrieved tools to generate the response.

### 3.2. Implementation Strategy

#### Step 1: Define Tools as Objects
We already define tools using `FunctionTool.from_defaults(fn)`. We need to ensure every tool has a clear `name` and `description` so the retriever can match them effectively.

#### Step 2: Create a Tool Index
Use Llama Index's `VectorStoreIndex` (or `ObjectIndex`) to index the tool definitions.
```python
from llama_index.core import VectorStoreIndex
from llama_index.core.tools import FunctionTool
from llama_index.core.agent.workflow import FunctionAgent

# 1. Define all tools (but don't pass them directly to the agent yet)
all_tools = [math_tool_1, git_tool_1, os_tool_1, ...]

# 2. Create an index of these tools
tool_index = VectorStoreIndex.from_objects(
    all_tools,
    llm=llm,
)

# 3. Create a retriever from the index
tool_retriever = tool_index.as_retriever(similarity_top_k=5) # Retrieve top 5 relevant tools
```

#### Step 3: Initialize Agent with Retriever
```python
agent = FunctionAgent(
    llm=llm,
    tool_retriever=tool_retriever, # <-- Pass the retriever instead of 'tools'
    memory=chat_memory,
    system_prompt="..."
)
```

### 3.3. Benefits of This Approach
1.  **Native Support:** No need for custom "meta-tools" or complex state hacking. Llama Index handles the retrieval loop internally.
2.  **Automatic Filtering:** The LLM doesn't see irrelevant tools. If the user asks a math question, only math tools are retrieved and presented to the LLM.
3.  **Scalability:** We can add hundreds of tools to the index without increasing the context window size per turn.
4.  **Semantic Matching:** The retriever uses embeddings to find tools that *semantically* match the user's intent, which is often more accurate than keyword matching.

## 4. Implementation Plan

### Phase 1: Refactor Tool Definitions
*   Ensure all tools in `agent_git_toolkit`, `agent_os_toolkit`, etc., have high-quality descriptions.
*   Export a function `get_all_tools()` that returns a list of `FunctionTool` objects.

### Phase 2: Implement Retriever
*   Create a `tool_retriever` using `VectorStoreIndex.from_objects`.
*   Tune `similarity_top_k` (e.g., start with 5-10) to balance context size vs. tool availability.

### Phase 3: Update Agent Initialization
*   Modify `agent-torvalds.py` to use `tool_retriever=...` instead of `tools=...`.
*   Test with various queries to ensure the correct tools are being retrieved.

### Phase 4: Advanced Tuning (Optional)
*   **Hybrid Retrieval:** Combine vector search with keyword search for better precision.
*   **Tool Categories:** Add metadata to tools (e.g., "category: git") to allow filtering if needed.
*   **Fallback:** Ensure that if no tools are retrieved, the agent can still respond conversationally.

## 5. Example Interaction

**User:** "What is the latest commit in the current repo?"

**Agent (Internal Process):**
1.  Query: "What is the latest commit in the current repo?"
2.  Retriever searches tool index.
3.  Matches: `git_get_latest_commit` (high similarity).
4.  Returns: `[git_get_latest_commit]`
5.  Agent receives only `git_get_latest_commit` as an available tool.
6.  Agent calls `git_get_latest_commit(path=".")`.

## 6. Risks & Mitigation
*   **Risk:** The retriever might miss a relevant tool if the description is poor.
    *   *Mitigation:* Invest time in writing clear, detailed tool descriptions. Use `similarity_top_k` that is slightly higher (e.g., 10) to increase the chance of inclusion.
*   **Risk:** Retrieval latency.
    *   *Mitigation:* The embedding search is very fast (<100ms). This is negligible compared to LLM inference time.

## 7. Conclusion
Using Llama Index's built-in `tool_retriever` is the most efficient and maintainable way to achieve on-demand tool loading. It solves the context window problem while leveraging the framework's native capabilities.