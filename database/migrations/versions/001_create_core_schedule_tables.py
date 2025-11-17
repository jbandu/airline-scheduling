"""Create core schedule tables

Revision ID: 001
Revises:
Create Date: 2025-01-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply migration: Create core schedule tables"""

    # Read and execute the SQL schema file
    with open('../schemas/001_core_schedule_tables.sql', 'r') as f:
        sql_commands = f.read()

    # Execute the SQL
    op.execute(sql_commands)


def downgrade() -> None:
    """Revert migration: Drop core schedule tables"""

    # Drop views
    op.execute("DROP VIEW IF EXISTS v_daily_operations CASCADE")
    op.execute("DROP VIEW IF EXISTS v_active_flights CASCADE")

    # Drop tables in reverse order (respecting foreign keys)
    op.execute("DROP TABLE IF EXISTS flight_legs CASCADE")
    op.execute("DROP TABLE IF EXISTS schedule_changes CASCADE")
    op.execute("DROP TABLE IF EXISTS ssm_messages CASCADE")
    op.execute("DROP TABLE IF EXISTS flights CASCADE")
    op.execute("DROP TABLE IF EXISTS schedules CASCADE")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS service_type CASCADE")
    op.execute("DROP TYPE IF EXISTS change_type CASCADE")
    op.execute("DROP TYPE IF EXISTS processing_status CASCADE")
    op.execute("DROP TYPE IF EXISTS message_format CASCADE")
    op.execute("DROP TYPE IF EXISTS ssm_message_type CASCADE")
    op.execute("DROP TYPE IF EXISTS schedule_status CASCADE")
