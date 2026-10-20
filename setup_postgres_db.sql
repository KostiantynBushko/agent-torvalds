-- ============================================================================
-- setup_postgres_db.sql
--
-- Bootstrap the PostgreSQL database used by the Torvalds agent for
-- persistent chat memory and chat-session metadata.
--
-- Consumers of this database:
--   * agent_chat_memory.py  -- LlamaIndex PostgresChatStore (message bodies)
--   * chat_manager/storage  -- SQLAlchemy CustomDBConnector (users + sessions)
--   * chat_manager/backend  -- PostgresChatStoreBackend (message backend)
--
-- Defaults match the agent's built-in defaults (TORVALDS_PG_*), so the
-- script works out of the box with no arguments:
--   host=127.0.0.1  port=5432  user=postgres  password=postgres
--   database=llama_index_db
--
-- ---------------------------------------------------------------------------
-- Usage
-- ---------------------------------------------------------------------------
--   psql -U postgres -h 127.0.0.1 -d postgres -v ON_ERROR_STOP=1 \
--        -v app_user=llama -v app_password=llama \
--        -v app_database=llama_index_db -f setup_postgres_db.sql
--
-- Every variable is optional; the values below are used when omitted.
--
-- NOTE: this script must be run against the "postgres" maintenance
-- database, not the application database, because CREATE DATABASE cannot run
-- inside a transaction block.
--
-- ---------------------------------------------------------------------------
-- Idempotency
-- ---------------------------------------------------------------------------
-- The script is safe to re-run. Existing roles and databases are reused
-- rather than recreated, and the role password is re-applied so that the
-- credentials always match the configured values.
-- ============================================================================

\set ON_ERROR_STOP on

-- ---------------------------------------------------------------------------
-- Configuration (overridable with -v on the psql command line)
-- ---------------------------------------------------------------------------
\if :{?app_user}
\else
  \set app_user 'llama'
\endif

\if :{?app_password}
\else
  \set app_password 'llama'
\endif

\if :{?app_database}
\else
  \set app_database 'llama_index_db'
\endif

\if :{?app_host}
\else
  \set app_host '127.0.0.1'
\endif

\if :{?app_port}
\else
  \set app_port '5432'
\endif

\echo '============================================================'
\echo ' Torvalds PostgreSQL setup'
\echo '------------------------------------------------------------'
\echo '  role      :' :app_user
\echo '  database  :' :app_database
\echo '  endpoint  :' :app_host ':' :app_port
\echo '============================================================'


-- ===========================================================================
-- 1. Role
--
-- CREATE ROLE ... IF NOT EXISTS does not exist in PostgreSQL, so the role is
-- created only when it is missing. Password and LOGIN are (re)applied on
-- every run so the role always matches the configured credentials.
-- ===========================================================================
SELECT format('CREATE ROLE %I WITH LOGIN PASSWORD %L', :'app_user', :'app_password')
WHERE NOT EXISTS (
    SELECT 1 FROM pg_roles WHERE rolname = :'app_user'
)\gexec

-- Re-apply the password and LOGIN privilege. This is intentionally not
-- conditional: it keeps an existing role in sync with the configuration.
SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'app_user', :'app_password')
\gexec


-- ===========================================================================
-- 2. Database
--
-- CREATE DATABASE has no IF NOT EXISTS form either, so the same
-- create-if-missing pattern is used. The database is owned by the app role
-- so that the role can create its own tables (LlamaIndex creates the
-- "chatstore" table, SQLAlchemy creates "users" and "chat_sessions").
-- ===========================================================================
SELECT format('CREATE DATABASE %I OWNER %I ENCODING ''UTF8''', :'app_database', :'app_user')
WHERE NOT EXISTS (
    SELECT 1 FROM pg_database WHERE datname = :'app_database'
)\gexec


-- ===========================================================================
-- 3. Privileges
--
-- The grants below must be applied from *inside* the target database:
-- database-level privileges (CONNECT/CREATE) are stored per database, while
-- schema and table privileges are stored per database as well. Connecting
-- to the maintenance database would grant nothing to the application role.
-- ===========================================================================
\connect :app_database

-- Database-level privileges: let the role connect and create its own
-- objects (CREATE on the database implies CREATE on the public schema for
-- PostgreSQL 14 and earlier; on 15+ the schema grant below covers it).
GRANT CONNECT, TEMPORARY ON DATABASE :"app_database" TO :"app_user";

-- Schema privileges on public: CREATE is required so the role can create
-- the tables the agent relies on. pg_database_owner (PostgreSQL 14+) already
-- grants this to the database owner, but the explicit grant keeps the
-- script working on older servers and after an ownership change.
GRANT USAGE, CREATE ON SCHEMA public TO :"app_user";

