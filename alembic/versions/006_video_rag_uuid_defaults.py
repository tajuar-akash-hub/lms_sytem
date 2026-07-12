"""Add UUID defaults to video RAG tables.

Revision ID: 006_video_rag_uuid_defaults
Revises: 005_video_rag_tables
Create Date: 2026-07-12
"""

from typing import Sequence, Union

from alembic import op

revision: str = "006_video_rag_uuid_defaults"
down_revision: Union[str, Sequence[str], None] = "005_video_rag_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for table in (
        "videos",
        "transcript_chunks",
        "video_summaries",
        "chat_messages",
    ):
        op.execute(
            f"ALTER TABLE {table} "
            f"ALTER COLUMN id SET DEFAULT gen_random_uuid();"
        )


def downgrade() -> None:
    for table in (
        "videos",
        "transcript_chunks",
        "video_summaries",
        "chat_messages",
    ):
        op.execute(f"ALTER TABLE {table} ALTER COLUMN id DROP DEFAULT;")
