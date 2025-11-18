"""Create utility functions

Revision ID: 005
Revises: 004
Create Date: 2025-01-17 00:04:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply migration: Create utility functions"""

    # Read and execute the SQL schema file
    with open('../schemas/005_functions_utilities.sql', 'r') as f:
        sql_commands = f.read()

    # Execute the SQL
    op.execute(sql_commands)


def downgrade() -> None:
    """Revert migration: Drop utility functions"""

    # Drop functions in reverse order
    op.execute("DROP FUNCTION IF EXISTS validate_schedule_data_quality CASCADE")
    op.execute("DROP FUNCTION IF EXISTS calculate_block_time CASCADE")
    op.execute("DROP FUNCTION IF EXISTS iata_time_to_timestamp CASCADE")
    op.execute("DROP FUNCTION IF EXISTS parse_ssm_basic CASCADE")
    op.execute("DROP FUNCTION IF EXISTS calculate_schedule_utilization CASCADE")
    op.execute("DROP FUNCTION IF EXISTS check_slot_availability CASCADE")
    op.execute("DROP FUNCTION IF EXISTS detect_aircraft_conflicts CASCADE")
    op.execute("DROP FUNCTION IF EXISTS find_connecting_flights CASCADE")
    op.execute("DROP FUNCTION IF EXISTS get_daily_schedule CASCADE")
    op.execute("DROP FUNCTION IF EXISTS validate_flight_continuity CASCADE")
    op.execute("DROP FUNCTION IF EXISTS detect_schedule_gaps CASCADE")
    op.execute("DROP FUNCTION IF EXISTS get_schedule_by_season CASCADE")
    op.execute("DROP FUNCTION IF EXISTS get_operating_dates CASCADE")
    op.execute("DROP FUNCTION IF EXISTS calculate_next_occurrence CASCADE")
    op.execute("DROP FUNCTION IF EXISTS flight_operates_on_date CASCADE")
    op.execute("DROP FUNCTION IF EXISTS parse_ssm_operating_days CASCADE")
