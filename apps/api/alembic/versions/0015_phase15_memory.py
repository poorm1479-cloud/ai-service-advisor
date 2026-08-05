"""phase 15 long-term ai memory

Revision ID: 0015_phase15_memory
Revises: 0014_phase14_mcp_hub
Create Date: 2026-07-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_phase15_memory"
down_revision: Union[str, None] = "0014_phase14_mcp_hub"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("memory_type", sa.String(32), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("importance", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("embedding_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("tags_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("source", sa.String(32), nullable=False, server_default="system"),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_ai_memories_shop", "ai_memories", ["shop_id"])
    op.create_index("ix_ai_memories_shop_customer", "ai_memories", ["shop_id", "customer_id"])
    op.create_index("ix_ai_memories_shop_type", "ai_memories", ["shop_id", "memory_type"])
    op.create_index("ix_ai_memories_shop_category", "ai_memories", ["shop_id", "category"])

    op.execute("ALTER TABLE ai_memories ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_memories FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY ai_memories_shop_isolation ON ai_memories
        FOR ALL
        USING (shop_id::text = current_setting('app.shop_id', true))
        WITH CHECK (shop_id::text = current_setting('app.shop_id', true))
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS ai_memories_shop_isolation ON ai_memories")
    op.drop_table("ai_memories")
