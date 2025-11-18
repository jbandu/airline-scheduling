"""
Workflow API Routes
Manage and monitor schedule update workflows
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging
import os
import psycopg2
from dotenv import load_dotenv

from ..workflows.schedule_update import WeeklyScheduleUpdateWorkflow, ScheduleUpdateState
from ..workflows.schedule_update.scheduler import get_scheduler

load_dotenv()
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/schedules/workflows", tags=["workflows"])


# ===================================================================
# Request/Response Models
# ===================================================================

class WorkflowStartRequest(BaseModel):
    """Request to start a new workflow"""
    schedule_season: str = Field(..., description="Schedule season (e.g., W25, S25)")
    airline_code: str = Field(..., description="Airline code")
    ssm_messages: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Optional SSM messages (if None, fetches pending)"
    )


class WorkflowResponse(BaseModel):
    """Workflow response"""
    workflow_id: str
    schedule_season: str
    airline_code: str
    status: str  # running, completed, failed
    started_at: str
    completed_at: Optional[str] = None
    progress_percent: int
    current_phase: str
    messages: List[Dict[str, Any]]


class WorkflowProgressResponse(BaseModel):
    """Real-time workflow progress"""
    workflow_id: str
    status: str
    progress_percent: int
    current_phase: str
    current_agent: str
    completed_agents: List[str]
    pending_agents: List[str]
    messages: List[Dict[str, Any]]
    estimated_completion_minutes: int


class WorkflowSummaryResponse(BaseModel):
    """Workflow execution summary"""
    workflow_id: str
    schedule_season: str
    status: str
    total_flights_parsed: int
    conflicts_detected: int
    conflicts_resolved: int
    validation_summary: Dict[str, Any]
    execution_time_seconds: float
    agents_executed: List[str]


# ===================================================================
# Dependencies
# ===================================================================

def get_db():
    """Get database connection"""
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            database=os.getenv("DB_NAME", "airline_scheduling"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "")
        )
        yield conn
    finally:
        conn.close()


# ===================================================================
# API Endpoints
# ===================================================================

@router.post("/start", response_model=Dict[str, str])
async def start_workflow(
    request: WorkflowStartRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db)
):
    """
    Start a new schedule update workflow

    This endpoint triggers a new workflow execution in the background.
    Use the returned workflow_id to track progress.

    Returns:
        workflow_id: ID to track workflow progress
        status: "started"
    """
    try:
        logger.info(f"Starting workflow for season {request.schedule_season}")

        # Get scheduler
        scheduler = get_scheduler(db)

        # Start workflow asynchronously
        workflow_id = await scheduler.run_manual_update(
            season=request.schedule_season,
            airline_code=request.airline_code,
            ssm_messages=request.ssm_messages
        )

        return {
            "workflow_id": workflow_id,
            "status": "started",
            "message": "Workflow started successfully"
        }

    except Exception as e:
        logger.error(f"Failed to start workflow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list", response_model=List[WorkflowResponse])
async def list_workflows(
    status: Optional[str] = None,
    season: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db=Depends(get_db)
):
    """
    List all workflows with optional filtering

    Query parameters:
    - status: Filter by status (running, completed, failed)
    - season: Filter by schedule season
    - limit: Maximum results (default 50)
    - offset: Pagination offset
    """
    try:
        cursor = db.cursor()

        # Build query
        query = """
            SELECT workflow_id, schedule_season, status,
                   started_at, completed_at, output_data
            FROM schedule_workflows
            WHERE workflow_type = 'weekly_update'
        """
        params = []

        if status:
            query += " AND status = %s"
            params.append(status)

        if season:
            query += " AND schedule_season = %s"
            params.append(season)

        query += " ORDER BY started_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor.execute(query, params)

        workflows = []
        for row in cursor.fetchall():
            workflow_id, schedule_season, wf_status, started_at, completed_at, output_data = row

            # Get messages
            messages = _get_workflow_messages(db, workflow_id)

            # Calculate progress
            progress = _calculate_progress(wf_status, messages)

            workflows.append(WorkflowResponse(
                workflow_id=workflow_id,
                schedule_season=schedule_season,
                airline_code="CM",  # TODO: Get from workflow data
                status=wf_status,
                started_at=started_at.isoformat() if started_at else None,
                completed_at=completed_at.isoformat() if completed_at else None,
                progress_percent=progress["percent"],
                current_phase=progress["phase"],
                messages=messages[-10:]  # Last 10 messages
            ))

        cursor.close()
        return workflows

    except Exception as e:
        logger.error(f"Failed to list workflows: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: str, db=Depends(get_db)):
    """
    Get detailed workflow information

    Returns complete workflow state including all agent messages
    and execution details.
    """
    try:
        cursor = db.cursor()

        cursor.execute("""
            SELECT workflow_id, schedule_season, status,
                   started_at, completed_at, output_data
            FROM schedule_workflows
            WHERE workflow_id = %s
        """, (workflow_id,))

        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Workflow not found")

        workflow_id, schedule_season, status, started_at, completed_at, output_data = row

        # Get messages
        messages = _get_workflow_messages(db, workflow_id)

        # Calculate progress
        progress = _calculate_progress(status, messages)

        cursor.close()

        return WorkflowResponse(
            workflow_id=workflow_id,
            schedule_season=schedule_season,
            airline_code="CM",
            status=status,
            started_at=started_at.isoformat() if started_at else None,
            completed_at=completed_at.isoformat() if completed_at else None,
            progress_percent=progress["percent"],
            current_phase=progress["phase"],
            messages=messages
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workflow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workflow_id}/progress", response_model=WorkflowProgressResponse)
async def get_workflow_progress(workflow_id: str, db=Depends(get_db)):
    """
    Get real-time workflow progress

    Returns current execution status, progress percentage,
    and recently completed agents.

    Use this endpoint for polling or dashboard updates.
    """
    try:
        # Check scheduler first for running workflows
        scheduler = get_scheduler(db)
        workflow_status = scheduler.get_workflow_status(workflow_id)

        if workflow_status:
            # Workflow is tracked by scheduler
            status = workflow_status["status"]
        else:
            # Query database
            cursor = db.cursor()
            cursor.execute("""
                SELECT status FROM schedule_workflows
                WHERE workflow_id = %s
            """, (workflow_id,))

            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Workflow not found")

            status = row[0]
            cursor.close()

        # Get messages
        messages = _get_workflow_messages(db, workflow_id)

        # Calculate progress
        progress = _calculate_progress(status, messages)

        # Determine current agent
        current_agent = "none"
        if messages:
            latest = messages[-1]
            if latest.get("status") == "completed":
                current_agent = "supervisor"  # Between agents
            else:
                current_agent = latest.get("agent", "unknown")

        # Get completed and pending agents
        all_agents = [
            "ssm_parser", "validator", "conflict_resolver",
            "fleet_assignment", "crew_feasibility", "slot_compliance", "distribution"
        ]

        completed_agents = [
            m["agent"] for m in messages
            if m.get("status") == "completed" and m.get("agent") != "supervisor"
        ]

        pending_agents = [a for a in all_agents if a not in completed_agents]

        # Estimate completion time
        remaining_agents = len(pending_agents)
        estimated_minutes = remaining_agents * 15  # 15 min per agent

        return WorkflowProgressResponse(
            workflow_id=workflow_id,
            status=status,
            progress_percent=progress["percent"],
            current_phase=progress["phase"],
            current_agent=current_agent,
            completed_agents=completed_agents,
            pending_agents=pending_agents,
            messages=messages[-10:],  # Last 10 messages
            estimated_completion_minutes=estimated_minutes
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workflow progress: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{workflow_id}/summary", response_model=WorkflowSummaryResponse)
async def get_workflow_summary(workflow_id: str, db=Depends(get_db)):
    """
    Get workflow execution summary

    Returns high-level summary of workflow results including
    flights parsed, conflicts resolved, and validation results.
    """
    try:
        cursor = db.cursor()

        cursor.execute("""
            SELECT workflow_id, schedule_season, status,
                   started_at, completed_at, output_data
            FROM schedule_workflows
            WHERE workflow_id = %s
        """, (workflow_id,))

        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Workflow not found")

        workflow_id, schedule_season, status, started_at, completed_at, output_data = row

        # Get messages
        messages = _get_workflow_messages(db, workflow_id)

        # Calculate execution time
        execution_time = 0
        if started_at and completed_at:
            execution_time = (completed_at - started_at).total_seconds()

        # Get agents executed
        agents_executed = [
            m["agent"] for m in messages
            if m.get("status") == "completed" and m.get("agent") != "supervisor"
        ]

        # Extract summary from output_data
        import json
        output = json.loads(output_data) if output_data else {}

        cursor.close()

        return WorkflowSummaryResponse(
            workflow_id=workflow_id,
            schedule_season=schedule_season,
            status=status,
            total_flights_parsed=output.get("parsed_flights", 0),
            conflicts_detected=output.get("conflicts", 0),
            conflicts_resolved=output.get("resolutions", 0),
            validation_summary={
                "total_issues": output.get("total_issues", 0),
                "critical_issues": output.get("critical_issues", 0)
            },
            execution_time_seconds=execution_time,
            agents_executed=agents_executed
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workflow summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workflow_id}/cancel")
async def cancel_workflow(workflow_id: str, db=Depends(get_db)):
    """
    Cancel a running workflow

    Attempts to gracefully stop a running workflow.
    Note: Already completed agents cannot be rolled back.
    """
    try:
        # Update workflow status
        cursor = db.cursor()
        cursor.execute("""
            UPDATE schedule_workflows
            SET status = 'cancelled',
                completed_at = NOW()
            WHERE workflow_id = %s
              AND status = 'running'
        """, (workflow_id,))

        rows_updated = cursor.rowcount
        db.commit()
        cursor.close()

        if rows_updated == 0:
            raise HTTPException(
                status_code=400,
                detail="Workflow not found or not running"
            )

        logger.info(f"Workflow {workflow_id} cancelled")

        return {"workflow_id": workflow_id, "status": "cancelled"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel workflow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{workflow_id}/retry")
async def retry_workflow(
    workflow_id: str,
    background_tasks: BackgroundTasks,
    db=Depends(get_db)
):
    """
    Retry a failed workflow

    Creates a new workflow with the same parameters as the failed workflow.
    """
    try:
        # Get original workflow
        cursor = db.cursor()
        cursor.execute("""
            SELECT schedule_season, status
            FROM schedule_workflows
            WHERE workflow_id = %s
        """, (workflow_id,))

        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Workflow not found")

        schedule_season, status = row
        cursor.close()

        if status != "failed":
            raise HTTPException(
                status_code=400,
                detail="Only failed workflows can be retried"
            )

        # Start new workflow
        scheduler = get_scheduler(db)
        new_workflow_id = await scheduler.run_manual_update(
            season=schedule_season,
            airline_code="CM",  # TODO: Get from original workflow
            ssm_messages=None  # Will fetch pending
        )

        logger.info(f"Retrying workflow {workflow_id} as {new_workflow_id}")

        return {
            "original_workflow_id": workflow_id,
            "new_workflow_id": new_workflow_id,
            "status": "started"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retry workflow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ===================================================================
# Helper Functions
# ===================================================================

def _get_workflow_messages(db, workflow_id: str) -> List[Dict[str, Any]]:
    """Get all messages for a workflow"""
    try:
        cursor = db.cursor()
        cursor.execute("""
            SELECT agent_name, status, execution_time_ms,
                   output_summary, executed_at
            FROM agent_executions
            WHERE workflow_id = %s
            ORDER BY executed_at ASC
        """, (workflow_id,))

        messages = []
        for row in cursor.fetchall():
            agent_name, status, exec_time_ms, output_summary, executed_at = row

            messages.append({
                "agent": agent_name,
                "status": status,
                "execution_time_ms": exec_time_ms,
                "summary": output_summary,
                "timestamp": executed_at.isoformat() if executed_at else None
            })

        cursor.close()
        return messages

    except Exception as e:
        logger.error(f"Failed to get workflow messages: {e}")
        return []


def _calculate_progress(status: str, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate workflow progress percentage and phase"""
    if status == "completed":
        return {"percent": 100, "phase": "Completed"}
    elif status == "failed":
        return {"percent": 0, "phase": "Failed"}
    elif status == "cancelled":
        return {"percent": 0, "phase": "Cancelled"}

    # Calculate based on completed agents
    total_agents = 7
    completed_agents = len([
        m for m in messages
        if m.get("status") == "completed" and m.get("agent") != "supervisor"
    ])

    percent = int((completed_agents / total_agents) * 100)

    # Determine phase
    if completed_agents == 0:
        phase = "Starting"
    elif completed_agents <= 2:
        phase = "Parsing and Validation"
    elif completed_agents <= 4:
        phase = "Conflict Resolution"
    elif completed_agents <= 6:
        phase = "Fleet and Crew Assignment"
    else:
        phase = "Distribution"

    return {"percent": percent, "phase": phase}
