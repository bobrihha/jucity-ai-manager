from __future__ import annotations

import asyncio
import os
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.repos.facts_repo import FactsRepo
from app.repos.kb_sources_repo import KBSourcesRepo
from app.services.kb_indexer import KBIndexer


async def main() -> int:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async with SessionLocal() as session:
        facts = FactsRepo(session)
        park = await facts.get_park_by_slug("nn")
        if not park:
            raise RuntimeError("park_slug=nn not found; did you run sql/seed_nn.sql?")

        fixtures_dir = Path(__file__).resolve().parents[1] / "fixtures" / "kb"
        sources_repo = KBSourcesRepo(session)

        await sources_repo.ensure_source(
            park_id=park.id,
            source_type="file_path",
            source_url=f"{park.base_url.rstrip('/')}/rules/",
            file_path=str(fixtures_dir / "rules.html"),
            title="Правила посещения",
        )
        await sources_repo.ensure_source(
            park_id=park.id,
            source_type="file_path",
            source_url=f"{park.base_url.rstrip('/')}/attractions/",
            file_path=str(fixtures_dir / "attractions.html"),
            title="Аттракционы",
        )
        await sources_repo.ensure_source(
            park_id=park.id,
            source_type="file_path",
            source_url=f"{park.base_url.rstrip('/')}/rest/",
            file_path=str(fixtures_dir / "restaurant.html"),
            title="Ресторан",
        )

        indexer = KBIndexer(session)
        await indexer.run_reindex(park_id=park.id, park_slug=park.slug, triggered_by="script", reason="fixtures")
        await session.commit()

    await engine.dispose()
    print("OK: fixtures indexed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
