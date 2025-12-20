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

        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_admin_chat_ids = os.getenv("TELEGRAM_ADMIN_CHAT_IDS", "")
        self.public_api_base_url = os.getenv("PUBLIC_API_BASE_URL", "")

        self.llm_enabled = os.getenv("LLM_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
        self.llm_provider = os.getenv("LLM_PROVIDER", "mock").strip().lower()
        self.llm_api_key = os.getenv("LLM_API_KEY", "").strip()
        self.llm_model = os.getenv("LLM_MODEL", "").strip()
        self.brand_voice = os.getenv("BRAND_VOICE", "jucity_nn").strip()

        self.llm_mode = os.getenv("LLM_MODE", "classic").strip().lower()  # classic|planner
        self.llm_planner_provider = os.getenv("LLM_PLANNER_PROVIDER", "mock").strip().lower()  # mock|openai
        self.llm_planner_api_key = (os.getenv("LLM_PLANNER_API_KEY", "").strip() or self.llm_api_key)
        self.llm_planner_model = (os.getenv("LLM_PLANNER_MODEL", "").strip() or self.llm_model)


settings = Settings()
