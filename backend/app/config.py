"""
Application configuration.

All tunables live here and are sourced from environment variables (see `.env`).
Nothing else in the codebase should call `os.getenv` directly - import `settings`
from this module instead, so every setting has one source of truth.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- LLM (any OpenAI-compatible provider: OpenAI, Groq, OpenRouter, Ollama, ...) ---
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o-mini"

    # --- Embeddings ---
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    # --- Chunking / retrieval ---
    CHUNK_SIZE: int = 600
    CHUNK_OVERLAP: int = 120
    TOP_K: int = 5
    # Cosine distance (0 = identical, 1 = unrelated). If the best match's distance
    # exceeds this, the question is treated as out-of-scope without calling the LLM.
    SIMILARITY_THRESHOLD: float = 0.95
    MAX_HISTORY_TURNS: int = 5

    # --- Paths ---
    CHROMA_PERSIST_DIR: str = "app/database/chroma_db"
    UPLOAD_DIR: str = "app/uploads"
    CONVERSATION_HISTORY_PATH: str = "app/conversation/history.json"
    PROCESSED_DATA_DIR: str = "data/processed"
    EMBEDDINGS_CACHE_DIR: str = "data/embeddings"

    # --- Server ---
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    RELOAD: bool = True

    # --- Fixed response text ---
    OUT_OF_SCOPE_MESSAGE: str = (
        "This question is outside the scope of the uploaded document. "
        "Please ask questions related to the uploaded PDF only."
    )


settings = Settings()
