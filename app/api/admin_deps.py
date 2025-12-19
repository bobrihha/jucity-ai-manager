from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.config import settings


def require_admin_api_key(x_admin_api_key: str | None = Header(default=None)) -> str:
    if not settings.admin_api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="ADMIN_API_KEY is not configured")
    if not x_admin_api_key or x_admin_api_key != settings.admin_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin api key")
    return x_admin_api_key


def get_admin_actor(x_admin_actor: str | None = Header(default=None)) -> str:
    return x_admin_actor or "admin"

