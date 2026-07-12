"""Add Supabase user id to students.

Revision ID: 002_supabase_user_id
Revises: 001_initial
Create Date: 2026-07-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_supabase_user_id"
down_revision: Union[str, Sequence[str], None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "students",
        sa.Column("supabase_user_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        "ix_students_supabase_user_id",
        "students",
        ["supabase_user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_students_supabase_user_id", table_name="students")
    op.drop_column("students", "supabase_user_id")
