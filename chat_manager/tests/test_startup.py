"""Tests for startup integration."""

import unittest
from unittest.mock import patch, MagicMock
from chat_manager.startup import (
    initialize_chat_manager,
    get_chat_manager,
    shutdown_chat_manager,
    is_chat_manager_initialized,
)


class TestStartupIntegration(unittest.TestCase):
    """Tests for startup module."""

    def setUp(self):
        """Reset global state before each test."""
        shutdown_chat_manager()

    def test_initialize_returns_manager(self):
        """Initialize returns a ChatHistoryManager."""
        with patch("chat_manager.manager.ChatHistoryManager") as MockManager:
            mock_instance = MagicMock()
            mock_instance.current_user = MagicMock()
            mock_instance.current_user.username = "testuser"
            mock_instance.get_active_session.return_value = MagicMock()
            mock_instance.get_active_session.return_value.session_name = "General Chat"
            MockManager.return_value = mock_instance

            result = initialize_chat_manager()
            self.assertIsNotNone(result)
            MockManager.assert_called_once()
            mock_instance.initialize.assert_called_once()

    def test_get_chat_manager_before_init(self):
        """Get manager before initialization returns None."""
        self.assertIsNone(get_chat_manager())

    def test_get_chat_manager_after_init(self):
        """Get manager after initialization returns the instance."""
        with patch("chat_manager.manager.ChatHistoryManager") as MockManager:
            mock_instance = MagicMock()
            mock_instance.current_user = MagicMock()
            mock_instance.current_user.username = "testuser"
            mock_instance.get_active_session.return_value = MagicMock()
            mock_instance.get_active_session.return_value.session_name = "General Chat"
            MockManager.return_value = mock_instance

            initialize_chat_manager()
            self.assertIsNotNone(get_chat_manager())

    def test_is_initialized_before_init(self):
        """Check initialization status before init."""
        self.assertFalse(is_chat_manager_initialized())

    def test_is_initialized_after_init(self):
        """Check initialization status after init."""
        with patch("chat_manager.manager.ChatHistoryManager") as MockManager:
            mock_instance = MagicMock()
            mock_instance.is_initialized = True
            mock_instance.current_user = MagicMock()
            mock_instance.current_user.username = "testuser"
            mock_instance.get_active_session.return_value = MagicMock()
            mock_instance.get_active_session.return_value.session_name = "General Chat"
            MockManager.return_value = mock_instance

            initialize_chat_manager()
            self.assertTrue(is_chat_manager_initialized())

    def test_shutdown(self):
        """Shutdown clears the global instance."""
        with patch("chat_manager.manager.ChatHistoryManager") as MockManager:
            mock_instance = MagicMock()
            mock_instance.current_user = MagicMock()
            mock_instance.current_user.username = "testuser"
            mock_instance.get_active_session.return_value = MagicMock()
            mock_instance.get_active_session.return_value.session_name = "General Chat"
            MockManager.return_value = mock_instance

            initialize_chat_manager()
            shutdown_chat_manager()
            self.assertIsNone(get_chat_manager())
            mock_instance.shutdown.assert_called_once()

    def test_double_initialize(self):
        """Double initialize returns existing instance."""
        with patch("chat_manager.manager.ChatHistoryManager") as MockManager:
            mock_instance = MagicMock()
            mock_instance.current_user = MagicMock()
            mock_instance.current_user.username = "testuser"
            mock_instance.get_active_session.return_value = MagicMock()
            mock_instance.get_active_session.return_value.session_name = "General Chat"
            MockManager.return_value = mock_instance

            initialize_chat_manager()
            initialize_chat_manager()
            MockManager.assert_called_once()  # Only created once


if __name__ == "__main__":
    unittest.main()
