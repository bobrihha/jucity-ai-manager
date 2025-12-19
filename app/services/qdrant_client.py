from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings


@dataclass(frozen=True)
class QdrantSearchResult:
    score: float
    payload: dict[str, Any]


class QdrantClient:
    def __init__(self, url: str | None = None) -> None:
        self._url = (url or settings.qdrant_url).rstrip("/")

    async def ensure_collection(self, name: str, *, vector_size: int) -> None:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(f"{self._url}/collections/{name}")
            if r.status_code == 200:
                return
            if r.status_code not in {404}:
                r.raise_for_status()

            payload = {
                "vectors": {"size": vector_size, "distance": "Cosine"},
            }
            cr = await client.put(f"{self._url}/collections/{name}", json=payload)
            cr.raise_for_status()

    async def upsert_points(self, collection: str, *, points: list[dict[str, Any]]) -> None:
        if not points:
            return
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.put(
                f"{self._url}/collections/{collection}/points",
                json={"points": points},
            )
            r.raise_for_status()

    async def search(
        self,
        collection: str,
        *,
        query_vector: list[float],
        top_k: int,
        query_filter: dict[str, Any] | None = None,
    ) -> list[QdrantSearchResult]:
        body: dict[str, Any] = {"vector": query_vector, "limit": top_k, "with_payload": True}
        if query_filter:
            body["filter"] = query_filter
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(f"{self._url}/collections/{collection}/points/search", json=body)
            r.raise_for_status()
            data = r.json()
        result = []
        for item in data.get("result", []):
            result.append(QdrantSearchResult(score=float(item.get("score", 0.0)), payload=item.get("payload", {})))
        return result

    async def delete_collection(self, name: str) -> None:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.delete(f"{self._url}/collections/{name}")
            if r.status_code in {200, 202, 404}:
                return
            r.raise_for_status()

