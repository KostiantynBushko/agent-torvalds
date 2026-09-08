from llama_index.storage.chat_store.postgres import PostgresChatStore
from llama_index.core.memory import ChatMemoryBuffer

# Connect to Postgres
chat_store = PostgresChatStore.from_uri(
    uri="postgres+asyncpg://llama:llama@127.0.0.1:5432/llama_index_db",
)

# Create memory buffer backed by Postgres
chat_memory = ChatMemoryBuffer.from_defaults(
    token_limit=3000,
    chat_store=chat_store,
    chat_store_key="user1",  # unique key per conversation
)