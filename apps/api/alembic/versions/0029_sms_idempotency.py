"""SMS idempotency unique index + status helpers.

Revision ID: 0029_sms_idempotency
Revises: 0028_mfa_and_portal
Create Date: 2026-07-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029_sms_idempotency"
down_revision: Union[str, None] = "0028_mfa_and_portal"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Deduplicate any existing non-null SIDs before unique index
    op.execute(
        sa.text(
            """
            DELETE FROM sms_messages a
            USING sms_messages b
            WHERE a.twilio_sid IS NOT NULL
              AND a.twilio_sid = b.twilio_sid
              AND a.created_at < b.created_at
            """
        )
    )
    op.create_index(
        "uq_sms_messages_twilio_sid",
        "sms_messages",
        ["twilio_sid"],
        unique=True,
        postgresql_where=sa.text("twilio_sid IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_sms_messages_twilio_sid", table_name="sms_messages")
