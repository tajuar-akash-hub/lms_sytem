import asyncio

from app.database import AsyncSessionLocal
from app.services.league import soft_reset_leagues
from app.services.pair_challenge import (
    match_pair_challenges,
    rematch_unaccepted_challenges,
)
from app.services.streak import check_streaks
from app.tasks.celery_app import celery_app


def _run_async(coro):
    return asyncio.run(coro)


@celery_app.task(name="app.tasks.background.run_streak_check")
def run_streak_check() -> int:
    async def _inner() -> int:
        async with AsyncSessionLocal() as session:
            return await check_streaks(session)

    return _run_async(_inner())


@celery_app.task(name="app.tasks.background.run_pair_challenge_matching")
def run_pair_challenge_matching() -> int:
    async def _inner() -> int:
        async with AsyncSessionLocal() as session:
            created = await match_pair_challenges(session)
            return len(created)

    return _run_async(_inner())


@celery_app.task(name="app.tasks.background.run_pair_challenge_rematch")
def run_pair_challenge_rematch() -> int:
    async def _inner() -> int:
        async with AsyncSessionLocal() as session:
            rematched = await rematch_unaccepted_challenges(session)
            return len(rematched)

    return _run_async(_inner())


@celery_app.task(name="app.tasks.background.run_league_soft_reset")
def run_league_soft_reset() -> int:
    async def _inner() -> int:
        async with AsyncSessionLocal() as session:
            return await soft_reset_leagues(session)

    return _run_async(_inner())
