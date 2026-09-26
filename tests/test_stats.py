"""
Test script to verify the RequestStatsHandler callback handler works correctly.
"""
import asyncio
import time
from llama_index.core.callbacks import CallbackManager
from llama_index.core.callbacks.schema import CBEventType, EventPayload
from llama_index.llms.ollama import Ollama
from llama_index.core.llms import ChatMessage, CompletionResponse
import sys
sys.path.insert(0, '.')
from components.stats_handler import RequestStatsHandler

async def test_stats_handler():
    print("Testing RequestStatsHandler...")
    
    # Create a handler
    handler = RequestStatsHandler(request_id="test-001", user_query="What is 2+2?")
    callback_manager = CallbackManager([handler])
    
    # Create Ollama LLM with the callback manager
    llm = Ollama(
        model="richardyoung/qwen3.6-27b-abliterated:Q4_K_M",
        callback_manager=callback_manager,
        request_timeout=30,
    )
    
    print(f"LLM callback_manager: {llm.callback_manager}")
    print(f"LLM callback_manager handlers: {llm.callback_manager.handlers}")
    
    # Call the LLM directly
    messages = [ChatMessage(role="user", content="What is 2+2?")]
    print("Calling LLM...")
    response = await llm.achat(messages)
    print(f"Response: {response}")
    print(f"Response raw type: {type(response.raw)}")
    print(f"Response raw: {response.raw}")
    
    # Finalize stats
    stats = handler.finalize()
    print(f"\n=== Stats Results ===")
    print(f"LLM Call Count: {stats.llm_call_count}")
    print(f"Total Prompt Tokens: {stats.total_prompt_tokens}")
    print(f"Total Completion Tokens: {stats.total_completion_tokens}")
    print(f"Total Tokens: {stats.total_tokens}")
    
    if stats.llm_call_count == 0 or stats.total_tokens == 0:
        print("\n⚠️ WARNING: Stats are 0! This is the bug.")
        print(f"Response raw keys: {response.raw.keys() if isinstance(response.raw, dict) else 'N/A'}")
        if isinstance(response.raw, dict):
            for key in response.raw:
                print(f"  {key}: {response.raw[key]}")
    else:
        print("\n✅ Stats collected successfully!")

if __name__ == "__main__":
    asyncio.run(test_stats_handler())
