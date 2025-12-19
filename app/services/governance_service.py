from __future__ import annotations

import json
from datetime import date, datetime, time, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repos.facts_repo import FactsRepo


class GovernanceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._facts = FactsRepo(session)

    async def build_facts_snapshot(self, park_id: UUID) -> dict[str, Any]:
        facts = await self._facts.get_live_facts(park_id)
        snapshot = {
            "contacts": facts.contacts,
            "location": facts.location,
            "opening_hours": facts.opening_hours,
            "transport": facts.transport,
            "site_pages": facts.site_pages,
            "legal_documents": facts.legal_documents,
            "promotions": facts.promotions,
            "faq": facts.faq,
            "opening_hours_text": facts.opening_hours_text,
            "primary_phone": facts.primary_phone,
        }
        return _jsonable(snapshot)

    async def publish_facts(self, *, park_id: UUID, published_by: str, notes: str | None) -> UUID:
        async with self._session.begin():
            snapshot = await self.build_facts_snapshot(park_id)
            now = datetime.now(timezone.utc)
            res = await self._session.execute(
                text(
                    """
                    INSERT INTO facts_versions (park_id, status, published_at, published_by, notes)
                    VALUES (:park_id, 'published', :published_at, :published_by, :notes)
                    RETURNING id
                    """
                ),
                {
                    "park_id": park_id,
                    "published_at": now,
                    "published_by": published_by,
                    "notes": notes,
                },
            )
            version_id: UUID = res.scalar_one()

            await self._session.execute(
                text("INSERT INTO facts_snapshots (facts_version_id, snapshot_json) VALUES (:id, CAST(:snap AS jsonb))"),
                {"id": version_id, "snap": json.dumps(snapshot, ensure_ascii=False)},
            )

            await self._session.execute(
                text(
                    """
                    INSERT INTO park_published_state (park_id, published_version_id, updated_at)
                    VALUES (:park_id, :vid, now())
                    ON CONFLICT (park_id) DO UPDATE
                    SET published_version_id = EXCLUDED.published_version_id,
                        updated_at = now()
                    """
                ),
                {"park_id": park_id, "vid": version_id},
            )

            return version_id

    async def rollback_facts(self, *, park_id: UUID, rolled_back_by: str) -> UUID:
        async with self._session.begin():
            current = await self._facts.get_published_version_id(park_id)
            if not current:
                raise ValueError("No published version to rollback")

            res = await self._session.execute(
                text(
                    """
                    SELECT id
                    FROM facts_versions
                    WHERE park_id = :park_id
                      AND status = 'published'
                      AND published_at < (SELECT published_at FROM facts_versions WHERE id = :current)
                    ORDER BY published_at DESC
                    LIMIT 1
                    """
                ),
                {"park_id": park_id, "current": current},
            )
            row = res.mappings().first()
            if not row:
                raise ValueError("No previous published version to rollback to")
            prev: UUID = row["id"]

            await self._session.execute(
                text("UPDATE park_published_state SET published_version_id=:vid, updated_at=now() WHERE park_id=:park_id"),
                {"park_id": park_id, "vid": prev},
            )
            _ = rolled_back_by
            return prev

    # MVP-3 naming (thin wrappers)
    async def publish_snapshot(self, park_id: UUID, actor: str, notes: str | None) -> UUID:
        return await self.publish_facts(park_id=park_id, published_by=actor, notes=notes)

    async def rollback_snapshot(self, park_id: UUID, actor: str, reason: str | None) -> UUID:
        _ = actor
        _ = reason
        return await self.rollback_facts(park_id=park_id, rolled_back_by=actor)


def _jsonable(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (datetime, date, time)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return str(obj)
