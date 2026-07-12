from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Student
from app.models.enums import LeagueTier

LEAGUE_ORDER = list(LeagueTier)


def demote_league(tier: LeagueTier, steps: int = 2) -> LeagueTier:
    index = LEAGUE_ORDER.index(tier)
    new_index = max(0, index - steps)
    return LEAGUE_ORDER[new_index]


async def soft_reset_leagues(session: AsyncSession, steps: int = 2) -> int:
    """
    End-of-season soft reset: shift every student's league down by 2 tiers.
    Minimum floor is IRON.
    """
    result = await session.execute(select(Student))
    students = result.scalars().all()
    updated = 0

    for student in students:
        new_tier = demote_league(student.current_league, steps=steps)
        if new_tier != student.current_league:
            student.current_league = new_tier
            updated += 1

    await session.commit()
    return updated
