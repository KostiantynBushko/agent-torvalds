"""
Database Toolkit - SQL query execution for PostgreSQL and MySQL.

This module provides functions to run SQL queries against PostgreSQL and MySQL
databases using connection parameters loaded from a YAML configuration file.

Category: Database
Retriever Keywords: sql, postgres, mysql, query, database, schema, rows

Prerequisites:
    - db_toolkit_config.yaml must exist in the working directory
    - psycopg2 (for PostgreSQL) and mysql-connector-python (for MySQL) must be installed
"""
import yaml
import psycopg2
import mysql.connector
from llama_index.core.tools import FunctionTool

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


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

def get_all_tools() -> list[FunctionTool]:
    """
    Return all database tools as FunctionTool objects for on-demand loading.
    
    Each tool includes category metadata for better retrieval.
    
    Returns:
        list[FunctionTool]: List of database FunctionTool objects
    """
    return [
        FunctionTool.from_defaults(
            fn=run_postgres_query,
            description="Run a SQL query on PostgreSQL. Use for SELECT, DDL, DML on Postgres. Category: Database",
        ),
        FunctionTool.from_defaults(
            fn=run_mysql_query,
            description="Run a SQL query on MySQL. Use for SELECT, DDL, DML on MySQL. Category: Database",
        ),
    ]


# ---------------------------------------------------------------------------
# Legacy top-level tool instances (kept for backward compatibility)
# ---------------------------------------------------------------------------

postgres_tool = FunctionTool.from_defaults(run_postgres_query)
mysql_tool = FunctionTool.from_defaults(run_mysql_query)