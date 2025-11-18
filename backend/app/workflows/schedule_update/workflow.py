"""
Weekly Schedule Update Workflow
Orchestrates all scheduling agents using LangGraph SupervisorAgent pattern
"""

from typing import TypedDict, List, Dict, Any, Annotated, Literal
from datetime import datetime, timedelta
import operator
import uuid
import json
import logging

from langgraph.graph import StateGraph, END
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


class ScheduleUpdateState(TypedDict):
    """Global state for weekly schedule update workflow"""
    workflow_id: str
    schedule_season: str  # W25, S25, etc.
    airline_code: str
    ssm_messages: List[Dict[str, Any]]
    parsed_flights: List[Dict[str, Any]]
    validation_results: Dict[str, Any]
    conflicts: List[Dict[str, Any]]
    resolutions: List[Dict[str, Any]]
    fleet_assignments: Dict[str, Any]
    crew_feasibility: Dict[str, Any]
    slot_allocations: Dict[str, Any]
    distribution_status: Dict[str, Any]
    current_agent: str
    messages: Annotated[List[Dict[str, Any]], operator.add]
    next_agent: str
    workflow_status: str  # running, completed, failed
    error_message: str


class WeeklyScheduleUpdateWorkflow:
    """
    Complete weekly schedule update workflow orchestrator

    Coordinates execution of all scheduling agents:
    1. SSM Parser - Parse incoming schedule messages
    2. Validation - Validate schedule against constraints
    3. Conflict Resolution - Resolve detected conflicts
    4. Fleet Assignment - Assign aircraft to flights
    5. Crew Feasibility - Validate crew availability
    6. Slot Compliance - Ensure airport slot compliance
    7. Distribution - Publish to GDS/OTA channels

    Uses LangGraph SupervisorAgent pattern for intelligent orchestration.
    """

    def __init__(
        self,
        db_connection,
        neo4j_driver=None,
        llm_model: str = "claude-sonnet-4-20250514"
    ):
        self.db = db_connection
        self.neo4j = neo4j_driver
        self.supervisor_llm = ChatAnthropic(model=llm_model, temperature=0)

        # Import agents (lazy loading to avoid circular imports)
        from ..agents.ssm_parser import SSMParserAgent
        from ..agents.schedule_validation import ScheduleValidationAgent

        # Initialize agents
        self.ssm_parser = SSMParserAgent(db_connection, neo4j_driver)
        self.validator = ScheduleValidationAgent(db_connection)

        # Placeholder for agents to be implemented
        self.conflict_resolver = None  # ConflictResolutionAgent
        self.fleet_agent = None  # FleetAssignmentAgent
        self.crew_agent = None  # CrewFeasibilityAgent
        self.slot_agent = None  # SlotComplianceAgent
        self.distribution_agent = None  # DistributionAgent

        # Build workflow graph
        self.graph = self._build_workflow_graph()

    def _build_workflow_graph(self) -> StateGraph:
        """
        Build LangGraph workflow with SupervisorAgent pattern

        Flow:
        - Supervisor decides which agent runs next
        - Each agent executes and reports back to supervisor
        - Supervisor evaluates results and routes to next agent or END
        """
        workflow = StateGraph(ScheduleUpdateState)

        # Add supervisor node
        workflow.add_node("supervisor", self.supervisor_agent)

        # Add agent nodes
        workflow.add_node("ssm_parser", self.run_ssm_parser)
        workflow.add_node("validator", self.run_validator)
        workflow.add_node("conflict_resolver", self.run_conflict_resolver)
        workflow.add_node("fleet_assignment", self.run_fleet_assignment)
        workflow.add_node("crew_feasibility", self.run_crew_feasibility)
        workflow.add_node("slot_compliance", self.run_slot_compliance)
        workflow.add_node("distribution", self.run_distribution)

        # Supervisor is the entry point
        workflow.set_entry_point("supervisor")

        # All agents report back to supervisor
        workflow.add_edge("ssm_parser", "supervisor")
        workflow.add_edge("validator", "supervisor")
        workflow.add_edge("conflict_resolver", "supervisor")
        workflow.add_edge("fleet_assignment", "supervisor")
        workflow.add_edge("crew_feasibility", "supervisor")
        workflow.add_edge("slot_compliance", "supervisor")
        workflow.add_edge("distribution", "supervisor")

        # Supervisor routes to next agent or finishes
        workflow.add_conditional_edges(
            "supervisor",
            self.route_supervisor_decision,
            {
                "ssm_parser": "ssm_parser",
                "validator": "validator",
                "conflict_resolver": "conflict_resolver",
                "fleet_assignment": "fleet_assignment",
                "crew_feasibility": "crew_feasibility",
                "slot_compliance": "slot_compliance",
                "distribution": "distribution",
                "FINISH": END
            }
        )

        return workflow.compile()

    def supervisor_agent(self, state: ScheduleUpdateState) -> ScheduleUpdateState:
        """
        Supervisor Agent - Decides which agent to invoke next

        Uses Claude to analyze workflow state and make intelligent
        routing decisions based on:
        - What has been completed
        - What issues were found
        - Dependencies between agents
        - Optimization opportunities (parallel execution)
        """
        logger.info(f"Supervisor evaluating workflow {state['workflow_id']}")

        # Build comprehensive context
        context = self._build_workflow_context(state)

        # Create supervisor prompt
        system_prompt = """You are the Supervisor Agent for an airline weekly schedule update workflow.
Your job is to decide which agent should run next based on the current workflow state.

Available Agents:
1. ssm_parser - Parse incoming SSM/SSIM schedule messages
2. validator - Validate schedule against all constraints (slots, aircraft, crew, MCT, curfews, regulatory, routing, patterns)
3. conflict_resolver - Resolve detected schedule conflicts
4. fleet_assignment - Optimize aircraft assignments
5. crew_feasibility - Validate crew availability and compliance
6. slot_compliance - Ensure airport slot compliance
7. distribution - Publish schedule to GDS/OTA channels

Workflow Rules:
- SSM Parser must run first to ingest messages
- Validator runs after parser completes
- If validator finds conflicts, Conflict Resolver must run
- Fleet/Crew/Slot agents can run after conflicts are resolved (or if no conflicts)
- Distribution runs last when all validations pass with no critical issues
- If any agent fails critically, workflow should FINISH with error

Analyze the current state and decide the next agent."""

        user_prompt = f"""Current Workflow State:
- Workflow ID: {state['workflow_id']}
- Schedule Season: {state['schedule_season']}
- Airline: {state['airline_code']}
- Status: {state.get('workflow_status', 'running')}

Progress:
- SSM Messages: {len(state.get('ssm_messages', []))}
- Parsed Flights: {len(state.get('parsed_flights', []))}
- Validation Complete: {state.get('validation_results') is not None}
- Conflicts Detected: {len(state.get('conflicts', []))}
- Conflicts Resolved: {len(state.get('resolutions', []))}
- Fleet Assignments: {state.get('fleet_assignments') is not None}
- Crew Validated: {state.get('crew_feasibility') is not None}
- Slots Validated: {state.get('slot_allocations') is not None}
- Distribution Complete: {state.get('distribution_status') is not None}

Current Phase: {context['current_phase']}
Progress: {context['progress']['percent_complete']}%

Recent Agent Messages (last 3):
{json.dumps(state.get('messages', [])[-3:], indent=2) if state.get('messages') else "None"}

Critical Issues:
{self._format_critical_issues(state)}

Decide which agent should run next, or if workflow is complete.

Respond with JSON only:
{{
    "next_agent": "agent_name or FINISH",
    "reasoning": "brief explanation of decision",
    "estimated_time_minutes": 5
}}"""

        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            response = self.supervisor_llm.invoke(messages)

            # Parse decision
            decision = json.loads(response.content)

            state["next_agent"] = decision["next_agent"]
            state["current_agent"] = "supervisor"

            # Log decision
            state["messages"].append({
                "agent": "supervisor",
                "timestamp": datetime.utcnow().isoformat(),
                "decision": decision,
                "workflow_phase": context['current_phase']
            })

            logger.info(
                f"Supervisor decision: {decision['next_agent']} - "
                f"{decision['reasoning']}"
            )

        except Exception as e:
            logger.error(f"Supervisor decision error: {e}")
            state["next_agent"] = "FINISH"
            state["workflow_status"] = "failed"
            state["error_message"] = f"Supervisor error: {str(e)}"

        return state

    def route_supervisor_decision(
        self, state: ScheduleUpdateState
    ) -> Literal["ssm_parser", "validator", "conflict_resolver", "fleet_assignment",
                 "crew_feasibility", "slot_compliance", "distribution", "FINISH"]:
        """Route to next agent based on supervisor decision"""
        return state["next_agent"]

    # ===================================================================
    # Agent Execution Wrappers
    # ===================================================================

    def run_ssm_parser(self, state: ScheduleUpdateState) -> ScheduleUpdateState:
        """Execute SSM Parser Agent"""
        logger.info(
            f"Running SSM Parser - {len(state.get('ssm_messages', []))} messages"
        )

        start_time = datetime.utcnow()
        state["current_agent"] = "ssm_parser"

        try:
            # Process all SSM messages
            parsed_results = []
            errors = []

            for msg in state.get("ssm_messages", []):
                try:
                    result = self.ssm_parser.process(msg["content"])
                    if result["status"] == "success":
                        parsed_results.append(result["parsed_data"])
                    else:
                        errors.append({
                            "message_id": msg.get("id"),
                            "error": result.get("error")
                        })
                except Exception as e:
                    errors.append({
                        "message_id": msg.get("id"),
                        "error": str(e)
                    })

            # Update state
            state["parsed_flights"] = parsed_results
            execution_time = (datetime.utcnow() - start_time).total_seconds()

            # Log execution
            self._log_agent_execution(
                workflow_id=state["workflow_id"],
                agent_name="ssm_parser",
                status="completed",
                execution_time_ms=int(execution_time * 1000),
                output_summary=f"Parsed {len(parsed_results)} flights, {len(errors)} errors"
            )

            state["messages"].append({
                "agent": "ssm_parser",
                "timestamp": datetime.utcnow().isoformat(),
                "status": "completed",
                "parsed_flights": len(parsed_results),
                "errors": len(errors),
                "execution_time_seconds": execution_time
            })

        except Exception as e:
            logger.error(f"SSM Parser failed: {e}", exc_info=True)
            state["messages"].append({
                "agent": "ssm_parser",
                "timestamp": datetime.utcnow().isoformat(),
                "status": "failed",
                "error": str(e)
            })

        return state

    def run_validator(self, state: ScheduleUpdateState) -> ScheduleUpdateState:
        """Execute Schedule Validation Agent"""
        logger.info(
            f"Running Validator - {len(state.get('parsed_flights', []))} flights"
        )

        start_time = datetime.utcnow()
        state["current_agent"] = "validator"

        try:
            # Run validation
            validation_result = self.validator.validate(
                schedule_id=state["workflow_id"],
                flights=state.get("parsed_flights", [])
            )

            state["validation_results"] = validation_result

            # Extract conflicts (critical issues)
            all_issues = validation_result.get("all_issues", [])
            state["conflicts"] = [
                i for i in all_issues
                if i.get("severity") in ("critical", "high")
            ]

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            # Log execution
            self._log_agent_execution(
                workflow_id=state["workflow_id"],
                agent_name="validator",
                status="completed",
                execution_time_ms=int(execution_time * 1000),
                output_summary=f"Found {len(all_issues)} issues, {len(state['conflicts'])} conflicts"
            )

            state["messages"].append({
                "agent": "validator",
                "timestamp": datetime.utcnow().isoformat(),
                "status": "completed",
                "total_issues": len(all_issues),
                "critical_issues": len([i for i in all_issues if i.get("severity") == "critical"]),
                "high_issues": len([i for i in all_issues if i.get("severity") == "high"]),
                "conflicts": len(state["conflicts"]),
                "execution_time_seconds": execution_time
            })

        except Exception as e:
            logger.error(f"Validator failed: {e}", exc_info=True)
            state["messages"].append({
                "agent": "validator",
                "timestamp": datetime.utcnow().isoformat(),
                "status": "failed",
                "error": str(e)
            })

        return state

    def run_conflict_resolver(self, state: ScheduleUpdateState) -> ScheduleUpdateState:
        """Execute Conflict Resolution Agent"""
        logger.info(f"Running Conflict Resolver - {len(state.get('conflicts', []))} conflicts")

        start_time = datetime.utcnow()
        state["current_agent"] = "conflict_resolver"

        try:
            if not self.conflict_resolver:
                # Agent not yet implemented - placeholder
                logger.warning("Conflict Resolver agent not implemented yet")
                state["resolutions"] = []
                state["messages"].append({
                    "agent": "conflict_resolver",
                    "timestamp": datetime.utcnow().isoformat(),
                    "status": "skipped",
                    "reason": "Agent not implemented"
                })
                return state

            # Run conflict resolution
            resolution_result = self.conflict_resolver.resolve(
                conflicts=state.get("conflicts", [])
            )

            state["resolutions"] = resolution_result.get("resolutions", [])

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            state["messages"].append({
                "agent": "conflict_resolver",
                "timestamp": datetime.utcnow().isoformat(),
                "status": "completed",
                "conflicts_resolved": len(state["resolutions"]),
                "execution_time_seconds": execution_time
            })

        except Exception as e:
            logger.error(f"Conflict Resolver failed: {e}", exc_info=True)
            state["messages"].append({
                "agent": "conflict_resolver",
                "timestamp": datetime.utcnow().isoformat(),
                "status": "failed",
                "error": str(e)
            })

        return state

    def run_fleet_assignment(self, state: ScheduleUpdateState) -> ScheduleUpdateState:
        """Execute Fleet Assignment Agent"""
        logger.info("Running Fleet Assignment Agent")

        start_time = datetime.utcnow()
        state["current_agent"] = "fleet_assignment"

        try:
            if not self.fleet_agent:
                # Agent not yet implemented - placeholder
                logger.warning("Fleet Assignment agent not implemented yet")
                state["fleet_assignments"] = {"status": "skipped"}
                state["messages"].append({
                    "agent": "fleet_assignment",
                    "timestamp": datetime.utcnow().isoformat(),
                    "status": "skipped",
                    "reason": "Agent not implemented"
                })
                return state

            # Run fleet assignment
            fleet_result = self.fleet_agent.assign(
                flights=state.get("parsed_flights", [])
            )

            state["fleet_assignments"] = fleet_result

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            state["messages"].append({
                "agent": "fleet_assignment",
                "timestamp": datetime.utcnow().isoformat(),
                "status": "completed",
                "execution_time_seconds": execution_time
            })

        except Exception as e:
            logger.error(f"Fleet Assignment failed: {e}", exc_info=True)
            state["messages"].append({
                "agent": "fleet_assignment",
                "timestamp": datetime.utcnow().isoformat(),
                "status": "failed",
                "error": str(e)
            })

        return state

    def run_crew_feasibility(self, state: ScheduleUpdateState) -> ScheduleUpdateState:
        """Execute Crew Feasibility Agent"""
        logger.info("Running Crew Feasibility Agent")

        start_time = datetime.utcnow()
        state["current_agent"] = "crew_feasibility"

        try:
            if not self.crew_agent:
                # Agent not yet implemented - placeholder
                logger.warning("Crew Feasibility agent not implemented yet")
                state["crew_feasibility"] = {"status": "skipped"}
                state["messages"].append({
                    "agent": "crew_feasibility",
                    "timestamp": datetime.utcnow().isoformat(),
                    "status": "skipped",
                    "reason": "Agent not implemented"
                })
                return state

            # Run crew feasibility check
            crew_result = self.crew_agent.validate(
                flights=state.get("parsed_flights", [])
            )

            state["crew_feasibility"] = crew_result

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            state["messages"].append({
                "agent": "crew_feasibility",
                "timestamp": datetime.utcnow().isoformat(),
                "status": "completed",
                "execution_time_seconds": execution_time
            })

        except Exception as e:
            logger.error(f"Crew Feasibility failed: {e}", exc_info=True)
            state["messages"].append({
                "agent": "crew_feasibility",
                "timestamp": datetime.utcnow().isoformat(),
                "status": "failed",
                "error": str(e)
            })

        return state

    def run_slot_compliance(self, state: ScheduleUpdateState) -> ScheduleUpdateState:
        """Execute Slot Compliance Agent"""
        logger.info("Running Slot Compliance Agent")

        start_time = datetime.utcnow()
        state["current_agent"] = "slot_compliance"

        try:
            if not self.slot_agent:
                # Agent not yet implemented - placeholder
                logger.warning("Slot Compliance agent not implemented yet")
                state["slot_allocations"] = {"status": "skipped"}
                state["messages"].append({
                    "agent": "slot_compliance",
                    "timestamp": datetime.utcnow().isoformat(),
                    "status": "skipped",
                    "reason": "Agent not implemented"
                })
                return state

            # Run slot compliance check
            slot_result = self.slot_agent.validate(
                flights=state.get("parsed_flights", [])
            )

            state["slot_allocations"] = slot_result

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            state["messages"].append({
                "agent": "slot_compliance",
                "timestamp": datetime.utcnow().isoformat(),
                "status": "completed",
                "execution_time_seconds": execution_time
            })

        except Exception as e:
            logger.error(f"Slot Compliance failed: {e}", exc_info=True)
            state["messages"].append({
                "agent": "slot_compliance",
                "timestamp": datetime.utcnow().isoformat(),
                "status": "failed",
                "error": str(e)
            })

        return state

    def run_distribution(self, state: ScheduleUpdateState) -> ScheduleUpdateState:
        """Execute Distribution Agent"""
        logger.info("Running Distribution Agent")

        start_time = datetime.utcnow()
        state["current_agent"] = "distribution"

        try:
            if not self.distribution_agent:
                # Agent not yet implemented - placeholder
                logger.warning("Distribution agent not implemented yet")
                state["distribution_status"] = {"status": "skipped"}
                state["messages"].append({
                    "agent": "distribution",
                    "timestamp": datetime.utcnow().isoformat(),
                    "status": "skipped",
                    "reason": "Agent not implemented"
                })
                return state

            # Run distribution
            distribution_result = self.distribution_agent.publish(
                schedule_season=state["schedule_season"],
                flights=state.get("parsed_flights", [])
            )

            state["distribution_status"] = distribution_result

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            state["messages"].append({
                "agent": "distribution",
                "timestamp": datetime.utcnow().isoformat(),
                "status": "completed",
                "execution_time_seconds": execution_time
            })

        except Exception as e:
            logger.error(f"Distribution failed: {e}", exc_info=True)
            state["messages"].append({
                "agent": "distribution",
                "timestamp": datetime.utcnow().isoformat(),
                "status": "failed",
                "error": str(e)
            })

        return state

    # ===================================================================
    # Utility Methods
    # ===================================================================

    def _build_workflow_context(self, state: ScheduleUpdateState) -> Dict[str, Any]:
        """Build comprehensive workflow context for supervisor"""
        total_agents = 7
        completed_agents = len([
            m for m in state.get("messages", [])
            if m.get("status") == "completed" and m.get("agent") != "supervisor"
        ])

        return {
            "progress": {
                "completed_agents": completed_agents,
                "total_agents": total_agents,
                "percent_complete": int((completed_agents / total_agents) * 100)
            },
            "current_phase": self._determine_phase(state),
            "estimated_completion_time": self._estimate_completion(state)
        }

    def _determine_phase(self, state: ScheduleUpdateState) -> str:
        """Determine current workflow phase"""
        if not state.get("parsed_flights"):
            return "Parsing SSM Messages"
        elif not state.get("validation_results"):
            return "Validating Schedule"
        elif state.get("conflicts") and not state.get("resolutions"):
            return "Resolving Conflicts"
        elif not state.get("fleet_assignments"):
            return "Assigning Fleet & Crew"
        elif not state.get("distribution_status"):
            return "Publishing Schedule"
        else:
            return "Complete"

    def _estimate_completion(self, state: ScheduleUpdateState) -> str:
        """Estimate workflow completion time"""
        # Simple estimation based on remaining agents
        messages = state.get("messages", [])
        if not messages:
            return "2-4 hours"

        completed = len([m for m in messages if m.get("status") == "completed"])
        remaining = 7 - completed

        minutes = remaining * 15  # Assume 15 min per agent
        return f"{minutes} minutes"

    def _format_critical_issues(self, state: ScheduleUpdateState) -> str:
        """Format critical issues for supervisor prompt"""
        validation_results = state.get("validation_results")
        if not validation_results:
            return "No validation results yet"

        all_issues = validation_results.get("all_issues", [])
        critical = [i for i in all_issues if i.get("severity") == "critical"]

        if not critical:
            return "No critical issues"

        formatted = []
        for i, issue in enumerate(critical[:5], 1):
            formatted.append(
                f"{i}. {issue.get('issue_type')}: {issue.get('description')}"
            )

        if len(critical) > 5:
            formatted.append(f"... and {len(critical) - 5} more critical issues")

        return "\n".join(formatted)

    def _log_agent_execution(
        self,
        workflow_id: str,
        agent_name: str,
        status: str,
        execution_time_ms: int,
        output_summary: str
    ):
        """Log agent execution to database"""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                INSERT INTO agent_executions (
                    workflow_id, agent_name, status,
                    execution_time_ms, output_summary,
                    executed_at
                )
                VALUES (%s, %s, %s, %s, %s, NOW())
            """, (workflow_id, agent_name, status, execution_time_ms, output_summary))
            self.db.commit()
            cursor.close()
        except Exception as e:
            logger.error(f"Failed to log agent execution: {e}")

    # ===================================================================
    # Public API
    # ===================================================================

    def execute(self, initial_state: ScheduleUpdateState) -> ScheduleUpdateState:
        """Execute workflow synchronously"""
        logger.info(f"Starting workflow {initial_state['workflow_id']}")

        try:
            # Record workflow start
            self._record_workflow_start(initial_state)

            # Execute graph
            final_state = self.graph.invoke(initial_state)

            # Record workflow completion
            self._record_workflow_completion(final_state)

            return final_state

        except Exception as e:
            logger.error(f"Workflow execution failed: {e}", exc_info=True)
            initial_state["workflow_status"] = "failed"
            initial_state["error_message"] = str(e)
            self._record_workflow_completion(initial_state)
            raise

    async def execute_async(
        self, initial_state: ScheduleUpdateState
    ) -> ScheduleUpdateState:
        """Execute workflow asynchronously"""
        logger.info(f"Starting async workflow {initial_state['workflow_id']}")

        try:
            # Record workflow start
            self._record_workflow_start(initial_state)

            # Execute graph
            final_state = await self.graph.ainvoke(initial_state)

            # Record workflow completion
            self._record_workflow_completion(final_state)

            return final_state

        except Exception as e:
            logger.error(f"Async workflow execution failed: {e}", exc_info=True)
            initial_state["workflow_status"] = "failed"
            initial_state["error_message"] = str(e)
            self._record_workflow_completion(initial_state)
            raise

    def _record_workflow_start(self, state: ScheduleUpdateState):
        """Record workflow start in database"""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                INSERT INTO schedule_workflows (
                    workflow_id, workflow_type, schedule_season,
                    status, started_at
                )
                VALUES (%s, %s, %s, %s, NOW())
            """, (
                state["workflow_id"],
                "weekly_update",
                state["schedule_season"],
                "running"
            ))
            self.db.commit()
            cursor.close()
        except Exception as e:
            logger.error(f"Failed to record workflow start: {e}")

    def _record_workflow_completion(self, state: ScheduleUpdateState):
        """Record workflow completion in database"""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                UPDATE schedule_workflows
                SET status = %s,
                    completed_at = NOW(),
                    output_data = %s
                WHERE workflow_id = %s
            """, (
                state.get("workflow_status", "completed"),
                json.dumps({
                    "parsed_flights": len(state.get("parsed_flights", [])),
                    "conflicts": len(state.get("conflicts", [])),
                    "resolutions": len(state.get("resolutions", []))
                }),
                state["workflow_id"]
            ))
            self.db.commit()
            cursor.close()
        except Exception as e:
            logger.error(f"Failed to record workflow completion: {e}")
