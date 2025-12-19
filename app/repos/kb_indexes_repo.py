from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class KBIndexesRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_index(self, *, park_id: UUID, label: str) -> UUID:
        res = await self._session.execute(
            text("INSERT INTO kb_indexes (park_id, label) VALUES (:park_id, :label) RETURNING id"),
            {"park_id": park_id, "label": label},
        )
        return res.scalar_one()

    async def activate_index(self, *, park_id: UUID, index_id: UUID) -> None:
        await self._session.execute(
            text("UPDATE kb_indexes SET status='active', activated_at=now() WHERE id=:id"),
            {"id": index_id},
        )
        await self._session.execute(
            text("UPDATE parks SET active_kb_index_id=:idx WHERE id=:park_id"),
            {"park_id": park_id, "idx": index_id},
        )

    async def get_active_index_id(self, *, park_id: UUID) -> UUID | None:
        res = await self._session.execute(
            text("SELECT active_kb_index_id FROM parks WHERE id=:park_id LIMIT 1"),
            {"park_id": park_id},
        )
        row = res.mappings().first()
        return row["active_kb_index_id"] if row else None

