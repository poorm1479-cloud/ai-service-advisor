"""SaaS foundation: durable OTP, billing, usage quotas, password reset.

Revision ID: 0027_saas_foundation
Revises: 0026_heal_email_verified
Create Date: 2026-07-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_saas_foundation"
down_revision: Union[str, None] = "0026_heal_email_verified"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_otp_challenges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("target", sa.String(320), nullable=False),
        sa.Column("purpose", sa.String(32), nullable=False),
        sa.Column("code_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_auth_otp_active",
        "auth_otp_challenges",
        ["channel", "target", "purpose"],
    )

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_password_reset_user", "password_reset_tokens", ["user_id"])

    op.create_table(
        "saas_plans",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("price_cents_monthly", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stripe_price_id", sa.String(120), nullable=True),
        sa.Column("ai_calls_monthly", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("sms_monthly", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("seats", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "shop_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("plan_id", sa.String(64), sa.ForeignKey("saas_plans.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="trialing"),
        sa.Column("stripe_customer_id", sa.String(120), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(120), nullable=True),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "shop_usage_counters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shop_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_ym", sa.String(7), nullable=False),
        sa.Column("metric", sa.String(32), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("shop_id", "period_ym", "metric", name="uq_shop_usage_period_metric"),
    )
    op.create_index("ix_shop_usage_shop", "shop_usage_counters", ["shop_id"])

    op.execute(
        sa.text(
            """
            INSERT INTO saas_plans (id, name, description, price_cents_monthly, ai_calls_monthly, sms_monthly, seats, is_public, sort_order)
            VALUES
              ('free', 'Free', 'Trial / starter for independent shops', 0, 50, 50, 2, true, 0),
              ('pro', 'Pro', 'Growing shops with higher AI and SMS limits', 9900, 200, 200, 4, true, 1),
              ('enterprise', 'Enterprise', 'Multi-location and custom limits', 29900, 500, 500, 10, true, 2)
            """
        )
    )

    # Backfill free trial subscription for existing shops
    op.execute(
        sa.text(
            """
            INSERT INTO shop_subscriptions (id, shop_id, plan_id, status, trial_ends_at)
            SELECT gen_random_uuid(), s.id, 'free', 'trialing', now() + interval '14 days'
            FROM shops s
            WHERE NOT EXISTS (
              SELECT 1 FROM shop_subscriptions ss WHERE ss.shop_id = s.id
            )
            """
        )
    )


def downgrade() -> None:
    op.drop_table("shop_usage_counters")
    op.drop_table("shop_subscriptions")
    op.drop_table("saas_plans")
    op.drop_index("ix_password_reset_user", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
    op.drop_index("ix_auth_otp_active", table_name="auth_otp_challenges")
    op.drop_table("auth_otp_challenges")
