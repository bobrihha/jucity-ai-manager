from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repos.kb_indexes_repo import KBIndexesRepo
from app.repos.kb_jobs_repo import KBJobsRepo
from app.repos.kb_sources_repo import KBSourcesRepo
from app.services.chunker import chunk_text
from app.services.embeddings import Embeddings
from app.services.kb_fetcher import KBFetcher
from app.services.qdrant_client import QdrantClient


@dataclass(frozen=True)
class IndexStats:
    sources_count: int
    chunks_count: int
    embed_time_ms: int
    upsert_time_ms: int


class KBIndexer:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._sources_repo = KBSourcesRepo(session)
        self._jobs_repo = KBJobsRepo(session)
        self._indexes_repo = KBIndexesRepo(session)
        self._fetcher = KBFetcher()
        self._embed = Embeddings()
        self._qdrant = QdrantClient()

    async def run_reindex(self, *, park_id: UUID, park_slug: str, triggered_by: str | None, reason: str | None) -> UUID:
        sources = await self._sources_repo.list_enabled_sources(park_id)
        job_id = await self._jobs_repo.create_job(
            park_id=park_id,
            triggered_by=triggered_by,
            reason=reason,
            sources_json=[
                {
                    "id": str(s.id),
                    "source_type": s.source_type,
                    "source_url": s.source_url,
                    "file_path": s.file_path,
                    "title": s.title,
                }
                for s in sources
            ],
        )
        await self._jobs_repo.set_job_running(job_id)

        index_id = await self._indexes_repo.create_index(park_id=park_id, label=f"reindex {datetime.now(timezone.utc).isoformat()}")
        collection = f"jucity_{park_slug}_idx_{index_id}".replace("-", "")

        try:
            await self._qdrant.ensure_collection(collection, vector_size=self._embed.vector_size)

            chunks_count = 0
            embed_ms = 0
            upsert_ms = 0

            for src in sources:
                if src.expires_at and src.expires_at <= datetime.now(timezone.utc):
                    continue

                fetched = await self._fetcher.fetch_source_text(src)
                if src.last_hash and fetched.text_hash == src.last_hash:
                    continue

                chunks = chunk_text(text=fetched.text, title=fetched.title or src.title, source_url=fetched.source_url or src.source_url)
                if not chunks:
                    continue

                t0 = time.time()
                emb = await self._embed.embed([c.chunk_text for c in chunks])
                embed_ms += int((time.time() - t0) * 1000)

                now = datetime.now(timezone.utc).isoformat()
                expires_epoch = _expires_epoch(src.expires_at)
                points = []
                for c, vec in zip(chunks, emb.vectors, strict=True):
                    points.append(
                        {
                            "id": c.chunk_id,
                            "vector": vec,
                            "payload": {
                                "park_slug": park_slug,
                                "kb_index_id": str(index_id),
                                "source_url": c.source_url,
                                "title": c.title,
                                "chunk_id": c.chunk_id,
                                "chunk_index": c.chunk_index,
                                "text_hash": fetched.text_hash,
                                "text": c.chunk_text[:4000],
                                "created_at": now,
                                "expires_at_epoch": expires_epoch,
                            },
                        }
                    )

                t1 = time.time()
                await self._qdrant.upsert_points(collection, points=points)
                upsert_ms += int((time.time() - t1) * 1000)

                chunks_count += len(chunks)
                await self._sources_repo.update_last_fetched(src.id, last_hash=fetched.text_hash, content_type=fetched.content_type)

            stats = IndexStats(
                sources_count=len(sources),
                chunks_count=chunks_count,
                embed_time_ms=embed_ms,
                upsert_time_ms=upsert_ms,
            )
            await self._jobs_repo.set_job_success(job_id, stats_json=stats.__dict__)
            await self._indexes_repo.activate_index(park_id=park_id, index_id=index_id)
            return job_id
        except Exception as e:
            await self._jobs_repo.set_job_failed(job_id, error_text=str(e))
            raise


def _expires_epoch(expires_at: datetime | None) -> int:
    if not expires_at:
        return 32503680000  # year 3000-01-01
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return int(expires_at.timestamp())
