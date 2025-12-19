from __future__ import annotations

import os
from uuid import UUID

import httpx


API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")


def _admin_headers() -> dict[str, str]:
    if not ADMIN_API_KEY:
        raise SystemExit("ADMIN_API_KEY env is required")
    return {"X-Admin-API-Key": ADMIN_API_KEY, "X-Admin-Actor": "smoke"}


def main() -> int:
    client = httpx.Client(timeout=30.0)

    r = client.get(f"{API_URL}/v1/admin/health", headers=_admin_headers())
    if r.status_code != 200:
        print("admin/health failed", r.status_code, r.text)
        return 2

    park_slug = "nn"
    session_id = UUID("00000000-0000-0000-0000-000000000099")

    phone1 = "+7 (999) 000-00-01"
    phone2 = "+7 (999) 000-00-02"

    def put_contacts(phone: str) -> None:
        rr = client.put(
            f"{API_URL}/v1/admin/parks/{park_slug}/contacts",
            headers=_admin_headers(),
            json={
                "items": [
                    {"type": "phone", "value": phone, "is_primary": True},
                    {"type": "email", "value": "info@example.com", "is_primary": False},
                ],
                "reason": "smoke",
            },
        )
        rr.raise_for_status()

    def publish() -> str:
        rr = client.post(
            f"{API_URL}/v1/admin/parks/{park_slug}/publish",
            headers=_admin_headers(),
            json={"notes": "smoke"},
        )
        rr.raise_for_status()
        return rr.json()["published_version_id"]

    def rollback() -> str:
        rr = client.post(
            f"{API_URL}/v1/admin/parks/{park_slug}/rollback",
            headers=_admin_headers(),
        )
        rr.raise_for_status()
        return rr.json()["published_version_id"]

    def ask_phone() -> str:
        rr = client.post(
            f"{API_URL}/v1/chat/message",
            json={
                "park_slug": park_slug,
                "channel": "smoke",
                "session_id": str(session_id),
                "message": "Подскажите телефон",
            },
        )
        rr.raise_for_status()
        return rr.json()["reply"]

    put_contacts(phone1)
    v1 = publish()

    put_contacts(phone2)
    reply_after_live_change = ask_phone()
    if phone2 in reply_after_live_change:
        print("FAIL: reply used live facts while published snapshot is active")
        print(reply_after_live_change)
        return 2
    if phone1 not in reply_after_live_change:
        print("FAIL: reply does not contain snapshot phone1")
        print(reply_after_live_change)
        return 2

    v2 = publish()
    reply_v2 = ask_phone()
    if phone2 not in reply_v2:
        print("FAIL: reply does not contain snapshot phone2 after publishing v2")
        print(reply_v2)
        return 2

    rb = rollback()
    reply_rb = ask_phone()
    if phone1 not in reply_rb:
        print("FAIL: rollback did not restore previous snapshot (expected phone1)")
        print("rollback_to=", rb, "published_v1=", v1, "published_v2=", v2)
        print(reply_rb)
        return 2

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

