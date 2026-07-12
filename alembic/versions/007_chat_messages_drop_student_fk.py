"""Allow anonymous chat sessions without students FK.

Revision ID: 007_chat_messages_drop_student_fk
Revises: 006_video_rag_uuid_defaults
Create Date: 2026-07-12
"""

from typing import Sequence, Union

from alembic import op

revision: str = "007_chat_no_fk"
down_revision: Union[str, Sequence[str], None] = "006_video_rag_uuid_defaults"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "chat_messages_student_id_fkey",
        "chat_messages",
        type_="foreignkey",
    )


def downgrade() -> None:
    op.create_foreign_key(
        "chat_messages_student_id_fkey",
        "chat_messages",
        "students",
        ["student_id"],
        ["id"],
        ondelete="SET NULL",
    )
