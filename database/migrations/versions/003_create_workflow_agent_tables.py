"""Create workflow and agent tables

Revision ID: 003
Revises: 002
Create Date: 2025-01-17 00:02:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply migration: Create workflow and agent tables"""

    # Read and execute the SQL schema file
    with open('../schemas/003_workflow_agent_tables.sql', 'r') as f:
        sql_commands = f.read()

    # Execute the SQL
    op.execute(sql_commands)


def downgrade() -> None:
    """Revert migration: Drop workflow and agent tables"""

    # Drop views
    op.execute("DROP VIEW IF EXISTS v_agent_performance CASCADE")
    op.execute("DROP VIEW IF EXISTS v_unresolved_conflicts CASCADE")
    op.execute("DROP VIEW IF EXISTS v_active_workflows CASCADE")

    # Drop functions
    op.execute("DROP FUNCTION IF EXISTS get_workflow_summary CASCADE")
    op.execute("DROP FUNCTION IF EXISTS update_workflow_progress CASCADE")
    op.execute("DROP FUNCTION IF EXISTS trigger_update_conflict_count CASCADE")
    op.execute("DROP FUNCTION IF EXISTS trigger_update_workflow_progress CASCADE")

    # Drop tables
    op.execute("DROP TABLE IF EXISTS workflow_approvals CASCADE")
    op.execute("DROP TABLE IF EXISTS agent_communications CASCADE")
    op.execute("DROP TABLE IF EXISTS schedule_conflicts CASCADE")
    op.execute("DROP TABLE IF EXISTS agent_executions CASCADE")
    op.execute("DROP TABLE IF EXISTS schedule_workflows CASCADE")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS resolution_status CASCADE")
    op.execute("DROP TYPE IF EXISTS conflict_severity CASCADE")
    op.execute("DROP TYPE IF EXISTS conflict_type CASCADE")
    op.execute("DROP TYPE IF EXISTS agent_execution_status CASCADE")
    op.execute("DROP TYPE IF EXISTS workflow_status CASCADE")
    op.execute("DROP TYPE IF EXISTS workflow_type CASCADE")
