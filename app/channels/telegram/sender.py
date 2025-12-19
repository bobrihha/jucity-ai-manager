from __future__ import annotations

import os
from dataclasses import dataclass


def _parse_admin_chat_ids(raw: str) -> list[int]:
    ids: list[int] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        ids.append(int(part))
    return ids


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    admin_chat_ids: list[int]


def telegram_config_from_env() -> TelegramConfig | None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    ids_raw = os.getenv("TELEGRAM_ADMIN_CHAT_IDS", "").strip()
    if not token or not ids_raw:
        return None
    return TelegramConfig(bot_token=token, admin_chat_ids=_parse_admin_chat_ids(ids_raw))


async def send_admin_notification(text: str) -> None:
    cfg = telegram_config_from_env()
    if not cfg:
        return

    from aiogram import Bot

    bot = Bot(token=cfg.bot_token)
    try:
        for chat_id in cfg.admin_chat_ids:
            await bot.send_message(chat_id=chat_id, text=text)
    finally:
        await bot.session.close()

