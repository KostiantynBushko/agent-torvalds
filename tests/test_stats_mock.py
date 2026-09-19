"""
Test script to verify the RequestStatsHandler token extraction works correctly.
Uses mocked events instead of actual LLM calls.
"""
import sys
sys.path.insert(0, '.')

from llama_index.core.callbacks.schema import CBEventType, EventPayload
from agent_stats_handler import RequestStatsHandler


def test_token_extraction():
    """Test that token counts are properly extracted from callback payloads."""
    print("Testing RequestStatsHandler token extraction...")
    
    # Create handler
    handler = RequestStatsHandler(request_id="test-001", user_query="What is 2+2?")
    
    # Simulate LLM event start
    handler.on_event_start(
        event_type=CBEventType.LLM,
        event_id="llm-001",
        payload={},
    )
    
    # Simulate LLM event end with token usage (Ollama-style response)
    class MockResponse:
        def __init__(self, raw_data):
            self.raw = raw_data
    
    # Test 1: Ollama-style response with "prompt_tokens" and "completion_tokens"
    print("\n--- Test 1: Ollama-style response ---")
    handler.on_event_end(
        event_type=CBEventType.LLM,
        event_id="llm-001",
        payload={
            EventPayload.RESPONSE: MockResponse({
                "prompt_tokens": 100,
                "completion_tokens": 50,
            })
        },
    )
    
    stats = handler.stats
    print(f"LLM Call Count: {stats.llm_call_count}")
    print(f"Total Prompt Tokens: {stats.total_prompt_tokens}")
    print(f"Total Completion Tokens: {stats.total_completion_tokens}")
    print(f"Total Tokens: {stats.total_tokens}")
    
    assert stats.llm_call_count == 1, f"Expected 1 LLM call, got {stats.llm_call_count}"
    assert stats.total_prompt_tokens == 100, f"Expected 100 prompt tokens, got {stats.total_prompt_tokens}"
    assert stats.total_completion_tokens == 50, f"Expected 50 completion tokens, got {stats.total_completion_tokens}"
    assert stats.total_tokens == 150, f"Expected 150 total tokens, got {stats.total_tokens}"
    print("✅ Test 1 passed!")
    
    # Test 2: Alternative format with "input_tokens" and "output_tokens"
    print("\n--- Test 2: Alternative format (input/output tokens) ---")
    handler.on_event_end(
        event_type=CBEventType.LLM,
        event_id="llm-002",
        payload={
            EventPayload.RESPONSE: MockResponse({
                "input_tokens": 200,
                "output_tokens": 75,
            })
        },
    )
    
    print(f"LLM Call Count: {stats.llm_call_count}")
    print(f"Total Prompt Tokens: {stats.total_prompt_tokens}")
    print(f"Total Completion Tokens: {stats.total_completion_tokens}")
    print(f"Total Tokens: {stats.total_tokens}")
    
    assert stats.llm_call_count == 2, f"Expected 2 LLM calls, got {stats.llm_call_count}"
    assert stats.total_prompt_tokens == 300, f"Expected 300 prompt tokens, got {stats.total_prompt_tokens}"
    assert stats.total_completion_tokens == 125, f"Expected 125 completion tokens, got {stats.total_completion_tokens}"
    assert stats.total_tokens == 425, f"Expected 425 total tokens, got {stats.total_tokens}"
    print("✅ Test 2 passed!")
    
    # Test 3: No response payload (edge case)
    print("\n--- Test 3: No response payload ---")
    handler.on_event_end(
        event_type=CBEventType.LLM,
        event_id="llm-003",
        payload={},
    )
    
    print(f"LLM Call Count: {stats.llm_call_count}")
    assert stats.llm_call_count == 3, f"Expected 3 LLM calls, got {stats.llm_call_count}"
    print("✅ Test 3 passed!")
    
    # Test 4: Test tool call tracking
    print("\n--- Test 4: Tool call tracking ---")
    handler.on_event_start(
        event_type=CBEventType.FUNCTION_CALL,
        event_id="tool-001",
        payload={
            EventPayload.TOOL_NAME: "add",
        },
    )
    handler.on_event_end(
        event_type=CBEventType.FUNCTION_CALL,
        event_id="tool-001",
        payload={},
    )
    
    print(f"Tool calls recorded: {len(stats.tool_calls)}")
    assert len(stats.tool_calls) == 1, f"Expected 1 tool call, got {len(stats.tool_calls)}"
    assert stats.tool_calls[0].tool_name == "add", f"Expected tool name 'add', got {stats.tool_calls[0].tool_name}"
    print("✅ Test 4 passed!")
    
    # Finalize and check
    final_stats = handler.finalize()
    print(f"\n=== Final Stats ===")
    print(f"Duration: {final_stats.total_duration_ms:.2f}ms")
    print(f"LLM Calls: {final_stats.llm_call_count}")
    print(f"Total Tokens: {final_stats.total_tokens}")
    print(f"Tool Calls: {len(final_stats.tool_calls)}")
    print("\n✅ All tests passed!")


if __name__ == "__main__":
    test_token_extraction()
