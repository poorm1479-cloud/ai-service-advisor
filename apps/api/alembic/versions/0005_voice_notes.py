"""voice notes for mechanic speech intake

Revision ID: 0005_voice_notes
Revises: 0004_walkin
Create Date: 2026-07-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_voice_notes"
down_revision: Union[str, None] = "0004_walkin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "voice_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("audio_url", sa.String(length=500), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_voice_notes_shop_id", "voice_notes", ["shop_id"])
    op.create_index("ix_voice_notes_employee_id", "voice_notes", ["employee_id"])

    op.execute("ALTER TABLE voice_notes ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE voice_notes FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY voice_notes_shop_isolation ON voice_notes
        FOR ALL
        USING (shop_id::text = current_setting('app.shop_id', true))
        WITH CHECK (shop_id::text = current_setting('app.shop_id', true))
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS voice_notes_shop_isolation ON voice_notes")
    op.drop_table("voice_notes")
