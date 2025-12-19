from __future__ import annotations

import pytest

from app.repos.kb_jobs_repo import KBJobAlreadyActiveError, KBJobsRepo


@pytest.mark.asyncio
async def test_reindex_db_lock_prevents_second_job(db_session, test_park) -> None:
    repo = KBJobsRepo(db_session)

    job1 = await repo.create_job(park_id=test_park["id"], triggered_by="t", reason="t", sources_json=[])
    await db_session.commit()

    with pytest.raises(KBJobAlreadyActiveError):
        await repo.create_job(park_id=test_park["id"], triggered_by="t", reason="t", sources_json=[])

    await db_session.rollback()

    await repo.set_job_failed(job1, error_text="done")
    await db_session.commit()

    job2 = await repo.create_job(park_id=test_park["id"], triggered_by="t", reason="t", sources_json=[])
    await db_session.commit()
    assert job2

