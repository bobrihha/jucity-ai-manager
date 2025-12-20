from __future__ import annotations

import asyncio
import os
import logging

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

from app.channels.telegram.handlers import router


async def main() -> None:
    load_dotenv(override=False)

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    dp = Dispatcher()
    dp.include_router(router)

    bot = Bot(token=token)
    try:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("aiogram").setLevel(logging.INFO)
        await bot.delete_webhook(drop_pending_updates=True)
        logging.info("Telegram bot started (polling)")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
