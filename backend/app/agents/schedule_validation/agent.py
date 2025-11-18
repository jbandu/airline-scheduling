"""
Schedule Validation Agent
Multi-constraint validation for airline flight schedules

Validates schedules against:
- Airport slots
- Aircraft availability
- Crew feasibility
- Minimum connect times (MCT)
- Airport operating hours/curfews
- Regulatory compliance
- Aircraft routing
- Schedule patterns
"""

import json
import logging
from datetime import datetime, time, timedelta
from typing import TypedDict, List, Dict, Any, Optional
from enum import Enum

from langgraph.graph import StateGraph, END
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from .validators.slot_validator import SlotValidator
from .validators.aircraft_validator import AircraftValidator
from .validators.crew_validator import CrewValidator
from .validators.mct_validator import MCTValidator
from .validators.curfew_validator import CurfewValidator
from .validators.regulatory_validator import RegulatoryValidator
from .validators.routing_validator import RoutingValidator
from .validators.pattern_validator import PatternValidator
from .analyzers.conflict_analyzer import ConflictAnalyzer
from .reports.report_generator import ReportGenerator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class IssueSeverity(str, Enum):
    """Issue severity levels"""
    CRITICAL = "critical"  # Blocks schedule publication
    HIGH = "high"          # Should be resolved before publication
    MEDIUM = "medium"      # Should be addressed
    LOW = "low"            # Informational
    INFO = "info"          # No action required


class ValidationStatus(str, Enum):
    """Overall validation status"""
    VALID = "valid"                     # No issues
    WARNINGS = "warnings"               # Has warnings but publishable
    CRITICAL_ERRORS = "critical_errors" # Cannot publish
    FAILED = "failed"                   # Validation process failed


class ValidationState(TypedDict):
    """State for schedule validation workflow"""
    # Input
    schedule_id: str
    validate_all: bool
    flight_ids_to_validate: Optional[List[str]]

    # Loaded data
    flights_to_validate: List[Dict[str, Any]]
    schedule_metadata: Dict[str, Any]

    # Validation results by category
    validation_results: Dict[str, List[Dict[str, Any]]]

    # Overall status
    overall_status: str
    validation_summary: Dict[str, Any]

    # Performance metrics
    validation_start_time: Optional[datetime]
    validation_end_time: Optional[datetime]
    validation_duration_ms: Optional[int]

    # LLM usage
    llm_tokens_used: int
    llm_calls_made: int


