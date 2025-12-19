from __future__ import annotations

import os
from uuid import UUID

import httpx


API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")


def _admin_headers() -> dict[str, str]:
    if not ADMIN_API_KEY:
        raise SystemExit("ADMIN_API_KEY env is required")
    return {"X-Admin-Key": ADMIN_API_KEY}


def main() -> int:
    client = httpx.Client(timeout=30.0)

    r = client.get(f"{API_URL}/v1/admin/health", headers=_admin_headers())
    if r.status_code != 200:
        print("admin/health failed", r.status_code, r.text)
        return 2

    park_slug = "nn"
    session_id = UUID("00000000-0000-0000-0000-000000000101")

    phone_old = "+7 (999) 000-00-11"
    phone_new = "+7 (999) 000-00-22"

    def put_contacts(phone: str) -> None:
        rr = client.put(
            f"{API_URL}/v1/admin/parks/{park_slug}/contacts",
            headers=_admin_headers(),
            json={
                "items": [{"type": "phone", "value": phone, "is_primary": True}],
                "reason": "smoke",
            },
        )
        rr.raise_for_status()

    def publish() -> None:
        rr = client.post(
            f"{API_URL}/v1/admin/parks/{park_slug}/publish",
            headers=_admin_headers(),
            json={"notes": "smoke"},
        )
        rr.raise_for_status()

    def rollback() -> None:
        rr = client.post(
            f"{API_URL}/v1/admin/parks/{park_slug}/rollback",
            headers=_admin_headers(),
            json={"reason": "smoke"},
        )
        rr.raise_for_status()

    def ask_phone() -> str:
        rr = client.post(
            f"{API_URL}/v1/chat/message",
            json={
                "park_slug": park_slug,
                "channel": "smoke",
                "session_id": str(session_id),
                "message": "Какой у вас телефон?",
            },
        )
        rr.raise_for_status()
        return rr.json()["reply"]

    # publish old
    put_contacts(phone_old)
    publish()

    # change live, but answer should stay old because snapshot is active
    put_contacts(phone_new)
    reply1 = ask_phone()
    if phone_old not in reply1:
        print("FAIL: expected snapshot phone_old")
        print(reply1)
        return 2
    if phone_new in reply1:
        print("FAIL: should not leak live phone_new while snapshot active")
        print(reply1)
        return 2

    # publish new
    publish()
    reply2 = ask_phone()
    if phone_new not in reply2:
        print("FAIL: expected snapshot phone_new after publish")
        print(reply2)
        return 2

    # rollback to previous snapshot
    rollback()
    reply3 = ask_phone()
    if phone_old not in reply3:
        print("FAIL: expected phone_old after rollback")
        print(reply3)
        return 2

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

