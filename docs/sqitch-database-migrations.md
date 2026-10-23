# Sqitch Database Migration System

## Overview

This document describes the integration of [Sqitch](https://sqitch.org/) as the database migration management system for the Torvalds agent's PostgreSQL database. Sqitch provides a robust, dependency-aware approach to database version control that complements the existing `setup_postgres_db.sql` bootstrap script.

## Architecture

### Current Database Setup

The Torvalds agent uses PostgreSQL for:
- **Chat Memory**: LlamaIndex PostgresChatStore for persistent conversation history
- **Session Management**: SQLAlchemy-based user and session tracking
- **Vector Storage**: pgvector extension for semantic search capabilities

### Database Components

| Component | Purpose | Tables |
|-----------|---------|--------|
| LlamaIndex ChatStore | Message storage and retrieval | `chatstore` |
| Chat Manager | User and session management | `users`, `chat_sessions` |
| Vector Store | Semantic search and embeddings | Vector indexes (via pgvector) |

## Sqitch Configuration

### Installation

```bash
# Ubuntu/Debian
sudo apt install sqitch

# Or via cpan (Perl)
cpan install App::Sqitch

# Or via Homebrew (macOS)
brew install sqitch
```

### Project Structure

```
agent-torvalds/
├── .sqitch/
│   └── config          # Sqitch configuration
├── sqitch.conf         # Main configuration file
├── deploy/             # Forward deployment scripts
│   ├── users.sql
│   ├── chat_sessions.sql
│   ├── chatstore.sql
│   └── ...
├── revert/             # Rollback scripts
│   ├── users.sql
│   ├── chat_sessions.sql
│   └── ...
├── verify/             # Verification scripts (optional)
│   ├── users.sql
│   └── ...
└── setup_postgres_db.sql  # Bootstrap script (unchanged)
```

## Migration Strategy

### Phase 1: Initial Setup

The existing `setup_postgres_db.sql` script handles:
1. Role creation and configuration
2. Database creation
3. Permission grants
4. Extension installation (pgvector, pg_trgm)

This script remains unchanged as it handles infrastructure setup.

### Phase 2: Schema Management with Sqitch

Sqitch will manage:
1. Table creation and modifications
2. Index management
3. Constraint changes
4. Data migrations
5. Schema versioning

## Configuration Files

### sqitch.conf

```ini
[sqitch]
project = agent-torvalds
top = RDBD::PostgreSQL

[target db]
rdbms = postgresql
dsn = db:llama_index_db
user = llama
password = llama
host = 127.0.0.1
port = 5432

[deploy]
default_target = db

[verify]
default_target = db

[revert]
default_target = db
```

### .sqitch/config

```ini
[sqitch]
project = agent-torvalds
```

## Deployment Scripts

### Example: Users Table

**deploy/users.sql**
```sql
-- Changes in this deployment:
--   * Create users table for chat session management
-- Deployed by: sqitch add users

BEGIN;

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) NOT NULL UNIQUE,
    email VARCHAR(255) UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_email ON users(email);

COMMIT;
```

**revert/users.sql**
```sql
-- Revert users table creation

BEGIN;

DROP TABLE IF EXISTS users;

COMMIT;
```

### Example: Chat Sessions Table

**deploy/chat_sessions.sql**
```sql
-- Changes in this deployment:
--   * Create chat_sessions table for session tracking
--   * Add foreign key relationship to users
-- Deployed by: sqitch add chat_sessions -r users

BEGIN;

CREATE TABLE IF NOT EXISTS chat_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    session_id VARCHAR(255) NOT NULL UNIQUE,
    title VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_chat_sessions_user_id ON chat_sessions(user_id);
CREATE INDEX idx_chat_sessions_session_id ON chat_sessions(session_id);
CREATE INDEX idx_chat_sessions_is_active ON chat_sessions(is_active);

COMMIT;
```

**revert/chat_sessions.sql**
```sql
-- Revert chat_sessions table creation

BEGIN;

DROP TABLE IF EXISTS chat_sessions;

COMMIT;
```

## Workflow

### Adding a New Migration

```bash
# Add a new deployment
sqitch add migration_name -d "Description of changes"

# Add with dependencies
sqitch add migration_name -r dependency1,dependency2 -d "Description"

# This creates:
# - deploy/migration_name.sql
# - revert/migration_name.sql
# - verify/migration_name.sql (optional)
```

### Deploying Changes

```bash
# Deploy all pending changes
sqitch deploy

# Deploy to specific target
sqitch deploy target:db

# Deploy specific changes
sqitch deploy change1 change2

# Verify deployment
sqitch verify

# Revert changes
sqitch revert

# Revert to specific point
sqitch revert change_name
```

### Status and Inspection

```bash
# Show current status
sqitch status

# Show dependency plan
sqitch plan

# Show changes
sqitch changes

# Show bundle information
sqitch bundle
```

## Integration with Existing System

### Bootstrap Process

1. Run `setup_postgres_db.sql` to create database and roles
2. Initialize Sqitch: `sqitch init`
3. Add target configuration
4. Deploy initial schema migrations

### Runtime Considerations

- **LlamaIndex**: Creates `chatstore` table automatically if missing
- **SQLAlchemy**: Creates tables via `create_all()` if missing
- **Sqitch**: Manages schema evolution and versioning

### Migration Best Practices

1. **Idempotency**: Use `IF NOT EXISTS` where possible
2. **Dependencies**: Explicitly declare table dependencies
3. **Rollbacks**: Always provide revert scripts
4. **Testing**: Verify migrations in development first
5. **Documentation**: Comment changes in deployment scripts

## Environment Variables

Sqitch configuration can be overridden with environment variables:

```bash
export SQITCH_TARGET=db
export SQITCH_DEPLOY_DEFAULT_TARGET=db
export SQITCH_VERIFY_DEFAULT_TARGET=db
export SQITCH_REVERT_DEFAULT_TARGET=db
```

Or use a `.env` file:

```bash
SQITCH_TARGET=db
SQITCH_DEPLOY_DEFAULT_TARGET=db
SQITCH_VERIFY_DEFAULT_TARGET=db
SQITCH_REVERT_DEFAULT_TARGET=db
```

## Troubleshooting

### Common Issues

1. **Connection Problems**: Verify PostgreSQL is running and credentials are correct
2. **Permission Issues**: Ensure the `llama` role has appropriate grants
3. **Dependency Conflicts**: Check `sqitch plan` for circular dependencies
4. **Rollback Failures**: Test revert scripts in development environment

### Debug Mode

```bash
# Enable debug output
sqitch deploy --debug

# Show SQL being executed
sqitch deploy --verbose
```

## References

- [Sqitch Documentation](https://sqitch.org/docs/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [LlamaIndex Postgres Integration](https://docs.llamaindex.ai/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
