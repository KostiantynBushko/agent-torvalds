"""Tests for User and Session data models."""

import unittest
from chat_manager.user import User
from chat_manager.session import Session, SessionType


class TestUser(unittest.TestCase):
    """Tests for the User data model."""

    def test_create_user_defaults(self):
        """User creation with defaults."""
        user = User(user_id="test-uuid", username="testuser")
        self.assertEqual(user.user_id, "test-uuid")
        self.assertEqual(user.username, "testuser")
        self.assertEqual(user.backend_type, "postgres")
        self.assertEqual(user.token_limit, 5000)
        self.assertIsNotNone(user.created_at)
        self.assertIsNotNone(user.updated_at)

    def test_create_user_custom_values(self):
        """User creation with custom values."""
        user = User(
            user_id="custom-uuid",
            username="customuser",
            backend_type="mysql",
            token_limit=10000,
        )
        self.assertEqual(user.backend_type, "mysql")
        self.assertEqual(user.token_limit, 10000)

    def test_user_repr(self):
        """User repr includes username."""
        user = User(user_id="123", username="alice")
        self.assertIn("alice", repr(user))

    def test_user_equality(self):
        """Users are equal if user_id matches."""
        u1 = User(user_id="same-id", username="a")
        u2 = User(user_id="same-id", username="b")
        u3 = User(user_id="diff-id", username="a")
        self.assertEqual(u1, u2)
        self.assertNotEqual(u1, u3)


class TestSession(unittest.TestCase):
    """Tests for the Session data model."""

    def test_create_session_defaults(self):
        """Session creation with defaults."""
        session = Session(
            session_id="sess-uuid",
            user_id="user-uuid",
            session_name="Test Session",
            session_type=SessionType.CUSTOM,
            chat_key="test-key",
        )
        self.assertEqual(session.session_id, "sess-uuid")
        self.assertEqual(session.user_id, "user-uuid")
        self.assertEqual(session.session_name, "Test Session")
        self.assertEqual(session.session_type, SessionType.CUSTOM)
        self.assertEqual(session.chat_key, "test-key")
        self.assertFalse(session.is_active)
        self.assertIsNotNone(session.created_at)

    def test_create_session_active(self):
        """Session creation with active flag."""
        session = Session(
            session_id="sess-uuid",
            user_id="user-uuid",
            session_name="Active Session",
            session_type=SessionType.GENERAL,
            chat_key="active-key",
            is_active=True,
        )
        self.assertTrue(session.is_active)

    def test_session_repr(self):
        """Session repr includes name and type."""
        session = Session(
            session_id="123",
            user_id="user1",
            session_name="My Session",
            session_type=SessionType.PROJECT,
            chat_key="key1",
        )
        self.assertIn("My Session", repr(session))
        self.assertIn("project", repr(session))

    def test_session_equality(self):
        """Sessions are equal if session_id matches."""
        s1 = Session(
            session_id="same", user_id="u", session_name="a",
            session_type=SessionType.CUSTOM, chat_key="k"
        )
        s2 = Session(
            session_id="same", user_id="u", session_name="b",
            session_type=SessionType.GENERAL, chat_key="k2"
        )
        s3 = Session(
            session_id="diff", user_id="u", session_name="a",
            session_type=SessionType.CUSTOM, chat_key="k"
        )
        self.assertEqual(s1, s2)
        self.assertNotEqual(s1, s3)


class TestSessionType(unittest.TestCase):
    """Tests for SessionType enum."""

    def test_session_type_values(self):
        """SessionType has expected values."""
        self.assertEqual(SessionType.GENERAL.value, "general")
        self.assertEqual(SessionType.PROJECT.value, "project")
        self.assertEqual(SessionType.CUSTOM.value, "custom")

    def test_session_type_from_string(self):
        """SessionType can be created from string."""
        self.assertEqual(SessionType("general"), SessionType.GENERAL)
        self.assertEqual(SessionType("project"), SessionType.PROJECT)
        self.assertEqual(SessionType("custom"), SessionType.CUSTOM)

    def test_session_type_invalid(self):
        """Invalid string raises ValueError."""
        with self.assertRaises(ValueError):
            SessionType("invalid")


if __name__ == "__main__":
    unittest.main()
