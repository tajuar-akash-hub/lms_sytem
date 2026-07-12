import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.database import Base
from app.models.enums import (
    ExamType,
    LeagueTier,
    LearningStatus,
    ModuleType,
    PairChallengeStatus,
)


class Module(Base):
    __tablename__ = "modules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[ModuleType] = mapped_column(
        Enum(ModuleType, name="module_type"), nullable=False
    )
    module_book: Mapped[str | None] = mapped_column(Text)
    ai_summary: Mapped[str | None] = mapped_column(Text)
    vid_link: Mapped[str | None] = mapped_column(String(255))
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    release_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    students_current: Mapped[list["Student"]] = relationship(
        back_populates="current_module",
        foreign_keys="Student.current_module_id",
    )
    progress_records: Mapped[list["StudentModuleProgress"]] = relationship(
        back_populates="module"
    )
    pair_challenges: Mapped[list["PairChallenge"]] = relationship(
        back_populates="target_module"
    )
    phitron_book: Mapped["PhitronBook | None"] = relationship(
        back_populates="module", uselist=False
    )
    exams: Mapped[list["Exam"]] = relationship(back_populates="module")
    videos: Mapped[list["Video"]] = relationship(back_populates="module")


class Student(Base):
    __tablename__ = "students"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    supabase_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    phone_number: Mapped[str | None] = mapped_column(String(20))
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pair_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    streak_freeze_points: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    current_module_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("modules.id"), nullable=True
    )
    job_profile: Mapped[str | None] = mapped_column(Text)
    life_goal: Mapped[str | None] = mapped_column(Text)
    soul: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    current_league: Mapped[LeagueTier] = mapped_column(
        Enum(LeagueTier, name="league_tier"),
        default=LeagueTier.IRON,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    current_module: Mapped[Module | None] = relationship(
        back_populates="students_current",
        foreign_keys=[current_module_id],
    )
    module_progress: Mapped[list["StudentModuleProgress"]] = relationship(
        back_populates="student"
    )
    ai_interviews: Mapped[list["AIInterview"]] = relationship(back_populates="student")
    learning_assessments: Mapped[list["LearningAssessment"]] = relationship(
        back_populates="student"
    )
    daily_activity_logs: Mapped[list["DailyActivityLog"]] = relationship(
        back_populates="student"
    )
    pair_challenges_as_s1: Mapped[list["PairChallenge"]] = relationship(
        back_populates="student_1",
        foreign_keys="PairChallenge.student_1_id",
    )
    pair_challenges_as_s2: Mapped[list["PairChallenge"]] = relationship(
        back_populates="student_2",
        foreign_keys="PairChallenge.student_2_id",
    )
    league_participations: Mapped[list["LeagueParticipant"]] = relationship(
        back_populates="student"
    )
    exam_results: Mapped[list["StudentExamResult"]] = relationship(
        back_populates="student"
    )

    __table_args__ = (Index("ix_students_email", "email"),)


class StudentModuleProgress(Base):
    __tablename__ = "student_module_progress"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id"), nullable=False
    )
    module_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("modules.id"), nullable=False
    )
    watch_time_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quiz_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    student: Mapped[Student] = relationship(back_populates="module_progress")
    module: Mapped[Module] = relationship(back_populates="progress_records")


class Exam(Base):
    __tablename__ = "exams"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    module_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("modules.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[ExamType] = mapped_column(
        Enum(ExamType, name="exam_type"), nullable=False
    )
    total_marks: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    module: Mapped[Module | None] = relationship(back_populates="exams")
    results: Mapped[list["StudentExamResult"]] = relationship(back_populates="exam")


