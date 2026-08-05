"""Phase 19 — AI Knowledge Base & Shop Memory extensions.

Revision ID: 0021_phase19_knowledge_memory
Revises: 0020_external_integrations
Create Date: 2026-07-29

Additive only — does not alter Phase 15 ``ai_memories`` or Workflow Engine tables.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_phase19_knowledge_memory"
down_revision: Union[str, None] = "0020_external_integrations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_knowledge_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("tags_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("source", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_ai_knowledge_documents_shop",
        "ai_knowledge_documents",
        ["shop_id"],
    )

    op.create_table(
        "ai_shop_memory_profiles",
        sa.Column(
            "shop_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("shops.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("display_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="America/Los_Angeles"),
        sa.Column("specialties_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("hours_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("preferences_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.execute(
        sa.text(
            """
            ALTER TABLE ai_knowledge_documents ENABLE ROW LEVEL SECURITY;
            ALTER TABLE ai_knowledge_documents FORCE ROW LEVEL SECURITY;
            CREATE POLICY ai_knowledge_documents_shop_isolation
              ON ai_knowledge_documents
              USING (shop_id::text = current_setting('app.shop_id', true));

            ALTER TABLE ai_shop_memory_profiles ENABLE ROW LEVEL SECURITY;
            ALTER TABLE ai_shop_memory_profiles FORCE ROW LEVEL SECURITY;
            CREATE POLICY ai_shop_memory_profiles_shop_isolation
              ON ai_shop_memory_profiles
              USING (shop_id::text = current_setting('app.shop_id', true));
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DROP POLICY IF EXISTS ai_shop_memory_profiles_shop_isolation ON ai_shop_memory_profiles;
            DROP POLICY IF EXISTS ai_knowledge_documents_shop_isolation ON ai_knowledge_documents;
            """
        )
    )
    op.drop_table("ai_shop_memory_profiles")
    op.drop_table("ai_knowledge_documents")
