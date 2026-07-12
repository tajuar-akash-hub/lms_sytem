from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import (
    ExamType,
    LeagueTier,
    LearningStatus,
    ModuleType,
    PairChallengeStatus,
)


class ORMBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Students ---


class StudentBase(BaseModel):
    name: str
    email: EmailStr
    phone_number: str | None = None
    job_profile: str | None = None
    life_goal: str | None = None
    soul: dict[str, Any] | None = None
    current_module_id: UUID | None = None


class StudentCreate(StudentBase):
    pass


class StudentUpdate(BaseModel):
    name: str | None = None
    phone_number: str | None = None
    job_profile: str | None = None
    life_goal: str | None = None
    soul: dict[str, Any] | None = None
    current_module_id: UUID | None = None
    points: int | None = None
    pair_points: int | None = None
    streak_freeze_points: int | None = None
    current_league: LeagueTier | None = None


class StudentRead(StudentBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    supabase_user_id: UUID | None = None
    points: int
    pair_points: int
    streak_freeze_points: int
    current_league: LeagueTier
    created_at: datetime


# --- Auth ---


class AuthSignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=8)
    phone_number: str | None = None


class AuthLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class AuthRefreshRequest(BaseModel):
    refresh_token: str


class AuthTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int | None = None
    student: StudentRead


class AuthMessageResponse(BaseModel):
    message: str


# --- Modules ---


class ModuleBase(BaseModel):
    name: str
    type: ModuleType
    module_book: str | None = None
    ai_summary: str | None = None
    vid_link: str | None = None
    duration_minutes: int | None = None
    release_time: datetime | None = None


class ModuleCreate(ModuleBase):
    pass


class ModuleRead(ModuleBase):
    id: UUID


# --- Progress ---


class StudentModuleProgressBase(BaseModel):
    student_id: UUID
    module_id: UUID
    watch_time_minutes: int = 0
    quiz_score: float = 0.0
    is_completed: bool = False


class StudentModuleProgressCreate(StudentModuleProgressBase):
    pass


class StudentModuleProgressRead(StudentModuleProgressBase):
    id: UUID
    completed_at: datetime | None = None


# --- Exams ---


class ExamBase(BaseModel):
    name: str
    type: ExamType
    total_marks: float
    module_id: UUID | None = None


class ExamCreate(ExamBase):
    pass


class ExamRead(ExamBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime


class StudentExamResultBase(BaseModel):
    student_id: UUID
    exam_id: UUID
    marks_obtained: float


class StudentExamResultCreate(StudentExamResultBase):
    pass


class StudentExamResultRead(StudentExamResultBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    submitted_at: datetime


# --- AI Interviews ---


class AIInterviewCreate(BaseModel):
    student_id: UUID
    points_spent: int
    technical_score: float | None = None
    behavioral_score: float | None = None
    strengths: list[str] | None = None
    weaknesses: list[str] | None = None
    improvement_suggestions: str | None = None


class AIInterviewRead(AIInterviewCreate):
    id: UUID
    created_at: datetime


# --- Learning Path ---


class LearningAssessmentCreate(BaseModel):
    student_id: UUID
    topic_name: str
    score_percentage: float
    status: LearningStatus


class LearningAssessmentRead(LearningAssessmentCreate):
    id: UUID
    reassessed_at: datetime | None = None


class LearningRecommendationCreate(BaseModel):
    assessment_id: UUID
    recommended_content_link: str
    is_completed: bool = False


class LearningRecommendationRead(LearningRecommendationCreate):
    id: UUID


# --- Daily Activity ---


class DailyActivityLogCreate(BaseModel):
    student_id: UUID
    date: date
    modules_watched: int = 0
    quizzes_passed: int = 0
    assignments_submitted: int = 0
    revision_minutes: int = 0
    contribution_score: int = 0
    is_streak_maintained: bool = False
    used_freeze_point: bool = False


class DailyActivityLogRead(DailyActivityLogCreate):
    id: UUID


HeatmapColor = Literal["cry", "yellow", "light_green", "dark_green"]


class HeatmapResult(BaseModel):
    percentage: float
    color: HeatmapColor
    requirements_met: bool


# --- Pair Challenges ---


class PairChallengeCreate(BaseModel):
    date: date
    student_1_id: UUID
    student_2_id: UUID
    target_module_id: UUID
    status: PairChallengeStatus = PairChallengeStatus.PENDING


class PairChallengeRead(PairChallengeCreate):
    id: UUID
    s1_accepted: bool
    s2_accepted: bool
    s1_completed: bool
    s2_completed: bool


# --- League ---


class LeagueSeasonCreate(BaseModel):
    season_number: int
    start_date: date
    end_date: date


class LeagueSeasonRead(LeagueSeasonCreate):
    id: UUID


class LeagueGroupCreate(BaseModel):
    season_id: UUID
    week_number: int
    tier: LeagueTier


class LeagueGroupRead(LeagueGroupCreate):
    id: UUID


class LeagueParticipantCreate(BaseModel):
    group_id: UUID
    student_id: UUID
    tournament_points: int = 0
    rank_in_group: int | None = None
    promotion_status: str | None = None


class LeagueParticipantRead(LeagueParticipantCreate):
    id: UUID


# --- Marketing ---


class MarketingSuggestionCreate(BaseModel):
    topic: str
    ai_generated_content: str
    target_audience: str


class MarketingSuggestionRead(MarketingSuggestionCreate):
    id: UUID


# --- RAG ---


class PhitronBookCreate(BaseModel):
    module_id: UUID
    text: str
    module_summary: str | None = None
    embedding: list[float] | None = None


class PhitronBookRead(PhitronBookCreate):
    id: UUID
