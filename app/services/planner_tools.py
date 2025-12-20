from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repos.facts_repo import FactsRepo
from app.repos.leads_repo import LeadsRepo
from app.services.rag_service import RAGService


@dataclass(frozen=True)
class ToolExecutionResult:
    name: str
    ok: bool
    result: dict[str, Any]


async def execute_tool(
    *,
    session: AsyncSession,
    tool_name: str,
    args: dict[str, Any],
    park_id: UUID,
    park_slug: str,
    session_id: UUID,
) -> ToolExecutionResult:
    if tool_name == "tool_get_facts":
        facts_repo = FactsRepo(session)
        facts = await facts_repo.get_facts(park_id)
        pages: dict[str, str] = {}
        for key in ["contact", "rules", "restaurant", "party_main", "prices_tickets", "promotions"]:
            url = await facts_repo.get_page_url(park_id, key)
            if url:
                pages[key] = url
        return ToolExecutionResult(
            name=tool_name,
            ok=True,
            result={
                "facts": {
                    "opening_hours_text": facts.opening_hours_text,
                    "primary_phone": facts.primary_phone,
                    "address_text": (facts.location or {}).get("address_text") if facts.location else None,
                },
                "pages": pages,
            },
        )

    if tool_name == "tool_search_kb":
        query = str(args.get("query") or "").strip()
        rag = RAGService(session)
        chunks = await rag.retrieve(park_id=park_id, park_slug=park_slug, query=query, top_k=5)
        return ToolExecutionResult(
            name=tool_name,
            ok=True,
            result={
                "chunks": [
                    {"score": c.score, "source_url": c.source_url, "chunk_id": c.chunk_id, "text": c.chunk_text}
                    for c in chunks[:5]
                ]
            },
        )

    if tool_name == "tool_upsert_lead":
        slot_updates = args.get("slot_updates") if isinstance(args.get("slot_updates"), dict) else {}
        leads = LeadsRepo(session)
        lead = await leads.upsert_lead_by_session(
            park_id=park_id,
            session_id=session_id,
            intent=str(args.get("intent") or "party_main"),
            slots_patch=dict(slot_updates),
            missing_required_slots=[],
            conversation_append=None,
            admin_message=None,
        )
        return ToolExecutionResult(name=tool_name, ok=True, result={"lead_id": str(lead.id)})

    if tool_name == "tool_create_handoff":
        # The classic flow already supports handoff creation; planner can request it and ChatService will finalize.
        return ToolExecutionResult(name=tool_name, ok=True, result={"handoff_created": True})

    return ToolExecutionResult(name=tool_name, ok=False, result={"error": f"unknown tool: {tool_name}"})

