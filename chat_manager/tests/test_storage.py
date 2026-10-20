"""Tests for CustomDBConnector with SQLite in-memory backend."""

import unittest
from chat_manager.storage import CustomDBConnector
from chat_manager.user import User
from chat_manager.session import Session, SessionType


class TestConnectorLifecycle(unittest.TestCase):
    """Tests for connector lifecycle."""

    def test_connect_and_close(self):
        """Connector can be connected and closed."""
        conn = CustomDBConnector(connection_uri="sqlite:///:memory:")
        conn.connect()
        self.assertIsNotNone(conn._engine)
        conn.close()
        self.assertIsNone(conn._engine)

    def test_create_tables(self):
        """Tables are created on connect."""
        conn = CustomDBConnector(connection_uri="sqlite:///:memory:")
        conn.connect()
        # Should not raise
        conn.close()


class TestUserOperations(unittest.TestCase):
    """Tests for user CRUD operations."""

    def setUp(self):
        self.conn = CustomDBConnector(connection_uri="sqlite:///:memory:")
        self.conn.connect()

    def tearDown(self):
        self.conn.close()

    def test_create_and_get_user(self):
        """Create a user and retrieve by username."""
        user = User(
            user_id="test-user-1",
            username="testuser",
            backend_type="postgres",
            token_limit=5000,
        )
        created = self.conn.create_user(user)
        self.assertEqual(created.user_id, "test-user-1")
        self.assertEqual(created.username, "testuser")

        retrieved = self.conn.get_user_by_username("testuser")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.user_id, "test-user-1")

    def test_get_user_by_id(self):
        """Retrieve user by ID."""
        user = User(user_id="test-user-2", username="testuser2")
        self.conn.create_user(user)
        retrieved = self.conn.get_user_by_id("test-user-2")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.username, "testuser2")

    def test_get_nonexistent_user(self):
        """Get non-existent user returns None."""
        self.assertIsNone(self.conn.get_user_by_username("nonexistent"))
        self.assertIsNone(self.conn.get_user_by_id("nonexistent-id"))

    def test_update_user(self):
        """Update user preferences."""
        user = User(
            user_id="test-user-3",
            username="testuser3",
            token_limit=5000,
        )
        self.conn.create_user(user)
        user.token_limit = 10000
        updated = self.conn.update_user(user)
        self.assertEqual(updated.token_limit, 10000)

        retrieved = self.conn.get_user_by_id("test-user-3")
        self.assertEqual(retrieved.token_limit, 10000)


class TestSessionOperations(unittest.TestCase):
    """Tests for session CRUD operations."""

    def setUp(self):
        self.conn = CustomDBConnector(connection_uri="sqlite:///:memory:")
        self.conn.connect()
        # Create a test user
        self.user = User(user_id="session-test-user", username="sessiontest")
        self.user = self.conn.create_user(self.user)

    def tearDown(self):
        self.conn.close()

    def test_create_session(self):
        """Create a session."""
        session = Session(
            session_id="test-session-1",
            user_id=self.user.user_id,
            session_name="Test Session",
            session_type=SessionType.CUSTOM,
            chat_key="test-chat-key",
            is_active=False,
        )
        created = self.conn.create_session(session)
        self.assertEqual(created.session_id, "test-session-1")
        self.assertEqual(created.session_name, "Test Session")
        self.assertFalse(created.is_active)

    def test_list_sessions(self):
        """List sessions for a user."""
        for i, (name, stype) in enumerate([
            ("Session 1", SessionType.GENERAL),
            ("Session 2", SessionType.PROJECT),
        ]):
            self.conn.create_session(Session(
                session_id=f"list-sess-{i}",
                user_id=self.user.user_id,
                session_name=name,
                session_type=stype,
                chat_key=f"list-key-{i}",
            ))

        sessions = self.conn.list_sessions(self.user.user_id)
        self.assertEqual(len(sessions), 2)

    def test_activate_session(self):
        """Activate a session."""
        s1 = Session(
            session_id="activate-sess-1",
            user_id=self.user.user_id,
            session_name="Session 1",
            session_type=SessionType.GENERAL,
            chat_key="activate-key-1",
            is_active=False,
        )
        s2 = Session(
            session_id="activate-sess-2",
            user_id=self.user.user_id,
            session_name="Session 2",
            session_type=SessionType.CUSTOM,
            chat_key="activate-key-2",
            is_active=False,
        )
        self.conn.create_session(s1)
        self.conn.create_session(s2)

        # Activate s2
        activated = self.conn.activate_session("activate-sess-2", self.user.user_id)
        self.assertTrue(activated.is_active)

        # s1 should no longer be active
        s1_retrieved = self.conn.get_active_session(self.user.user_id)
        self.assertEqual(s1_retrieved.session_id, "activate-sess-2")

    def test_get_active_session(self):
        """Get active session for user."""
        session = Session(
            session_id="active-sess",
            user_id=self.user.user_id,
            session_name="Active Session",
            session_type=SessionType.GENERAL,
            chat_key="active-key",
            is_active=True,
        )
        self.conn.create_session(session)

        active = self.conn.get_active_session(self.user.user_id)
        self.assertIsNotNone(active)
        self.assertEqual(active.session_id, "active-sess")

    def test_delete_session(self):
        """Delete a session."""
        session = Session(
            session_id="delete-sess",
            user_id=self.user.user_id,
            session_name="Delete Me",
            session_type=SessionType.CUSTOM,
            chat_key="delete-key",
        )
        self.conn.create_session(session)

        result = self.conn.delete_session("delete-sess")
        self.assertTrue(result)

        sessions = self.conn.list_sessions(self.user.user_id)
        self.assertTrue(all(s.session_id != "delete-sess" for s in sessions))

    def test_delete_nonexistent_session(self):
        """Delete non-existent session returns False."""
        self.assertFalse(self.conn.delete_session("nonexistent"))


if __name__ == "__main__":
    unittest.main()
