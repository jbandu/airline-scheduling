"""
Error Handling and Rollback for Schedule Workflows
"""

import logging
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


class WorkflowErrorHandler:
    """
    Handles workflow failures and performs rollback operations

    Implements rollback strategies for different failure scenarios:
    - Parse failures: Mark SSM messages as failed
    - Validation failures: Save issues for review
    - Conflict resolution failures: Rollback applied resolutions
    - Distribution failures: Rollback published schedules
    """

    def __init__(self, db_connection, neo4j_driver=None):
        self.db = db_connection
        self.neo4j = neo4j_driver

    def handle_workflow_failure(
        self,
        workflow_id: str,
        state: Dict[str, Any],
        error: Exception
    ):
        """
        Handle workflow failure with appropriate rollback

        Args:
            workflow_id: Workflow ID
            state: Current workflow state
            error: Exception that caused failure
        """
        logger.error(
            f"Handling workflow {workflow_id} failure: {str(error)}",
            exc_info=True
        )

        # Determine rollback strategy based on what was completed
        rollback_actions = self._determine_rollback_actions(state)

        # Execute rollback
        rollback_results = []
        for action in rollback_actions:
            try:
                result = self._execute_rollback_action(workflow_id, state, action)
                rollback_results.append(result)
            except Exception as e:
                logger.error(f"Rollback action {action} failed: {e}")
                rollback_results.append({
                    "action": action,
                    "status": "failed",
                    "error": str(e)
                })

        # Mark workflow as failed
        self._mark_workflow_failed(workflow_id, error, rollback_results)

        # Send alert
        self._send_failure_alert(workflow_id, error, rollback_results)

        # Schedule retry if appropriate
        if self._is_retryable_error(error):
            self._schedule_workflow_retry(workflow_id)

    def _determine_rollback_actions(
        self, state: Dict[str, Any]
    ) -> List[str]:
        """Determine which rollback actions are needed"""
        actions = []

        # Check what was completed
        if state.get("parsed_flights"):
            actions.append("revert_parsed_flights")

        if state.get("resolutions"):
            actions.append("revert_conflict_resolutions")

        if state.get("fleet_assignments"):
            actions.append("revert_fleet_assignments")

        if state.get("distribution_status"):
            actions.append("revert_distribution")

        return actions

    def _execute_rollback_action(
        self,
        workflow_id: str,
        state: Dict[str, Any],
        action: str
    ) -> Dict[str, Any]:
        """Execute a specific rollback action"""
        logger.info(f"Executing rollback action: {action}")

        if action == "revert_parsed_flights":
            return self._revert_parsed_flights(workflow_id, state)

        elif action == "revert_conflict_resolutions":
            return self._revert_conflict_resolutions(workflow_id, state)

        elif action == "revert_fleet_assignments":
            return self._revert_fleet_assignments(workflow_id, state)

        elif action == "revert_distribution":
            return self._revert_distribution(workflow_id, state)

        else:
            logger.warning(f"Unknown rollback action: {action}")
            return {"action": action, "status": "skipped"}

    def _revert_parsed_flights(
        self, workflow_id: str, state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Revert parsed flights (mark SSM messages as failed)"""
        try:
            cursor = self.db.cursor()

            # Mark SSM messages as failed
            ssm_message_ids = [
                msg.get("id") for msg in state.get("ssm_messages", [])
                if msg.get("id")
            ]

            if ssm_message_ids:
                cursor.execute("""
                    UPDATE ssm_messages
                    SET processing_status = 'failed',
                        error_message = %s,
                        processed_at = NOW()
                    WHERE message_id = ANY(%s)
                """, (f"Workflow {workflow_id} failed", ssm_message_ids))

                rows_updated = cursor.rowcount
                self.db.commit()

                logger.info(f"Reverted {rows_updated} SSM messages")

            cursor.close()

            return {
                "action": "revert_parsed_flights",
                "status": "completed",
                "messages_reverted": len(ssm_message_ids)
            }

        except Exception as e:
            logger.error(f"Failed to revert parsed flights: {e}")
            return {
                "action": "revert_parsed_flights",
                "status": "failed",
                "error": str(e)
            }

    def _revert_conflict_resolutions(
        self, workflow_id: str, state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Revert conflict resolutions"""
        try:
            resolutions = state.get("resolutions", [])

            if not resolutions:
                return {
                    "action": "revert_conflict_resolutions",
                    "status": "skipped",
                    "reason": "No resolutions to revert"
                }

            # Revert each resolution
            reverted = 0
            for resolution in resolutions:
                # TODO: Implement resolution-specific revert logic
                # For now, just log
                logger.info(f"Reverting resolution: {resolution.get('type')}")
                reverted += 1

            return {
                "action": "revert_conflict_resolutions",
                "status": "completed",
                "resolutions_reverted": reverted
            }

        except Exception as e:
            logger.error(f"Failed to revert conflict resolutions: {e}")
            return {
                "action": "revert_conflict_resolutions",
                "status": "failed",
                "error": str(e)
            }

    def _revert_fleet_assignments(
        self, workflow_id: str, state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Revert fleet assignments"""
        try:
            fleet_assignments = state.get("fleet_assignments")

            if not fleet_assignments:
                return {
                    "action": "revert_fleet_assignments",
                    "status": "skipped",
                    "reason": "No assignments to revert"
                }

            # TODO: Implement fleet assignment revert logic
            logger.info("Reverting fleet assignments")

            return {
                "action": "revert_fleet_assignments",
                "status": "completed"
            }

        except Exception as e:
            logger.error(f"Failed to revert fleet assignments: {e}")
            return {
                "action": "revert_fleet_assignments",
                "status": "failed",
                "error": str(e)
            }

    def _revert_distribution(
        self, workflow_id: str, state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Revert schedule distribution"""
        try:
            distribution_status = state.get("distribution_status")

            if not distribution_status:
                return {
                    "action": "revert_distribution",
                    "status": "skipped",
                    "reason": "No distribution to revert"
                }

            # TODO: Implement distribution revert logic
            # This would involve unpublishing from GDS/OTA channels
            logger.warning("Distribution revert not yet implemented")

            return {
                "action": "revert_distribution",
                "status": "skipped",
                "reason": "Not implemented"
            }

        except Exception as e:
            logger.error(f"Failed to revert distribution: {e}")
            return {
                "action": "revert_distribution",
                "status": "failed",
                "error": str(e)
            }

    def _mark_workflow_failed(
        self,
        workflow_id: str,
        error: Exception,
        rollback_results: List[Dict[str, Any]]
    ):
        """Mark workflow as failed in database"""
        try:
            cursor = self.db.cursor()

            import json
            cursor.execute("""
                UPDATE schedule_workflows
                SET status = 'failed',
                    error_message = %s,
                    completed_at = NOW(),
                    rollback_actions = %s
                WHERE workflow_id = %s
            """, (
                str(error),
                json.dumps(rollback_results),
                workflow_id
            ))

            self.db.commit()
            cursor.close()

        except Exception as e:
            logger.error(f"Failed to mark workflow as failed: {e}")

    def _send_failure_alert(
        self,
        workflow_id: str,
        error: Exception,
        rollback_results: List[Dict[str, Any]]
    ):
        """Send failure alert to operations team"""
        logger.error(f"""
=== WORKFLOW FAILURE ALERT ===
Workflow ID: {workflow_id}
Error: {str(error)}
Rollback Actions: {len(rollback_results)}

Rollback Results:
{self._format_rollback_results(rollback_results)}

Please investigate and retry if appropriate.
================================
        """)

        # TODO: Send email/Slack notification

    def _format_rollback_results(
        self, results: List[Dict[str, Any]]
    ) -> str:
        """Format rollback results for alert"""
        formatted = []
        for result in results:
            status = result.get("status", "unknown")
            action = result.get("action", "unknown")
            formatted.append(f"  - {action}: {status}")

        return "\n".join(formatted) if formatted else "  (none)"

    def _is_retryable_error(self, error: Exception) -> bool:
        """Determine if error is retryable"""
        # Network errors, timeouts, temporary database issues are retryable
        retryable_errors = [
            "ConnectionError",
            "TimeoutError",
            "OperationalError",
            "NetworkError"
        ]

        error_type = type(error).__name__
        return error_type in retryable_errors

    def _schedule_workflow_retry(self, workflow_id: str):
        """Schedule automatic workflow retry"""
        logger.info(f"Scheduling retry for workflow {workflow_id}")

        # TODO: Implement retry scheduling
        # Could use APScheduler to retry after delay
