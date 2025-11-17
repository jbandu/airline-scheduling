"""Create distribution and publishing tables

Revision ID: 004
Revises: 003
Create Date: 2025-01-17 00:03:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply migration: Create distribution and publishing tables"""

    # Read and execute the SQL schema file
    with open('../schemas/004_distribution_publishing_tables.sql', 'r') as f:
        sql_commands = f.read()

    # Execute the SQL
    op.execute(sql_commands)


def downgrade() -> None:
    """Revert migration: Drop distribution and publishing tables"""

    # Drop views
    op.execute("DROP VIEW IF EXISTS v_channel_health CASCADE")
    op.execute("DROP VIEW IF EXISTS v_active_publications CASCADE")

    # Drop functions
    op.execute("DROP FUNCTION IF EXISTS get_publication_stats CASCADE")
    op.execute("DROP FUNCTION IF EXISTS should_publish_to_subscription CASCADE")
    op.execute("DROP FUNCTION IF EXISTS update_subscription_stats CASCADE")
    op.execute("DROP FUNCTION IF EXISTS update_channel_stats CASCADE")

    # Drop tables
    op.execute("DROP TABLE IF EXISTS distribution_logs CASCADE")
    op.execute("DROP TABLE IF EXISTS publication_confirmations CASCADE")
    op.execute("DROP TABLE IF EXISTS distribution_subscriptions CASCADE")
    op.execute("DROP TABLE IF EXISTS publication_flights CASCADE")
    op.execute("DROP TABLE IF EXISTS schedule_publications CASCADE")
    op.execute("DROP TABLE IF EXISTS distribution_channels CASCADE")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS subscription_tier CASCADE")
    op.execute("DROP TYPE IF EXISTS distribution_format CASCADE")
    op.execute("DROP TYPE IF EXISTS publication_status CASCADE")
    op.execute("DROP TYPE IF EXISTS distribution_channel CASCADE")
