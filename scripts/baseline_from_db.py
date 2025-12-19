from __future__ import annotations

import os
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres",
)


@dataclass(frozen=True)
class Baseline:
    total: int
    fallback: int
    fallback_rate: float
    top_questions: list[tuple[str, int]]


async def compute_baseline(limit: int = 10) -> Baseline:
    engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async with SessionLocal() as session:  # type: AsyncSession
        total = await _scalar(
            session,
            """
            SELECT COUNT(*)::int
            FROM event_log
            WHERE event_name = 'intent_routed'
            """,
        )
        fallback = await _scalar(
            session,
            """
            SELECT COUNT(*)::int
            FROM event_log
            WHERE event_name = 'intent_routed'
              AND payload->>'intent' = 'fallback'
            """,
        )
        rows = await session.execute(
            text(
                """
                SELECT payload->>'message' AS msg, COUNT(*)::int AS cnt
                FROM event_log
                WHERE event_name = 'message_received'
                GROUP BY payload->>'message'
                ORDER BY COUNT(*) DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
        top = [(r[0], r[1]) for r in rows.all() if r[0]]

    await engine.dispose()
    rate = (fallback / total) if total else 0.0
    return Baseline(total=total, fallback=fallback, fallback_rate=rate, top_questions=top)


async def _scalar(session: AsyncSession, sql: str) -> int:
    res = await session.execute(text(sql))
    val = res.scalar_one()
    return int(val)


async def main() -> int:
    b = await compute_baseline()
    print(f"total={b.total} fallback={b.fallback} fallback_rate={b.fallback_rate:.2%}")
    print("top_questions:")
    for msg, cnt in b.top_questions:
        print(f"- {cnt}x: {msg}")
    return 0


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(main()))
