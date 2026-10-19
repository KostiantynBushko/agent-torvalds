"""
ChatHistoryManager — Multi-user chat session management with SQL-backed persistence.

Provides session lifecycle management, user identification, and backend-agnostic
message storage via LlamaIndex integration.
"""

from chat_manager.user import User
from chat_manager.session import Session, SessionType

__all__ = [
    "User",
    "Session",
    "SessionType",
]
