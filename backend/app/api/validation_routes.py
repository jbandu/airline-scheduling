"""
Schedule Validation API Routes
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import logging
import os
import psycopg2
from dotenv import load_dotenv

from ..agents.schedule_validation import ScheduleValidationAgent

load_dotenv()
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/schedules/validation", tags=["validation"])


# Request/Response Models
class ValidationRequest(BaseModel):
    """Request to validate a schedule"""
    schedule_id: str = Field(..., description="Schedule ID to validate")
    airline_code: Optional[str] = Field(None, description="Airline code")
    validation_options: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Validation options"
    )


class ValidationResponse(BaseModel):
    """Validation response"""
    schedule_id: str
    status: str
    total_flights: int
    total_issues: int
    critical_issues: int
    high_issues: int
    medium_issues: int
    low_issues: int
    validation_complete: bool
    report_url: Optional[str] = None
    summary: str


class ValidationIssue(BaseModel):
    """Individual validation issue"""
    severity: str
    category: str
    issue_type: str
    flight_id: str
    flight_number: str
    description: str
    recommended_action: str
    impact: str


class ValidationReportRequest(BaseModel):
    """Request for validation report"""
    schedule_id: str
    format: str = Field("json", description="Report format: json, markdown, html, csv")


# Dependency: Database connection
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


@router.post("/validate", response_model=ValidationResponse)
async def validate_schedule(
    request: ValidationRequest,
    db=Depends(get_db)
):
    """
    Validate a schedule against all constraints

    This endpoint runs all 8 validation categories in parallel:
    - Airport slot validation
    - Aircraft availability validation
    - Crew feasibility validation
    - MCT (Minimum Connect Time) validation
    - Curfew and airport hours validation
    - Regulatory compliance validation
    - Aircraft routing validation
    - Schedule pattern validation

    Returns comprehensive validation results with LLM-enhanced analysis.
    """
    try:
        logger.info(f"Starting validation for schedule {request.schedule_id}")

        # Initialize agent
        agent = ScheduleValidationAgent(
            db_connection=db,
            llm_model="claude-sonnet-4-20250514"
        )

        # Run validation
        result = agent.validate(
            schedule_id=request.schedule_id,
            options=request.validation_options
        )

        # Extract statistics
        issues = result.get("all_issues", [])
        critical = len([i for i in issues if i.get("severity") == "critical"])
        high = len([i for i in issues if i.get("severity") == "high"])
        medium = len([i for i in issues if i.get("severity") == "medium"])
        low = len([i for i in issues if i.get("severity") == "low"])

        # Determine status
        if critical > 0:
            status = "failed"
        elif high > 5:
            status = "warning"
        else:
            status = "passed"

        response = ValidationResponse(
            schedule_id=request.schedule_id,
            status=status,
            total_flights=result.get("total_flights", 0),
            total_issues=len(issues),
            critical_issues=critical,
            high_issues=high,
            medium_issues=medium,
            low_issues=low,
            validation_complete=result.get("validation_complete", False),
            summary=result.get("analysis_result", {}).get("summary", "")
        )

        logger.info(f"Validation completed: {status} - {len(issues)} issues found")
        return response

    except Exception as e:
        logger.error(f"Validation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/results/{schedule_id}", response_model=Dict[str, Any])
async def get_validation_results(
    schedule_id: str,
    db=Depends(get_db)
):
    """
    Get detailed validation results for a schedule

    Returns all validation issues, analysis, and recommendations.
    """
    try:
        # Initialize agent
        agent = ScheduleValidationAgent(db_connection=db)

        # Get cached results (if available) or run validation
        result = agent.validate(schedule_id=schedule_id)

        return result

    except Exception as e:
        logger.error(f"Error retrieving results: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/issues/{schedule_id}", response_model=List[ValidationIssue])
async def get_validation_issues(
    schedule_id: str,
    severity: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db=Depends(get_db)
):
    """
    Get validation issues for a schedule with filtering

    Query parameters:
    - severity: Filter by severity (critical, high, medium, low)
    - category: Filter by category (slot_validation, aircraft_validation, etc.)
    - limit: Maximum number of issues to return
    - offset: Number of issues to skip (for pagination)
    """
    try:
        # Get validation results
        agent = ScheduleValidationAgent(db_connection=db)
        result = agent.validate(schedule_id=schedule_id)

        issues = result.get("all_issues", [])

        # Apply filters
        if severity:
            issues = [i for i in issues if i.get("severity") == severity]

        if category:
            issues = [i for i in issues if i.get("category") == category]

        # Apply pagination
        paginated_issues = issues[offset:offset + limit]

        return paginated_issues

    except Exception as e:
        logger.error(f"Error retrieving issues: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/report", response_model=Dict[str, str])
async def generate_validation_report(
    request: ValidationReportRequest,
    db=Depends(get_db)
):
    """
    Generate validation report in specified format

    Supported formats:
    - json: Machine-readable JSON
    - markdown: Human-readable Markdown
    - html: Web-friendly HTML
    - csv: Tabular CSV for spreadsheet import
    """
    try:
        # Get validation results
        agent = ScheduleValidationAgent(db_connection=db)
        result = agent.validate(schedule_id=request.schedule_id)

        # Generate report
        from ..agents.schedule_validation.report_generator import ReportGenerator

        generator = ReportGenerator()
        report = generator.generate_report(result, format=request.format)

        return {
            "schedule_id": request.schedule_id,
            "format": request.format,
            "report": report
        }

    except Exception as e:
        logger.error(f"Error generating report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories")
async def get_validation_categories():
    """
    Get list of all validation categories

    Returns information about each validation category including
    what it checks and potential issues.
    """
    return {
        "categories": [
            {
                "id": "slot_validation",
                "name": "Airport Slot Validation",
                "description": "Validates airport slot allocations per IATA WSG",
                "checks": [
                    "Slot exists at coordinated airports",
                    "Slot time matches scheduled time",
                    "Slot is confirmed",
                    "Historical rights are maintained"
                ]
            },
            {
                "id": "aircraft_validation",
                "name": "Aircraft Availability Validation",
                "description": "Validates aircraft availability and routing",
                "checks": [
                    "Aircraft exists and is active",
                    "Aircraft type matches requirements",
                    "No maintenance conflicts",
                    "Sufficient turnaround time",
                    "Routing continuity"
                ]
            },
            {
                "id": "crew_validation",
                "name": "Crew Feasibility Validation",
                "description": "Validates crew availability and compliance",
                "checks": [
                    "Minimum crew complement",
                    "Aircraft type ratings",
                    "Flight duty period limits",
                    "Rest requirements",
                    "Monthly/yearly hour limits"
                ]
            },
            {
                "id": "mct_validation",
                "name": "Minimum Connect Time Validation",
                "description": "Validates passenger connection times",
                "checks": [
                    "Connection time meets MCT",
                    "Terminal change time",
                    "Immigration/customs time",
                    "Baggage re-check time"
                ]
            },
            {
                "id": "curfew_validation",
                "name": "Airport Curfew Validation",
                "description": "Validates airport operating hours and curfews",
                "checks": [
                    "Airport operating hours",
                    "Noise curfew restrictions",
                    "Night movement limits",
                    "Noise category requirements"
                ]
            },
            {
                "id": "regulatory_validation",
                "name": "Regulatory Compliance Validation",
                "description": "Validates aviation regulatory requirements",
                "checks": [
                    "Traffic rights (freedoms of air)",
                    "Bilateral agreements",
                    "Cabotage restrictions",
                    "Designated carrier status"
                ]
            },
            {
                "id": "routing_validation",
                "name": "Aircraft Routing Validation",
                "description": "Validates aircraft routing efficiency",
                "checks": [
                    "Routing continuity",
                    "Aircraft range limitations",
                    "Hub connectivity",
                    "Positioning efficiency"
                ]
            },
            {
                "id": "pattern_validation",
                "name": "Schedule Pattern Validation",
                "description": "Validates schedule patterns and consistency",
                "checks": [
                    "Operating days format",
                    "Frequency consistency",
                    "Equipment consistency",
                    "Schedule symmetry"
                ]
            }
        ]
    }


@router.post("/bulk-validate")
async def bulk_validate_schedules(
    schedule_ids: List[str],
    db=Depends(get_db)
):
    """
    Validate multiple schedules in batch

    Useful for validating all schedules for a season or airline.
    """
    try:
        results = []

        for schedule_id in schedule_ids:
            try:
                agent = ScheduleValidationAgent(db_connection=db)
                result = agent.validate(schedule_id=schedule_id)

                issues = result.get("all_issues", [])
                critical = len([i for i in issues if i.get("severity") == "critical"])

                results.append({
                    "schedule_id": schedule_id,
                    "status": "failed" if critical > 0 else "passed",
                    "total_issues": len(issues),
                    "critical_issues": critical
                })

            except Exception as e:
                results.append({
                    "schedule_id": schedule_id,
                    "status": "error",
                    "error": str(e)
                })

        return {"results": results}

    except Exception as e:
        logger.error(f"Bulk validation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
