from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, time
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class Lead:
    id: UUID
    park_id: UUID
    session_id: UUID
    status: str
    intent: str | None
    client_phone: str | None
    client_name: str | None
    event_date: date | None
    event_time: time | None
    day_of_week: int | None
    kids_count: int | None
    kids_age_main: int | None
    adults_count: int | None
    need_room: bool | None
    need_banquet: bool | None
    add_ons: str | None
    conversation_summary: str | None
    conversation_json: list[dict[str, Any]]
    missing_required_slots: list[str]
    admin_message: str | None


class LeadsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_open_lead_by_session(self, park_id: UUID, session_id: UUID) -> Lead | None:
        res = await self._session.execute(
            text(
                """
                SELECT *
                FROM leads
                WHERE park_id = :park_id
                  AND session_id = :session_id
                  AND status <> 'closed'
                ORDER BY updated_at DESC
                LIMIT 1
                """
            ),
            {"park_id": park_id, "session_id": session_id},
        )
        row = res.mappings().first()
        return self._to_lead(row) if row else None

    async def create_lead(
        self,
        *,
        park_id: UUID,
        session_id: UUID,
        intent: str | None,
    ) -> Lead:
        res = await self._session.execute(
            text(
                """
                INSERT INTO leads (park_id, session_id, intent)
                VALUES (:park_id, :session_id, :intent)
                RETURNING *
                """
            ),
            {"park_id": park_id, "session_id": session_id, "intent": intent},
        )
        row = res.mappings().one()
        return self._to_lead(row)

    async def update_lead(self, lead_id: UUID, patch: dict[str, Any]) -> Lead:
        if not patch:
            res = await self._session.execute(text("SELECT * FROM leads WHERE id=:id"), {"id": lead_id})
            row = res.mappings().one()
            return self._to_lead(row)

        set_parts = []
        params: dict[str, Any] = {"id": lead_id}
        for i, (k, v) in enumerate(patch.items()):
            pname = f"p{i}"
            set_parts.append(f"{k} = :{pname}")
            if k in {"conversation_json", "missing_required_slots"}:
                params[pname] = json.dumps(v, ensure_ascii=False)
            else:
                params[pname] = v

        sql = f"""
        UPDATE leads
        SET updated_at = now(), {", ".join(set_parts)}
        WHERE id = :id
        RETURNING *
        """
        res = await self._session.execute(text(sql), params)
        row = res.mappings().one()
        return self._to_lead(row)

    async def upsert_lead_by_session(
        self,
        *,
        park_id: UUID,
        session_id: UUID,
        intent: str | None,
        slots_patch: dict[str, Any],
        missing_required_slots: list[str],
        conversation_append: dict[str, Any] | None,
        admin_message: str | None,
    ) -> Lead:
        lead = await self.get_open_lead_by_session(park_id=park_id, session_id=session_id)
        if lead is None:
            lead = await self.create_lead(park_id=park_id, session_id=session_id, intent=intent)

        merged = {
            "intent": intent or lead.intent,
            "missing_required_slots": missing_required_slots,
        }
        merged.update(slots_patch)

        conv = lead.conversation_json
        if conversation_append:
            conv = (conv + [conversation_append])[-50:]
            merged["conversation_json"] = conv

        if admin_message:
            merged["admin_message"] = admin_message

        merged["conversation_summary"] = build_lead_summary({**lead_to_dict(lead), **slots_patch})
        return await self.update_lead(lead.id, merged)

    def _to_lead(self, row: Any) -> Lead:
        conv = row.get("conversation_json") or []
        if isinstance(conv, str):
            conv = json.loads(conv)
        miss = row.get("missing_required_slots") or []
        if isinstance(miss, str):
            miss = json.loads(miss)
        return Lead(
            id=row["id"],
            park_id=row["park_id"],
            session_id=row["session_id"],
            status=row["status"],
            intent=row.get("intent"),
            client_phone=row.get("client_phone"),
            client_name=row.get("client_name"),
            event_date=row.get("event_date"),
            event_time=row.get("event_time"),
            day_of_week=row.get("day_of_week"),
            kids_count=row.get("kids_count"),
            kids_age_main=row.get("kids_age_main"),
            adults_count=row.get("adults_count"),
            need_room=row.get("need_room"),
            need_banquet=row.get("need_banquet"),
            add_ons=row.get("add_ons"),
            conversation_summary=row.get("conversation_summary"),
            conversation_json=list(conv),
            missing_required_slots=list(miss),
            admin_message=row.get("admin_message"),
        )


def lead_to_dict(lead: Lead) -> dict[str, Any]:
    return {
        "intent": lead.intent,
        "client_phone": lead.client_phone,
        "event_date": lead.event_date,
        "event_time": lead.event_time,
        "day_of_week": lead.day_of_week,
        "kids_count": lead.kids_count,
        "kids_age_main": lead.kids_age_main,
    }


def build_lead_summary(data: dict[str, Any]) -> str:
    intent = data.get("intent")
    parts = []
    if intent:
        label = {
            "party_main": "ДР",
            "graduation": "Выпускной",
            "new_year_trees": "Ёлки",
            "handoff": "Запрос менеджера",
        }.get(intent, intent)
        parts.append(label)

    d: date | None = data.get("event_date")
    if d:
        parts.append(f"дата {d.isoformat()}")
    dow = data.get("day_of_week")
    if dow is not None and d is None:
        parts.append(f"день недели {dow}")

    kids = data.get("kids_count")
    if kids:
        parts.append(f"дети {kids}")
    age = data.get("kids_age_main")
    if age:
        parts.append(f"возраст {age}")

    phone = data.get("client_phone")
    if phone:
        parts.append("телефон есть")

    return ". ".join(parts) if parts else ""

