"""
Database Toolkit - the library half.

This module provides functions to run SQL queries against PostgreSQL and MySQL
databases using connection parameters loaded from a YAML configuration file.

This is the **library half** of the database toolkit.  It carries **no
LlamaIndex import**, so it stays usable - and testable - as a plain Python
library.  The LlamaIndex adapter lives next to it in
``agent_db_toolkit.py`` and is the one module of the toolkit that knows
about the agent framework.

The operations are the ones that used to live in the single module
``agent_db_toolkit.py`` at the project root.  They moved here **verbatim**:
same names, same signatures, same docstrings, same error contract - a
failure is reported as a message string, never raised.

One property of the module moved with it, and it is worth knowing about:
the configuration is read **at import time**, from
``db_toolkit_config.yaml`` in the working directory.  That is what the
original module did, and it is preserved - so importing this module
without that file raises ``FileNotFoundError``, exactly as importing the
original did.

Category: Database
Retriever Keywords: sql, postgres, mysql, query, database, schema, rows

Prerequisites:
    - db_toolkit_config.yaml must exist in the working directory
    - psycopg2 (for PostgreSQL) and mysql-connector-python (for MySQL) must be installed
"""
import yaml
import psycopg2
import mysql.connector
import logging

# Logging is configured centrally in agent-torvalds.py.
# Do NOT call logging.basicConfig() here — it is a no-op after the first call.
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration loader
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_PATH = "db_toolkit_config.yaml"

def _load_config(path: str = _DEFAULT_CONFIG_PATH) -> dict:
    """
    Load database configuration from a YAML file.
    
    Args:
        path: Path to the YAML config file (default: 'db_toolkit_config.yaml')
        
    Returns:
        dict: Parsed configuration dictionary
        
    Raises:
        FileNotFoundError: If config file does not exist
        yaml.YAMLError: If the file is not valid YAML
    """
    with open(path) as f:
        return yaml.safe_load(f)


# Load config once at import time (lazy reload available via _load_config)
_cfg = _load_config()

# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------

def run_postgres_query(query: str) -> list[dict]:
    """
    Run a SQL query on PostgreSQL and return rows as a list of dictionaries.
    
    Use this tool for executing SELECT queries, schema inspection, data retrieval,
    or DDL/DML operations on a PostgreSQL database.
    
    Connection parameters are read from `db_toolkit_config.yaml` under the
    `postgres` key.
    
    Args:
        query (str): SQL query string to execute
        
    Returns:
        list[dict]: List of rows where each row is a dict mapping column names
                    to values. Returns an empty list for non-SELECT queries.
        
    Example:
        >>> run_postgres_query("SELECT id, name FROM users LIMIT 5")
        [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}, ...]
        
        >>> run_postgres_query("CREATE TABLE test (id INT)")
        []
        
    Keywords: postgres, postgresql, select, insert, update, delete, schema, table, query
    """
    logger.info(f"run_postgres_query called with query: {query}")
    try:
        conf = _cfg["postgres"]
        conn = psycopg2.connect(**conf)
        cur = conn.cursor()
        cur.execute(query)
        
        # Fetch results only if the query produces a result set
        if cur.description:
            cols = [desc[0] for desc in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        else:
            rows = []
        
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        return f"Error running PostgreSQL query: {str(e)}"


# ---------------------------------------------------------------------------
# MySQL
# ---------------------------------------------------------------------------

def run_mysql_query(query: str) -> list[dict]:
    """
    Run a SQL query on MySQL and return rows as a list of dictionaries.
    
    Use this tool for executing SELECT queries, schema inspection, data retrieval,
    or DDL/DML operations on a MySQL database.
    
    Connection parameters are read from `db_toolkit_config.yaml` under the
    `mysql` key.
    
    Args:
        query (str): SQL query string to execute
        
    Returns:
        list[dict]: List of rows where each row is a dict mapping column names
                    to values. Returns an empty list for non-SELECT queries.
        
    Example:
        >>> run_mysql_query("SELECT id, name FROM users LIMIT 5")
        [{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}, ...]
        
        >>> run_mysql_query("CREATE TABLE test (id INT)")
        []
        
    Keywords: mysql, select, insert, update, delete, schema, table, query
    """
    logger.info(f"run_mysql_query called with query: {query}")
    try:
        conf = _cfg["mysql"]
        conn = mysql.connector.connect(**conf)
        cur = conn.cursor()
        cur.execute(query)
        
        # Fetch results only if the query produces a result set
        if cur.description:
            cols = [desc[0] for desc in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        else:
            rows = []
        
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        return f"Error running MySQL query: {str(e)}"
