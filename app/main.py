from __future__ import annotations

from fastapi import FastAPI

from app.api.admin_routes import router as admin_router
from app.api.chat_routes import router as chat_router


app = FastAPI(title="jucity-ai-manager", version="0.0.1")
app.include_router(chat_router)
app.include_router(admin_router)


@app.get("/v1/health")
async def health() -> dict:
    return {"status": "ok"}
