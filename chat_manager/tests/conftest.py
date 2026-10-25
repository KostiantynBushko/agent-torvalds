"""Pytest configuration for chat_manager tests."""

import pytest
import os
import sys

# Ensure the self-development directory is in the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def clear_env():
    """Clear chat-related env vars for each test."""
    saved = {}
    for key in (
        "TORVALDS_STORAGE_URI",
        "TORVALDS_LLAMA_URI",
        "TORVALDS_CHAT_KEY",
        "TORVALDS_STORAGE_FALLBACK_URI",
        "TORVALDS_STORAGE_FALLBACK",
    ):
        if key in os.environ:
            saved[key] = os.environ[key]
            del os.environ[key]
    yield
    for key, val in saved.items():
        os.environ[key] = val
