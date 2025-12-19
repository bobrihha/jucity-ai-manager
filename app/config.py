from __future__ import annotations

import os

from dotenv import load_dotenv


class Settings:
    def __init__(self) -> None:
        load_dotenv(override=False)

        self.database_url = os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres",
        )

        self.qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        self.rag_enabled = os.getenv("RAG_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
        self.embeddings_provider = os.getenv("EMBEDDINGS_PROVIDER", "local_hash")

        self.admin_api_key = os.getenv("ADMIN_API_KEY", "")


settings = Settings()
