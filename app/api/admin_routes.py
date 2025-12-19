from __future__ import annotations
from datetime import date, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin_deps import get_admin_actor, verify_admin_key
from app.db import get_session
from app.repos.facts_repo import FactsRepo
from app.repos.kb_indexes_repo import KBIndexesRepo
from app.repos.kb_jobs_repo import KBJobAlreadyActiveError, KBJobsRepo
from app.repos.kb_sources_repo import KBSourcesRepo
from app.services.governance_service import GovernanceService
from app.services.kb_indexer import KBIndexer
from app.repos.facts_versions_repo import FactsVersionsRepo


router = APIRouter(prefix="/v1/admin", dependencies=[Depends(verify_admin_key)])


@router.get("/health")
async def admin_health() -> dict:
    return {"status": "ok"}


class PublishRequest(BaseModel):
    notes: str | None = None


class PublishResponse(BaseModel):
    published_version_id: UUID


@router.post("/parks/{park_slug}/publish", response_model=PublishResponse)
async def publish_facts(
    park_slug: str,
    payload: PublishRequest,
    actor: Annotated[str, Depends(get_admin_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PublishResponse:
    facts_repo = FactsRepo(session)
    park = await facts_repo.get_park_by_slug(park_slug)
    if not park:
        raise HTTPException(status_code=404, detail="park not found")
    gov = GovernanceService(session)
    version_id = await gov.publish_snapshot(park_id=park.id, actor=actor, notes=payload.notes)
    await session.commit()
    return PublishResponse(published_version_id=version_id)


class RollbackRequest(BaseModel):
    reason: str | None = None


@router.post("/parks/{park_slug}/rollback", response_model=PublishResponse)
async def rollback_facts(
    park_slug: str,
    actor: Annotated[str, Depends(get_admin_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
    payload: RollbackRequest | None = None,
) -> PublishResponse:
    facts_repo = FactsRepo(session)
    park = await facts_repo.get_park_by_slug(park_slug)
    if not park:
        raise HTTPException(status_code=404, detail="park not found")
    gov = GovernanceService(session)
    try:
        payload = payload or RollbackRequest()
        version_id = await gov.rollback_snapshot(park_id=park.id, actor=actor, reason=payload.reason)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    await session.commit()
    return PublishResponse(published_version_id=version_id)


@router.get("/parks/{park_slug}/versions")
async def list_versions(
    park_slug: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    facts_repo = FactsRepo(session)
    park = await facts_repo.get_park_by_slug(park_slug)
    if not park:
        raise HTTPException(status_code=404, detail="park not found")
    versions = await FactsVersionsRepo(session).list_published_versions(park.id, limit=20)
    return {"versions": versions}


@router.get("/parks/{park_slug}/facts")
async def get_live_facts(
    park_slug: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    facts_repo = FactsRepo(session)
    park = await facts_repo.get_park_by_slug(park_slug)
    if not park:
        raise HTTPException(status_code=404, detail="park not found")
    bundle = await facts_repo.get_live_facts(park.id)
    published_version_id = await facts_repo.get_published_version_id(park.id)
    return {"park_slug": park.slug, "published_version_id": published_version_id, "facts": bundle.__dict__}


class ContactIn(BaseModel):
    type: str
    value: str
    is_primary: bool = False


class LocationIn(BaseModel):
    address_text: str
    city: str | None = None
    lat: float | None = None
    lon: float | None = None


class OpeningHourIn(BaseModel):
    dow: int = Field(ge=0, le=6)
    open_time: str | None = None  # HH:MM
    close_time: str | None = None  # HH:MM
    is_closed: bool = False
    note: str | None = None

    @field_validator("open_time", "close_time")
    @classmethod
    def _validate_hhmm(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if len(v) != 5 or v[2] != ":":
            raise ValueError("time must be HH:MM")
        hh = int(v[:2])
        mm = int(v[3:])
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError("time must be HH:MM")
        return v


class TransportIn(BaseModel):
    kind: str
    text: str


class SitePageIn(BaseModel):
    key: str
    path: str | None = None
    absolute_url: str | None = None

    @field_validator("path")
    @classmethod
    def _path_slash(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.startswith("/"):
            raise ValueError("path must start with '/'")
        return v


class LegalDocumentIn(BaseModel):
    key: str
    title: str
    path: str | None = None
    absolute_url: str | None = None


class PromotionIn(BaseModel):
    key: str
    title: str
    text: str
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    expires_at: datetime | None = None

    @field_validator("valid_to")
    @classmethod
    def _validate_from_to(cls, v: datetime | None, info):  # type: ignore[no-untyped-def]
        data = info.data
        vf = data.get("valid_from")
        if v is not None and vf is not None and vf > v:
            raise ValueError("valid_from must be <= valid_to")
        return v


class FAQIn(BaseModel):
    question: str
    answer: str
    is_active: bool = True


class ReplaceRequest(BaseModel):
    items: list[Any] = Field(default_factory=list)
    reason: str | None = None


def _validate_expires_at(expires_at: datetime | None) -> None:
    if not expires_at:
        return
    if expires_at.date() < date.today():
        raise HTTPException(status_code=422, detail="expires_at must be >= today")


@router.put("/parks/{park_slug}/contacts")
async def put_contacts(
    park_slug: str,
    payload: ReplaceRequest,
    actor: Annotated[str, Depends(get_admin_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    contacts = [ContactIn.model_validate(i).model_dump() for i in payload.items]
    try:
        FactsRepo.validate_contacts(contacts)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    facts_repo = FactsRepo(session)
    park = await facts_repo.get_park_by_slug(park_slug)
    if not park:
        raise HTTPException(status_code=404, detail="park not found")
    before = (await facts_repo.get_live_facts(park.id)).contacts
    await facts_repo.replace_contacts(park.id, contacts)
    await facts_repo.write_change_log(
        park_id=park.id,
        actor=actor,
        entity_table="park_contacts",
        action="replace",
        before_json=before,
        after_json=contacts,
        reason=payload.reason,
    )
    await session.commit()
    return {"ok": True}


@router.put("/parks/{park_slug}/location")
async def put_location(
    park_slug: str,
    payload: LocationIn,
    actor: Annotated[str, Depends(get_admin_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    facts_repo = FactsRepo(session)
    park = await facts_repo.get_park_by_slug(park_slug)
    if not park:
        raise HTTPException(status_code=404, detail="park not found")
    before = (await facts_repo.get_live_facts(park.id)).location
    await facts_repo.replace_location(park.id, payload.model_dump())
    await facts_repo.write_change_log(
        park_id=park.id,
        actor=actor,
        entity_table="park_locations",
        action="replace",
        before_json=before,
        after_json=payload.model_dump(),
        reason=None,
    )
    await session.commit()
    return {"ok": True}


@router.put("/parks/{park_slug}/opening-hours")
async def put_opening_hours(
    park_slug: str,
    payload: ReplaceRequest,
    actor: Annotated[str, Depends(get_admin_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    hours = [OpeningHourIn.model_validate(i).model_dump() for i in payload.items]
    try:
        FactsRepo.validate_opening_hours(hours)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    facts_repo = FactsRepo(session)
    park = await facts_repo.get_park_by_slug(park_slug)
    if not park:
        raise HTTPException(status_code=404, detail="park not found")
    before = (await facts_repo.get_live_facts(park.id)).opening_hours
    await facts_repo.replace_opening_hours(park.id, hours)
    await facts_repo.write_change_log(
        park_id=park.id,
        actor=actor,
        entity_table="park_opening_hours",
        action="replace",
        before_json=before,
        after_json=hours,
        reason=payload.reason,
    )
    await session.commit()
    return {"ok": True}


@router.put("/parks/{park_slug}/transport")
async def put_transport(
    park_slug: str,
    payload: ReplaceRequest,
    actor: Annotated[str, Depends(get_admin_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    items = [TransportIn.model_validate(i).model_dump() for i in payload.items]
    facts_repo = FactsRepo(session)
    park = await facts_repo.get_park_by_slug(park_slug)
    if not park:
        raise HTTPException(status_code=404, detail="park not found")
    before = (await facts_repo.get_live_facts(park.id)).transport
    await facts_repo.replace_transport(park.id, items)
    await facts_repo.write_change_log(
        park_id=park.id,
        actor=actor,
        entity_table="park_transport",
        action="replace",
        before_json=before,
        after_json=items,
        reason=payload.reason,
    )
    await session.commit()
    return {"ok": True}


@router.put("/parks/{park_slug}/site-pages")
async def put_site_pages(
    park_slug: str,
    payload: ReplaceRequest,
    actor: Annotated[str, Depends(get_admin_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    items = [SitePageIn.model_validate(i).model_dump() for i in payload.items]
    facts_repo = FactsRepo(session)
    park = await facts_repo.get_park_by_slug(park_slug)
    if not park:
        raise HTTPException(status_code=404, detail="park not found")
    before = (await facts_repo.get_live_facts(park.id)).site_pages
    await facts_repo.replace_site_pages(park.id, items)
    await facts_repo.write_change_log(
        park_id=park.id,
        actor=actor,
        entity_table="site_pages",
        action="replace",
        before_json=before,
        after_json=items,
        reason=payload.reason,
    )
    await session.commit()
    return {"ok": True}


@router.put("/parks/{park_slug}/legal-documents")
async def put_legal_documents(
    park_slug: str,
    payload: ReplaceRequest,
    actor: Annotated[str, Depends(get_admin_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    items = [LegalDocumentIn.model_validate(i).model_dump() for i in payload.items]
    facts_repo = FactsRepo(session)
    park = await facts_repo.get_park_by_slug(park_slug)
    if not park:
        raise HTTPException(status_code=404, detail="park not found")
    before = (await facts_repo.get_live_facts(park.id)).legal_documents
    await facts_repo.replace_legal_documents(park.id, items)
    await facts_repo.write_change_log(
        park_id=park.id,
        actor=actor,
        entity_table="legal_documents",
        action="replace",
        before_json=before,
        after_json=items,
        reason=payload.reason,
    )
    await session.commit()
    return {"ok": True}


@router.put("/parks/{park_slug}/promotions")
async def put_promotions(
    park_slug: str,
    payload: ReplaceRequest,
    actor: Annotated[str, Depends(get_admin_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    items = [PromotionIn.model_validate(i).model_dump() for i in payload.items]
    for i in items:
        _validate_expires_at(i.get("expires_at"))
    facts_repo = FactsRepo(session)
    park = await facts_repo.get_park_by_slug(park_slug)
    if not park:
        raise HTTPException(status_code=404, detail="park not found")
    before = (await facts_repo.get_live_facts(park.id)).promotions
    await facts_repo.replace_promotions(park.id, items)
    await facts_repo.write_change_log(
        park_id=park.id,
        actor=actor,
        entity_table="promotions",
        action="replace",
        before_json=before,
        after_json=items,
        reason=payload.reason,
    )
    await session.commit()
    return {"ok": True}


@router.put("/parks/{park_slug}/faq")
async def put_faq(
    park_slug: str,
    payload: ReplaceRequest,
    actor: Annotated[str, Depends(get_admin_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    items = [FAQIn.model_validate(i).model_dump() for i in payload.items]
    facts_repo = FactsRepo(session)
    park = await facts_repo.get_park_by_slug(park_slug)
    if not park:
        raise HTTPException(status_code=404, detail="park not found")
    before = (await facts_repo.get_live_facts(park.id)).faq
    await facts_repo.replace_faq(park.id, items)
    await facts_repo.write_change_log(
        park_id=park.id,
        actor=actor,
        entity_table="faq",
        action="replace",
        before_json=before,
        after_json=items,
        reason=payload.reason,
    )
    await session.commit()
    return {"ok": True}


class KBSourceCreate(BaseModel):
    source_type: str = Field(pattern="^(url|pdf|file_path)$")
    source_url: str | None = None
    file_path: str | None = None
    title: str | None = None
    enabled: bool = True
    expires_at: datetime | None = None


class KBSourcePatch(BaseModel):
    enabled: bool | None = None
    expires_at: datetime | None = None
    title: str | None = None
    source_url: str | None = None
    file_path: str | None = None


@router.get("/parks/{park_slug}/kb/sources")
async def kb_list_sources(
    park_slug: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    facts_repo = FactsRepo(session)
    park = await facts_repo.get_park_by_slug(park_slug)
    if not park:
        raise HTTPException(status_code=404, detail="park not found")
    sources = await KBSourcesRepo(session).list_all_sources(park.id)
    return {"sources": [s.__dict__ for s in sources]}


@router.post("/parks/{park_slug}/kb/sources", status_code=status.HTTP_201_CREATED)
async def kb_create_source(
    park_slug: str,
    payload: KBSourceCreate,
    actor: Annotated[str, Depends(get_admin_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    _validate_expires_at(payload.expires_at)
    facts_repo = FactsRepo(session)
    park = await facts_repo.get_park_by_slug(park_slug)
    if not park:
        raise HTTPException(status_code=404, detail="park not found")
    repo = KBSourcesRepo(session)
    source_id = await repo.ensure_source(
        park_id=park.id,
        source_type=payload.source_type,
        source_url=payload.source_url,
        file_path=payload.file_path,
        title=payload.title,
        enabled=payload.enabled,
        expires_at=payload.expires_at,
    )
    await facts_repo.write_change_log(
        park_id=park.id,
        actor=actor,
        entity_table="kb_sources",
        action="upsert",
        before_json=None,
        after_json={**payload.model_dump(), "id": str(source_id)},
        reason=None,
    )
    await session.commit()
    return {"id": source_id}


@router.patch("/parks/{park_slug}/kb/sources/{source_id}")
async def kb_patch_source(
    park_slug: str,
    source_id: UUID,
    payload: KBSourcePatch,
    actor: Annotated[str, Depends(get_admin_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    if payload.expires_at is not None:
        _validate_expires_at(payload.expires_at)
    facts_repo = FactsRepo(session)
    park = await facts_repo.get_park_by_slug(park_slug)
    if not park:
        raise HTTPException(status_code=404, detail="park not found")
    repo = KBSourcesRepo(session)
    src = await repo.get_source(source_id)
    if not src or src.park_id != park.id:
        raise HTTPException(status_code=404, detail="source not found")
    before = src.__dict__
    await repo.patch_source(
        source_id,
        enabled=payload.enabled,
        expires_at=payload.expires_at,
        title=payload.title,
        source_url=payload.source_url,
        file_path=payload.file_path,
    )
    after = (await repo.get_source(source_id)).__dict__
    await facts_repo.write_change_log(
        park_id=park.id,
        actor=actor,
        entity_table="kb_sources",
        action="patch",
        before_json=before,
        after_json=after,
        reason=None,
    )
    await session.commit()
    return {"ok": True}


class KBReindexRequest(BaseModel):
    reason: str | None = None


@router.post("/parks/{park_slug}/kb/reindex")
async def kb_reindex(
    park_slug: str,
    background: BackgroundTasks,
    actor: Annotated[str, Depends(get_admin_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
    payload: KBReindexRequest | None = None,
) -> dict:
    facts_repo = FactsRepo(session)
    park = await facts_repo.get_park_by_slug(park_slug)
    if not park:
        raise HTTPException(status_code=404, detail="park not found")

    jobs_repo = KBJobsRepo(session)
    running = await jobs_repo.get_running_job_id(park.id)
    if running:
        raise HTTPException(status_code=409, detail=f"kb_index_job is already running: {running}")

    payload = payload or KBReindexRequest()
    sources = await KBSourcesRepo(session).list_enabled_sources(park.id)
    try:
        job_id = await jobs_repo.create_job(
            park_id=park.id,
            triggered_by=actor,
            reason=payload.reason,
            sources_json=[
                {
                    "id": str(s.id),
                    "source_type": s.source_type,
                    "source_url": s.source_url,
                    "file_path": s.file_path,
                    "title": s.title,
                }
                for s in sources
            ],
        )
    except KBJobAlreadyActiveError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    await session.commit()

    from app.db import SessionLocal

    async def run_in_bg() -> None:
        async with SessionLocal() as s:
            facts = FactsRepo(s)
            p = await facts.get_park_by_slug(park_slug)
            if not p:
                return
            await KBIndexer(s).run_reindex(
                park_id=p.id,
                park_slug=p.slug,
                triggered_by=actor,
                reason=payload.reason,
                existing_job_id=job_id,
                enable_auto_activate=True,
            )
            await s.commit()

    def schedule() -> None:
        import asyncio

        asyncio.create_task(run_in_bg())

    background.add_task(schedule)
    return {"ok": True, "job_id": job_id}


@router.get("/parks/{park_slug}/kb/jobs")
async def kb_jobs(
    park_slug: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    facts_repo = FactsRepo(session)
    park = await facts_repo.get_park_by_slug(park_slug)
    if not park:
        raise HTTPException(status_code=404, detail="park not found")
    jobs = await KBJobsRepo(session).list_jobs(park.id, limit=20)
    return {"jobs": jobs}


class ActivateIndexRequest(BaseModel):
    kb_index_id: UUID | None = None
    index_id: UUID | None = None


@router.post("/parks/{park_slug}/kb/index/activate")
async def kb_activate_index(
    park_slug: str,
    payload: ActivateIndexRequest,
    actor: Annotated[str, Depends(get_admin_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    facts_repo = FactsRepo(session)
    park = await facts_repo.get_park_by_slug(park_slug)
    if not park:
        raise HTTPException(status_code=404, detail="park not found")
    idx = payload.kb_index_id or payload.index_id
    if not idx:
        raise HTTPException(status_code=422, detail="kb_index_id is required")
    await KBIndexesRepo(session).activate_index(park_id=park.id, index_id=idx)
    await facts_repo.write_change_log(
        park_id=park.id,
        actor=actor,
        entity_table="kb_indexes",
        action="activate",
        before_json=None,
        after_json={"kb_index_id": str(idx)},
        reason=None,
    )
    await session.commit()
    return {"ok": True}
