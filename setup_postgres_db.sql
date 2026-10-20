-- Setup PostgreSQL database for the Torvalds chat memory module.
-- Creates the "llama" role and the "llama_index_db" database used by
-- agent_chat_memory.py (TORVALDS_PG_DATABASE, default: llama_index_db).

CREATE USER llama WITH PASSWORD 'llama';
CREATE DATABASE llama_index_db OWNER llama;
GRANT ALL PRIVILEGES ON DATABASE llama_index_db TO llama;
