"""
Torvalds AI Agent - Components Module

Provides reusable components for the agent:
- SpinnerController: Console spinner with pause/resume capabilities
- StateHandler: Agent state management during workflow execution
- EventConsumer: Real-time workflow event consumption
- SignalHandler: Graceful shutdown with signal handling
- WhiptailPasswordPrompter: Terminal dialog-based password prompting
"""

from components.spinner_controller import SpinnerController
from components.state_handler import StateHandler
from components.event_consumer import EventConsumer
from components.signal_handler import SignalHandler
from components.whiptail_password import (
    WhiptailPasswordPrompter,
    get_prompter,
    prompt_sudo_password_whiptail,
)

__all__ = [
    "SpinnerController",
    "StateHandler",
    "EventConsumer",
    "SignalHandler",
    "WhiptailPasswordPrompter",
    "get_prompter",
    "prompt_sudo_password_whiptail",
]