class StudentExamResult(Base):
    __tablename__ = "student_exam_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id"), nullable=False
    )
    exam_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exams.id"), nullable=False
    )
    marks_obtained: Mapped[float] = mapped_column(Float, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    student: Mapped[Student] = relationship(back_populates="exam_results")
    exam: Mapped[Exam] = relationship(back_populates="results")

    __table_args__ = (
        UniqueConstraint("student_id", "exam_id", name="uq_student_exam_result"),
    )


class AIInterview(Base):
    __tablename__ = "ai_interviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id"), nullable=False
    )
    points_spent: Mapped[int] = mapped_column(Integer, nullable=False)
    technical_score: Mapped[float | None] = mapped_column(Float)
    behavioral_score: Mapped[float | None] = mapped_column(Float)
    strengths: Mapped[list[str] | None] = mapped_column(JSONB)
    weaknesses: Mapped[list[str] | None] = mapped_column(JSONB)
    improvement_suggestions: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    student: Mapped[Student] = relationship(back_populates="ai_interviews")


class LearningAssessment(Base):
    __tablename__ = "learning_assessments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id"), nullable=False
    )
    topic_name: Mapped[str] = mapped_column(String(255), nullable=False)
    score_percentage: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[LearningStatus] = mapped_column(
        Enum(LearningStatus, name="learning_status"), nullable=False
    )
    reassessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    student: Mapped[Student] = relationship(back_populates="learning_assessments")
    recommendations: Mapped[list["LearningRecommendation"]] = relationship(
        back_populates="assessment"
    )


class LearningRecommendation(Base):
    __tablename__ = "learning_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("learning_assessments.id"), nullable=False
    )
    recommended_content_link: Mapped[str] = mapped_column(String(255), nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    assessment: Mapped[LearningAssessment] = relationship(
        back_populates="recommendations"
    )


class DailyActivityLog(Base):
    __tablename__ = "daily_activity_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    modules_watched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quizzes_passed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    assignments_submitted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    revision_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    contribution_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_streak_maintained: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    used_freeze_point: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    student: Mapped[Student] = relationship(back_populates="daily_activity_logs")

    __table_args__ = (
        UniqueConstraint("student_id", "date", name="uq_daily_activity_student_date"),
    )


class PairChallenge(Base):
    __tablename__ = "pair_challenges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    student_1_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id"), nullable=False
    )
    student_2_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id"), nullable=False
    )
    target_module_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("modules.id"), nullable=False
    )
    status: Mapped[PairChallengeStatus] = mapped_column(
        Enum(PairChallengeStatus, name="pair_challenge_status"), nullable=False
    )
    s1_accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    s2_accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    s1_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    s2_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    student_1: Mapped[Student] = relationship(
        back_populates="pair_challenges_as_s1",
        foreign_keys=[student_1_id],
    )
    student_2: Mapped[Student] = relationship(
        back_populates="pair_challenges_as_s2",
        foreign_keys=[student_2_id],
    )
    target_module: Mapped[Module] = relationship(back_populates="pair_challenges")


class LeagueSeason(Base):
    __tablename__ = "league_seasons"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    season_number: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)

    groups: Mapped[list["LeagueGroup"]] = relationship(back_populates="season")


class LeagueGroup(Base):
    __tablename__ = "league_groups"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    season_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("league_seasons.id"), nullable=False
    )
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    tier: Mapped[LeagueTier] = mapped_column(
        Enum(LeagueTier, name="league_tier", create_type=False), nullable=False
    )

    season: Mapped[LeagueSeason] = relationship(back_populates="groups")
    participants: Mapped[list["LeagueParticipant"]] = relationship(
        back_populates="group"
    )


class LeagueParticipant(Base):
    __tablename__ = "league_participants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("league_groups.id"), nullable=False
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id"), nullable=False
    )
    tournament_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rank_in_group: Mapped[int | None] = mapped_column(Integer)
    promotion_status: Mapped[str | None] = mapped_column(String(50))

    group: Mapped[LeagueGroup] = relationship(back_populates="participants")
    student: Mapped[Student] = relationship(back_populates="league_participations")


class MarketingSuggestion(Base):
    __tablename__ = "marketing_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    ai_generated_content: Mapped[str] = mapped_column(Text, nullable=False)
    target_audience: Mapped[str] = mapped_column(String(255), nullable=False)


class PhitronBook(Base):
    __tablename__ = "phitron_book"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    module_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("modules.id"), unique=True, nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    module_summary: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))

    module: Mapped[Module] = relationship(back_populates="phitron_book")


from app.models.videos import ChatMessage, TranscriptChunk, Video, VideoSummary
