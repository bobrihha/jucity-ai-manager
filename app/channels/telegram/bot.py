from __future__ import annotations

import asyncio
import os

from aiogram import Bot, Dispatcher

from app.channels.telegram.handlers import router


async def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    dp = Dispatcher()
    dp.include_router(router)

    bot = Bot(token=token)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

