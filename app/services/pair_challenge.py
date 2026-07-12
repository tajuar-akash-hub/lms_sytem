from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Module, PairChallenge, Student, StudentModuleProgress
from app.models.enums import PairChallengeStatus


def module_progress_ratio(student: Student, module_count: int) -> float:
    if module_count == 0:
        return 0.0
    if student.current_module_id is None:
        return 0.0
    return 1.0


async def _get_student_module_index(
    session: AsyncSession, student: Student
) -> int | None:
    if student.current_module_id is None:
        return None

    progress_result = await session.execute(
        select(StudentModuleProgress)
        .where(
            StudentModuleProgress.student_id == student.id,
            StudentModuleProgress.is_completed.is_(True),
        )
    )
    completed_count = len(progress_result.scalars().all())
    return completed_count


async def match_pair_challenges(
    session: AsyncSession, match_date: date | None = None
) -> list[PairChallenge]:
    """
    Run at 10:00 AM. Match active students where module progress differs by <= 20%.
    """
    today = match_date or datetime.now(timezone.utc).date()

    students_result = await session.execute(
        select(Student).where(Student.current_module_id.is_not(None))
    )
    students = list(students_result.scalars().all())

    modules_result = await session.execute(select(Module))
    total_modules = len(modules_result.scalars().all()) or 1

    indexed_students: list[tuple[Student, float]] = []
    for student in students:
        completed = await _get_student_module_index(session, student)
        if completed is None:
            continue
        ratio = completed / total_modules
        indexed_students.append((student, ratio))

    indexed_students.sort(key=lambda item: item[1])
    created: list[PairChallenge] = []
    used: set[UUID] = set()

    for i, (student_a, ratio_a) in enumerate(indexed_students):
        if student_a.id in used:
            continue

        for student_b, ratio_b in indexed_students[i + 1 :]:
            if student_b.id in used:
                continue

            if abs(ratio_a - ratio_b) <= 0.20:
                target_module_id = student_a.current_module_id or student_b.current_module_id
                if target_module_id is None:
                    continue

                challenge = PairChallenge(
                    date=today,
                    student_1_id=student_a.id,
                    student_2_id=student_b.id,
                    target_module_id=target_module_id,
                    status=PairChallengeStatus.PENDING,
                )
                session.add(challenge)
                created.append(challenge)
                used.add(student_a.id)
                used.add(student_b.id)
                break

    await session.commit()
    return created


async def rematch_unaccepted_challenges(
    session: AsyncSession, check_time: datetime | None = None
) -> list[PairChallenge]:
    """
    At 12:00 PM, re-run matching for students whose partner failed to accept.
    """
    now = check_time or datetime.now(timezone.utc)
    today = now.date()

    pending_result = await session.execute(
        select(PairChallenge).where(
            PairChallenge.date == today,
            PairChallenge.status == PairChallengeStatus.PENDING,
            or_(
                PairChallenge.s1_accepted.is_(True),
                PairChallenge.s2_accepted.is_(True),
            ),
        )
    )
    challenges = pending_result.scalars().all()
    rematched: list[PairChallenge] = []

    for challenge in challenges:
        accepted_id = None
        waiting_id = None

        if challenge.s1_accepted and not challenge.s2_accepted:
            accepted_id = challenge.student_1_id
            waiting_id = challenge.student_2_id
        elif challenge.s2_accepted and not challenge.s1_accepted:
            accepted_id = challenge.student_2_id
            waiting_id = challenge.student_1_id

        if accepted_id is None or waiting_id is None:
            continue

        challenge.status = PairChallengeStatus.FAILED
        active_student_result = await session.execute(
            select(Student).where(Student.id == accepted_id)
        )
        active_student = active_student_result.scalar_one()

        if active_student.current_module_id is None:
            continue

        candidates_result = await session.execute(
            select(Student).where(
                Student.current_module_id.is_not(None),
                Student.id != accepted_id,
                Student.id != waiting_id,
            )
        )
        candidates = candidates_result.scalars().all()

        for candidate in candidates:
            new_challenge = PairChallenge(
                date=today,
                student_1_id=active_student.id,
                student_2_id=candidate.id,
                target_module_id=active_student.current_module_id,
                status=PairChallengeStatus.PENDING,
            )
            session.add(new_challenge)
            rematched.append(new_challenge)
            break

    await session.commit()
    return rematched


async def penalize_consecutive_pair_misses(
    session: AsyncSession, student_id: UUID, lookback_days: int = 3
) -> bool:
    """
    Deduct pair_points to 0 if a student misses 3 days in a row.
    """
    today = datetime.now(timezone.utc).date()
    dates = [today.fromordinal(today.toordinal() - offset) for offset in range(lookback_days)]

    result = await session.execute(
        select(PairChallenge).where(
            PairChallenge.date.in_(dates),
            or_(
                PairChallenge.student_1_id == student_id,
                PairChallenge.student_2_id == student_id,
            ),
        )
    )
    challenges = result.scalars().all()

    missed_days = 0
    for day in dates:
        day_challenges = [c for c in challenges if c.date == day]
        if not day_challenges:
            missed_days += 1
            continue

        participated = any(
            c.status in {PairChallengeStatus.ACCEPTED, PairChallengeStatus.COMPLETED}
            for c in day_challenges
        )
        if not participated:
            missed_days += 1

    if missed_days >= lookback_days:
        student_result = await session.execute(
            select(Student).where(Student.id == student_id)
        )
        student = student_result.scalar_one()
        student.pair_points = 0
        await session.commit()
        return True

    return False
