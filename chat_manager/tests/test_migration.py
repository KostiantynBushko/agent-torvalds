"""Tests for the schema migration that renames the chat-token limit column.

The setting was called ``token_limit`` and is now called ``chat_token_limit``.
An existing database still has the old column, so the connector renames it in
place on connect — the values are kept and no manual step is needed.
"""

import unittest

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from chat_manager.storage import CustomDBConnector
from chat_manager.user import User


LEGACY_DDL = """
CREATE TABLE users (
    user_id       TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    backend_type  TEXT NOT NULL DEFAULT 'postgres',
    token_limit   INTEGER NOT NULL DEFAULT 5000,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


class TestTokenLimitColumnMigration(unittest.TestCase):
    """Tests for the idempotent column rename."""

    def _make_legacy_database(self):
        """Build a database that still has the old column name.

        Returns:
            A tuple of (engine, session factory).
        """
        engine = create_engine("sqlite:///:memory:", echo=False)
        with engine.begin() as connection:
            connection.execute(text(LEGACY_DDL))
        return engine, sessionmaker(bind=engine)

    def test_legacy_column_is_renamed(self):
        """The old column is renamed to the canonical one."""
        engine, _ = self._make_legacy_database()

        connector = CustomDBConnector(connection_uri="sqlite:///:memory:")
        connector._engine = engine
        connector._session_factory = sessionmaker(bind=engine)
        connector._migrate_schema()

        columns = {c["name"] for c in inspect(engine).get_columns("users")}
        self.assertIn("chat_token_limit", columns)
        self.assertNotIn("token_limit", columns)

    def test_migration_keeps_the_values(self):
        """The values in the renamed column survive the migration."""
        engine, factory = self._make_legacy_database()

        session = factory()
        session.execute(
            text(
                "INSERT INTO users (user_id, username, backend_type, token_limit) "
                "VALUES ('u1', 'tester', 'postgres', 12345)"
            )
        )
        session.commit()
        session.close()

        connector = CustomDBConnector(connection_uri="sqlite:///:memory:")
        connector._engine = engine
        connector._session_factory = factory
        connector._migrate_schema()

        session = factory()
        try:
            value = session.execute(
                text("SELECT chat_token_limit FROM users WHERE user_id = 'u1'")
            ).scalar()
        finally:
            session.close()

        self.assertEqual(value, 12345)

    def test_migration_is_idempotent(self):
        """Running the migration twice does not raise."""
        engine, factory = self._make_legacy_database()

        connector = CustomDBConnector(connection_uri="sqlite:///:memory:")
        connector._engine = engine
        connector._session_factory = factory

        connector._migrate_schema()
        connector._migrate_schema()  # must not raise

        columns = {c["name"] for c in inspect(engine).get_columns("users")}
        self.assertIn("chat_token_limit", columns)

    def test_migration_is_a_no_op_on_a_current_schema(self):
        """A database that already has the canonical column is left alone."""
        connector = CustomDBConnector(connection_uri="sqlite:///:memory:")
        connector.connect()
        try:
            columns = {c["name"] for c in inspect(connector._engine).get_columns("users")}
            self.assertIn("chat_token_limit", columns)
        finally:
            connector.close()

    def test_migration_failure_does_not_break_the_connect(self):
        """A failing migration is logged, not fatal."""
        connector = CustomDBConnector(connection_uri="sqlite:///:memory:")
        connector.connect()
        try:
            connector._engine = None
            # A missing engine must not raise.
            connector._migrate_schema()
        finally:
            connector.close()


class TestConnectorUserRoundTrip(unittest.TestCase):
    """Tests that the renamed column is written and read back."""

    def setUp(self):
        self.conn = CustomDBConnector(connection_uri="sqlite:///:memory:")
        self.conn.connect()

    def tearDown(self):
        self.conn.close()

    def test_user_round_trip(self):
        """The chat-token limit survives a write/read cycle."""
        user = User(
            user_id="round-trip-1",
            username="roundtrip",
            backend_type="postgres",
            chat_token_limit=11000,
        )
        self.conn.create_user(user)

        retrieved = self.conn.get_user_by_username("roundtrip")
        self.assertEqual(retrieved.chat_token_limit, 11000)

    def test_update_user_writes_the_renamed_column(self):
        """update_user writes the canonical column."""
        user = User(user_id="round-trip-2", username="roundtrip2")
        self.conn.create_user(user)

        user.chat_token_limit = 13000
        updated = self.conn.update_user(user)
        self.assertEqual(updated.chat_token_limit, 13000)

        retrieved = self.conn.get_user_by_id("round-trip-2")
        self.assertEqual(retrieved.chat_token_limit, 13000)

    def test_orm_synonym_keeps_the_old_attribute_working(self):
        """The ORM still answers to the old attribute name."""
        user = User(user_id="round-trip-3", username="roundtrip3", chat_token_limit=4242)
        self.conn.create_user(user)

        from chat_manager.storage.models import User as ORMUser

        session = self.conn._session_factory()
        try:
            orm_user = session.query(ORMUser).filter(ORMUser.username == "roundtrip3").first()
            self.assertEqual(orm_user.token_limit, 4242)
            self.assertEqual(orm_user.chat_token_limit, 4242)
        finally:
            session.close()

    def test_fresh_database_uses_the_canonical_column(self):
        """A fresh database is created with the canonical column."""
        columns = {c["name"] for c in inspect(self.conn._engine).get_columns("users")}
        self.assertIn("chat_token_limit", columns)
        self.assertNotIn("token_limit", columns)


if __name__ == "__main__":
    unittest.main()
