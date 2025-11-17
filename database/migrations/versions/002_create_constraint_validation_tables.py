"""Create constraint and validation tables

Revision ID: 002
Revises: 001
Create Date: 2025-01-17 00:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply migration: Create constraint and validation tables"""

    # Read and execute the SQL schema file
    with open('../schemas/002_constraint_validation_tables.sql', 'r') as f:
        sql_commands = f.read()

    # Execute the SQL
    op.execute(sql_commands)


def downgrade() -> None:
    """Revert migration: Drop constraint and validation tables"""

    # Drop views
    op.execute("DROP VIEW IF EXISTS v_available_aircraft CASCADE")
    op.execute("DROP VIEW IF EXISTS v_current_slot_allocations CASCADE")

    # Drop functions
    op.execute("DROP FUNCTION IF EXISTS is_aircraft_available CASCADE")
    op.execute("DROP FUNCTION IF EXISTS get_minimum_connect_time CASCADE")
    op.execute("DROP FUNCTION IF EXISTS check_curfew_violation CASCADE")

    # Drop tables
    op.execute("DROP TABLE IF EXISTS regulatory_requirements CASCADE")
    op.execute("DROP TABLE IF EXISTS crew_bases CASCADE")
    op.execute("DROP TABLE IF EXISTS minimum_connect_times CASCADE")
    op.execute("DROP TABLE IF EXISTS aircraft_availability CASCADE")
    op.execute("DROP TABLE IF EXISTS airport_constraints CASCADE")
    op.execute("DROP TABLE IF EXISTS airport_slots CASCADE")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS connection_type CASCADE")
    op.execute("DROP TYPE IF EXISTS coordination_level CASCADE")
    op.execute("DROP TYPE IF EXISTS aircraft_status CASCADE")
    op.execute("DROP TYPE IF EXISTS constraint_type CASCADE")
    op.execute("DROP TYPE IF EXISTS slot_type CASCADE")
