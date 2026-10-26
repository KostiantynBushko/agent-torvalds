"""
Unit tests for the database toolkit's library half.

Tests the SQL operations:
- run_postgres_query, run_mysql_query
- the private _load_config helper

The toolkit used to be a single module at the project root,
``agent_db_toolkit.py``, and it carried **no** test suite at all.  This
one came with the move.

The suite is **offline**: it drives the operations through a stubbed
``psycopg2`` and a stubbed ``mysql.connector``, so it never opens a
connection to anything and needs no database server.  That matters - the
build that has to stay green runs in CI, where no database is waiting.
"""

import contextlib
import inspect
import tempfile
import textwrap
import unittest
import unittest.mock as mock
from pathlib import Path

import yaml

from .. import operations
from ..operations import (
    _load_config,
    run_mysql_query,
    run_postgres_query,
)


#: The configuration the operations are driven with.
CONFIG = {
    "postgres": {
        "host": "db.example",
        "port": 5432,
        "user": "pg_user",
        "password": "pg_password",
    },
    "mysql": {
        "host": "mysql.example",
        "port": 3306,
        "user": "my_user",
        "password": "my_password",
    },
}


class _FakeCursor:
    """A stand-in for a DB-API cursor."""

    def __init__(self, description=None, rows=(), error=None):
        self.description = description
        self._rows = list(rows)
        self._error = error
        self.executed = []
        self.closed = False

    def execute(self, query):
        self.executed.append(query)
        if self._error is not None:
            raise self._error

    def fetchall(self):
        return list(self._rows)

    def close(self):
        self.closed = True


class _FakeConnection:
    """A stand-in for a DB-API connection."""

    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


def _driver(description=None, rows=(), error=None):
    """A stubbed ``connect`` that hands out a fake connection.

    The stub records the connection parameters it was called with, so a
    test can check that the configuration reached the driver.
    """
    cursor = _FakeCursor(description=description, rows=rows)
    connection = _FakeConnection(cursor)

    def connect(**kwargs):
        if error is not None:
            raise error
        connect.calls.append(kwargs)
        return connection

    connect.calls = []
    connect.cursor = cursor
    connect.connection = connection
    return connect


@contextlib.contextmanager
def _stubbed_drivers(postgres=None, mysql=None):
    """Stub both database drivers and pin the configuration.

    The configuration is pinned because the toolkit loads it **at import
    time**: the operations read the module-level ``_cfg``, so a test that
    wants a different configuration has to replace that one.
    """
    postgres = postgres or _driver()
    mysql = mysql or _driver()
    with mock.patch.object(operations, "_cfg", CONFIG), mock.patch.object(
        operations.psycopg2, "connect", postgres
    ), mock.patch.object(operations.mysql.connector, "connect", mysql):
        yield postgres, mysql


