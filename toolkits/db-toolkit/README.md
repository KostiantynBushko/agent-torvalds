# Database Toolkit

SQL query execution for PostgreSQL and MySQL, exposed as tools for a
LlamaIndex `FunctionAgent`.

The toolkit is a **module** — a folder, not a loose file:

```
toolkits/db-toolkit/
├── __init__.py           # the public API surface
├── operations.py         # the SQL operations — the library half
├── agent_db_toolkit.py   # the LlamaIndex adapter
├── py.typed              # PEP 561 marker
└── tests/                # the module-local tests
```

## The two halves

| Module | Role | LlamaIndex | Third party |
|--------|------|------------|-------------|
| `operations.py` | the 2 SQL operations and the config loader | **no** | `PyYAML`, `psycopg2`, `mysql-connector-python` |
| `agent_db_toolkit.py` | the adapter — `get_all_tools()` | **yes** | `llama-index-core` |

The split is the point. `operations.py` carries **no** LlamaIndex import,
so the SQL operations stay usable — and testable — as a plain Python
library. The adapter is the one module that knows about the agent
framework, and it is imported on demand. Importing the toolkit therefore
never pulls LlamaIndex into the process.

Unlike the OS, the Linux and the Windows toolkits, this toolkit's
**library half does have third-party dependencies**: the two database
drivers, and `PyYAML`, which reads the configuration file.

## Installing

Standalone:

```bash
pip install .            # the library half
pip install '.[agent]'   # and the LlamaIndex adapter
```

## Importing

The directory name contains a hyphen, so the package is reached through the
alias that `toolkits/__init__.py` registers:

```python
from toolkits.db_toolkit import run_postgres_query, run_mysql_query
```

The adapter is a submodule of the package, imported on demand:

```python
from toolkits.db_toolkit.agent_db_toolkit import get_all_tools
```

The adapter re-exports the operations, so a star import keeps working the
way it did when the toolkit was a single module:

```python
from toolkits.db_toolkit.agent_db_toolkit import *
```

## The configuration

The connection parameters are read from `db_toolkit_config.yaml` in the
**working directory**:

```yaml
postgres:
  host: 127.0.0.1
  port: 5432
  user: postgres
  password: postgres

mysql:
  host: 127.0.0.1
  port: 3306
  user: root
  password: root
```

> **The configuration is read at import time.** The module loads it once,
> when it is imported, and the operations use the loaded values. That is
> the behaviour the toolkit had as a single module at the project root,
> and the move preserved it — so importing the toolkit without that file
> raises `FileNotFoundError`.

Because the file is read at import time, the toolkit is **optional** for
the agent: a missing configuration file, a missing driver or a broken
toolkit degrades to "no database tools" rather than to a failed boot.

## The operations

| Operation | What it does | Returns |
|-----------|--------------|---------|
| `run_postgres_query(query)` | run a SQL query on PostgreSQL | `list[dict]` |
| `run_mysql_query(query)` | run a SQL query on MySQL | `list[dict]` |

A query that produces a result set comes back as a list of dictionaries,
one per row, keyed by column name. A query that produces no result set —
`CREATE TABLE`, `INSERT`, `UPDATE` — comes back as an empty list.

```python
>>> run_postgres_query("SELECT id, name FROM users LIMIT 5")
[{'id': 1, 'name': 'Alice'}, {'id': 2, 'name': 'Bob'}]
>>> run_postgres_query("CREATE TABLE test (id INT)")
[]
```

## The error contract

Every operation **reports** a failure; none of them raises. A query that
fails — a wrong password, a missing table, a syntax error — comes back as
a **string**, not as an exception:

```python
>>> run_postgres_query("SELECT * FROM nope")
'Error running PostgreSQL query: relation "nope" does not exist'
```

This is the contract the toolkit has always had, and the move preserved it
exactly.

## Safety

These operations run **arbitrary SQL** against the configured databases,
as the user the agent runs as. There is no allow-list, no read-only mode
and no sandbox: a `DROP TABLE` reaches the server exactly as it was
written. The tool descriptions say what the operations do; the guard is
the operator's.

## Testing

```bash
pytest toolkits/db-toolkit/tests
```

The suite is offline: it drives the operations through a stubbed
`psycopg2` and a stubbed `mysql.connector`, so it never opens a
connection to anything.

## See also

- `db_toolkit_config.yaml` — the connection parameters, in the working
  directory
- `setup_postgres_db.sql` — the PostgreSQL setup the agent's own chat
  store uses
