from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class KBSource:
    id: UUID
    park_id: UUID
    enabled: bool
    source_type: str
    source_url: str | None
    file_path: str | None
    title: str | None
    content_type: str | None
    last_hash: str | None
    expires_at: datetime | None


class KBSourcesRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_enabled_sources(self, park_id: UUID) -> list[KBSource]:
        res = await self._session.execute(
            text(
                """
                SELECT id, park_id, enabled, source_type, source_url, file_path, title, content_type, last_hash, expires_at
                FROM kb_sources
                WHERE park_id = :park_id AND enabled = true
                ORDER BY created_at ASC
                """
            ),
            {"park_id": park_id},
        )
        return [self._to_source(r) for r in res.mappings().all()]

    async def list_all_sources(self, park_id: UUID) -> list[KBSource]:
        res = await self._session.execute(
            text(
                """
                SELECT id, park_id, enabled, source_type, source_url, file_path, title, content_type, last_hash, expires_at
                FROM kb_sources
                WHERE park_id = :park_id
                ORDER BY created_at ASC
                """
            ),
            {"park_id": park_id},
        )
        return [self._to_source(r) for r in res.mappings().all()]

    async def get_source(self, source_id: UUID) -> KBSource | None:
        res = await self._session.execute(
            text(
                """
                SELECT id, park_id, enabled, source_type, source_url, file_path, title, content_type, last_hash, expires_at
                FROM kb_sources
                WHERE id = :id
                LIMIT 1
                """
            ),
            {"id": source_id},
        )
        row = res.mappings().first()
        return self._to_source(row) if row else None

    async def update_last_fetched(self, source_id: UUID, *, last_hash: str, content_type: str | None) -> None:
        await self._session.execute(
            text(
                """
                UPDATE kb_sources
                SET last_hash = :last_hash,
                    content_type = COALESCE(:content_type, content_type),
                    last_fetched_at = now()
                WHERE id = :id
                """
            ),
            {"id": source_id, "last_hash": last_hash, "content_type": content_type},
        )

    async def patch_source(
        self,
        source_id: UUID,
        *,
        enabled: bool | None = None,
        expires_at: datetime | None = None,
        title: str | None = None,
        source_url: str | None = None,
        file_path: str | None = None,
    ) -> None:
        parts = []
        params: dict[str, Any] = {"id": source_id}
        if enabled is not None:
            parts.append("enabled = :enabled")
            params["enabled"] = enabled
        if expires_at is not None:
            parts.append("expires_at = :expires_at")
            params["expires_at"] = expires_at
        if title is not None:
            parts.append("title = :title")
            params["title"] = title
        if source_url is not None:
            parts.append("source_url = :source_url")
            params["source_url"] = source_url
        if file_path is not None:
            parts.append("file_path = :file_path")
            params["file_path"] = file_path
        if not parts:
            return
        await self._session.execute(
            text(f"UPDATE kb_sources SET {', '.join(parts)} WHERE id = :id"),
            params,
        )

    async def ensure_source(
        self,
        *,
        park_id: UUID,
        source_type: str,
        source_url: str | None,
        file_path: str | None,
        title: str | None,
        enabled: bool = True,
        expires_at: datetime | None = None,
    ) -> UUID:
        res = await self._session.execute(
            text(
                """
                SELECT id
                FROM kb_sources
                WHERE park_id = :park_id
                  AND source_type = :source_type
                  AND COALESCE(source_url, '') = COALESCE(:source_url, '')
                  AND COALESCE(file_path, '') = COALESCE(:file_path, '')
                LIMIT 1
                """
            ),
            {"park_id": park_id, "source_type": source_type, "source_url": source_url, "file_path": file_path},
        )
        row = res.mappings().first()
        if row:
            await self._session.execute(
                text("UPDATE kb_sources SET enabled=:enabled, expires_at=:expires_at WHERE id=:id"),
                {"id": row["id"], "enabled": enabled, "expires_at": expires_at},
            )
            return row["id"]

        ins = await self._session.execute(
            text(
                """
                INSERT INTO kb_sources (park_id, enabled, source_type, source_url, file_path, title, expires_at)
                VALUES (:park_id, :enabled, :source_type, :source_url, :file_path, :title, :expires_at)
                RETURNING id
                """
            ),
            {
                "park_id": park_id,
                "enabled": enabled,
                "source_type": source_type,
                "source_url": source_url,
                "file_path": file_path,
                "title": title,
                "expires_at": expires_at,
            },
        )
        return ins.scalar_one()

    def _to_source(self, row: Any) -> KBSource:
        return KBSource(
            id=row["id"],
            park_id=row["park_id"],
            enabled=bool(row["enabled"]),
            source_type=row["source_type"],
            source_url=row.get("source_url"),
            file_path=row.get("file_path"),
            title=row.get("title"),
            content_type=row.get("content_type"),
            last_hash=row.get("last_hash"),
            expires_at=row.get("expires_at"),
        )
