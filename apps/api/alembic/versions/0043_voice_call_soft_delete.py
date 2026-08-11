"""Soft-delete voice calls so dashboard metrics survive history purge.

Revision ID: 0043_voice_call_soft_delete
Revises: 0042_shop_ai_paused
Create Date: 2026-08-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0043_voice_call_soft_delete"
down_revision: Union[str, None] = "0042_shop_ai_paused"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "voice_calls",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_voice_calls_deleted_at", "voice_calls", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_voice_calls_deleted_at", table_name="voice_calls")
    op.drop_column("voice_calls", "deleted_at")
