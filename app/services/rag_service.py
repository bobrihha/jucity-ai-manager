from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repos.kb_indexes_repo import KBIndexesRepo
from app.services.embeddings import Embeddings
from app.services.qdrant_client import QdrantClient


@dataclass(frozen=True)
class RetrievedChunk:
    score: float
    source_url: str | None
    title: str | None
    chunk_id: str | None
    chunk_text: str


class RAGService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._indexes_repo = KBIndexesRepo(session)
        self._embed = Embeddings()
        self._qdrant = QdrantClient()

    async def retrieve(self, *, park_id: UUID, park_slug: str, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        idx = await self._indexes_repo.get_active_index_id(park_id=park_id)
        if not idx:
            return []
        collection = f"jucity_{park_slug}_idx_{idx}".replace("-", "")
        emb = await self._embed.embed([query])
        now_epoch = int(datetime.now(timezone.utc).timestamp())
        results = await self._qdrant.search(
            collection,
            query_vector=emb.vectors[0],
            top_k=top_k,
            query_filter={
                "must": [
                    {"range": {"expires_at_epoch": {"gte": now_epoch}}},
                ]
            },
        )
        out: list[RetrievedChunk] = []
        for r in results:
            payload = r.payload or {}
            out.append(
                RetrievedChunk(
                    score=r.score,
                    source_url=payload.get("source_url"),
                    title=payload.get("title"),
                    chunk_id=payload.get("chunk_id"),
                    chunk_text=payload.get("text") or "",
                )
            )
        return out
