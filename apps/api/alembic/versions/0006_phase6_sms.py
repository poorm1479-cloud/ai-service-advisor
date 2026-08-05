"""phase 6 sms conversations

Revision ID: 0006_phase6_sms
Revises: 0005_voice_notes
Create Date: 2026-07-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_phase6_sms"
down_revision: Union[str, None] = "0005_voice_notes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "shops",
        sa.Column("sms_phone_e164", sa.String(length=32), nullable=True),
    )
    op.create_index("ix_shops_sms_phone_e164", "shops", ["sms_phone_e164"], unique=True)

    op.create_table(
        "sms_conversations",
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
        sa.Column("customer_phone", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("last_intent", sa.String(length=64), nullable=True),
        sa.Column("owner_summary", sa.Text(), nullable=True),
        sa.Column("reply_preview", sa.Text(), nullable=True),
        sa.Column("escalate", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("escalation_reason", sa.Text(), nullable=True),
        sa.Column("human_takeover", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("shop_id", "customer_phone", name="uq_sms_conversation_shop_phone"),
    )
    op.create_index("ix_sms_conversations_shop_id", "sms_conversations", ["shop_id"])
    op.create_index("ix_sms_conversations_customer_id", "sms_conversations", ["customer_id"])
    op.create_index("ix_sms_conversations_status", "sms_conversations", ["status"])

    op.create_table(
        "sms_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sms_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("twilio_sid", sa.String(length=64), nullable=True),
        sa.Column("intent", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_sms_messages_conversation_id", "sms_messages", ["conversation_id"])
    op.create_index("ix_sms_messages_shop_id", "sms_messages", ["shop_id"])

    for table in ("sms_conversations", "sms_messages"):
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
    for table in ("sms_messages", "sms_conversations"):
        op.execute(f"DROP POLICY IF EXISTS {table}_shop_isolation ON {table}")
    op.drop_table("sms_messages")
    op.drop_table("sms_conversations")
    op.drop_index("ix_shops_sms_phone_e164", table_name="shops")
    op.drop_column("shops", "sms_phone_e164")
