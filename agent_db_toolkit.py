import yaml
import psycopg2
import mysql.connector
from llama_index.core.tools import FunctionTool

# Load config once
with open("db_toolkit_config.yaml") as f:
    """
    postgres:
        host: 127.0.0.1
        port: 5432
        user: llama
        password: secret123
        database: llama_index_db

    mysql:
        host: 127.0.0.1
        port: 3306
        user: llama
        password: secret123
        database: llama_index_db
    """
    cfg = yaml.safe_load(f)

def run_postgres_query(query: str) -> list[dict]:
    """
    Run a SQL query on Postgres and return rows as dicts.
    """
    conf = cfg["postgres"]
    conn = psycopg2.connect(**conf)
    cur = conn.cursor()
    cur.execute(query)
    cols = [desc[0] for desc in cur.description] if cur.description else []
    rows = [dict(zip(cols, row)) for row in cur.fetchall()] if cols else []
    cur.close()
    conn.close()
    return rows

def run_mysql_query(query: str) -> list[dict]:
    """
    Run a SQL query on MySQL and return rows as dicts.
    """
    conf = cfg["mysql"]
    conn = mysql.connector.connect(**conf)
    cur = conn.cursor()
    cur.execute(query)
    cols = [desc[0] for desc in cur.description] if cur.description else []
    rows = [dict(zip(cols, row)) for row in cur.fetchall()] if cols else []
    cur.close()
    conn.close()
    return rows

postgres_tool = FunctionTool.from_defaults(run_postgres_query)
mysql_tool = FunctionTool.from_defaults(run_mysql_query)
