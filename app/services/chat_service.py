from __future__ import annotations

from dataclasses import dataclass
import time
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import ChatMessageRequest, ChatMessageResponse
from app.domain.composer import Composer
from app.domain.extraction.slots import SlotsPatch, extract_slots, mask_phone
from app.domain.router import Router
from app.repos.event_log_repo import EventLogRepo
from app.repos.facts_repo import FactsRepo
from app.repos.leads_repo import LeadsRepo, lead_to_dict
from app.services.rag_service import RAGService
from app.services.llm_service import render_text as llm_render_text
from app.services.telegram_notifications import notify_admins_telegram
from app.utils import mask_phones
from app.config import settings


@dataclass(frozen=True)
class ChatContext:
    trace_id: UUID
    session_id: UUID
    park_id: UUID
    park_slug: str
    channel: str
    user_id: str | None


class ChatService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._facts_repo = FactsRepo(session)
        self._event_log = EventLogRepo(session)
        self._leads_repo = LeadsRepo(session)
        self._router = Router()
        self._composer = Composer()
        self._rag = RAGService(session)

    async def handle_message(self, req: ChatMessageRequest) -> ChatMessageResponse:
        trace_id = uuid4()
        session_id = req.session_id or uuid4()

        park = await self._facts_repo.get_park_by_slug(req.park_slug)
        if park is None:
            raise ValueError(f"Unknown park_slug: {req.park_slug}")
        published_version_id = await self._facts_repo.get_published_version_id(park.id)

        ctx = ChatContext(
            trace_id=trace_id,
            session_id=session_id,
            park_id=park.id,
            park_slug=park.slug,
            channel=req.channel,
            user_id=req.user_id,
        )

        await self._event_log.write_event(
            trace_id=ctx.trace_id,
            session_id=ctx.session_id,
            user_id=ctx.user_id,
            park_id=ctx.park_id,
            park_slug=ctx.park_slug,
            channel=ctx.channel,
            event_name="message_received",
            payload={"message": mask_phones(req.message)},
            facts_version_id=published_version_id,
        )

        route = self._router.route(req.message)
        await self._event_log.write_event(
            trace_id=ctx.trace_id,
            session_id=ctx.session_id,
            user_id=ctx.user_id,
            park_id=ctx.park_id,
            park_slug=ctx.park_slug,
            channel=ctx.channel,
            event_name="intent_routed",
            payload={
                "intent": route.intent,
                "mode": route.mode,
                "confidence": route.confidence,
                "link_intent": route.link_intent,
                "required_slots": route.required_slots,
            },
            facts_version_id=published_version_id,
        )

        facts = await self._facts_repo.get_facts(ctx.park_id)
        facts_link_url = (
            await self._facts_repo.get_page_url(ctx.park_id, route.link_intent) if route.link_intent else None
        )

        lead = None
        missing_slots: list[str] = []
        handoff_created = False
        admin_message: str | None = None
        rag_chunks = []
        rag_used = False

        if route.mode in {"lead_mode", "handoff_mode"}:
            party_context = route.intent in {"party_main", "graduation", "new_year_trees"}
            slots_patch: SlotsPatch = extract_slots(req.message, party_context=party_context)
            extracted = {
                "client_phone": slots_patch.client_phone,
                "event_date": slots_patch.event_date,
                "event_time": slots_patch.event_time,
                "day_of_week": slots_patch.day_of_week,
                "kids_count": slots_patch.kids_count,
                "kids_age_main": slots_patch.kids_age_main,
            }
            extracted_masked = dict(extracted)
            if extracted_masked.get("client_phone"):
                extracted_masked["client_phone"] = mask_phone(extracted_masked["client_phone"])

            await self._event_log.write_event(
                trace_id=ctx.trace_id,
                session_id=ctx.session_id,
                user_id=ctx.user_id,
                park_id=ctx.park_id,
                park_slug=ctx.park_slug,
                channel=ctx.channel,
                event_name="slots_extracted",
                payload={
                    "pii_masking_applied": True,
                    "slots_extracted": {k: v for k, v in extracted_masked.items() if v is not None},
                },
                facts_version_id=published_version_id,
            )

            lead = await self._leads_repo.get_open_lead_by_session(park_id=ctx.park_id, session_id=ctx.session_id)
            existing = lead_to_dict(lead) if lead else {}
            merged = {}
            for k, v in extracted.items():
                if v is None:
                    continue
                if existing.get(k) in (None, "", 0):
                    merged[k] = v

            missing_slots = compute_missing_slots(
                intent=route.intent,
                required_slots=route.required_slots,
                existing=existing,
                patch=merged,
            )

            if should_create_handoff(intent=route.intent, missing_slots=missing_slots, merged={**existing, **merged}):
                admin_message = build_admin_message(
                    intent=route.intent,
                    park_slug=ctx.park_slug,
                    slots={**existing, **merged},
                    last_user_message=req.message,
                )
                handoff_created = True

            lead = await self._leads_repo.upsert_lead_by_session(
                park_id=ctx.park_id,
                session_id=ctx.session_id,
                intent=route.intent,
                slots_patch=merged,
                missing_required_slots=missing_slots,
                conversation_append={"role": "user", "text": mask_phones(req.message)},
                admin_message=admin_message,
            )

            await self._event_log.write_event(
                trace_id=ctx.trace_id,
                session_id=ctx.session_id,
                user_id=ctx.user_id,
                park_id=ctx.park_id,
                park_slug=ctx.park_slug,
                channel=ctx.channel,
                event_name="lead_updated",
                payload={
                    "lead_id": str(lead.id),
                    "missing_slots": missing_slots,
                    "pii_masking_applied": True,
                },
                facts_version_id=published_version_id,
            )

            if handoff_created and admin_message:
                await self._event_log.write_event(
                    trace_id=ctx.trace_id,
                    session_id=ctx.session_id,
                    user_id=ctx.user_id,
                    park_id=ctx.park_id,
                    park_slug=ctx.park_slug,
                    channel=ctx.channel,
                    event_name="handoff_created",
                    payload={
                        "lead_id": str(lead.id),
                        "admin_message_preview": mask_phones(admin_message)[:200],
                        "pii_masking_applied": True,
                    },
                    facts_version_id=published_version_id,
                )

                # Telegram admin notifications (deduped by admin_message hash on lead)
                notified = await self._leads_repo.mark_admin_message_notified(lead.id, admin_message=admin_message)
                if notified:
                    await notify_admins_telegram(lead_id=str(lead.id), park_slug=ctx.park_slug, admin_message=admin_message)

        use_rag = should_use_rag(intent=route.intent, rag_enabled=settings.rag_enabled)
        if use_rag:
            try:
                t0 = time.monotonic()
                rag_chunks = await self._rag.retrieve(
                    park_id=ctx.park_id,
                    park_slug=ctx.park_slug,
                    query=req.message,
                    top_k=5,
                )
                latency_ms = int((time.monotonic() - t0) * 1000)
                rag_used = bool(rag_chunks)
                await self._event_log.write_event(
                    trace_id=ctx.trace_id,
                    session_id=ctx.session_id,
                    user_id=ctx.user_id,
                    park_id=ctx.park_id,
                    park_slug=ctx.park_slug,
                    channel=ctx.channel,
                    event_name="rag_retrieved",
                    payload={
                        "query": mask_phones(req.message),
                        "top_k": 5,
                        "latency_ms": latency_ms,
                        "results": [
                            {"score": c.score, "chunk_id": c.chunk_id, "source_url": c.source_url}
                            for c in rag_chunks[:5]
                        ],
                    },
                    facts_version_id=published_version_id,
                )
            except Exception as e:
                rag_chunks = []
                rag_used = False
                await self._event_log.write_event(
                    trace_id=ctx.trace_id,
                    session_id=ctx.session_id,
                    user_id=ctx.user_id,
                    park_id=ctx.park_id,
                    park_slug=ctx.park_slug,
                    channel=ctx.channel,
                    event_name="rag_retrieved",
                    payload={"query": mask_phones(req.message), "error": str(e), "top_k": 5},
                    facts_version_id=published_version_id,
                )

        link_url = rag_chunks[0].source_url if rag_chunks and rag_chunks[0].source_url else facts_link_url

        used_keys = self._composer.facts_keys_used(intent=route.intent)
        await self._event_log.write_event(
            trace_id=ctx.trace_id,
            session_id=ctx.session_id,
            user_id=ctx.user_id,
            park_id=ctx.park_id,
            park_slug=ctx.park_slug,
            channel=ctx.channel,
            event_name="facts_used",
            payload={"keys": used_keys},
            facts_version_id=published_version_id,
        )

        draft_plan = self._composer.build_plan(
            intent=route.intent,
            facts=facts,
            link_url=link_url,
            user_message=mask_phones(req.message),
            lead=lead,
            missing_slots=missing_slots,
            handoff_created=handoff_created,
            admin_message=admin_message,
            rag_chunks=rag_chunks if use_rag else None,
        )
        draft_text = self._composer.render_from_plan(draft_plan)

        final_text = draft_text
        llm_ok = False
        if settings.llm_enabled:
            try:
                t0 = time.monotonic()
                rendered = await llm_render_text(
                    draft_plan,
                    channel=ctx.channel,
                    voice=settings.brand_voice or "jucity_nn",
                )
                llm_ok = True
                await self._event_log.write_event(
                    trace_id=ctx.trace_id,
                    session_id=ctx.session_id,
                    user_id=ctx.user_id,
                    park_id=ctx.park_id,
                    park_slug=ctx.park_slug,
                    channel=ctx.channel,
                    event_name="llm_rendered",
                    payload={
                        "provider": rendered.provider,
                        "model": rendered.model,
                        "latency_ms": rendered.latency_ms or int((time.monotonic() - t0) * 1000),
                    },
                    facts_version_id=published_version_id,
                )
                final_text = rendered.text
            except Exception as e:
                await self._event_log.write_event(
                    trace_id=ctx.trace_id,
                    session_id=ctx.session_id,
                    user_id=ctx.user_id,
                    park_id=ctx.park_id,
                    park_slug=ctx.park_slug,
                    channel=ctx.channel,
                    event_name="llm_failed",
                    payload={"error": str(e), "provider": settings.llm_provider, "model": settings.llm_model},
                    facts_version_id=published_version_id,
                )
                final_text = draft_text

        safe_reply, safety_guard_applied, rag_conflict_detected = apply_guardrails(
            reply=final_text,
            intent=route.intent,
            rag_used=rag_used,
        )
        if rag_conflict_detected:
            await self._event_log.write_event(
                trace_id=ctx.trace_id,
                session_id=ctx.session_id,
                user_id=ctx.user_id,
                park_id=ctx.park_id,
                park_slug=ctx.park_slug,
                channel=ctx.channel,
                event_name="rag_conflict_detected",
                payload={"rag_used": rag_used, "safety_guard_applied": safety_guard_applied},
                facts_version_id=published_version_id,
            )

        await self._event_log.write_event(
            trace_id=ctx.trace_id,
            session_id=ctx.session_id,
            user_id=ctx.user_id,
            park_id=ctx.park_id,
            park_slug=ctx.park_slug,
            channel=ctx.channel,
            event_name="answer_composed",
            payload={
                "reply_length": len(safe_reply),
                "questions": list(draft_plan.get("questions") or [])[:2],
                "link": link_url,
                "missing_slots": missing_slots,
                "pii_masking_applied": True if missing_slots else False,
                "rag_used": rag_used,
                "safety_guard_applied": safety_guard_applied,
                "llm_used": llm_ok,
            },
            facts_version_id=published_version_id,
        )

        await self._session.commit()

        return ChatMessageResponse(
            reply=safe_reply,
            session_id=ctx.session_id,
            trace_id=ctx.trace_id,
        )


