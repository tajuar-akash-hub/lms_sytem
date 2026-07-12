"""Initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-07-12
"""

from typing import Sequence, Union

import pgvector.sqlalchemy
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    league_tier = postgresql.ENUM(
        "IRON",
        "BRONZE",
        "SILVER",
        "GOLD",
        "PLATINUM",
        "ASCENDANT",
        "IMMORTAL",
        "RADIANT",
        name="league_tier",
        create_type=False,
    )
    module_type = postgresql.ENUM(
        "REGULAR",
        "EXAM",
        "CONCEPTUAL",
        "GROWTH_DAY",
        name="module_type",
        create_type=False,
    )
    pair_challenge_status = postgresql.ENUM(
        "PENDING",
        "ACCEPTED",
        "REJECTED",
        "COMPLETED",
        "FAILED",
        name="pair_challenge_status",
        create_type=False,
    )
    learning_status = postgresql.ENUM(
        "WEAK",
        "IMPROVING",
        "RESOLVED",
        name="learning_status",
        create_type=False,
    )

    league_tier.create(op.get_bind(), checkfirst=True)
    module_type.create(op.get_bind(), checkfirst=True)
    pair_challenge_status.create(op.get_bind(), checkfirst=True)
    learning_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "modules",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", module_type, nullable=False),
        sa.Column("module_book", sa.Text(), nullable=True),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("vid_link", sa.String(length=255), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("release_time", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "students",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone_number", sa.String(length=20), nullable=True),
        sa.Column("points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pair_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "streak_freeze_points", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("current_module_id", sa.UUID(), nullable=True),
        sa.Column("job_profile", sa.Text(), nullable=True),
        sa.Column("life_goal", sa.Text(), nullable=True),
        sa.Column("soul", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "current_league",
            league_tier,
            nullable=False,
            server_default="IRON",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["current_module_id"], ["modules.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_students_email", "students", ["email"], unique=False)

    op.create_table(
        "student_module_progress",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("module_id", sa.UUID(), nullable=False),
        sa.Column("watch_time_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quiz_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["module_id"], ["modules.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "ai_interviews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("points_spent", sa.Integer(), nullable=False),
        sa.Column("technical_score", sa.Integer(), nullable=True),
        sa.Column("behavioral_score", sa.Integer(), nullable=True),
        sa.Column("strengths", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("weaknesses", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("improvement_suggestions", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "learning_assessments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("topic_name", sa.String(length=255), nullable=False),
        sa.Column("score_percentage", sa.Float(), nullable=False),
        sa.Column("status", learning_status, nullable=False),
        sa.Column("reassessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "learning_recommendations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("assessment_id", sa.UUID(), nullable=False),
        sa.Column("recommended_content_link", sa.String(length=255), nullable=False),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default="false"),
        sa.ForeignKeyConstraint(["assessment_id"], ["learning_assessments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "daily_activity_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("watch_time_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quiz_score", sa.Integer(), nullable=True),
        sa.Column("heatmap_percentage", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "is_streak_maintained", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "used_freeze_point", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "student_id", "date", name="uq_daily_activity_student_date"
        ),
    )

    op.create_table(
        "pair_challenges",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("student_1_id", sa.UUID(), nullable=False),
        sa.Column("student_2_id", sa.UUID(), nullable=False),
        sa.Column("target_module_id", sa.UUID(), nullable=False),
        sa.Column("status", pair_challenge_status, nullable=False),
        sa.Column("s1_accepted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("s2_accepted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("s1_completed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("s2_completed", sa.Boolean(), nullable=False, server_default="false"),
        sa.ForeignKeyConstraint(["student_1_id"], ["students.id"]),
        sa.ForeignKeyConstraint(["student_2_id"], ["students.id"]),
        sa.ForeignKeyConstraint(["target_module_id"], ["modules.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "league_seasons",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("season_number", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "league_groups",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("season_id", sa.UUID(), nullable=False),
        sa.Column("week_number", sa.Integer(), nullable=False),
        sa.Column("tier", league_tier, nullable=False),
        sa.ForeignKeyConstraint(["season_id"], ["league_seasons.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "league_participants",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("group_id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("tournament_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rank_in_group", sa.Integer(), nullable=True),
        sa.Column("promotion_status", sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["league_groups.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "marketing_suggestions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("ai_generated_content", sa.Text(), nullable=False),
        sa.Column("target_audience", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "phitron_book",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("module_id", sa.UUID(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("module_summary", sa.Text(), nullable=True),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(1536), nullable=True),
        sa.ForeignKeyConstraint(["module_id"], ["modules.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("module_id"),
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_phitron_book_embedding_hnsw "
        "ON phitron_book USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_phitron_book_embedding_hnsw", table_name="phitron_book")
    op.drop_table("phitron_book")
    op.drop_table("marketing_suggestions")
    op.drop_table("league_participants")
    op.drop_table("league_groups")
    op.drop_table("league_seasons")
    op.drop_table("pair_challenges")
    op.drop_table("daily_activity_logs")
    op.drop_table("learning_recommendations")
    op.drop_table("learning_assessments")
    op.drop_table("ai_interviews")
    op.drop_table("student_module_progress")
    op.drop_index("ix_students_email", table_name="students")
    op.drop_table("students")
    op.drop_table("modules")

    op.execute("DROP TYPE IF EXISTS learning_status")
    op.execute("DROP TYPE IF EXISTS pair_challenge_status")
    op.execute("DROP TYPE IF EXISTS module_type")
    op.execute("DROP TYPE IF EXISTS league_tier")
