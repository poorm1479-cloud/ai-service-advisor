"""User notification preferences JSON.

Revision ID: 0031_user_notification_prefs
Revises: 0030_mfa_backup_incidents
Create Date: 2026-08-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0031_user_notification_prefs"
down_revision: Union[str, None] = "0030_mfa_backup_incidents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("notification_prefs_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "notification_prefs_json")
