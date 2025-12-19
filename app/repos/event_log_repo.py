from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class EventLogRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def write_event(
        self,
        *,
        trace_id: UUID,
        session_id: UUID,
        user_id: str | None,
        park_id: UUID | None,
        park_slug: str | None,
        channel: str | None,
        event_name: str,
        payload: dict[str, Any],
        facts_version_id: UUID | None,
    ) -> None:
        await self._session.execute(
            text(
                """
                INSERT INTO event_log (
                  trace_id, session_id, user_id, park_id, park_slug, channel,
                  event_name, facts_version_id, payload
                )
                VALUES (
                  :trace_id, :session_id, :user_id, :park_id, :park_slug, :channel,
                  :event_name, :facts_version_id, CAST(:payload AS jsonb)
                )
                """
            ),
            {
                "trace_id": trace_id,
                "session_id": session_id,
                "user_id": user_id,
                "park_id": park_id,
                "park_slug": park_slug,
                "channel": channel,
                "event_name": event_name,
                "facts_version_id": facts_version_id,
                "payload": json.dumps(payload, ensure_ascii=False),
            },
        )
