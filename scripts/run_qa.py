from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
import asyncio
from uuid import UUID, uuid4

import httpx


API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
RAG_ENABLED = os.getenv("RAG_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Case:
    id: str
    message: str
    expect_link: bool
    expect_any: tuple[str, ...] = ()


CASES: list[Case] = [
    # C01–C15 (контакты/транспорт/часы) — представительные формулировки
    Case("C01", "Где вы находитесь? Какой адрес?", True, ("Адрес:",)),
    Case("C02", "Подскажите телефон для связи", True, ("Телефон:",)),
    Case("C03", "Как до вас добраться на метро?", True, ("Как добраться:", "Метро")),
    Case("C04", "Как доехать на машине, есть парковка?", True, ("Как добраться:", "На машине")),
    Case("C05", "Во сколько вы открываетесь в понедельник?", True, ("Часы работы:",)),
    Case("C06", "Режим работы в выходные?", True, ("Часы работы:",)),
    Case("C07", "Часы работы сегодня?", True, ("Часы работы:",)),
    Case("C08", "Как доехать общественным транспортом?", True, ("Как добраться:",)),
    Case("C09", "Контакты пожалуйста", True, ("Адрес:", "Телефон:", "Часы работы:")),
    Case("C10", "Где вход и адрес", True, ("Адрес:",)),
    Case("C11", "Номер телефона +7 999 123-45-67", True, ("Телефон:",)),
    Case("C12", "Как добраться пешком от метро?", True, ("Как добраться:",)),
    Case("C13", "График работы", True, ("Часы работы:",)),
    Case("C14", "Адрес и время работы", True, ("Адрес:", "Часы работы:")),
    Case("C15", "Как доехать?", True, ("Как добраться:", "Адрес:")),
    # X01–X05 (правила/оффер/оператор) — в MVP-0 без handoff, но со ссылкой
    Case("X01", "Какие у вас правила посещения?", True, ("правила", "Правила")),
    Case("X02", "Можно ли с собакой?", True, ("правила", "Правила")),
    Case("X03", "Нельзя ли приносить еду?", True, ("правила", "Правила")),
    Case("X04", "Есть ли скидки?", True, ("Подроб", "странице")),
    Case("X05", "Сколько стоит билет?", True, ("Подроб", "странице")),
]


def main() -> int:
    if RAG_ENABLED:
        try:
            asyncio.run(_ensure_kb_indexed())
        except Exception as e:
            print(json.dumps({"ok": False, "error": f"kb_index_failed: {e}"}, ensure_ascii=False, indent=2))
            return 2

    client = httpx.Client(timeout=10.0)
    ok = 0
    results = []

    # Stateless cases
    for c in CASES:
        r = client.post(
            f"{API_URL}/v1/chat/message",
            json={
                "park_slug": "nn",
                "channel": "qa",
                "message": c.message,
            },
        )
        if r.status_code != 200:
            results.append({"id": c.id, "ok": False, "status": r.status_code, "body": r.text})
            continue
        data = r.json()
        reply = data.get("reply", "")
        has_link = "http://" in reply or "https://" in reply
        contains_ok = True
        if c.expect_any:
            contains_ok = any(s in reply for s in c.expect_any)

        link_ok = (has_link is True) if c.expect_link else (has_link is False)
        case_ok = link_ok and contains_ok
        ok += 1 if case_ok else 0
        results.append(
            {
                "id": c.id,
                "ok": case_ok,
                "trace_id": data.get("trace_id"),
                "session_id": data.get("session_id"),
                "has_link": has_link,
                "contains_ok": contains_ok,
                "reply_preview": reply[:120],
            }
        )

    # B01–B10 (праздники): проверка, что телефон не просят первым сообщением
    b_session = uuid4()
    b_cases_ok = _run_lead_flow(client, session_id=b_session, results=results)
    rag_ok = True
    rag_passed = 0
    rag_total = 0
    if RAG_ENABLED:
        rag_ok, rag_passed, rag_total = _run_rag_cases(client, results=results)

    total = len(CASES) + 3 + rag_total
    ok_total = ok + (3 if b_cases_ok else 0) + rag_passed

    print(json.dumps({"passed": ok_total, "total": total, "results": results}, ensure_ascii=False, indent=2))
    return 0 if ok_total == total else 2


def _run_lead_flow(client: httpx.Client, *, session_id: UUID, results: list[dict]) -> bool:
    # B01: старт — должны спросить дату/детей и НЕ просить телефон
    r1 = client.post(
        f"{API_URL}/v1/chat/message",
        json={
            "park_slug": "nn",
            "channel": "qa",
            "session_id": str(session_id),
            "message": "Хочу день рождения ребенку",
        },
    )
    if r1.status_code != 200:
        results.append({"id": "B01", "ok": False, "status": r1.status_code, "body": r1.text})
        return False
    reply1 = r1.json().get("reply", "")
    b01_ok = ("дат" in reply1.lower() or "день недели" in reply1.lower()) and ("телефон" not in reply1.lower())
    results.append({"id": "B01", "ok": b01_ok, "reply_preview": reply1[:120]})

    # B02: дали дату/детей — теперь можно попросить телефон
    r2 = client.post(
        f"{API_URL}/v1/chat/message",
        json={
            "park_slug": "nn",
            "channel": "qa",
            "session_id": str(session_id),
            "message": "15.01, будет 8 детей по 6 лет",
        },
    )
    if r2.status_code != 200:
        results.append({"id": "B02", "ok": False, "status": r2.status_code, "body": r2.text})
        return False
    reply2 = r2.json().get("reply", "")
    b02_ok = "телефон" in reply2.lower()
    results.append({"id": "B02", "ok": b02_ok, "reply_preview": reply2[:120]})

    # B03: дали телефон — ожидаем подтверждение, без новых вопросов
    r3 = client.post(
        f"{API_URL}/v1/chat/message",
        json={
            "park_slug": "nn",
            "channel": "qa",
            "session_id": str(session_id),
            "message": "+7 999 123-45-67",
        },
    )
    if r3.status_code != 200:
        results.append({"id": "B03", "ok": False, "status": r3.status_code, "body": r3.text})
        return False
    reply3 = r3.json().get("reply", "")
    b03_ok = ("перед" in reply3.lower() or "свяж" in reply3.lower()) and ("телефон" not in reply3.lower())
    results.append({"id": "B03", "ok": b03_ok, "reply_preview": reply3[:120]})

    return b01_ok and b02_ok and b03_ok


def _run_rag_cases(client: httpx.Client, *, results: list[dict]) -> tuple[bool, int, int]:
    rag_cases = [
        ("R01", "Какие у вас правила посещения?", ("безопасност",), "https://nn.jucity.ru/rules/"),
        ("R02", "Какие аттракционы есть?", ("батут", "лабиринт", "горк", "vr"), "https://nn.jucity.ru/attractions/"),
        ("R03", "Есть ресторан или кафе?", ("кафе", "меню"), "https://nn.jucity.ru/rest/"),
        # Guardrails: currency in KB should be masked for non-price intents when included
        ("R04", "Сколько стоит в ресторане комбо?", ("—",), "https://nn.jucity.ru/rest/"),
        # Prices intent must not include numbers (RAG disabled for prices)
        ("P01", "Сколько стоит билет?", ("Подроб", "странице"), "https://nn.jucity.ru/prices/tickets/"),
    ]

    passed = 0
    for cid, msg, expect_any, expect_link in rag_cases:
        r = client.post(
            f"{API_URL}/v1/chat/message",
            json={"park_slug": "nn", "channel": "qa", "message": msg},
        )
        if r.status_code != 200:
            results.append({"id": cid, "ok": False, "status": r.status_code, "body": r.text})
            continue
        reply = r.json().get("reply", "")
        has_link = expect_link in reply
        contains_ok = any(s.lower() in reply.lower() for s in expect_any)
        ok_case = has_link and contains_ok
        passed += 1 if ok_case else 0
        results.append({"id": cid, "ok": ok_case, "has_link": has_link, "reply_preview": reply[:140]})

    return passed == len(rag_cases), passed, len(rag_cases)


async def _ensure_kb_indexed() -> None:
    # Import inside to avoid importing SQLAlchemy/qdrant deps when RAG is off
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.config import settings
    from app.repos.facts_repo import FactsRepo
    from app.repos.kb_sources_repo import KBSourcesRepo
    from app.services.kb_indexer import KBIndexer

    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        park = await FactsRepo(session).get_park_by_slug("nn")
        if not park:
            raise RuntimeError("park_slug=nn not found")

        fixtures_dir = os.path.join(os.path.dirname(__file__), "..", "fixtures", "kb")
        sources = KBSourcesRepo(session)
        await sources.ensure_source(
            park_id=park.id,
            source_type="file_path",
            source_url=f"{park.base_url.rstrip('/')}/rules/",
            file_path=os.path.abspath(os.path.join(fixtures_dir, "rules.html")),
            title="Правила посещения",
        )
        await sources.ensure_source(
            park_id=park.id,
            source_type="file_path",
            source_url=f"{park.base_url.rstrip('/')}/attractions/",
            file_path=os.path.abspath(os.path.join(fixtures_dir, "attractions.html")),
            title="Аттракционы",
        )
        await sources.ensure_source(
            park_id=park.id,
            source_type="file_path",
            source_url=f"{park.base_url.rstrip('/')}/rest/",
            file_path=os.path.abspath(os.path.join(fixtures_dir, "restaurant.html")),
            title="Ресторан",
        )

        await KBIndexer(session).run_reindex(park_id=park.id, park_slug=park.slug, triggered_by="qa", reason="qa")
        await session.commit()
    await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
