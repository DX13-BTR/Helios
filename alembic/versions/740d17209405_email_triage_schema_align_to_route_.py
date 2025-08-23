# revision identifiers, used by Alembic.
revision = "email_triage_alignment_001"
down_revision = "<PUT_PREV_REVISION_ID_HERE>"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

def upgrade():
    # --- email_tasks additions ---
    with op.batch_alter_table("email_tasks") as b:
        b.add_column(sa.Column("gmail_link", sa.String(), nullable=True))
        b.add_column(sa.Column("thread_id", sa.String(), nullable=True))
        b.add_column(sa.Column("received_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("source_label", sa.String(), nullable=True))
        b.add_column(sa.Column("priority", sa.String(length=16), nullable=True))
        b.add_column(sa.Column("client_key_hint", sa.String(), nullable=True))
        b.create_index("ix_email_tasks_sender", ["sender"], unique=False)
        b.create_index("ix_email_tasks_thread_id", ["thread_id"], unique=False)
        b.create_index("ix_email_tasks_received_at", ["received_at"], unique=False)

    # --- processed_emails additions ---
    with op.batch_alter_table("processed_emails") as b:
        b.add_column(sa.Column("helios_task_id", sa.String(), nullable=True))
        b.add_column(sa.Column("status", sa.String(length=32), nullable=True))
        b.add_column(sa.Column("received_at", sa.DateTime(), nullable=True))
        b.create_index("ix_processed_emails_helios_task_id", ["helios_task_id"], unique=False)

    # --- task_meta additions matching route usage ---
    with op.batch_alter_table("task_meta") as b:
        b.add_column(sa.Column("start_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("due_at", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("source", sa.String(length=32), nullable=True))


def downgrade():
    # --- task_meta removals ---
    with op.batch_alter_table("task_meta") as b:
        b.drop_column("source")
        b.drop_column("due_at")
        b.drop_column("start_at")

    # --- processed_emails removals ---
    with op.batch_alter_table("processed_emails") as b:
        b.drop_index("ix_processed_emails_helios_task_id")
        b.drop_column("received_at")
        b.drop_column("status")
        b.drop_column("helios_task_id")

    # --- email_tasks removals ---
    with op.batch_alter_table("email_tasks") as b:
        b.drop_index("ix_email_tasks_received_at")
        b.drop_index("ix_email_tasks_thread_id")
        b.drop_index("ix_email_tasks_sender")
        b.drop_column("client_key_hint")
        b.drop_column("priority")
        b.drop_column("source_label")
        b.drop_column("received_at")
        b.drop_column("thread_id")
        b.drop_column("gmail_link")
"""Email triage schema: align to route fields

Revision ID: 740d17209405
Revises: b5b5c0d2ebb8
Create Date: 2025-08-21 17:36:35.381836

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '740d17209405'
down_revision: Union[str, Sequence[str], None] = 'b5b5c0d2ebb8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
