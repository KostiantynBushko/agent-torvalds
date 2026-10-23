-- Verify chat_sessions table exists and has correct structure

SELECT 1
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name = 'chat_sessions';

SELECT 1
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'chat_sessions'
  AND column_name = 'id';

SELECT 1
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'chat_sessions'
  AND column_name = 'session_id';
