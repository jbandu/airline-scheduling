"""
Scheduled Trigger System for Weekly Schedule Updates
"""

import asyncio
import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .workflow import WeeklyScheduleUpdateWorkflow, ScheduleUpdateState

logger = logging.getLogger(__name__)


class ScheduleWorkflowScheduler:
    """
    Manages scheduled execution of weekly schedule update workflows

    Default schedule: Every Sunday at 22:00 UTC
    """

    def __init__(self, db_connection, neo4j_driver=None):
        self.db = db_connection
        self.neo4j = neo4j_driver
        self.scheduler = AsyncIOScheduler()
        self._running_workflows = {}  # Track active workflows

    def start(self):
        """Start the scheduler"""
        logger.info("Starting schedule workflow scheduler")

        # Add weekly schedule update job
        self.scheduler.add_job(
            self.run_weekly_update,
            trigger=CronTrigger(day_of_week='sun', hour=22, minute=0),
            id='weekly_schedule_update',
            name='Weekly Schedule Update',
            replace_existing=True
        )

        self.scheduler.start()
        logger.info("Scheduler started - Weekly updates run Sunday 22:00 UTC")

    def stop(self):
        """Stop the scheduler"""
        logger.info("Stopping schedule workflow scheduler")
        self.scheduler.shutdown()

    async def run_weekly_update(self):
        """
        Execute weekly schedule update workflow
        Triggered every Sunday at 22:00 UTC
        """
        logger.info("=== Starting Weekly Schedule Update ===")

        try:
            # Fetch pending SSM messages
            ssm_messages = self._fetch_pending_ssm_messages()

            if not ssm_messages:
                logger.info("No pending SSM messages - skipping workflow")
                return

            # Get current season
            season = self._get_current_season()

            # Create workflow
            workflow = WeeklyScheduleUpdateWorkflow(self.db, self.neo4j)

            # Initialize state
            workflow_id = str(uuid.uuid4())
            initial_state = ScheduleUpdateState(
                workflow_id=workflow_id,
                schedule_season=season,
                airline_code=self._get_airline_code(),
                ssm_messages=ssm_messages,
                parsed_flights=[],
                validation_results=None,
                conflicts=[],
                resolutions=[],
                fleet_assignments=None,
                crew_feasibility=None,
                slot_allocations=None,
                distribution_status=None,
                current_agent="",
                messages=[],
                next_agent="ssm_parser",
                workflow_status="running",
                error_message=""
            )

            # Track workflow
            self._running_workflows[workflow_id] = {
                "started_at": datetime.utcnow(),
                "status": "running"
            }

            # Execute workflow asynchronously
            try:
                final_state = await workflow.execute_async(initial_state)

                # Send completion report
                await self._send_workflow_summary(final_state)

                # Update tracking
                self._running_workflows[workflow_id]["status"] = "completed"
                self._running_workflows[workflow_id]["completed_at"] = datetime.utcnow()

                logger.info(f"=== Weekly Schedule Update Completed: {workflow_id} ===")

            except Exception as e:
                logger.error(f"Workflow execution failed: {e}", exc_info=True)
                self._running_workflows[workflow_id]["status"] = "failed"
                self._running_workflows[workflow_id]["error"] = str(e)

                # Send failure alert
                await self._send_failure_alert(workflow_id, e)

        except Exception as e:
            logger.error(f"Failed to start weekly update: {e}", exc_info=True)

    async def run_manual_update(
        self,
        season: str,
        airline_code: str,
        ssm_messages: Optional[list] = None
    ) -> str:
        """
        Manually trigger a schedule update workflow

        Args:
            season: Schedule season (e.g., "W25")
            airline_code: Airline code
            ssm_messages: Optional list of SSM messages (if None, fetches pending)

        Returns:
            Workflow ID
        """
        logger.info(f"Starting manual schedule update for {season}")

        # Fetch messages if not provided
        if ssm_messages is None:
            ssm_messages = self._fetch_pending_ssm_messages()

        # Create workflow
        workflow = WeeklyScheduleUpdateWorkflow(self.db, self.neo4j)

        # Initialize state
        workflow_id = str(uuid.uuid4())
        initial_state = ScheduleUpdateState(
            workflow_id=workflow_id,
            schedule_season=season,
            airline_code=airline_code,
            ssm_messages=ssm_messages,
            parsed_flights=[],
            validation_results=None,
            conflicts=[],
            resolutions=[],
            fleet_assignments=None,
            crew_feasibility=None,
            slot_allocations=None,
            distribution_status=None,
            current_agent="",
            messages=[],
            next_agent="ssm_parser",
            workflow_status="running",
            error_message=""
        )

        # Track workflow
        self._running_workflows[workflow_id] = {
            "started_at": datetime.utcnow(),
            "status": "running"
        }

        # Execute asynchronously in background
        asyncio.create_task(self._execute_workflow_task(workflow, initial_state))

        return workflow_id

    async def _execute_workflow_task(
        self, workflow: WeeklyScheduleUpdateWorkflow, initial_state: ScheduleUpdateState
    ):
        """Execute workflow as background task"""
        workflow_id = initial_state["workflow_id"]

        try:
            final_state = await workflow.execute_async(initial_state)

            # Send completion report
            await self._send_workflow_summary(final_state)

            # Update tracking
            self._running_workflows[workflow_id]["status"] = "completed"
            self._running_workflows[workflow_id]["completed_at"] = datetime.utcnow()

        except Exception as e:
            logger.error(f"Workflow {workflow_id} failed: {e}", exc_info=True)
            self._running_workflows[workflow_id]["status"] = "failed"
            self._running_workflows[workflow_id]["error"] = str(e)

            # Send failure alert
            await self._send_failure_alert(workflow_id, e)

    def get_workflow_status(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a running or completed workflow"""
        return self._running_workflows.get(workflow_id)

    def list_active_workflows(self) -> Dict[str, Dict[str, Any]]:
        """List all active (running) workflows"""
        return {
            wf_id: info
            for wf_id, info in self._running_workflows.items()
            if info["status"] == "running"
        }

    # ===================================================================
    # Helper Methods
    # ===================================================================

    def _fetch_pending_ssm_messages(self) -> list:
        """Fetch pending SSM messages from database"""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                SELECT message_id, message_type, raw_message, received_at
                FROM ssm_messages
                WHERE processing_status = 'pending'
                  AND received_at >= NOW() - INTERVAL '7 days'
                ORDER BY received_at ASC
                LIMIT 1000
            """)

            messages = []
            for row in cursor.fetchall():
                messages.append({
                    "id": row[0],
                    "type": row[1],
                    "content": row[2],
                    "received_at": row[3].isoformat() if row[3] else None
                })

            cursor.close()
            logger.info(f"Fetched {len(messages)} pending SSM messages")
            return messages

        except Exception as e:
            logger.error(f"Failed to fetch SSM messages: {e}")
            return []

    def _get_current_season(self) -> str:
        """Determine current IATA season"""
        now = datetime.utcnow()
        year = now.year % 100  # Last 2 digits

        # IATA seasons:
        # Summer (S): Last Sunday of March to last Saturday of October
        # Winter (W): Last Sunday of October to last Saturday of March

        if 3 <= now.month <= 10:
            return f"S{year}"
        else:
            return f"W{year}"

    def _get_airline_code(self) -> str:
        """Get airline code from environment or database"""
        # For now, return default airline
        # In production, fetch from config or database
        return "CM"  # Copa Airlines

    async def _send_workflow_summary(self, state: ScheduleUpdateState):
        """Send workflow completion summary email"""
        try:
            summary = self._build_workflow_summary(state)

            # Log summary
            logger.info(f"Workflow Summary:\n{summary}")

            # TODO: Send email notification
            # await send_email(
            #     to=["operations@airline.com"],
            #     subject=f"Schedule Update Complete: {state['schedule_season']}",
            #     body=summary
            # )

        except Exception as e:
            logger.error(f"Failed to send workflow summary: {e}")

    async def _send_failure_alert(self, workflow_id: str, error: Exception):
        """Send workflow failure alert"""
        try:
            logger.error(f"ALERT: Workflow {workflow_id} failed: {error}")

            # TODO: Send alert email/Slack notification
            # await send_alert(
            #     channel="#schedule-operations",
            #     message=f"⚠️ Schedule Update Failed: {workflow_id}\nError: {error}"
            # )

        except Exception as e:
            logger.error(f"Failed to send failure alert: {e}")

    def _build_workflow_summary(self, state: ScheduleUpdateState) -> str:
        """Build human-readable workflow summary"""
        messages = state.get("messages", [])
        completed_agents = [
            m for m in messages
            if m.get("status") == "completed" and m.get("agent") != "supervisor"
        ]

        summary = f"""
=== Weekly Schedule Update Summary ===

Workflow ID: {state['workflow_id']}
Season: {state['schedule_season']}
Airline: {state['airline_code']}
Status: {state.get('workflow_status', 'completed')}

Results:
- SSM Messages Processed: {len(state.get('ssm_messages', []))}
- Flights Parsed: {len(state.get('parsed_flights', []))}
- Conflicts Detected: {len(state.get('conflicts', []))}
- Conflicts Resolved: {len(state.get('resolutions', []))}

Agents Executed ({len(completed_agents)}):
"""

        for agent in completed_agents:
            execution_time = agent.get("execution_time_seconds", 0)
            summary += f"  ✓ {agent['agent']}: {execution_time:.1f}s\n"

        # Add validation summary if available
        validation_results = state.get("validation_results")
        if validation_results:
            all_issues = validation_results.get("all_issues", [])
            critical = len([i for i in all_issues if i.get("severity") == "critical"])
            high = len([i for i in all_issues if i.get("severity") == "high"])

            summary += f"\nValidation Results:\n"
            summary += f"  - Total Issues: {len(all_issues)}\n"
            summary += f"  - Critical: {critical}\n"
            summary += f"  - High: {high}\n"

        # Add distribution status if available
        distribution_status = state.get("distribution_status")
        if distribution_status:
            summary += f"\nDistribution Status:\n"
            summary += f"  - Status: {distribution_status.get('status', 'unknown')}\n"

        summary += "\n" + "=" * 40

        return summary


# Global scheduler instance
_scheduler_instance: Optional[ScheduleWorkflowScheduler] = None


def get_scheduler(db_connection, neo4j_driver=None) -> ScheduleWorkflowScheduler:
    """Get or create global scheduler instance"""
    global _scheduler_instance

    if _scheduler_instance is None:
        _scheduler_instance = ScheduleWorkflowScheduler(db_connection, neo4j_driver)

    return _scheduler_instance


def start_scheduler(db_connection, neo4j_driver=None):
    """Start the global scheduler"""
    scheduler = get_scheduler(db_connection, neo4j_driver)
    scheduler.start()
    logger.info("Global schedule workflow scheduler started")


def stop_scheduler():
    """Stop the global scheduler"""
    global _scheduler_instance

    if _scheduler_instance:
        _scheduler_instance.stop()
        _scheduler_instance = None
        logger.info("Global schedule workflow scheduler stopped")
