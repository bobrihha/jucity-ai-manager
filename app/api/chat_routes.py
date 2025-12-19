from __future__ import annotations

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import ChatMessageRequest, ChatMessageResponse
from app.db import get_session
from app.services.chat_service import ChatService


router = APIRouter(prefix="/v1")


@router.post("/chat/message", response_model=ChatMessageResponse)
async def post_chat_message(
    payload: ChatMessageRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ChatMessageResponse:
    try:
        return await ChatService(session=session).handle_message(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
