from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
    park_slug: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    session_id: UUID | None = None
    user_id: str | None = None
    message: str = Field(min_length=1)


class ChatMessageResponse(BaseModel):
    reply: str
    session_id: UUID
    trace_id: UUID

