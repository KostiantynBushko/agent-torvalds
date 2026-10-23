-- Revert chat_sessions table creation

BEGIN;

DROP TABLE IF EXISTS chat_sessions;

COMMIT;
