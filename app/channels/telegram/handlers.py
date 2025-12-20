from __future__ import annotations

import logging
from uuid import UUID, uuid5

from aiogram import F, Router
from aiogram.types import Message

from app.api.schemas import ChatMessageRequest
from app.db import SessionLocal
from app.services.chat_service import ChatService


router = Router()


def _telegram_session_id(telegram_user_id: int, *, park_slug: str) -> UUID:
    return uuid5(UUID("00000000-0000-0000-0000-000000000000"), f"telegram:{park_slug}:{telegram_user_id}")


@router.message(F.text)
async def on_text_message(message: Message) -> None:
    if not message.text:
        return

    text_raw = message.text.strip()
    text_lower = text_raw.lower()

    if text_lower.startswith("/whoami"):
        await message.answer(f"Твой chat_id: {message.chat.id}")
        return

    telegram_user_id = message.from_user.id if message.from_user else 0
    park_slug = "nn"
    logging.info("telegram.incoming user_id=%s text_len=%s", telegram_user_id, len(message.text))

    req = ChatMessageRequest(
        park_slug=park_slug,
        channel="telegram",
        session_id=_telegram_session_id(telegram_user_id, park_slug=park_slug),
        user_id=str(telegram_user_id),
        message=text_raw,
    )

    try:
        async with SessionLocal() as session:
            resp = await ChatService(session=session).handle_message(req)
            await session.commit()
    except Exception:
        logging.exception("telegram.handler_failed user_id=%s", telegram_user_id)
        await message.answer("Сервис сейчас недоступен. Попробуйте ещё раз через минуту.")
        return

    await message.answer(resp.reply)