class ScheduleValidationAgent:
    """
    Schedule Validation Agent

    Validates airline flight schedules against multiple constraints using
    parallel LangGraph nodes for performance.

    Features:
    - 8 validation categories
    - Parallel execution
    - LLM-enhanced conflict resolution
    - Comprehensive reporting
    - Incremental validation support
    """

    def __init__(
        self,
        db_connection,
        neo4j_driver=None,
        llm_model: str = "claude-sonnet-4-20250514",
        enable_llm_analysis: bool = True
    ):
        """
        Initialize Schedule Validation Agent

        Args:
            db_connection: PostgreSQL database connection
            neo4j_driver: Optional Neo4j driver
            llm_model: Claude model for intelligent analysis
            enable_llm_analysis: Enable LLM-powered conflict resolution
        """
        self.db = db_connection
        self.neo4j_driver = neo4j_driver
        self.enable_llm_analysis = enable_llm_analysis

        # Initialize LLM
        self.llm = ChatAnthropic(
            model=llm_model,
            temperature=0,
            max_tokens=4096
        )

        # Initialize validators
        self.slot_validator = SlotValidator(db_connection)
        self.aircraft_validator = AircraftValidator(db_connection)
        self.crew_validator = CrewValidator(db_connection)
        self.mct_validator = MCTValidator(db_connection)
        self.curfew_validator = CurfewValidator(db_connection)
        self.regulatory_validator = RegulatoryValidator(db_connection)
        self.routing_validator = RoutingValidator(db_connection)
        self.pattern_validator = PatternValidator(db_connection)

        # Initialize analyzers and generators
        self.conflict_analyzer = ConflictAnalyzer(self.llm)
        self.report_generator = ReportGenerator()

        # Build LangGraph workflow
        self.graph = self._build_graph()

        logger.info(f"ScheduleValidationAgent initialized with model: {llm_model}")

    def _build_graph(self) -> StateGraph:
        """
        Build LangGraph workflow with parallel validation nodes

        Workflow:
        1. Load schedule data
        2. Run 8 validators in parallel
        3. Compile results
        4. Analyze conflicts (LLM)
        5. Generate report
        """
        workflow = StateGraph(ValidationState)

        # Add nodes
        workflow.add_node("load_schedule", self.load_schedule_data)
        workflow.add_node("validate_slots", self.validate_airport_slots)
        workflow.add_node("validate_aircraft", self.validate_aircraft_availability)
        workflow.add_node("validate_crew", self.validate_crew_feasibility)
        workflow.add_node("validate_mct", self.validate_minimum_connect_times)
        workflow.add_node("validate_curfews", self.validate_airport_hours)
        workflow.add_node("validate_regulatory", self.validate_regulatory_compliance)
        workflow.add_node("validate_routing", self.validate_aircraft_routing)
        workflow.add_node("validate_patterns", self.validate_schedule_patterns)
        workflow.add_node("compile_results", self.compile_validation_results)
        workflow.add_node("analyze_conflicts", self.analyze_conflicts_with_llm)
        workflow.add_node("generate_report", self.generate_validation_report)

        # Set entry point
        workflow.set_entry_point("load_schedule")

        # Parallel validation edges (fan-out from load_schedule)
        workflow.add_edge("load_schedule", "validate_slots")
        workflow.add_edge("load_schedule", "validate_aircraft")
        workflow.add_edge("load_schedule", "validate_crew")
        workflow.add_edge("load_schedule", "validate_mct")
        workflow.add_edge("load_schedule", "validate_curfews")
        workflow.add_edge("load_schedule", "validate_regulatory")
        workflow.add_edge("load_schedule", "validate_routing")
        workflow.add_edge("load_schedule", "validate_patterns")

        # Converge to compilation (fan-in to compile_results)
        workflow.add_edge("validate_slots", "compile_results")
        workflow.add_edge("validate_aircraft", "compile_results")
        workflow.add_edge("validate_crew", "compile_results")
        workflow.add_edge("validate_mct", "compile_results")
        workflow.add_edge("validate_curfews", "compile_results")
        workflow.add_edge("validate_regulatory", "compile_results")
        workflow.add_edge("validate_routing", "compile_results")
        workflow.add_edge("validate_patterns", "compile_results")

        # Post-processing
        workflow.add_edge("compile_results", "analyze_conflicts")
        workflow.add_edge("analyze_conflicts", "generate_report")
        workflow.add_edge("generate_report", END)

        return workflow.compile()

    def validate(
        self,
        schedule_id: str,
        flight_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Validate schedule or specific flights

        Args:
            schedule_id: Schedule UUID to validate
            flight_ids: Optional list of specific flight IDs to validate

        Returns:
            Validation results with issues and recommendations
        """
        start_time = datetime.now()

        # Initialize state
        initial_state: ValidationState = {
            "schedule_id": schedule_id,
            "validate_all": flight_ids is None,
            "flight_ids_to_validate": flight_ids,
            "flights_to_validate": [],
            "schedule_metadata": {},
            "validation_results": {},
            "overall_status": ValidationStatus.VALID.value,
            "validation_summary": {},
            "validation_start_time": start_time,
            "validation_end_time": None,
            "validation_duration_ms": None,
            "llm_tokens_used": 0,
            "llm_calls_made": 0
        }

        try:
            # Execute workflow
            logger.info(f"Starting validation for schedule: {schedule_id}")
            final_state = self.graph.invoke(initial_state)

            # Calculate duration
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            final_state["validation_end_time"] = end_time
            final_state["validation_duration_ms"] = duration_ms

            logger.info(
                f"Validation complete: {final_state['overall_status']}, "
                f"{duration_ms}ms"
            )

            return self._format_result(final_state)

        except Exception as e:
            logger.error(f"Validation failed: {str(e)}", exc_info=True)
            return {
                "schedule_id": schedule_id,
                "status": ValidationStatus.FAILED.value,
                "error": str(e),
                "validation_duration_ms": int((datetime.now() - start_time).total_seconds() * 1000)
            }

    # =========================================================================
    # WORKFLOW NODES
    # =========================================================================

    def load_schedule_data(self, state: ValidationState) -> ValidationState:
        """Load schedule and flight data from database"""
        cursor = self.db.cursor()

        try:
            # Load schedule metadata
            cursor.execute(
                """
                SELECT schedule_id, season_code, effective_from, effective_to,
                       version_number, status
                FROM schedules
                WHERE schedule_id = %s
                """,
                (state["schedule_id"],)
            )

            schedule_row = cursor.fetchone()
            if not schedule_row:
                raise ValueError(f"Schedule not found: {state['schedule_id']}")

            state["schedule_metadata"] = {
                "schedule_id": str(schedule_row[0]),
                "season_code": schedule_row[1],
                "effective_from": schedule_row[2].isoformat() if schedule_row[2] else None,
                "effective_to": schedule_row[3].isoformat() if schedule_row[3] else None,
                "version_number": schedule_row[4],
                "status": schedule_row[5]
            }

            # Load flights to validate
            if state["validate_all"]:
                cursor.execute(
                    """
                    SELECT flight_id, flight_number, carrier_code,
                           origin_airport, destination_airport,
                           departure_time, arrival_time,
                           departure_day_offset, arrival_day_offset,
                           operating_days, effective_from, effective_to,
                           aircraft_type, service_type, frequency_per_week,
                           aircraft_registration, metadata
                    FROM flights
                    WHERE schedule_id = %s
                    ORDER BY departure_time
                    """,
                    (state["schedule_id"],)
                )
            else:
                cursor.execute(
                    """
                    SELECT flight_id, flight_number, carrier_code,
                           origin_airport, destination_airport,
                           departure_time, arrival_time,
                           departure_day_offset, arrival_day_offset,
                           operating_days, effective_from, effective_to,
                           aircraft_type, service_type, frequency_per_week,
                           aircraft_registration, metadata
                    FROM flights
                    WHERE flight_id = ANY(%s)
                    ORDER BY departure_time
                    """,
                    (state["flight_ids_to_validate"],)
                )

            flights = []
            for row in cursor.fetchall():
                flights.append({
                    "flight_id": str(row[0]),
                    "flight_number": row[1],
                    "carrier_code": row[2],
                    "origin_airport": row[3],
                    "destination_airport": row[4],
                    "departure_time": str(row[5]),
                    "arrival_time": str(row[6]),
                    "departure_day_offset": row[7],
                    "arrival_day_offset": row[8],
                    "operating_days": row[9],
                    "effective_from": row[10].isoformat() if row[10] else None,
                    "effective_to": row[11].isoformat() if row[11] else None,
                    "aircraft_type": row[12],
                    "service_type": row[13],
                    "frequency_per_week": row[14],
                    "aircraft_registration": row[15],
                    "metadata": row[16] if row[16] else {}
                })

            state["flights_to_validate"] = flights

            logger.info(f"Loaded {len(flights)} flights to validate")

            return state

        finally:
            cursor.close()

    def validate_airport_slots(self, state: ValidationState) -> ValidationState:
        """Validate airport slot allocations"""
        issues = self.slot_validator.validate(state["flights_to_validate"])
        state["validation_results"]["slot_validation"] = issues
        logger.info(f"Slot validation: {len(issues)} issues found")
        return state

    def validate_aircraft_availability(self, state: ValidationState) -> ValidationState:
        """Validate aircraft availability and routing"""
        issues = self.aircraft_validator.validate(state["flights_to_validate"])
        state["validation_results"]["aircraft_validation"] = issues
        logger.info(f"Aircraft validation: {len(issues)} issues found")
        return state

    def validate_crew_feasibility(self, state: ValidationState) -> ValidationState:
        """Validate crew availability and duty time compliance"""
        issues = self.crew_validator.validate(state["flights_to_validate"])
        state["validation_results"]["crew_validation"] = issues
        logger.info(f"Crew validation: {len(issues)} issues found")
        return state

    def validate_minimum_connect_times(self, state: ValidationState) -> ValidationState:
        """Validate minimum connection times"""
        issues = self.mct_validator.validate(state["flights_to_validate"])
        state["validation_results"]["mct_validation"] = issues
        logger.info(f"MCT validation: {len(issues)} issues found")
        return state

    def validate_airport_hours(self, state: ValidationState) -> ValidationState:
        """Validate airport operating hours and curfews"""
        issues = self.curfew_validator.validate(state["flights_to_validate"])
        state["validation_results"]["curfew_validation"] = issues
        logger.info(f"Curfew validation: {len(issues)} issues found")
        return state

    def validate_regulatory_compliance(self, state: ValidationState) -> ValidationState:
        """Validate regulatory compliance"""
        issues = self.regulatory_validator.validate(state["flights_to_validate"])
        state["validation_results"]["regulatory_validation"] = issues
        logger.info(f"Regulatory validation: {len(issues)} issues found")
        return state

    def validate_aircraft_routing(self, state: ValidationState) -> ValidationState:
        """Validate aircraft routing feasibility"""
        issues = self.routing_validator.validate(state["flights_to_validate"])
        state["validation_results"]["routing_validation"] = issues
        logger.info(f"Routing validation: {len(issues)} issues found")
        return state

    def validate_schedule_patterns(self, state: ValidationState) -> ValidationState:
        """Validate schedule patterns and consistency"""
        issues = self.pattern_validator.validate(state["flights_to_validate"])
        state["validation_results"]["pattern_validation"] = issues
        logger.info(f"Pattern validation: {len(issues)} issues found")
        return state

    def compile_validation_results(self, state: ValidationState) -> ValidationState:
        """Compile results from all validators"""
        total_issues = sum(
            len(issues) for issues in state["validation_results"].values()
        )

        critical_count = sum(
            len([i for i in issues if i["severity"] == IssueSeverity.CRITICAL.value])
            for issues in state["validation_results"].values()
        )

        high_count = sum(
            len([i for i in issues if i["severity"] == IssueSeverity.HIGH.value])
            for issues in state["validation_results"].values()
        )

        # Determine overall status
        if critical_count > 0:
            state["overall_status"] = ValidationStatus.CRITICAL_ERRORS.value
        elif total_issues > 0:
            state["overall_status"] = ValidationStatus.WARNINGS.value
        else:
            state["overall_status"] = ValidationStatus.VALID.value

        logger.info(
            f"Compiled results: {total_issues} total issues, "
            f"{critical_count} critical, {high_count} high"
        )

        return state

    def analyze_conflicts_with_llm(self, state: ValidationState) -> ValidationState:
        """Use LLM to analyze conflicts and suggest resolutions"""
        if not self.enable_llm_analysis:
            return state

        # Get all critical and high severity issues
        critical_issues = []
        for category, issues in state["validation_results"].items():
            for issue in issues:
                if issue["severity"] in [IssueSeverity.CRITICAL.value, IssueSeverity.HIGH.value]:
                    critical_issues.append({**issue, "category": category})

        if not critical_issues:
            return state

        logger.info(f"Analyzing {len(critical_issues)} critical/high issues with LLM")

        try:
            analysis = self.conflict_analyzer.analyze(
                critical_issues,
                state["schedule_metadata"]
            )

            state["llm_tokens_used"] += analysis.get("tokens_used", 0)
            state["llm_calls_made"] += 1

            # Add LLM suggestions to issues
            for issue in critical_issues:
                issue["llm_analysis"] = analysis.get("suggestions", {}).get(
                    issue.get("flight_id", ""), {}
                )

        except Exception as e:
            logger.error(f"LLM analysis failed: {str(e)}")

        return state

    def generate_validation_report(self, state: ValidationState) -> ValidationState:
        """Generate comprehensive validation report"""
        summary = self.report_generator.generate(
            state["validation_results"],
            state["schedule_metadata"],
            state["flights_to_validate"]
        )

        state["validation_summary"] = summary

        logger.info("Validation report generated")

        return state

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _format_result(self, state: ValidationState) -> Dict[str, Any]:
        """Format final result for API response"""
        return {
            "schedule_id": state["schedule_id"],
            "status": state["overall_status"],
            "summary": state["validation_summary"],
            "validation_results": state["validation_results"],
            "schedule_metadata": state["schedule_metadata"],
            "performance": {
                "flights_validated": len(state["flights_to_validate"]),
                "validation_duration_ms": state["validation_duration_ms"],
                "llm_tokens_used": state["llm_tokens_used"],
                "llm_calls_made": state["llm_calls_made"]
            },
            "validated_at": state["validation_end_time"].isoformat() if state["validation_end_time"] else None
        }
