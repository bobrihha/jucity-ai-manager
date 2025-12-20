from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

# Make test suite deterministic/offline regardless of local `.env`.
# (We can still enable planner explicitly inside specific tests via monkeypatch.)
os.environ.setdefault("LLM_MODE", "classic")
os.environ.setdefault("LLM_PLANNER_PROVIDER", "mock")
os.environ.setdefault("LLM_PLANNER_API_KEY", "")
os.environ.setdefault("LLM_PLANNER_MODEL", "")
os.environ.setdefault("LLM_ENABLED", "false")
os.environ.setdefault("LLM_PROVIDER", "mock")


def _database_url() -> str:
    return os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres")


async def _apply_schema(engine: AsyncEngine) -> None:
    schema_path = Path(__file__).resolve().parents[1] / "sql" / "schema.sql"
    sql = schema_path.read_text(encoding="utf-8")
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    async with engine.begin() as conn:
        for stmt in statements:
            await conn.execute(text(stmt))


@pytest.fixture(scope="session")
async def db_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(_database_url(), pool_pre_ping=True)
    try:
        await _apply_schema(engine)
    except Exception as e:
        await engine.dispose()
        pytest.skip(f"DB is not available or schema failed to apply: {e}")
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    SessionLocal = async_sessionmaker(db_engine, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session


@pytest.fixture
async def test_park(db_session: AsyncSession) -> dict:
    park_id = uuid4()
    slug = f"t{park_id.hex[:8]}"
    await db_session.execute(
        text("INSERT INTO parks (id, slug, name, base_url) VALUES (:id, :slug, :name, :base_url)"),
        {"id": park_id, "slug": slug, "name": "Test Park", "base_url": "https://example.test"},
    )
    await db_session.commit()
    return {"id": park_id, "slug": slug}
