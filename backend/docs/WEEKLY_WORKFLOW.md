# Weekly Schedule Update Workflow

Complete end-to-end orchestration system for airline schedule management using LangGraph SupervisorAgent pattern.

## Overview

The Weekly Schedule Update Workflow automatically processes SSM/SSIM messages, validates schedules, resolves conflicts, and publishes to distribution channels every Sunday at 22:00 UTC.

**Execution Time:** 2-4 hours (depending on schedule size)
**Frequency:** Weekly (every Sunday 22:00 UTC) or on-demand
**Success Rate:** Target 95%+

## Architecture

### SupervisorAgent Pattern

```
┌────────────────────────────────────────────────────────────┐
│                    SUPERVISOR AGENT                         │
│         (Claude Sonnet 4 - Intelligent Routing)            │
└─────────────┬──────────────────────────────┬───────────────┘
              │                              │
              ▼                              ▼
    ┌─────────────────┐            ┌─────────────────┐
    │  Agent Node 1   │            │  Agent Node 2   │
    │  (SSM Parser)   │            │  (Validator)    │
    └────────┬────────┘            └────────┬────────┘
             │                              │
             └──────────────┬───────────────┘
                            ▼
                     ┌─────────────┐
                     │  SUPERVISOR │ ← Routes to next agent
                     └─────────────┘
                            │
                            ▼
                     (Continues until FINISH)
```

### Workflow Agents

1. **SSM Parser** - Parse incoming SSM/SSIM messages
2. **Validator** - Validate schedule against 8 constraints
3. **Conflict Resolver** - Resolve detected conflicts
4. **Fleet Assignment** - Optimize aircraft assignments
5. **Crew Feasibility** - Validate crew availability
6. **Slot Compliance** - Ensure airport slot compliance
7. **Distribution** - Publish to GDS/OTA channels

## Workflow State

```python
class ScheduleUpdateState(TypedDict):
    workflow_id: str                    # Unique workflow ID
    schedule_season: str                # W25, S25, etc.
    airline_code: str                   # Airline code
    ssm_messages: List[dict]            # Input SSM messages
    parsed_flights: List[dict]          # Parsed flight data
    validation_results: dict            # Validation results
    conflicts: List[dict]               # Detected conflicts
    resolutions: List[dict]             # Applied resolutions
    fleet_assignments: dict             # Fleet assignments
    crew_feasibility: dict              # Crew validation
    slot_allocations: dict              # Slot allocations
    distribution_status: dict           # Distribution status
    current_agent: str                  # Currently executing agent
    messages: List[dict]                # Agent execution log
    next_agent: str                     # Next agent to execute
    workflow_status: str                # running/completed/failed
    error_message: str                  # Error if failed
```

## Execution Flow

### 1. Workflow Initialization

```python
from app.workflows.schedule_update import WeeklyScheduleUpdateWorkflow

# Initialize workflow
workflow = WeeklyScheduleUpdateWorkflow(db_connection, neo4j_driver)

# Create initial state
initial_state = ScheduleUpdateState(
    workflow_id=str(uuid.uuid4()),
    schedule_season="W25",
    airline_code="CM",
    ssm_messages=fetch_pending_ssm_messages(),
    next_agent="ssm_parser",
    workflow_status="running",
    messages=[]
)

# Execute workflow
final_state = await workflow.execute_async(initial_state)
```

### 2. Supervisor Decision Making

The Supervisor Agent uses Claude Sonnet 4 to make intelligent routing decisions:

```
Current State Analysis:
- What agents have completed?
- Were there any failures?
- What conflicts were detected?
- What dependencies exist?

Decision Factors:
- Sequential dependencies (parser → validator)
- Parallel opportunities (fleet + crew + slot)
- Error handling (retry vs rollback)
- Optimization (skip unnecessary agents)

Output:
- next_agent: "validator" | "conflict_resolver" | "FINISH"
- reasoning: "Why this agent should run next"
- estimated_time_minutes: 15
```

### 3. Agent Execution Wrapper

Each agent runs through a standardized wrapper:

```python
def run_agent(self, state: ScheduleUpdateState) -> ScheduleUpdateState:
    """Standard agent execution pattern"""

    # 1. Log execution start
    start_time = datetime.utcnow()
    logger.info(f"Running {agent_name}")

    try:
        # 2. Execute agent logic
        result = self.agent.execute(state)

        # 3. Update state
        state["agent_result"] = result

        # 4. Log success
        self._log_agent_execution(
            agent_name=agent_name,
            status="completed",
            execution_time_ms=(datetime.utcnow() - start_time).total_seconds() * 1000
        )

        # 5. Add message
        state["messages"].append({
            "agent": agent_name,
            "status": "completed",
            "timestamp": datetime.utcnow().isoformat()
        })

    except Exception as e:
        # 6. Handle error
        logger.error(f"{agent_name} failed: {e}")
        state["messages"].append({
            "agent": agent_name,
            "status": "failed",
            "error": str(e)
        })

    return state
```

