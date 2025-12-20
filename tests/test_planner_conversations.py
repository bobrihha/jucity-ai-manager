from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text

from app.api.schemas import ChatMessageRequest
from app.config import settings
from app.services.chat_service import ChatService


@pytest.fixture
def planner_mode(monkeypatch):
    monkeypatch.setattr(settings, "llm_mode", "planner")
    monkeypatch.setattr(settings, "llm_planner_provider", "mock")
    monkeypatch.setattr(settings, "rag_enabled", False)
    return True


async def _seed_pages(db_session, park_id):
    await db_session.execute(
        text(
            """
            INSERT INTO site_pages (park_id, key, path, absolute_url)
            VALUES (:park_id, 'restaurant', '/rest/', NULL)
            ON CONFLICT (park_id, key) DO UPDATE SET path=EXCLUDED.path
            """
        ),
        {"park_id": park_id},
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_planner_restaurant_with_link(db_session, test_park, planner_mode) -> None:
    await _seed_pages(db_session, test_park["id"])
    svc = ChatService(db_session)
    resp = await svc.handle_message(
        ChatMessageRequest(
            park_slug=test_park["slug"],
            channel="telegram",
            session_id=uuid4(),
            user_id="123",
            message="можно поесть?",
        )
    )
    assert "ресторан" in resp.reply.lower() or "кафе" in resp.reply.lower()
    assert "http" in resp.reply.lower()
    assert "/rest/" in resp.reply


@pytest.mark.asyncio
async def test_planner_party_collects_slots(db_session, test_park, planner_mode) -> None:
    svc = ChatService(db_session)
    resp = await svc.handle_message(
        ChatMessageRequest(
            park_slug=test_park["slug"],
            channel="telegram",
            session_id=uuid4(),
            user_id="123",
            message="хочу др",
        )
    )
    txt = resp.reply.lower()
    assert ("дат" in txt) or ("когда" in txt)
    assert ("дет" in txt) or ("возраст" in txt)
    assert txt.count("?") <= 2


@pytest.mark.asyncio
async def test_planner_handles_banter(db_session, test_park, planner_mode) -> None:
    svc = ChatService(db_session)
    resp = await svc.handle_message(
        ChatMessageRequest(
            park_slug=test_park["slug"],
            channel="telegram",
            session_id=uuid4(),
            user_id="123",
            message="ты скучный",
        )
    )
    txt = resp.reply.lower()
    assert "😅" in resp.reply or "шут" in txt or "ой" in txt
    assert "телефон" not in txt


@pytest.mark.asyncio
async def test_planner_no_banned_phrase(db_session, test_park, planner_mode) -> None:
    svc = ChatService(db_session)
    resp = await svc.handle_message(
        ChatMessageRequest(
            park_slug=test_park["slug"],
            channel="telegram",
            session_id=uuid4(),
            user_id="123",
            message="???",
        )
    )
    assert "что вас интересует" not in resp.reply.lower()


# A few extra smoke conversations (10 total)
@pytest.mark.asyncio
async def test_planner_start(db_session, test_park, planner_mode) -> None:
    svc = ChatService(db_session)
    resp = await svc.handle_message(
        ChatMessageRequest(
            park_slug=test_park["slug"],
            channel="telegram",
            session_id=uuid4(),
            user_id="123",
            message="/start",
        )
    )
    assert "джуси" in resp.reply.lower()


@pytest.mark.asyncio
async def test_planner_fallback_is_concrete(db_session, test_park, planner_mode) -> None:
    svc = ChatService(db_session)
    resp = await svc.handle_message(
        ChatMessageRequest(
            park_slug=test_park["slug"],
            channel="telegram",
            session_id=uuid4(),
            user_id="123",
            message="абракадабра",
        )
    )
    assert "график" in resp.reply.lower() or "как добраться" in resp.reply.lower() or "цены" in resp.reply.lower()


@pytest.mark.asyncio
async def test_planner_help(db_session, test_park, planner_mode) -> None:
    svc = ChatService(db_session)
    resp = await svc.handle_message(
        ChatMessageRequest(
            park_slug=test_park["slug"],
            channel="telegram",
            session_id=uuid4(),
            user_id="123",
            message="/help",
        )
    )
    assert "джуси" in resp.reply.lower()


@pytest.mark.asyncio
async def test_planner_no_money_strings(db_session, test_park, planner_mode) -> None:
    svc = ChatService(db_session)
    resp = await svc.handle_message(
        ChatMessageRequest(
            park_slug=test_park["slug"],
            channel="telegram",
            session_id=uuid4(),
            user_id="123",
            message="сколько стоит билет?",
        )
    )
    txt = resp.reply.lower()
    assert "₽" not in resp.reply
    assert "руб" not in txt


@pytest.mark.asyncio
async def test_planner_max_one_link(db_session, test_park, planner_mode) -> None:
    await _seed_pages(db_session, test_park["id"])
    svc = ChatService(db_session)
    resp = await svc.handle_message(
        ChatMessageRequest(
            park_slug=test_park["slug"],
            channel="telegram",
            session_id=uuid4(),
            user_id="123",
            message="ресторан и меню?",
        )
    )
    assert resp.reply.count("http://") + resp.reply.count("https://") <= 1


@pytest.mark.asyncio
async def test_planner_max_two_questions(db_session, test_park, planner_mode) -> None:
    svc = ChatService(db_session)
    resp = await svc.handle_message(
        ChatMessageRequest(
            park_slug=test_park["slug"],
            channel="telegram",
            session_id=uuid4(),
            user_id="123",
            message="хочу день рождения",
        )
    )
    assert resp.reply.count("?") <= 2
