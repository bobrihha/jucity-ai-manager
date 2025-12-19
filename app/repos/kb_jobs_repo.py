from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class KBJobsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_job(
        self,
        *,
        park_id: UUID,
        triggered_by: str | None,
        reason: str | None,
        sources_json: list[dict[str, Any]],
    ) -> UUID:
        res = await self._session.execute(
            text(
                """
                INSERT INTO kb_index_jobs (park_id, status, triggered_by, reason, sources_json)
                VALUES (:park_id, 'queued', :triggered_by, :reason, CAST(:sources_json AS jsonb))
                RETURNING id
                """
            ),
            {
                "park_id": park_id,
                "triggered_by": triggered_by,
                "reason": reason,
                "sources_json": json.dumps(sources_json, ensure_ascii=False),
            },
        )
        return res.scalar_one()

    async def set_job_running(self, job_id: UUID) -> None:
        await self._session.execute(
            text("UPDATE kb_index_jobs SET status='running', started_at=now() WHERE id=:id"),
            {"id": job_id},
        )

    async def set_job_success(self, job_id: UUID, *, stats_json: dict[str, Any]) -> None:
        await self._session.execute(
            text(
                """
                UPDATE kb_index_jobs
                SET status='success', finished_at=now(), stats_json=CAST(:stats AS jsonb)
                WHERE id=:id
                """
            ),
            {"id": job_id, "stats": json.dumps(stats_json, ensure_ascii=False)},
        )

    async def set_job_failed(self, job_id: UUID, *, error_text: str) -> None:
        await self._session.execute(
            text(
                """
                UPDATE kb_index_jobs
                SET status='failed', finished_at=now(), error_text=:err
                WHERE id=:id
                """
            ),
            {"id": job_id, "err": error_text},
        )

    async def get_running_job_id(self, park_id: UUID) -> UUID | None:
        res = await self._session.execute(
            text(
                """
                SELECT id
                FROM kb_index_jobs
                WHERE park_id = :park_id AND status = 'running'
                ORDER BY started_at DESC NULLS LAST, created_at DESC
                LIMIT 1
                """
            ),
            {"park_id": park_id},
        )
        row = res.mappings().first()
        return row["id"] if row else None

    async def list_jobs(self, park_id: UUID, *, limit: int = 50) -> list[dict[str, Any]]:
        res = await self._session.execute(
            text(
                """
                SELECT id, status, triggered_by, reason, created_at, started_at, finished_at, stats_json, error_text
                FROM kb_index_jobs
                WHERE park_id = :park_id
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"park_id": park_id, "limit": limit},
        )
        return [dict(r) for r in res.mappings().all()]