class TestLoadConfig(unittest.TestCase):
    """The private configuration loader."""

    def test_it_reads_the_yaml_file(self):
        """The file is parsed as YAML."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text("postgres:\n  host: localhost\n", encoding="utf-8")
            config = _load_config(str(path))

        self.assertEqual(config, {"postgres": {"host": "localhost"}})

    def test_it_returns_a_mapping(self):
        """The loader returns the parsed document."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text("mysql:\n  host: localhost\n", encoding="utf-8")
            config = _load_config(str(path))

        self.assertIsInstance(config, dict)

    def test_a_missing_file_raises_file_not_found(self):
        """A missing configuration file is an error, not an empty config."""
        with self.assertRaises(FileNotFoundError):
            _load_config("/nonexistent/db_toolkit_config.yaml")

    def test_invalid_yaml_raises_a_yaml_error(self):
        """A malformed configuration file is an error too."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text("postgres: [unclosed\n", encoding="utf-8")
            with self.assertRaises(yaml.YAMLError):
                _load_config(str(path))

    def test_the_default_path_is_the_config_file(self):
        """The default is the file in the working directory."""
        self.assertEqual(operations._DEFAULT_CONFIG_PATH, "db_toolkit_config.yaml")

    def test_the_default_path_is_used_when_no_path_is_given(self):
        """The default argument is the path that is read."""
        import inspect

        signature = inspect.signature(_load_config)
        self.assertEqual(
            signature.parameters["path"].default, operations._DEFAULT_CONFIG_PATH
        )

    def test_the_config_is_loaded_at_import_time(self):
        """The module-level ``_cfg`` is the loaded configuration.

        The toolkit reads its configuration when it is imported, and the
        operations use the loaded values.  That is behaviour, and the
        move preserved it.
        """
        self.assertIsInstance(operations._cfg, dict)

    def test_the_config_is_not_reloaded_on_every_call(self):
        """The operations use the loaded configuration, not the file.

        The comment in the source says so: the configuration is loaded
        once, at import time.
        """
        with mock.patch.object(operations, "_load_config") as load:
            with _stubbed_drivers():
                run_postgres_query("SELECT 1")

        load.assert_not_called()


class TestRunPostgresQuery(unittest.TestCase):
    """The PostgreSQL operation."""

    def test_it_returns_the_rows_as_dictionaries(self):
        """One dictionary per row, keyed by column name."""
        driver = _driver(description=(("id",), ("name",)), rows=[(1, "Alice"), (2, "Bob")])

        with _stubbed_drivers(postgres=driver):
            rows = run_postgres_query("SELECT id, name FROM users")

        self.assertEqual(rows, [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}])

    def test_it_returns_a_list(self):
        """The result is a list."""
        driver = _driver(description=(("id",),), rows=[(1,)])

        with _stubbed_drivers(postgres=driver):
            rows = run_postgres_query("SELECT id FROM users")

        self.assertIsInstance(rows, list)

    def test_the_column_names_come_from_the_cursor_description(self):
        """The keys of the dictionaries are the column names."""
        driver = _driver(description=(("first_name",), ("last_name",)), rows=[("A", "B")])

        with _stubbed_drivers(postgres=driver):
            rows = run_postgres_query("SELECT first_name, last_name FROM users")

        self.assertEqual(list(rows[0].keys()), ["first_name", "last_name"])

    def test_a_query_without_a_result_set_returns_an_empty_list(self):
        """A DDL or DML query produces no rows."""
        driver = _driver(description=None, rows=[])

        with _stubbed_drivers(postgres=driver):
            rows = run_postgres_query("CREATE TABLE test (id INT)")

        self.assertEqual(rows, [])

    def test_an_empty_result_set_returns_an_empty_list(self):
        """A SELECT that matches nothing returns an empty list."""
        driver = _driver(description=(("id",),), rows=[])

        with _stubbed_drivers(postgres=driver):
            rows = run_postgres_query("SELECT id FROM users WHERE id = -1")

        self.assertEqual(rows, [])

    def test_the_query_is_executed_on_the_cursor(self):
        """The SQL text reaches the cursor unchanged."""
        driver = _driver(description=(("id",),), rows=[])

        with _stubbed_drivers(postgres=driver):
            run_postgres_query("SELECT id FROM users")

        self.assertEqual(driver.cursor.executed, ["SELECT id FROM users"])

    def test_the_connection_parameters_come_from_the_configuration(self):
        """The ``postgres`` section of the configuration reaches the driver."""
        driver = _driver(description=(("id",),), rows=[])

        with _stubbed_drivers(postgres=driver):
            run_postgres_query("SELECT id FROM users")

        self.assertEqual(driver.calls, [CONFIG["postgres"]])

    def test_the_connection_and_the_cursor_are_closed(self):
        """A finished query leaves nothing open."""
        driver = _driver(description=(("id",),), rows=[])

        with _stubbed_drivers(postgres=driver):
            run_postgres_query("SELECT id FROM users")

        self.assertTrue(driver.cursor.closed)
        self.assertTrue(driver.connection.closed)

    # -- the error contract -------------------------------------------------

    def test_a_failing_connection_is_reported_not_raised(self):
        """A failure comes back as a string."""
        driver = _driver(error=RuntimeError("connection refused"))

        with _stubbed_drivers(postgres=driver):
            result = run_postgres_query("SELECT 1")

        self.assertIsInstance(result, str)

    def test_the_error_message_names_postgresql(self):
        """The message says which database failed."""
        driver = _driver(error=RuntimeError("connection refused"))

        with _stubbed_drivers(postgres=driver):
            result = run_postgres_query("SELECT 1")

        self.assertTrue(result.startswith("Error running PostgreSQL query:"), result)
        self.assertIn("connection refused", result)

    def test_a_failing_query_is_reported_not_raised(self):
        """A broken statement comes back as a string."""
        driver = _driver(error=RuntimeError('relation "nope" does not exist'))

        with _stubbed_drivers(postgres=driver):
            result = run_postgres_query("SELECT * FROM nope")

        self.assertIsInstance(result, str)
        self.assertIn('relation "nope" does not exist', result)

    def test_a_missing_configuration_section_is_reported_not_raised(self):
        """A configuration without a ``postgres`` key is an error, not a crash."""
        with mock.patch.object(operations, "_cfg", {"mysql": CONFIG["mysql"]}):
            with mock.patch.object(operations.psycopg2, "connect", _driver()):
                result = run_postgres_query("SELECT 1")

        self.assertIsInstance(result, str)
        self.assertIn("Error running PostgreSQL query:", result)


class TestRunMySqlQuery(unittest.TestCase):
    """The MySQL operation."""

    def test_it_returns_the_rows_as_dictionaries(self):
        """One dictionary per row, keyed by column name."""
        driver = _driver(description=(("id",), ("name",)), rows=[(1, "Alice"), (2, "Bob")])

        with _stubbed_drivers(mysql=driver):
            rows = run_mysql_query("SELECT id, name FROM users")

        self.assertEqual(rows, [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}])

    def test_it_returns_a_list(self):
        """The result is a list."""
        driver = _driver(description=(("id",),), rows=[(1,)])

        with _stubbed_drivers(mysql=driver):
            rows = run_mysql_query("SELECT id FROM users")

        self.assertIsInstance(rows, list)

    def test_the_column_names_come_from_the_cursor_description(self):
        """The keys of the dictionaries are the column names."""
        driver = _driver(description=(("first_name",), ("last_name",)), rows=[("A", "B")])

        with _stubbed_drivers(mysql=driver):
            rows = run_mysql_query("SELECT first_name, last_name FROM users")

        self.assertEqual(list(rows[0].keys()), ["first_name", "last_name"])

    def test_a_query_without_a_result_set_returns_an_empty_list(self):
        """A DDL or DML query produces no rows."""
        driver = _driver(description=None, rows=[])

        with _stubbed_drivers(mysql=driver):
            rows = run_mysql_query("CREATE TABLE test (id INT)")

        self.assertEqual(rows, [])

    def test_the_query_is_executed_on_the_cursor(self):
        """The SQL text reaches the cursor unchanged."""
        driver = _driver(description=(("id",),), rows=[])

        with _stubbed_drivers(mysql=driver):
            run_mysql_query("SELECT id FROM users")

        self.assertEqual(driver.cursor.executed, ["SELECT id FROM users"])

    def test_the_connection_parameters_come_from_the_configuration(self):
        """The ``mysql`` section of the configuration reaches the driver."""
        driver = _driver(description=(("id",),), rows=[])

        with _stubbed_drivers(mysql=driver):
            run_mysql_query("SELECT id FROM users")

        self.assertEqual(driver.calls, [CONFIG["mysql"]])

    def test_the_connection_and_the_cursor_are_closed(self):
        """A finished query leaves nothing open."""
        driver = _driver(description=(("id",),), rows=[])

        with _stubbed_drivers(mysql=driver):
            run_mysql_query("SELECT id FROM users")

        self.assertTrue(driver.cursor.closed)
        self.assertTrue(driver.connection.closed)

    # -- the error contract -------------------------------------------------

    def test_a_failing_connection_is_reported_not_raised(self):
        """A failure comes back as a string."""
        driver = _driver(error=RuntimeError("connection refused"))

        with _stubbed_drivers(mysql=driver):
            result = run_mysql_query("SELECT 1")

        self.assertIsInstance(result, str)

    def test_the_error_message_names_mysql(self):
        """The message says which database failed."""
        driver = _driver(error=RuntimeError("connection refused"))

        with _stubbed_drivers(mysql=driver):
            result = run_mysql_query("SELECT 1")

        self.assertTrue(result.startswith("Error running MySQL query:"), result)
        self.assertIn("connection refused", result)

    def test_a_failing_query_is_reported_not_raised(self):
        """A broken statement comes back as a string."""
        driver = _driver(error=RuntimeError("Table 'nope' doesn't exist"))

        with _stubbed_drivers(mysql=driver):
            result = run_mysql_query("SELECT * FROM nope")

        self.assertIsInstance(result, str)
        self.assertIn("Table 'nope' doesn't exist", result)

    def test_a_missing_configuration_section_is_reported_not_raised(self):
        """A configuration without a ``mysql`` key is an error, not a crash."""
        with mock.patch.object(operations, "_cfg", {"postgres": CONFIG["postgres"]}):
            with mock.patch.object(operations.mysql.connector, "connect", _driver()):
                result = run_mysql_query("SELECT 1")

        self.assertIsInstance(result, str)
        self.assertIn("Error running MySQL query:", result)


class TestTheErrorContract(unittest.TestCase):
    """The contract the whole toolkit shares.

    A failure is **reported**, never raised: the operations return a
    message string instead of letting an exception reach the agent.
    """

    def test_a_postgres_failure_is_a_string(self):
        driver = _driver(error=RuntimeError("boom"))

        with _stubbed_drivers(postgres=driver):
            result = run_postgres_query("SELECT 1")

        self.assertIsInstance(result, str)
        self.assertNotIsInstance(result, list)

    def test_a_mysql_failure_is_a_string(self):
        driver = _driver(error=RuntimeError("boom"))

        with _stubbed_drivers(mysql=driver):
            result = run_mysql_query("SELECT 1")

        self.assertIsInstance(result, str)
        self.assertNotIsInstance(result, list)

    def test_a_success_is_never_a_string(self):
        """A successful query returns rows, never a message."""
        driver = _driver(description=(("id",),), rows=[(1,)])

        with _stubbed_drivers(postgres=driver, mysql=driver):
            self.assertIsInstance(run_postgres_query("SELECT 1"), list)
            self.assertIsInstance(run_mysql_query("SELECT 1"), list)

    def test_the_operations_log_their_call(self):
        """Both operations log the query they were given."""
        driver = _driver(description=(("id",),), rows=[])

        with _stubbed_drivers(postgres=driver, mysql=driver):
            with self.assertLogs(operations.logger, level="INFO") as captured:
                run_postgres_query("SELECT 1")
                run_mysql_query("SELECT 2")

        joined = "\n".join(captured.output)
        self.assertIn("SELECT 1", joined)
        self.assertIn("SELECT 2", joined)


class TestTheModuleHeader(unittest.TestCase):
    """The module carries the things the rest of the repository expects."""

    def test_it_has_a_logger(self):
        """The toolkit logs through one logger."""
        self.assertIsNotNone(operations.logger)
        self.assertEqual(operations.logger.name, operations.__name__)

    def test_the_logger_is_not_configured_here(self):
        """The module must not call ``basicConfig`` itself.

        The logging is configured centrally, in the orchestrator, so a
        toolkit that configures it would take that configuration away
        from the operator.  The comment in the source says so - and it
        is a comment, so it is not a call.
        """
        source = textwrap.dedent(inspect.getsource(operations))
        calls = [
            line
            for line in source.splitlines()
            if "basicConfig" in line and not line.strip().startswith("#")
        ]
        self.assertEqual(calls, [], f"the module configures logging itself: {calls}")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
