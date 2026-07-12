"""GitHub-style daily activity logs.

Revision ID: 004_github_activity_logs
Revises: 003_sync_database_md
Create Date: 2026-07-12
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004_github_activity_logs"
down_revision: Union[str, Sequence[str], None] = "003_sync_database_md"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "daily_activity_logs",
        sa.Column("modules_watched", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "daily_activity_logs",
        sa.Column("quizzes_passed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "daily_activity_logs",
        sa.Column(
            "assignments_submitted", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "daily_activity_logs",
        sa.Column("revision_minutes", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "daily_activity_logs",
        sa.Column("contribution_score", sa.Integer(), nullable=False, server_default="0"),
    )

    op.drop_column("daily_activity_logs", "heatmap_percentage")
    op.drop_column("daily_activity_logs", "watch_time_minutes")


def downgrade() -> None:
    op.add_column(
        "daily_activity_logs",
        sa.Column("watch_time_minutes", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "daily_activity_logs",
        sa.Column("heatmap_percentage", sa.Float(), nullable=False, server_default="0"),
    )

    op.drop_column("daily_activity_logs", "contribution_score")
    op.drop_column("daily_activity_logs", "revision_minutes")
    op.drop_column("daily_activity_logs", "assignments_submitted")
    op.drop_column("daily_activity_logs", "quizzes_passed")
    op.drop_column("daily_activity_logs", "modules_watched")
