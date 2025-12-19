from __future__ import annotations

import pytest
from sqlalchemy import text

from app.repos.facts_repo import FactsRepo
from app.services.governance_service import GovernanceService


@pytest.mark.asyncio
async def test_publish_then_snapshot_overrides_live_then_rollback(db_session, test_park) -> None:
    facts = FactsRepo(db_session)
    gov = GovernanceService(db_session)
    park_id = test_park["id"]

    await facts.replace_contacts(
        park_id,
        [
            {"type": "phone", "value": "+7 (999) 000-00-11", "is_primary": True},
        ],
    )
    await db_session.commit()

    v1 = await gov.publish_snapshot(park_id=park_id, actor="alice", notes="v1")
    await db_session.commit()

    await facts.replace_contacts(
        park_id,
        [
            {"type": "phone", "value": "+7 (999) 000-00-22", "is_primary": True},
        ],
    )
    await db_session.commit()

    snap1 = await facts.get_facts(park_id)
    assert snap1.primary_phone == "+7 (999) 000-00-11"

    v2 = await gov.publish_snapshot(park_id=park_id, actor="bob", notes="v2")
    await db_session.commit()
    assert v2 != v1

    snap2 = await facts.get_facts(park_id)
    assert snap2.primary_phone == "+7 (999) 000-00-22"

    rb = await gov.rollback_snapshot(park_id=park_id, actor="bob", reason="oops")
    await db_session.commit()
    assert rb == v1

    snap3 = await facts.get_facts(park_id)
    assert snap3.primary_phone == "+7 (999) 000-00-11"

    rows = await db_session.execute(
        text("SELECT published_by FROM facts_versions WHERE id=:id"),
        {"id": v1},
    )
    assert rows.scalar_one() == "alice"


@pytest.mark.asyncio
async def test_rollback_with_single_version_returns_error(db_session, test_park) -> None:
    facts = FactsRepo(db_session)
    gov = GovernanceService(db_session)
    park_id = test_park["id"]

    await facts.replace_contacts(
        park_id,
        [{"type": "phone", "value": "+7 (999) 000-00-33", "is_primary": True}],
    )
    await db_session.commit()

    await gov.publish_snapshot(park_id=park_id, actor="alice", notes="only")
    await db_session.commit()

    with pytest.raises(ValueError) as e:
        await gov.rollback_snapshot(park_id=park_id, actor="alice", reason="nope")
    assert "No previous published version" in str(e.value)

