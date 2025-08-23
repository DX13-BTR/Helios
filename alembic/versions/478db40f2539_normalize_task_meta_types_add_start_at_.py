# revision identifiers, used by Alembic.
revision = "task_meta_normalize_001"
down_revision = "<PUT_PREV_REVISION_ID_HERE>"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

def upgrade():
    # Convert fixed_date TEXT -> TIMESTAMP
    op.alter_column(
        "task_meta",
        "fixed_date",
        type_=sa.DateTime(),
        postgresql_using='"fixed_date"::timestamp',
        existing_type=sa.TEXT(),
        existing_nullable=True,
    )

    # Convert calendar_blocked INTEGER -> BOOLEAN
    op.alter_column(
        "task_meta",
        "calendar_blocked",
        type_=sa.Boolean(),
        postgresql_using='"calendar_blocked" <> 0',
        existing_type=sa.INTEGER(),
        existing_nullable=True,
        server_default=sa.text("false"),
    )
    # Ensure default is boolean false
    op.execute('ALTER TABLE task_meta ALTER COLUMN calendar_blocked SET DEFAULT false')

    # task_type default is already 'flexible' (text); keep it

    # Add new columns used by email ingestion / scheduling
    with op.batch_alter_table("task_meta") as b:
        b.add_column(sa.Column("start_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("due_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("source", sa.String(length=32), nullable=True))


def downgrade():
    # Drop new columns
    with op.batch_alter_table("task_meta") as b:
        b.drop_column("source")
        b.drop_column("due_at")
        b.drop_column("start_at")

    # Revert calendar_blocked BOOLEAN -> INTEGER (true->1, false->0)
    op.alter_column(
        "task_meta",
        "calendar_blocked",
        type_=sa.Integer(),
        postgresql_using="CASE WHEN calendar_blocked THEN 1 ELSE 0 END",
        existing_type=sa.Boolean(),
        existing_nullable=True,
        server_default=sa.text("0"),
    )
    op.execute('ALTER TABLE task_meta ALTER COLUMN calendar_blocked SET DEFAULT 0')

    # Revert fixed_date TIMESTAMP -> TEXT
    op.alter_column(
        "task_meta",
        "fixed_date",
        type_=sa.Text(),
        postgresql_using="fixed_date::text",
        existing_type=sa.DateTime(),
        existing_nullable=True,
    )
"""Normalize task_meta types + add start_at/due_at/source

Revision ID: 478db40f2539
Revises: 740d17209405
Create Date: 2025-08-21 17:45:01.348715

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '478db40f2539'
down_revision: Union[str, Sequence[str], None] = '740d17209405'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
