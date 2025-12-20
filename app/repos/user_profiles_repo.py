from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class UserProfile:
    park_id: UUID
    channel: str
    user_key: str
    name: str | None
    summary: str | None


class UserProfilesRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, *, park_id: UUID, channel: str, user_key: str) -> UserProfile | None:
        res = await self._session.execute(
            text(
                """
                SELECT park_id, channel, user_key, name, summary
                FROM user_profiles
                WHERE park_id=:park_id AND channel=:channel AND user_key=:user_key
                LIMIT 1
                """
            ),
            {"park_id": park_id, "channel": channel, "user_key": user_key},
        )
        row = res.mappings().first()
        if not row:
            return None
        return UserProfile(
            park_id=row["park_id"],
            channel=row["channel"],
            user_key=row["user_key"],
            name=row.get("name"),
            summary=row.get("summary"),
        )

    async def upsert(
        self,
        *,
        park_id: UUID,
        channel: str,
        user_key: str,
        name: str | None = None,
        summary: str | None = None,
    ) -> None:
        await self._session.execute(
            text(
                """
                INSERT INTO user_profiles (park_id, channel, user_key, name, summary, updated_at)
                VALUES (:park_id, :channel, :user_key, :name, :summary, now())
                ON CONFLICT (park_id, channel, user_key) DO UPDATE SET
                  name = COALESCE(EXCLUDED.name, user_profiles.name),
                  summary = COALESCE(EXCLUDED.summary, user_profiles.summary),
                  updated_at = now()
                """
            ),
            {
                "park_id": park_id,
                "channel": channel,
                "user_key": user_key,
                "name": name,
                "summary": summary,
            },
        )

    async def set_summary(self, *, park_id: UUID, channel: str, user_key: str, summary: str | None) -> None:
        await self._session.execute(
            text(
                """
                INSERT INTO user_profiles (park_id, channel, user_key, summary, updated_at)
                VALUES (:park_id, :channel, :user_key, :summary, now())
                ON CONFLICT (park_id, channel, user_key) DO UPDATE SET
                  summary = EXCLUDED.summary,
                  updated_at = now()
                """
            ),
            {"park_id": park_id, "channel": channel, "user_key": user_key, "summary": summary},
        )

    # Backwards-compatible aliases used by ChatService.
    async def get_profile(self, park_id: UUID, channel: str, user_key: str) -> UserProfile | None:
        return await self.get(park_id=park_id, channel=channel, user_key=user_key)

    async def upsert_profile(
        self,
        *,
        park_id: UUID,
        channel: str,
        user_key: str,
        name: str | None = None,
        summary: str | None = None,
    ) -> None:
        await self.upsert(park_id=park_id, channel=channel, user_key=user_key, name=name, summary=summary)
