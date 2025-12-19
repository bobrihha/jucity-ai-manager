from __future__ import annotations

from app.channels.telegram.sender import send_admin_notification


async def notify_admins_telegram(*, lead_id: str, park_slug: str, admin_message: str) -> None:
    text = f"🔥 Новая заявка!\nПарк: {park_slug}\nLead: {lead_id}\n\n{admin_message}"
    await send_admin_notification(text)

