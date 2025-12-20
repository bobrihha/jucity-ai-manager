from __future__ import annotations

from uuid import uuid4

import pytest

from app.api.schemas import ChatMessageRequest
from app.services.chat_service import ChatService


@pytest.mark.asyncio
async def test_name_extracted_then_used_once_next_reply(db_session, test_park) -> None:
    svc = ChatService(db_session)
    session_id = uuid4()

    r1 = await svc.handle_message(
        ChatMessageRequest(
            park_slug=test_park["slug"],
            channel="telegram",
            session_id=session_id,
            user_id="123",
            message="меня зовут Аня",
        )
    )
    assert "Ок, Аня" not in r1.reply

    r2 = await svc.handle_message(
        ChatMessageRequest(
            park_slug=test_park["slug"],
            channel="telegram",
            session_id=session_id,
            user_id="123",
            message="График работы",
        )
    )
    assert "Аня" in r2.reply

    r3 = await svc.handle_message(
        ChatMessageRequest(
            park_slug=test_park["slug"],
            channel="telegram",
            session_id=session_id,
            user_id="123",
            message="Телефон?",
        )
    )
    assert r3.reply.count("Аня") == 0