-- Reassign objects created by the script's own user (typically "postgres")
-- to the app role, so that the role owns - and can therefore ALTER/DROP -
-- everything in its database. Objects already owned by the app role (such
-- as the LlamaIndex "chatstore" table) are left untouched.
--
-- The statements are generated with format() and executed via \gexec, because
-- psql does not substitute variables inside dollar-quoted blocks.
SELECT format(
           'ALTER %s %I.%I OWNER TO %I',
           CASE c.relkind
               WHEN 'r' THEN 'TABLE'
               WHEN 'p' THEN 'TABLE'
               WHEN 'S' THEN 'SEQUENCE'
               WHEN 'v' THEN 'VIEW'
               WHEN 'm' THEN 'MATERIALIZED VIEW'
           END,
           n.nspname, c.relname, :'app_user'
       )
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p', 'S', 'v', 'm')
  AND n.nspname = 'public'
  AND c.relname NOT LIKE 'pg\_%'
  AND c.relowner = (SELECT oid FROM pg_roles WHERE rolname = current_user)
  AND c.relowner <> (SELECT oid FROM pg_roles WHERE rolname = :'app_user')
\gexec

-- Explicit table-level grants for every table in the database, so the role
-- can read and write even when a table is owned by a different role.
-- GRANT ALL ON ALL TABLES covers the tables that exist right now; the
-- default privileges below cover tables created later (e.g. by LlamaIndex
-- or SQLAlchemy at runtime).
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO :"app_user";
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO :"app_user";
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO :"app_user";

-- Default privileges: anything created later in the public schema by the
-- script's own user is automatically accessible to the app role.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL ON TABLES TO :"app_user";
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL ON SEQUENCES TO :"app_user";


-- ===========================================================================
-- 4. Extensions
--
-- pgvector is required by llama-index-vector-stores-postgres
-- (PGVectorStore issues "CREATE EXTENSION IF NOT EXISTS vector").
-- The extension is normally packaged separately (postgresql-16-pgvector),
-- so its absence is reported as a warning instead of aborting the script:
-- the chat store and the chat-session metadata tables work without it,
-- and only the vector memory block needs it.
--
-- The CREATE EXTENSION call is wrapped in a DO block because a missing
-- extension raises an error that would otherwise stop the script.
-- ===========================================================================
DO $$
BEGIN
    BEGIN
        CREATE EXTENSION IF NOT EXISTS vector;
        RAISE NOTICE 'pgvector extension enabled.';
    EXCEPTION WHEN OTHERS THEN
        RAISE WARNING 'pgvector extension is not available (%). Install the '
                      'server package (e.g. "apt install postgresql-16-pgvector") '
                      'to enable vector memory blocks. Continuing without it.', SQLERRM;
    END;
END
$$;

-- pg_trgm backs the trigram similarity search used by the vector store's
-- hybrid search. Same graceful-degradation approach as pgvector.
DO $$
BEGIN
    BEGIN
        CREATE EXTENSION IF NOT EXISTS pg_trgm;
        RAISE NOTICE 'pg_trgm extension enabled.';
    EXCEPTION WHEN OTHERS THEN
        RAISE WARNING 'pg_trgm extension is not available (%). Hybrid search '
                      'will be unavailable. Continuing without it.', SQLERRM;
    END;
END
$$;


-- ===========================================================================
-- 5. Verification
-- ===========================================================================
\echo ''
\echo '------------------------------------------------------------'
\echo ' Verification'
\echo '------------------------------------------------------------'

SELECT rolname AS role,
       rolcanlogin AS can_login,
       rolcreatedb AS can_create_db
FROM pg_roles
WHERE rolname = :'app_user';

SELECT datname AS database,
       pg_get_userbyid(datdba) AS owner,
       pg_encoding_to_char(encoding) AS encoding
FROM pg_database
WHERE datname = :'app_database';

-- Objects the agent expects to exist in the target database.
SELECT n.nspname AS schema,
       c.relname AS object,
       pg_get_userbyid(c.relowner) AS owner
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'S')
  AND n.nspname = 'public'
  AND c.relname IN ('users', 'chat_sessions', 'chatstore')
ORDER BY c.relname;

SELECT extname AS extension, extversion AS version
FROM pg_extension
WHERE extname IN ('vector', 'pg_trgm')
ORDER BY extname;

\echo ''
\echo 'Setup complete. Connect with:'
\echo '  psql -h' :app_host '-p' :app_port '-U' :app_user '-d' :app_database
\echo ''