### 4. Progress Tracking

Real-time progress is calculated based on completed agents:

```python
progress_percent = (completed_agents / total_agents) * 100

phases = {
    0: "Starting",
    1-2: "Parsing and Validation",
    3-4: "Conflict Resolution",
    5-6: "Fleet and Crew Assignment",
    7: "Distribution"
}
```

## Scheduled Execution

### Automatic Weekly Trigger

```python
from app.workflows.schedule_update.scheduler import start_scheduler

# Start scheduler
start_scheduler(db_connection, neo4j_driver)

# Runs every Sunday at 22:00 UTC
# Cron: 0 22 * * SUN
```

### Manual Trigger via API

```bash
# Start workflow manually
curl -X POST http://localhost:8000/api/schedules/workflows/start \
  -H "Content-Type: application/json" \
  -d '{
    "schedule_season": "W25",
    "airline_code": "CM"
  }'

# Returns:
{
  "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "started"
}
```

## API Endpoints

### POST /api/schedules/workflows/start

Start a new workflow.

**Request:**
```json
{
  "schedule_season": "W25",
  "airline_code": "CM",
  "ssm_messages": []  // optional
}
```

**Response:**
```json
{
  "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "started"
}
```

### GET /api/schedules/workflows/list

List all workflows with filtering.

**Query Parameters:**
- `status`: Filter by status (running, completed, failed)
- `season`: Filter by schedule season
- `limit`: Maximum results (default 50)
- `offset`: Pagination offset

**Response:**
```json
[
  {
    "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
    "schedule_season": "W25",
    "airline_code": "CM",
    "status": "running",
    "started_at": "2025-11-18T22:00:00Z",
    "progress_percent": 42,
    "current_phase": "Conflict Resolution"
  }
]
```

### GET /api/schedules/workflows/{workflow_id}

Get detailed workflow information.

**Response:**
```json
{
  "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
  "schedule_season": "W25",
  "status": "running",
  "progress_percent": 42,
  "current_phase": "Conflict Resolution",
  "messages": [
    {
      "agent": "ssm_parser",
      "status": "completed",
      "timestamp": "2025-11-18T22:05:00Z",
      "execution_time_seconds": 120
    },
    {
      "agent": "validator",
      "status": "completed",
      "timestamp": "2025-11-18T22:10:00Z",
      "execution_time_seconds": 180
    }
  ]
}
```

### GET /api/schedules/workflows/{workflow_id}/progress

Get real-time progress updates (for polling).

**Response:**
```json
{
  "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "progress_percent": 42,
  "current_phase": "Conflict Resolution",
  "current_agent": "conflict_resolver",
  "completed_agents": ["ssm_parser", "validator"],
  "pending_agents": ["fleet_assignment", "crew_feasibility", "slot_compliance", "distribution"],
  "estimated_completion_minutes": 90
}
```

### GET /api/schedules/workflows/{workflow_id}/summary

Get workflow execution summary.

**Response:**
```json
{
  "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
  "schedule_season": "W25",
  "status": "completed",
  "total_flights_parsed": 450,
  "conflicts_detected": 12,
  "conflicts_resolved": 12,
  "validation_summary": {
    "total_issues": 35,
    "critical_issues": 0
  },
  "execution_time_seconds": 7200,
  "agents_executed": [
    "ssm_parser",
    "validator",
    "conflict_resolver",
    "fleet_assignment",
    "crew_feasibility",
    "slot_compliance",
    "distribution"
  ]
}
```

### POST /api/schedules/workflows/{workflow_id}/cancel

Cancel a running workflow.

### POST /api/schedules/workflows/{workflow_id}/retry

Retry a failed workflow.

## Error Handling

### Automatic Rollback

When a workflow fails, automatic rollback is triggered:

```python
rollback_actions = {
    "revert_parsed_flights": "Mark SSM messages as failed",
    "revert_conflict_resolutions": "Undo applied resolutions",
    "revert_fleet_assignments": "Clear temporary assignments",
    "revert_distribution": "Unpublish from GDS/OTA"
}
```

### Retry Logic

Retryable errors (network, timeout) trigger automatic retry:

```python
retryable_errors = [
    "ConnectionError",
    "TimeoutError",
    "OperationalError"
]

if is_retryable(error):
    schedule_retry(workflow_id, delay_minutes=30)
```

### Failure Alerts

Critical failures trigger immediate alerts:

```
⚠️ WORKFLOW FAILURE ALERT

Workflow ID: 550e8400-e29b-41d4-a716-446655440000
Season: W25
Error: Validation failed with 5 critical issues

Rollback Actions Completed:
  ✓ reverted parsed flights (120 messages)
  ✓ reverted conflict resolutions (8 resolutions)

Action Required:
  - Review validation issues
  - Fix underlying problems
  - Retry workflow when ready
```

## Performance

### Typical Execution Times

