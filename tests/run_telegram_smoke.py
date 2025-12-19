from __future__ import annotations

import pytest

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
