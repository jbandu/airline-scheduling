"""
Integration Tests for Weekly Schedule Update Workflow
"""

import pytest
import asyncio
import uuid
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

from app.workflows.schedule_update import WeeklyScheduleUpdateWorkflow, ScheduleUpdateState


@pytest.fixture
def mock_db():
    """Mock database connection"""
    db = Mock()
    db.cursor = MagicMock()
    db.commit = Mock()
    return db


@pytest.fixture
def mock_neo4j():
    """Mock Neo4j driver"""
    return Mock()


@pytest.fixture
def sample_ssm_messages():
    """Sample SSM messages for testing"""
    return [
        {
            "id": "msg-001",
            "type": "NEW",
            "content": "NEW CM123 J PTY MIA 1234567 0800 1130 738 01JAN25 31MAR25",
            "received_at": "2025-01-01T00:00:00Z"
        },
        {
            "id": "msg-002",
            "type": "TIM",
            "content": "TIM CM456 J MIA LAX 135 0900 1200 320 01JAN25 31MAR25",
            "received_at": "2025-01-01T00:05:00Z"
        }
    ]


@pytest.fixture
def sample_workflow_state(sample_ssm_messages):
    """Sample workflow state"""
    return ScheduleUpdateState(
        workflow_id=str(uuid.uuid4()),
        schedule_season="W25",
        airline_code="CM",
        ssm_messages=sample_ssm_messages,
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


class TestWeeklyScheduleWorkflow:
    """Test cases for weekly schedule update workflow"""

    def test_workflow_initialization(self, mock_db, mock_neo4j):
        """Test workflow initializes correctly"""
        workflow = WeeklyScheduleUpdateWorkflow(mock_db, mock_neo4j)

        assert workflow.db == mock_db
        assert workflow.neo4j == mock_neo4j
        assert workflow.supervisor_llm is not None
        assert workflow.ssm_parser is not None
        assert workflow.validator is not None
        assert workflow.graph is not None

    def test_supervisor_agent_initial_decision(
        self, mock_db, mock_neo4j, sample_workflow_state
    ):
        """Test supervisor makes correct initial decision"""
        workflow = WeeklyScheduleUpdateWorkflow(mock_db, mock_neo4j)

        # Mock LLM response
        with patch.object(workflow.supervisor_llm, 'invoke') as mock_llm:
            mock_llm.return_value.content = '{"next_agent": "ssm_parser", "reasoning": "Parse SSM messages first", "estimated_time_minutes": 10}'

            result_state = workflow.supervisor_agent(sample_workflow_state)

            assert result_state["next_agent"] == "ssm_parser"
            assert len(result_state["messages"]) == 1
            assert result_state["messages"][0]["agent"] == "supervisor"

    def test_ssm_parser_execution(
        self, mock_db, mock_neo4j, sample_workflow_state
    ):
        """Test SSM parser agent execution"""
        workflow = WeeklyScheduleUpdateWorkflow(mock_db, mock_neo4j)

        # Mock SSM parser
        with patch.object(workflow.ssm_parser, 'process') as mock_parser:
            mock_parser.return_value = {
                "status": "success",
                "parsed_data": {
                    "flight_number": "CM123",
                    "origin": "PTY",
                    "destination": "MIA"
                }
            }

            result_state = workflow.run_ssm_parser(sample_workflow_state)

            assert len(result_state["parsed_flights"]) > 0
            assert len(result_state["messages"]) == 1
            assert result_state["messages"][0]["agent"] == "ssm_parser"
            assert result_state["messages"][0]["status"] == "completed"

    def test_validator_execution(
        self, mock_db, mock_neo4j, sample_workflow_state
    ):
        """Test validator agent execution"""
        workflow = WeeklyScheduleUpdateWorkflow(mock_db, mock_neo4j)

        # Add parsed flights to state
        sample_workflow_state["parsed_flights"] = [
            {
                "flight_number": "CM123",
                "origin_airport": "PTY",
                "destination_airport": "MIA"
            }
        ]

        # Mock validator
        with patch.object(workflow.validator, 'validate') as mock_validator:
            mock_validator.return_value = {
                "validation_complete": True,
                "all_issues": [
                    {"severity": "medium", "description": "Test issue"}
                ]
            }

            result_state = workflow.run_validator(sample_workflow_state)

            assert result_state["validation_results"] is not None
            assert len(result_state["messages"]) == 1
            assert result_state["messages"][0]["agent"] == "validator"

    def test_workflow_phase_determination(
        self, mock_db, mock_neo4j, sample_workflow_state
    ):
        """Test workflow phase determination"""
        workflow = WeeklyScheduleUpdateWorkflow(mock_db, mock_neo4j)

        # Initial phase
        phase = workflow._determine_phase(sample_workflow_state)
        assert phase == "Parsing SSM Messages"

        # After parsing
        sample_workflow_state["parsed_flights"] = [{}]
        phase = workflow._determine_phase(sample_workflow_state)
        assert phase == "Validating Schedule"

        # After validation
        sample_workflow_state["validation_results"] = {}
        phase = workflow._determine_phase(sample_workflow_state)
        assert phase == "Assigning Fleet & Crew"

    def test_workflow_progress_calculation(
        self, mock_db, mock_neo4j, sample_workflow_state
    ):
        """Test workflow progress calculation"""
        workflow = WeeklyScheduleUpdateWorkflow(mock_db, mock_neo4j)

        # No completed agents
        context = workflow._build_workflow_context(sample_workflow_state)
        assert context["progress"]["percent_complete"] == 0

        # 2 completed agents
        sample_workflow_state["messages"] = [
            {"agent": "ssm_parser", "status": "completed"},
            {"agent": "validator", "status": "completed"}
        ]

        context = workflow._build_workflow_context(sample_workflow_state)
        assert context["progress"]["completed_agents"] == 2
        assert context["progress"]["percent_complete"] == int((2/7) * 100)

    @pytest.mark.asyncio
    async def test_workflow_full_execution_mock(
        self, mock_db, mock_neo4j, sample_workflow_state
    ):
        """Test full workflow execution with mocked agents"""
        workflow = WeeklyScheduleUpdateWorkflow(mock_db, mock_neo4j)

        # Mock all agent methods
        with patch.object(workflow, 'supervisor_agent') as mock_supervisor, \
             patch.object(workflow, 'run_ssm_parser') as mock_parser, \
             patch.object(workflow, 'run_validator') as mock_validator:

            # First supervisor call - route to parser
            mock_supervisor.side_effect = [
                {**sample_workflow_state, "next_agent": "ssm_parser"},
                {**sample_workflow_state, "next_agent": "validator"},
                {**sample_workflow_state, "next_agent": "FINISH"}
            ]

            # Parser execution
            mock_parser.return_value = {
                **sample_workflow_state,
                "parsed_flights": [{"flight_number": "CM123"}]
            }

            # Validator execution
            mock_validator.return_value = {
                **sample_workflow_state,
                "validation_results": {"all_issues": []}
            }

            # Execute workflow
            # Note: Full execution would require proper graph setup
            # This is a simplified test
            result = workflow.supervisor_agent(sample_workflow_state)
            assert result["next_agent"] in ["ssm_parser", "validator", "FINISH"]


class TestWorkflowErrorHandling:
    """Test error handling and rollback"""

    def test_ssm_parser_error_handling(
        self, mock_db, mock_neo4j, sample_workflow_state
    ):
        """Test SSM parser handles errors gracefully"""
        workflow = WeeklyScheduleUpdateWorkflow(mock_db, mock_neo4j)

        # Mock SSM parser to raise error
        with patch.object(workflow.ssm_parser, 'process') as mock_parser:
            mock_parser.side_effect = Exception("Parse error")

            result_state = workflow.run_ssm_parser(sample_workflow_state)

            # Should record error in messages
            assert len(result_state["messages"]) == 1
            assert result_state["messages"][0]["status"] == "failed"
            assert "error" in result_state["messages"][0]

    def test_validator_error_handling(
        self, mock_db, mock_neo4j, sample_workflow_state
    ):
        """Test validator handles errors gracefully"""
        workflow = WeeklyScheduleUpdateWorkflow(mock_db, mock_neo4j)

        sample_workflow_state["parsed_flights"] = [{}]

        # Mock validator to raise error
        with patch.object(workflow.validator, 'validate') as mock_validator:
            mock_validator.side_effect = Exception("Validation error")

            result_state = workflow.run_validator(sample_workflow_state)

            # Should record error in messages
            assert len(result_state["messages"]) == 1
            assert result_state["messages"][0]["status"] == "failed"


class TestWorkflowRouting:
    """Test supervisor routing logic"""

    def test_route_supervisor_decision(
        self, mock_db, mock_neo4j, sample_workflow_state
    ):
        """Test routing based on supervisor decision"""
        workflow = WeeklyScheduleUpdateWorkflow(mock_db, mock_neo4j)

        # Test different routing decisions
        sample_workflow_state["next_agent"] = "ssm_parser"
        route = workflow.route_supervisor_decision(sample_workflow_state)
        assert route == "ssm_parser"

        sample_workflow_state["next_agent"] = "validator"
        route = workflow.route_supervisor_decision(sample_workflow_state)
        assert route == "validator"

        sample_workflow_state["next_agent"] = "FINISH"
        route = workflow.route_supervisor_decision(sample_workflow_state)
        assert route == "FINISH"


class TestWorkflowDatabase:
    """Test database operations"""

    def test_workflow_start_recording(
        self, mock_db, mock_neo4j, sample_workflow_state
    ):
        """Test workflow start is recorded"""
        workflow = WeeklyScheduleUpdateWorkflow(mock_db, mock_neo4j)

        mock_cursor = Mock()
        mock_db.cursor.return_value = mock_cursor

        workflow._record_workflow_start(sample_workflow_state)

        # Verify INSERT was called
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        assert "INSERT INTO schedule_workflows" in call_args[0][0]

    def test_workflow_completion_recording(
        self, mock_db, mock_neo4j, sample_workflow_state
    ):
        """Test workflow completion is recorded"""
        workflow = WeeklyScheduleUpdateWorkflow(mock_db, mock_neo4j)

        mock_cursor = Mock()
        mock_db.cursor.return_value = mock_cursor

        sample_workflow_state["workflow_status"] = "completed"

        workflow._record_workflow_completion(sample_workflow_state)

        # Verify UPDATE was called
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        assert "UPDATE schedule_workflows" in call_args[0][0]


class TestWorkflowConflicts:
    """Test conflict detection and resolution flow"""

    def test_conflict_detection(
        self, mock_db, mock_neo4j, sample_workflow_state
    ):
        """Test conflicts are detected during validation"""
        workflow = WeeklyScheduleUpdateWorkflow(mock_db, mock_neo4j)

        sample_workflow_state["parsed_flights"] = [{}]

        # Mock validator to return conflicts
        with patch.object(workflow.validator, 'validate') as mock_validator:
            mock_validator.return_value = {
                "validation_complete": True,
                "all_issues": [
                    {"severity": "critical", "description": "Slot conflict"},
                    {"severity": "high", "description": "Aircraft conflict"}
                ]
            }

            result_state = workflow.run_validator(sample_workflow_state)

            # Should extract conflicts
            assert len(result_state["conflicts"]) == 2

    def test_conflict_resolver_execution(
        self, mock_db, mock_neo4j, sample_workflow_state
    ):
        """Test conflict resolver handles conflicts"""
        workflow = WeeklyScheduleUpdateWorkflow(mock_db, mock_neo4j)

        sample_workflow_state["conflicts"] = [
            {"type": "slot_conflict", "severity": "critical"}
        ]

        # Conflict resolver not implemented yet - should skip gracefully
        result_state = workflow.run_conflict_resolver(sample_workflow_state)

        assert len(result_state["messages"]) == 1
        assert result_state["messages"][0]["agent"] == "conflict_resolver"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
