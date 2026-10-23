-- Revert users table creation

BEGIN;

DROP TABLE IF EXISTS users;

COMMIT;
