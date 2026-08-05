"""phase 7 voice calls

Revision ID: 0007_phase7_voice
Revises: 0006_phase6_sms
Create Date: 2026-07-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_phase7_voice"
down_revision: Union[str, None] = "0006_phase6_sms"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "shops",
        sa.Column("voice_phone_e164", sa.String(length=32), nullable=True),
    )
    op.create_index("ix_shops_voice_phone_e164", "shops", ["voice_phone_e164"], unique=True)

    op.create_table(
        "voice_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("caller_phone", sa.String(length=32), nullable=False),
        sa.Column("called_phone", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ringing"),
        sa.Column("twilio_call_sid", sa.String(length=64), nullable=True),
        sa.Column("recording_sid", sa.String(length=64), nullable=True),
        sa.Column("recording_url", sa.String(length=500), nullable=True),
        sa.Column("recording_duration_sec", sa.Integer(), nullable=True),
        sa.Column("last_intent", sa.String(length=64), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("call_summary", sa.Text(), nullable=True),
        sa.Column("repair_notes_json", sa.Text(), nullable=True),
        sa.Column("owner_summary", sa.Text(), nullable=True),
        sa.Column("escalate", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("escalation_reason", sa.Text(), nullable=True),
        sa.Column("human_takeover", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_voice_calls_shop_id", "voice_calls", ["shop_id"])
    op.create_index("ix_voice_calls_customer_id", "voice_calls", ["customer_id"])
    op.create_index("ix_voice_calls_status", "voice_calls", ["status"])
    op.create_index("ix_voice_calls_twilio_call_sid", "voice_calls", ["twilio_call_sid"], unique=True)

    op.create_table(
        "voice_turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "call_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("voice_calls.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(length=64), nullable=True),
        sa.Column("interrupted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("audio_url", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_voice_turns_call_id", "voice_turns", ["call_id"])
    op.create_index("ix_voice_turns_shop_id", "voice_turns", ["shop_id"])

    for table in ("voice_calls", "voice_turns"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_shop_isolation ON {table}
            FOR ALL
            USING (shop_id::text = current_setting('app.shop_id', true))
            WITH CHECK (shop_id::text = current_setting('app.shop_id', true))
            """
        )


def downgrade() -> None:
    for table in ("voice_turns", "voice_calls"):
        op.execute(f"DROP POLICY IF EXISTS {table}_shop_isolation ON {table}")
    op.drop_table("voice_turns")
    op.drop_table("voice_calls")
    op.drop_index("ix_shops_voice_phone_e164", table_name="shops")
    op.drop_column("shops", "voice_phone_e164")
