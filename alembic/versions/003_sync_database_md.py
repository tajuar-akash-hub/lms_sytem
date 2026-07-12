"""Sync schema to updated Database.md.

Revision ID: 003_sync_database_md
Revises: 002_supabase_user_id
Create Date: 2026-07-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "003_sync_database_md"
down_revision: Union[str, Sequence[str], None] = "002_supabase_user_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    exam_type = postgresql.ENUM(
        "MCQ",
        "CODING",
        "WRITTEN",
        "MIXED",
        name="exam_type",
    )
    exam_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "exams",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("module_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "type",
            postgresql.ENUM(
                "MCQ",
                "CODING",
                "WRITTEN",
                "MIXED",
                name="exam_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("total_marks", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["module_id"], ["modules.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "student_exam_results",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("exam_id", sa.UUID(), nullable=False),
        sa.Column("marks_obtained", sa.Float(), nullable=False),
        sa.Column(
            "submitted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["exam_id"], ["exams.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "exam_id", name="uq_student_exam_result"),
    )

    op.alter_column(
        "student_module_progress",
        "quiz_score",
        existing_type=sa.Integer(),
        type_=sa.Float(),
        existing_nullable=False,
        server_default="0",
        postgresql_using="quiz_score::double precision",
    )
    op.alter_column(
        "student_module_progress",
        "quiz_score",
        server_default="0.0",
    )

    op.alter_column(
        "ai_interviews",
        "technical_score",
        existing_type=sa.Integer(),
        type_=sa.Float(),
        existing_nullable=True,
        postgresql_using="technical_score::double precision",
    )
    op.alter_column(
        "ai_interviews",
        "behavioral_score",
        existing_type=sa.Integer(),
        type_=sa.Float(),
        existing_nullable=True,
        postgresql_using="behavioral_score::double precision",
    )

    op.drop_column("daily_activity_logs", "quiz_score")
    op.drop_column("marketing_suggestions", "created_at")


def downgrade() -> None:
    op.add_column(
        "marketing_suggestions",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "daily_activity_logs",
        sa.Column("quiz_score", sa.Integer(), nullable=True),
    )

    op.alter_column(
        "ai_interviews",
        "behavioral_score",
        existing_type=sa.Float(),
        type_=sa.Integer(),
        existing_nullable=True,
        postgresql_using="behavioral_score::integer",
    )
    op.alter_column(
        "ai_interviews",
        "technical_score",
        existing_type=sa.Float(),
        type_=sa.Integer(),
        existing_nullable=True,
        postgresql_using="technical_score::integer",
    )

    op.alter_column(
        "student_module_progress",
        "quiz_score",
        existing_type=sa.Float(),
        type_=sa.Integer(),
        existing_nullable=False,
        server_default="0",
        postgresql_using="quiz_score::integer",
    )

    op.drop_table("student_exam_results")
    op.drop_table("exams")
    op.execute("DROP TYPE IF EXISTS exam_type")
