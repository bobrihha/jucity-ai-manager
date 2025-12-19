from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.config import settings


def verify_admin_key(
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
    x_admin_api_key: str | None = Header(default=None, alias="X-Admin-API-Key"),
) -> str:
    if not settings.admin_api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="ADMIN_API_KEY is not configured")
    provided = x_admin_key or x_admin_api_key
    if not provided or provided != settings.admin_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin api key")
    return provided


def get_admin_actor(x_admin_actor: str | None = Header(default=None)) -> str:
    return x_admin_actor or "admin"
