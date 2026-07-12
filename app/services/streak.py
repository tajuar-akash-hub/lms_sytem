from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DailyActivityLog, Module, Student, StudentModuleProgress


async def check_streaks(session: AsyncSession, check_time: datetime | None = None) -> int:
    """
    Run at 10 PM daily. If a student hasn't completed their current module
    within 24 hours, mark streak as broken unless a freeze point is available.
    """
    now = check_time or datetime.now(timezone.utc)
    today = now.date()
    updated_count = 0

    students_result = await session.execute(
        select(Student).where(Student.current_module_id.is_not(None))
    )
    students = students_result.scalars().all()

    for student in students:
        progress_result = await session.execute(
            select(StudentModuleProgress)
            .where(
                StudentModuleProgress.student_id == student.id,
                StudentModuleProgress.module_id == student.current_module_id,
                StudentModuleProgress.is_completed.is_(True),
            )
            .order_by(StudentModuleProgress.completed_at.desc())
            .limit(1)
        )
        latest_completion = progress_result.scalar_one_or_none()

        module_result = await session.execute(
            select(Module).where(Module.id == student.current_module_id)
        )
        module = module_result.scalar_one_or_none()
        if module is None:
            continue

        deadline = module.release_time or student.created_at
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)

        completed_in_window = (
            latest_completion is not None
            and latest_completion.completed_at is not None
            and latest_completion.completed_at >= deadline
            and latest_completion.completed_at <= deadline + timedelta(hours=24)
        )

        log_result = await session.execute(
            select(DailyActivityLog).where(
                DailyActivityLog.student_id == student.id,
                DailyActivityLog.date == today,
            )
        )
        log = log_result.scalar_one_or_none()

        if log is None:
            log = DailyActivityLog(
                student_id=student.id,
                date=today,
                modules_watched=0,
                quizzes_passed=0,
                assignments_submitted=0,
                revision_minutes=0,
                contribution_score=0,
                is_streak_maintained=completed_in_window,
                used_freeze_point=False,
            )
            session.add(log)
        else:
            log.is_streak_maintained = completed_in_window

        if not completed_in_window:
            if student.streak_freeze_points > 0:
                student.streak_freeze_points -= 1
                log.used_freeze_point = True
                log.is_streak_maintained = True
            else:
                log.is_streak_maintained = False

        updated_count += 1

    await session.commit()
    return updated_count