def compute_missing_slots(
    *,
    intent: str,
    required_slots: list[str],
    existing: dict,
    patch: dict,
) -> list[str]:
    merged = {**existing, **patch}

    def has_date_like() -> bool:
        return bool(merged.get("event_date") or merged.get("day_of_week") is not None)

    missing: list[str] = []
    for slot in required_slots:
        if slot == "event_date":
            if not has_date_like():
                missing.append(slot)
            continue
        if merged.get(slot) in (None, "", 0):
            missing.append(slot)

    if intent != "party_main" and "kids_age_main" in missing:
        missing.remove("kids_age_main")

    return missing


def should_create_handoff(*, intent: str, missing_slots: list[str], merged: dict) -> bool:
    phone_ok = bool(merged.get("client_phone"))
    if intent == "handoff":
        return phone_ok
    if intent not in {"party_main", "graduation", "new_year_trees"}:
        return False
    date_ok = bool(merged.get("event_date") or merged.get("day_of_week") is not None)
    return phone_ok and date_ok


def build_admin_message(*, intent: str, park_slug: str, slots: dict, last_user_message: str) -> str:
    phone = slots.get("client_phone")
    phone_masked = mask_phone(phone) if phone else None
    d = slots.get("event_date")
    dow = slots.get("day_of_week")
    kids = slots.get("kids_count")
    age = slots.get("kids_age_main")

    header = "🔥 Заявка"
    kind = {
        "party_main": "ДР",
        "graduation": "Выпускной",
        "new_year_trees": "Ёлки",
        "handoff": "Запрос менеджера",
    }.get(intent, intent)

    parts = [f"{header}: {kind} (park={park_slug})"]
    if d:
        parts.append(f"Дата: {d.isoformat()}")
    elif dow is not None:
        parts.append(f"День недели: {dow} (0=Пн..6=Вс)")
    if kids:
        parts.append(f"Дети: {kids}")
    if age and intent == "party_main":
        parts.append(f"Возраст: {age}")
    if phone_masked:
        parts.append(f"Тел: {phone_masked}")
    parts.append(f"Комментарий: {mask_phones(last_user_message)[:200]}")
    return "\n".join(parts)


