"""add task_meta for fixed/flexible task categorisation

Revision ID: b5b5c0d2ebb8
Revises: 174f284a6f82
Create Date: 2025-08-16 00:00:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b5b5c0d2ebb8"
down_revision: Union[str, Sequence[str], None] = "174f284a6f82"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "task_meta",
        sa.Column("task_id", sa.String(), primary_key=True),
        sa.Column("task_type", sa.String(length=20), server_default="flexible"),
        sa.Column("deadline_type", sa.String(length=50)),
        sa.Column("fixed_date", sa.DateTime()),
        sa.Column("calendar_blocked", sa.Boolean(), server_default=sa.text("0")),
        sa.Column("recurrence_pattern", sa.String(length=50)),
        sa.Column("client_code", sa.String(length=20)),
    )


def downgrade() -> None:
    op.drop_table("task_meta")
