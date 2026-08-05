"""phase 18 enterprise features

Revision ID: 0018_phase18_enterprise
Revises: 0017_phase17_production
Create Date: 2026-07-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_phase18_enterprise"
down_revision: Union[str, None] = "0017_phase17_production"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "enterprise_organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False, unique=True),
        sa.Column("franchise", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "enterprise_locations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("enterprise_organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("region", sa.String(128), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="America/Los_Angeles"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("organization_id", "code", name="uq_enterprise_location_code"),
    )
    op.create_index("ix_enterprise_locations_org", "enterprise_locations", ["organization_id"])

    op.create_table(
        "enterprise_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("enterprise_organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("location_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_enterprise_membership"),
    )

    op.create_table(
        "enterprise_brands",
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("enterprise_organizations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("primary_color", sa.String(32), nullable=False, server_default="#0F766E"),
        sa.Column("accent_color", sa.String(32), nullable=False, server_default="#134E4A"),
        sa.Column("logo_url", sa.Text(), nullable=True),
        sa.Column("favicon_url", sa.Text(), nullable=True),
        sa.Column("support_email", sa.String(320), nullable=True),
        sa.Column("custom_domain", sa.String(255), nullable=True),
        sa.Column("login_tagline", sa.Text(), nullable=True),
        sa.Column("hide_powered_by", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("css_vars_json", sa.Text(), nullable=False, server_default="{}"),
    )

    op.create_table(
        "enterprise_ai_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("enterprise_organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("effect", sa.String(32), nullable=False),
        sa.Column("rules_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_enterprise_ai_policies_org", "enterprise_ai_policies", ["organization_id"])

    op.create_table(
        "enterprise_sso_configs",
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("enterprise_organizations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("client_id", sa.String(255), nullable=False),
        sa.Column("issuer_url", sa.Text(), nullable=False),
        sa.Column("metadata_url", sa.Text(), nullable=True),
        sa.Column("domains_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("role_mapping_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
    )

    op.create_table(
        "enterprise_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_email", sa.String(320), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource", sa.String(128), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=True),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_enterprise_audit_org_created", "enterprise_audit_logs", ["organization_id", "created_at"])

    op.create_table(
        "enterprise_api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("enterprise_organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("key_prefix", sa.String(32), nullable=False),
        sa.Column("key_hash", sa.String(128), nullable=False),
        sa.Column("scopes_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("rate_limit_rpm", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_enterprise_api_keys_prefix", "enterprise_api_keys", ["key_prefix"])


def downgrade() -> None:
    for table in (
        "enterprise_api_keys",
        "enterprise_audit_logs",
        "enterprise_sso_configs",
        "enterprise_ai_policies",
        "enterprise_brands",
        "enterprise_memberships",
        "enterprise_locations",
        "enterprise_organizations",
    ):
        op.drop_table(table)
