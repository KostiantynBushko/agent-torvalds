-- Verify users table exists and has correct structure

SELECT 1
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name = 'users';

SELECT 1
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'users'
  AND column_name = 'id';

SELECT 1
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'users'
  AND column_name = 'username';
