from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.repos.facts_versions_repo import FactsVersionsRepo

@dataclass(frozen=True)
class Park:
    id: UUID
    slug: str
    name: str
    base_url: str


@dataclass(frozen=True)
class FactsBundle:
    contacts: list[dict[str, Any]]
    location: dict[str, Any] | None
    opening_hours: list[dict[str, Any]]
    transport: list[dict[str, Any]]
    site_pages: dict[str, dict[str, Any]]
    legal_documents: list[dict[str, Any]]
    promotions: list[dict[str, Any]]
    faq: list[dict[str, Any]]
    opening_hours_text: str | None
    primary_phone: str | None


class FactsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_park_by_slug(self, slug: str) -> Park | None:
        res = await self._session.execute(
            text(
                """
                SELECT id, slug, name, base_url
                FROM parks
                WHERE slug = :slug
                LIMIT 1
                """
            ),
            {"slug": slug},
        )
        row = res.mappings().first()
        if not row:
            return None
        return Park(id=row["id"], slug=row["slug"], name=row["name"], base_url=row["base_url"])

    async def get_facts(self, park_id: UUID) -> FactsBundle:
        published_version_id = await FactsVersionsRepo(self._session).get_published_version_id(park_id)
        if published_version_id:
            snap = await FactsVersionsRepo(self._session).get_snapshot_json(published_version_id)
            if snap:
                return self._bundle_from_snapshot(snap)

        return await self.get_live_facts(park_id)

    async def get_live_facts(self, park_id: UUID) -> FactsBundle:
        contacts = await self._fetch_all(
            """
            SELECT type, value, is_primary
            FROM park_contacts
            WHERE park_id = :park_id
            ORDER BY is_primary DESC
            """,
            {"park_id": park_id},
        )

        location = await self._fetch_one(
            """
            SELECT address_text, city, lat, lon
            FROM park_locations
            WHERE park_id = :park_id
            LIMIT 1
            """,
            {"park_id": park_id},
        )

        opening_hours = await self._fetch_all(
            """
            SELECT dow, open_time, close_time, is_closed, note
            FROM park_opening_hours
            WHERE park_id = :park_id
            ORDER BY dow
            """,
            {"park_id": park_id},
        )

        transport = await self._fetch_all(
            """
            SELECT kind, text
            FROM park_transport
            WHERE park_id = :park_id
            ORDER BY kind, id
            """,
            {"park_id": park_id},
        )

        pages = await self._fetch_all(
            """
            SELECT key, path, absolute_url, updated_at
            FROM site_pages
            WHERE park_id = :park_id
            """,
            {"park_id": park_id},
        )
        site_pages: dict[str, dict[str, Any]] = {p["key"]: p for p in pages}

        legal_documents = await self._fetch_all(
            """
            SELECT key, title, path, absolute_url, updated_at
            FROM legal_documents
            WHERE park_id = :park_id
            ORDER BY updated_at DESC
            """,
            {"park_id": park_id},
        )

        promotions = await self._fetch_all(
            """
            SELECT key, title, text, valid_from, valid_to, expires_at, created_at
            FROM promotions
            WHERE park_id = :park_id
            ORDER BY created_at DESC
            """,
            {"park_id": park_id},
        )

        faq = await self._fetch_all(
            """
            SELECT question, answer, is_active, created_at
            FROM faq
            WHERE park_id = :park_id
            ORDER BY created_at DESC
            """,
            {"park_id": park_id},
        )

        opening_hours_text = self._opening_hours_to_text(opening_hours)
        primary_phone = self._extract_primary_phone(contacts)

        return FactsBundle(
            contacts=contacts,
            location=location,
            opening_hours=opening_hours,
            transport=transport,
            site_pages=site_pages,
            legal_documents=legal_documents,
            promotions=promotions,
            faq=faq,
            opening_hours_text=opening_hours_text,
            primary_phone=primary_phone,
        )

    async def get_published_version_id(self, park_id: UUID) -> UUID | None:
        return await FactsVersionsRepo(self._session).get_published_version_id(park_id)

    async def get_page_url(self, park_id: UUID, key: str) -> str | None:
        park = await self._session.execute(
            text("SELECT base_url FROM parks WHERE id = :park_id LIMIT 1"),
            {"park_id": park_id},
        )
        park_row = park.mappings().first()
        if not park_row:
            return None
        base_url: str = park_row["base_url"].rstrip("/")

        res = await self._session.execute(
            text(
                """
                SELECT path, absolute_url
                FROM site_pages
                WHERE park_id = :park_id AND key = :key
                LIMIT 1
                """
            ),
            {"park_id": park_id, "key": key},
        )
        row = res.mappings().first()
        if not row:
            return None
        if row["absolute_url"]:
            return str(row["absolute_url"])
        path = (row["path"] or "").strip()
        if not path:
            return None
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return base_url + path

    async def get_primary_phone(self, park_id: UUID) -> str | None:
        res = await self._session.execute(
            text(
                """
                SELECT value
                FROM park_contacts
                WHERE park_id = :park_id AND type = 'phone'
                ORDER BY is_primary DESC, id ASC
                LIMIT 1
                """
            ),
            {"park_id": park_id},
        )
        row = res.mappings().first()
        return str(row["value"]) if row else None

    async def get_opening_hours_text(self, park_id: UUID) -> str | None:
        hours = await self._fetch_all(
            """
            SELECT dow, open_time, close_time, is_closed, note
            FROM park_opening_hours
            WHERE park_id = :park_id
            ORDER BY dow
            """,
            {"park_id": park_id},
        )
        return self._opening_hours_to_text(hours)

    async def _fetch_all(self, sql: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        res = await self._session.execute(text(sql), params)
        return [dict(r) for r in res.mappings().all()]

    async def _fetch_one(self, sql: str, params: dict[str, Any]) -> dict[str, Any] | None:
        res = await self._session.execute(text(sql), params)
        row = res.mappings().first()
        return dict(row) if row else None

    def _extract_primary_phone(self, contacts: list[dict[str, Any]]) -> str | None:
        phones = [c for c in contacts if c.get("type") == "phone" and c.get("value")]
        if not phones:
            return None
        return str(phones[0]["value"])

    def _bundle_from_snapshot(self, snapshot: dict[str, Any]) -> FactsBundle:
        return FactsBundle(
            contacts=list(snapshot.get("contacts") or []),
            location=snapshot.get("location"),
            opening_hours=list(snapshot.get("opening_hours") or []),
            transport=list(snapshot.get("transport") or []),
            site_pages=dict(snapshot.get("site_pages") or {}),
            legal_documents=list(snapshot.get("legal_documents") or []),
            promotions=list(snapshot.get("promotions") or []),
            faq=list(snapshot.get("faq") or []),
            opening_hours_text=snapshot.get("opening_hours_text"),
            primary_phone=snapshot.get("primary_phone"),
        )

    def _opening_hours_to_text(self, hours: list[dict[str, Any]]) -> str | None:
        if not hours:
            return None

        def day_name(d: int) -> str:
            return {
                0: "Пн",
                1: "Вт",
                2: "Ср",
                3: "Чт",
                4: "Пт",
                5: "Сб",
                6: "Вс",
            }.get(d, str(d))

        normalized: list[tuple[int, str]] = []
        for h in hours:
            d = int(h["dow"])
            if h.get("is_closed"):
                normalized.append((d, "выходной"))
                continue
            opens = h.get("open_time")
            closes = h.get("close_time")
            if opens and closes:
                normalized.append((d, f"{opens.strftime('%H:%M')}–{closes.strftime('%H:%M')}"))
            elif h.get("note"):
                normalized.append((d, str(h["note"])))
            else:
                normalized.append((d, "по расписанию"))

        groups: list[tuple[int, int, str]] = []
        start_d, prev_d, prev_val = normalized[0][0], normalized[0][0], normalized[0][1]
        for d, val in normalized[1:]:
            if val == prev_val and d == prev_d + 1:
                prev_d = d
                continue
            groups.append((start_d, prev_d, prev_val))
            start_d, prev_d, prev_val = d, d, val
        groups.append((start_d, prev_d, prev_val))

        parts: list[str] = []
        for a, b, val in groups:
            if a == b:
                parts.append(f"{day_name(a)} {val}")
            else:
                parts.append(f"{day_name(a)}–{day_name(b)} {val}")
        return ", ".join(parts)

    @staticmethod
    def validate_contacts(contacts: list[dict[str, Any]]) -> None:
        phones = [c for c in contacts if c.get("type") == "phone"]
        primary_phones = [c for c in phones if c.get("is_primary")]
        if phones and len(primary_phones) != 1:
            raise ValueError("Exactly 1 primary phone is required when phone contacts exist")

    @staticmethod
    def validate_opening_hours(hours: list[dict[str, Any]]) -> None:
        seen = set()
        for h in hours:
            dow = int(h["dow"])
            if dow < 0 or dow > 6:
                raise ValueError("dow must be 0..6")
            if dow in seen:
                raise ValueError("duplicate dow")
            seen.add(dow)
            is_closed = bool(h.get("is_closed"))
            ot = h.get("open_time")
            ct = h.get("close_time")
            if not is_closed:
                if not ot or not ct:
                    raise ValueError("open_time and close_time are required when is_closed=false")
                if str(ot) >= str(ct):
                    raise ValueError("open_time must be < close_time")

    async def replace_contacts(self, park_id: UUID, contacts: list[dict[str, Any]]) -> None:
        await self._session.execute(text("DELETE FROM park_contacts WHERE park_id=:park_id"), {"park_id": park_id})
        for c in contacts:
            await self._session.execute(
                text(
                    """
                    INSERT INTO park_contacts (park_id, type, value, is_primary)
                    VALUES (:park_id, :type, :value, :is_primary)
                    """
                ),
                {"park_id": park_id, "type": c["type"], "value": c["value"], "is_primary": bool(c.get("is_primary"))},
            )

    async def replace_location(self, park_id: UUID, location: dict[str, Any]) -> None:
        await self._session.execute(text("DELETE FROM park_locations WHERE park_id=:park_id"), {"park_id": park_id})
        await self._session.execute(
            text(
                """
                INSERT INTO park_locations (park_id, address_text, city, lat, lon)
                VALUES (:park_id, :address_text, :city, :lat, :lon)
                """
            ),
            {"park_id": park_id, **location},
        )

    async def replace_opening_hours(self, park_id: UUID, hours: list[dict[str, Any]]) -> None:
        await self._session.execute(text("DELETE FROM park_opening_hours WHERE park_id=:park_id"), {"park_id": park_id})
        for h in hours:
            await self._session.execute(
                text(
                    """
                    INSERT INTO park_opening_hours (park_id, dow, open_time, close_time, is_closed, note)
                    VALUES (:park_id, :dow, :open_time, :close_time, :is_closed, :note)
                    """
                ),
                {
                    "park_id": park_id,
                    "dow": int(h["dow"]),
                    "open_time": h.get("open_time"),
                    "close_time": h.get("close_time"),
                    "is_closed": bool(h.get("is_closed")),
                    "note": h.get("note"),
                },
            )

    async def replace_transport(self, park_id: UUID, items: list[dict[str, Any]]) -> None:
        await self._session.execute(text("DELETE FROM park_transport WHERE park_id=:park_id"), {"park_id": park_id})
        for t in items:
            await self._session.execute(
                text("INSERT INTO park_transport (park_id, kind, text) VALUES (:park_id,:kind,:text)"),
                {"park_id": park_id, "kind": t["kind"], "text": t["text"]},
            )

    async def replace_site_pages(self, park_id: UUID, items: list[dict[str, Any]]) -> None:
        await self._session.execute(text("DELETE FROM site_pages WHERE park_id=:park_id"), {"park_id": park_id})
        for p in items:
            await self._session.execute(
                text(
                    """
                    INSERT INTO site_pages (park_id, key, path, absolute_url)
                    VALUES (:park_id, :key, :path, :absolute_url)
                    """
                ),
                {"park_id": park_id, "key": p["key"], "path": p.get("path"), "absolute_url": p.get("absolute_url")},
            )

    async def replace_legal_documents(self, park_id: UUID, items: list[dict[str, Any]]) -> None:
        await self._session.execute(text("DELETE FROM legal_documents WHERE park_id=:park_id"), {"park_id": park_id})
        for d in items:
            await self._session.execute(
                text(
                    """
                    INSERT INTO legal_documents (park_id, key, title, path, absolute_url)
                    VALUES (:park_id, :key, :title, :path, :absolute_url)
                    """
                ),
                {
                    "park_id": park_id,
                    "key": d["key"],
                    "title": d["title"],
                    "path": d.get("path"),
                    "absolute_url": d.get("absolute_url"),
                },
            )

    async def replace_promotions(self, park_id: UUID, items: list[dict[str, Any]]) -> None:
        await self._session.execute(text("DELETE FROM promotions WHERE park_id=:park_id"), {"park_id": park_id})
        for p in items:
            await self._session.execute(
                text(
                    """
                    INSERT INTO promotions (park_id, key, title, text, valid_from, valid_to, expires_at)
                    VALUES (:park_id, :key, :title, :text, :valid_from, :valid_to, :expires_at)
                    """
                ),
                {
                    "park_id": park_id,
                    "key": p["key"],
                    "title": p["title"],
                    "text": p["text"],
                    "valid_from": p.get("valid_from"),
                    "valid_to": p.get("valid_to"),
                    "expires_at": p.get("expires_at"),
                },
            )

    async def replace_faq(self, park_id: UUID, items: list[dict[str, Any]]) -> None:
        await self._session.execute(text("DELETE FROM faq WHERE park_id=:park_id"), {"park_id": park_id})
        for f in items:
            await self._session.execute(
                text(
                    """
                    INSERT INTO faq (park_id, question, answer, is_active)
                    VALUES (:park_id, :question, :answer, :is_active)
                    """
                ),
                {
                    "park_id": park_id,
                    "question": f["question"],
                    "answer": f["answer"],
                    "is_active": bool(f.get("is_active", True)),
                },
            )

    async def write_change_log(
        self,
        *,
        park_id: UUID | None,
        actor: str,
        entity_table: str,
        action: str,
        before_json: Any,
        after_json: Any,
        reason: str | None,
    ) -> None:
        import json
        from datetime import date, datetime, time

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

        await self._session.execute(
            text(
                """
                INSERT INTO change_log (park_id, actor, entity_table, action, before_json, after_json, reason)
                VALUES (:park_id, :actor, :entity_table, :action, CAST(:before AS jsonb), CAST(:after AS jsonb), :reason)
                """
            ),
            {
                "park_id": park_id,
                "actor": actor,
                "entity_table": entity_table,
                "action": action,
                "before": json.dumps(_jsonable(before_json), ensure_ascii=False) if before_json is not None else None,
                "after": json.dumps(_jsonable(after_json), ensure_ascii=False) if after_json is not None else None,
                "reason": reason,
            },
        )
