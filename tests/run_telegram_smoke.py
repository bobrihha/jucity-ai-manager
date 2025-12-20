from __future__ import annotations

import pytest

from app.domain.composer import Composer
from app.domain.router import Router
from app.repos.facts_repo import FactsBundle
from app.services.telegram_notifications import notify_admins_telegram


@pytest.mark.asyncio
async def test_notify_admins_telegram_calls_sender(monkeypatch) -> None:
    called = {"n": 0, "text": ""}

    async def fake_send(text: str) -> None:
        called["n"] += 1
        called["text"] = text

    monkeypatch.setattr("app.channels.telegram.sender.send_admin_notification", fake_send)

    await notify_admins_telegram(lead_id="L1", park_slug="nn", admin_message="Тел: +79990000000")

    assert called["n"] == 1
    assert "Новая заявка" in called["text"]
    assert "Парк: nn" in called["text"]


def _empty_facts() -> FactsBundle:
    return FactsBundle(
        contacts=[],
        location=None,
        opening_hours=[],
        transport=[],
        site_pages={},
        legal_documents=[],
        promotions=[],
        faq=[],
        opening_hours_text=None,
        primary_phone=None,
    )


def test_start_compose_text() -> None:
    routed = Router().route("/start")
    assert routed.intent == "start"
    assert routed.confidence == 1.0

    ans = Composer().compose(
        intent=routed.intent,
        facts=_empty_facts(),
        link_url=None,
        user_message="/start",
    )
    assert "Я Джуси" in ans.reply
    assert "Как до вас добраться" in ans.reply
    assert "Сколько стоит билет" in ans.reply


def test_clarify_compose_text() -> None:
    routed = Router().route("в смысле?")
    assert routed.intent == "clarify"
    assert routed.confidence == 1.0

    ans = Composer().compose(
        intent=routed.intent,
        facts=_empty_facts(),
        link_url=None,
        user_message="в смысле?",
    )
    assert "извини" in ans.reply.lower()
    assert "администратор" in ans.reply.lower()