def should_use_rag(*, intent: str, rag_enabled: bool) -> bool:
    if not rag_enabled:
        return False
    if intent in {"prices_tickets", "prices_vr", "promotions", "gift_cards"}:
        return False
    return intent in {"rules", "attractions", "restaurant", "poster"}


def apply_guardrails(*, reply: str, intent: str, rag_used: bool) -> tuple[str, bool, bool]:
    import re

    from app.domain.patterns import MONEY_WITH_CURRENCY_RE

    if not rag_used:
        return reply, False, False

    # Hard rule: never show money amounts for price-related intents (even if rag accidentally used).
    if intent in {"prices_tickets", "prices_vr", "promotions", "gift_cards"}:
        cleaned = re.sub(r"\\b\\d[\\d\\s]*(?:[.,]\\d+)?\\s*(?:₽|руб\\.?|р\\.|рублей|рубля)\\b", "—", reply, flags=re.IGNORECASE)
        cleaned = re.sub(r"\\b\\d{2,}\\b", "—", cleaned)
        return cleaned, True, True

    # Soft filter: if answer contains currency markers, mask amounts.
    if MONEY_WITH_CURRENCY_RE.search(reply):
        cleaned = MONEY_WITH_CURRENCY_RE.sub("—", reply)
        return cleaned, True, True

    return reply, False, False
