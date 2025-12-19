from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class FactsVersionsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_published_version_id(self, park_id: UUID) -> UUID | None:
        res = await self._session.execute(
            text(
                """
                SELECT published_version_id
                FROM park_published_state
                WHERE park_id = :park_id
                LIMIT 1
                """
            ),
            {"park_id": park_id},
        )
        row = res.mappings().first()
        return row["published_version_id"] if row else None

    async def list_published_versions(self, park_id: UUID, *, limit: int = 20) -> list[dict[str, Any]]:
        res = await self._session.execute(
            text(
                """
                SELECT id, status, created_at, published_at, published_by, notes
                FROM facts_versions
                WHERE park_id = :park_id AND status = 'published'
                ORDER BY published_at DESC NULLS LAST, created_at DESC
                LIMIT :limit
                """
            ),
            {"park_id": park_id, "limit": limit},
        )
        return [dict(r) for r in res.mappings().all()]

    async def get_snapshot_json(self, version_id: UUID) -> dict[str, Any] | None:
        res = await self._session.execute(
            text(
                """
                SELECT snapshot_json
                FROM facts_snapshots
                WHERE facts_version_id = :id
                LIMIT 1
                """
            ),
            {"id": version_id},
        )
        row = res.mappings().first()
        if not row:
            return None
        snap = row["snapshot_json"]
        if isinstance(snap, str):
            return json.loads(snap)
        return snap

