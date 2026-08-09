"""Allow Twilio CallSid lookups under FORCE RLS via app.sid_lookup GUC.

Revision ID: 0041_voice_sid_lookup_rls
Revises: 0040_enterprise_plan_quotas
Create Date: 2026-08-09
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0041_voice_sid_lookup_rls"
down_revision: Union[str, None] = "0040_enterprise_plan_quotas"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Hang-up status / media-stream stop only know CallSid. FORCE RLS + non-superuser
    # cannot SET row_security=off, so unscoped SID reads always miss. Permit SELECT when
    # the app sets transaction-local app.sid_lookup='1' (writes still require app.shop_id).
    for table in ("voice_calls", "voice_turns", "sms_conversations", "sms_messages"):
        op.execute(f"DROP POLICY IF EXISTS {table}_shop_isolation ON {table}")
        op.execute(
            f"""
            CREATE POLICY {table}_shop_isolation ON {table}
            FOR ALL
            USING (
              shop_id::text = current_setting('app.shop_id', true)
              OR current_setting('app.sid_lookup', true) = '1'
            )
            WITH CHECK (
              shop_id::text = current_setting('app.shop_id', true)
            )
            """
        )


def downgrade() -> None:
    for table in ("voice_calls", "voice_turns", "sms_conversations", "sms_messages"):
        op.execute(f"DROP POLICY IF EXISTS {table}_shop_isolation ON {table}")
        op.execute(
            f"""
            CREATE POLICY {table}_shop_isolation ON {table}
            FOR ALL
            USING (shop_id::text = current_setting('app.shop_id', true))
            WITH CHECK (shop_id::text = current_setting('app.shop_id', true))
            """
        )