| Agent | Typical Time | Max Time |
|-------|-------------|----------|
| SSM Parser | 2-5 min | 15 min |
| Validator | 3-8 min | 20 min |
| Conflict Resolver | 10-30 min | 60 min |
| Fleet Assignment | 15-45 min | 90 min |
| Crew Feasibility | 10-20 min | 45 min |
| Slot Compliance | 5-10 min | 30 min |
| Distribution | 20-60 min | 120 min |
| **Total** | **65-178 min** | **380 min** |

### Optimization

Agents that can run in parallel:
- Fleet Assignment + Crew Feasibility + Slot Compliance

This reduces total time by ~30-60 minutes.

## Monitoring

### Database Tables

```sql
-- Main workflow tracking
CREATE TABLE schedule_workflows (
    workflow_id UUID PRIMARY KEY,
    workflow_type VARCHAR(50),
    schedule_season VARCHAR(10),
    status VARCHAR(20),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    output_data JSONB,
    error_message TEXT,
    rollback_actions JSONB
);

-- Agent execution tracking
CREATE TABLE agent_executions (
    execution_id UUID PRIMARY KEY,
    workflow_id UUID REFERENCES schedule_workflows(workflow_id),
    agent_name VARCHAR(100),
    status VARCHAR(20),
    execution_time_ms INTEGER,
    output_summary TEXT,
    executed_at TIMESTAMP
);
```

### Metrics

Key metrics to monitor:
- Workflow success rate
- Average execution time
- Agent failure rate
- Conflict resolution rate
- Distribution success rate

### Alerts

Set up alerts for:
- Workflow failures (immediate)
- Execution time > 6 hours (warning)
- Critical validation issues unresolved (high priority)
- Distribution failures (critical)

## Integration Tests

Run integration tests:

```bash
# Run all workflow tests
pytest backend/tests/integration/test_workflow.py -v

# Run specific test
pytest backend/tests/integration/test_workflow.py::TestWeeklyScheduleWorkflow::test_workflow_full_execution_mock -v

# Run with coverage
pytest backend/tests/integration/test_workflow.py --cov=app.workflows
```

## Production Deployment

### Environment Variables

```bash
# Database
DB_HOST=localhost
DB_NAME=airline_scheduling
DB_USER=postgres
DB_PASSWORD=<password>

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<password>

# LLM
ANTHROPIC_API_KEY=<key>

# Scheduler
SCHEDULE_CRON_DAY=sun
SCHEDULE_CRON_HOUR=22
SCHEDULE_CRON_MINUTE=0
```

### Start Services

```bash
# Start scheduler
python -m app.workflows.schedule_update.scheduler

# Start API server
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Start monitoring dashboard
cd frontend && npm run dev
```

### Docker Deployment

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Start scheduler and API
CMD ["python", "-m", "app.main"]
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  scheduler:
    build: .
    environment:
      - DB_HOST=postgres
      - NEO4J_URI=bolt://neo4j:7687
    depends_on:
      - postgres
      - neo4j

  postgres:
    image: postgres:15
    volumes:
      - postgres_data:/var/lib/postgresql/data

  neo4j:
    image: neo4j:5
    volumes:
      - neo4j_data:/data

volumes:
  postgres_data:
  neo4j_data:
```

## Troubleshooting

### Workflow Stuck

If workflow appears stuck:

```python
# Check workflow status
GET /api/schedules/workflows/{workflow_id}/progress

# Check last agent executed
SELECT * FROM agent_executions
WHERE workflow_id = '<workflow_id>'
ORDER BY executed_at DESC
LIMIT 5;

# Cancel if needed
POST /api/schedules/workflows/{workflow_id}/cancel
```

### Agent Failures

If specific agent keeps failing:

1. Check agent logs
2. Review error message
3. Check database connectivity
4. Verify input data quality
5. Retry with corrected data

### Performance Issues

If workflow takes too long:

1. Check database query performance
2. Review SSM message volume
3. Check conflict complexity
4. Consider parallel execution
5. Optimize agent implementations

## Future Enhancements

1. **Parallel Agent Execution**
   - Run Fleet + Crew + Slot in parallel
   - Reduce total execution time by 30-40%

2. **Incremental Updates**
   - Process only changed flights
   - Skip validation for unchanged data
   - Faster daily updates

3. **Predictive Scheduling**
   - AI-powered conflict prediction
   - Proactive resolution suggestions
   - Reduced manual intervention

4. **Real-time WebSocket Updates**
   - Live progress streaming
   - Dashboard auto-refresh
   - Mobile notifications

5. **Advanced Rollback**
   - Granular rollback by agent
   - Partial retry from failure point
   - State snapshots for recovery

## Support

For issues or questions:
- Check logs: `/var/log/airline-scheduling/`
- Review metrics: Grafana dashboard
- Contact: devops@airline.com

## References

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [SSM Parser Agent](./SSM_PARSER_AGENT.md)
- [Schedule Validation Agent](./SCHEDULE_VALIDATION_AGENT.md)
- [IATA Standards](https://www.iata.org/en/publications/manuals/)
