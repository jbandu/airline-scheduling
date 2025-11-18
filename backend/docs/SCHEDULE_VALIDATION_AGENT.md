# Schedule Validation Agent

Multi-constraint validation for airline flight schedules using LangGraph and LLM-enhanced analysis.

## Overview

The Schedule Validation Agent validates airline flight schedules against 8 comprehensive validation categories, running them in parallel for optimal performance. It uses Claude for intelligent conflict analysis and provides actionable recommendations.

## Architecture

### LangGraph Workflow

```
┌─────────────────┐
│  Load Schedule  │
└────────┬────────┘
         │
         ├──────────────┬──────────────┬──────────────┬──────────────┐
         │              │              │              │              │
         ▼              ▼              ▼              ▼              ▼
  ┌────────────┐ ┌──────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
  │   Slots    │ │ Aircraft │ │    Crew    │ │    MCT     │ │  Curfew    │
  │ Validation │ │Validation│ │ Validation │ │ Validation │ │ Validation │
  └────────────┘ └──────────┘ └────────────┘ └────────────┘ └────────────┘
         │              │              │              │              │
         │              ▼              ▼              ▼              │
         │       ┌──────────┐ ┌────────────┐ ┌────────────┐       │
         │       │Regulatory│ │  Routing   │ │  Pattern   │       │
         │       │Validation│ │ Validation │ │ Validation │       │
         │       └──────────┘ └────────────┘ └────────────┘       │
         │              │              │              │              │
         └──────────────┴──────────────┴──────────────┴──────────────┘
                               │
                               ▼
                      ┌─────────────────┐
                      │ Compile Results │
                      └────────┬────────┘
                               │
                               ▼
                      ┌─────────────────┐
                      │  LLM Analysis   │
                      └────────┬────────┘
                               │
                               ▼
                      ┌─────────────────┐
                      │ Generate Report │
                      └─────────────────┘
```

## Validation Categories

### 1. Airport Slot Validation

Validates airport slot allocations per IATA WSG standards.

**Checks:**
- Slot exists at Level 3 coordinated airports
- Slot time matches scheduled time (±5 min tolerance)
- Slot is confirmed by coordinator
- Historical rights are maintained

**Critical Airports:**
- LHR, JFK, LAX, HND, NRT, CDG, FRA, AMS, LGA, ORD, DCA, SFO, BOS, EWR, PHL, DEN, FCO, MAD, BCN, ZRH, MUC, SIN, HKG, ICN

**Example Issues:**
- Missing slot at coordinated airport (CRITICAL)
- Slot time mismatch (HIGH)
- Slot not confirmed (MEDIUM)

### 2. Aircraft Availability Validation

Validates aircraft are available and properly routed.

**Checks:**
- Aircraft exists and is active in fleet
- Aircraft type matches flight requirements
- No maintenance conflicts
- Sufficient turnaround time (45-90 min by type)
- Routing continuity (arrival airport = next departure)
- Daily utilization within limits (max 16 hours)

**Turnaround Times:**
- Narrow body (A320, B737): 45 minutes
- Wide body (A330, B777, B787): 90 minutes
- Regional (E190, CRJ): 30 minutes

**Example Issues:**
- Aircraft not found (CRITICAL)
- Routing discontinuity (CRITICAL)
- Insufficient turnaround (HIGH)
- Excessive daily utilization (MEDIUM)

### 3. Crew Feasibility Validation

Validates crew availability and regulatory compliance per FAA/EASA.

**Checks:**
- Minimum crew complement (2 pilots + cabin crew)
- Aircraft type ratings and certifications
- Flight Duty Period (FDP) limits (10-13 hours by sectors)
- Rest requirements (minimum 12 hours)
- Monthly hour limits (100 hours)
- Yearly hour limits (1000 hours)
- Crew base proximity

**FDP Limits:**
- 1-2 sectors: 13 hours
- 3 sectors: 12.5 hours
- 4 sectors: 12 hours
- 5 sectors: 11.5 hours
- 6 sectors: 11 hours
- 7+ sectors: 10 hours

**Example Issues:**
- Insufficient pilots/cabin crew (CRITICAL)
- Missing type rating (CRITICAL)
- FDP exceeded (CRITICAL)
- Insufficient rest (CRITICAL/HIGH)
- Monthly hours exceeded (CRITICAL)

### 4. Minimum Connect Time (MCT) Validation

Validates passenger connection times between flights.

**Checks:**
- Connection time meets airport MCT
- Domestic vs international connection requirements
- Terminal change time (if applicable)
- Interline connection buffer
- Baggage re-check time
- Immigration/customs processing time

**Default MCT:**
- Domestic-Domestic: 45 minutes
- Domestic-International: 75 minutes
- International-Domestic: 90 minutes
- International-International: 60 minutes
- Terminal change: +20 minutes
- Interline: +15 minutes
- Baggage re-check: +30 minutes

**Example Issues:**
- Insufficient connection time (HIGH)
- Tight connection (MEDIUM)

### 5. Airport Curfew Validation

Validates flights against airport operating hours and noise curfews.

**Checks:**
- Airport operating hours compliance
- Noise curfew restrictions
- Night movement quota limits
- Aircraft noise category requirements
- Curfew exemptions (if applicable)

**Airports with Strict Curfews:**
- LHR: 23:00-06:00
- SYD: 23:00-06:00
- FRA: 23:00-05:00
- ZRH: 23:30-06:00
- DCA: 22:00-07:00

**Example Issues:**
- Outside operating hours (CRITICAL)
- Curfew violation (CRITICAL/HIGH)
- Night movement quota exceeded (HIGH)
- Noise category violation (HIGH)

### 6. Regulatory Compliance Validation

Validates aviation regulatory requirements and bilateral agreements.

**Checks:**
- Traffic rights (freedoms of the air)
- Bilateral air service agreements
- Cabotage restrictions
- Frequency limitations
- Designated carrier status
- Wet lease approvals
- Code-share approvals

**Freedoms of the Air:**
1. Overflight
2. Technical stop
3. Discharge passengers from home country
4. Pick up passengers to home country
5. Carry traffic between foreign countries
6. Carry via home country
7. Carry between foreign countries without touching home
8. Cabotage (domestic within foreign country)

**Example Issues:**
- Missing traffic rights (CRITICAL)
- Cabotage violation (CRITICAL)
- Not designated carrier (CRITICAL)
- Frequency limit exceeded (HIGH)

### 7. Aircraft Routing Validation

Validates aircraft routing efficiency and feasibility.

**Checks:**
- Routing chain continuity
- Circular routing patterns (returns to base)
- Aircraft range limitations
- Fuel stops (if required)
- Hub connectivity
- Positioning flight efficiency

**Aircraft Ranges (nautical miles):**
- A320: 3,300 nm
- B737-800: 3,100 nm
- A330: 6,350 nm
- B777-200: 7,730 nm
- B787: 7,355 nm

**Example Issues:**
- Routing discontinuity (CRITICAL)
- Range exceeded (CRITICAL)
- Non-circular routing (MEDIUM)
- Inefficient positioning (LOW)

### 8. Schedule Pattern Validation

Validates schedule patterns and consistency.

**Checks:**
- Operating days format (1234567 or X)
- Frequency per week matches operating days
- Equipment consistency for same flight number
- Hub bank structures
- Schedule symmetry (outbound/inbound balance)
- Seasonal schedule variations
- No overlapping effective dates

**Example Issues:**
- Invalid operating days format (CRITICAL)
- No operating days (HIGH)
- Frequency mismatch (MEDIUM)
- Inconsistent equipment (MEDIUM)
- Schedule asymmetry (MEDIUM)
- Overlapping effective dates (HIGH)

## LLM-Enhanced Analysis

The agent uses Claude to provide:

1. **Root Cause Analysis**
   - Identifies patterns across multiple issues
   - Groups related problems
   - Suggests systemic fixes

2. **Business Impact Assessment**
   - Revenue impact
   - Operational impact
   - Regulatory impact

3. **Resolution Priority**
   - Which issues to fix first
   - Dependencies between issues
   - Resource allocation guidance

4. **Actionable Recommendations**
   - Specific steps to resolve issues
   - Timeline estimates
   - Alternative solutions

## API Endpoints

### POST /api/schedules/validation/validate

Validate a schedule against all constraints.

**Request:**
```json
{
  "schedule_id": "schedule-001",
  "airline_code": "CM",
  "validation_options": {}
}
```

**Response:**
```json
{
  "schedule_id": "schedule-001",
  "status": "failed",
  "total_flights": 45,
  "total_issues": 12,
  "critical_issues": 3,
  "high_issues": 5,
  "medium_issues": 3,
  "low_issues": 1,
  "validation_complete": true,
  "summary": "⚠️ CRITICAL: 3 blocking issues must be resolved..."
}
```

### GET /api/schedules/validation/results/{schedule_id}

Get detailed validation results.

**Response:**
```json
{
  "schedule_id": "schedule-001",
  "all_issues": [...],
  "analysis_result": {
    "summary": "...",
    "root_causes": [...],
    "recommendations": [...]
  }
}
```

### GET /api/schedules/validation/issues/{schedule_id}

Get validation issues with filtering.

**Query Parameters:**
- `severity`: Filter by severity (critical, high, medium, low)
- `category`: Filter by category
- `limit`: Maximum results (default 100)
- `offset`: Pagination offset

### POST /api/schedules/validation/report

Generate validation report.

**Request:**
```json
{
  "schedule_id": "schedule-001",
  "format": "markdown"
}
```

**Formats:**
- `json`: Machine-readable JSON
- `markdown`: Human-readable Markdown
- `html`: Web-friendly HTML with styling
- `csv`: Tabular CSV for spreadsheet import

### GET /api/schedules/validation/categories

Get information about all validation categories.

### POST /api/schedules/validation/bulk-validate

Validate multiple schedules in batch.

## Usage Example

### Python

```python
from app.agents.schedule_validation import ScheduleValidationAgent

# Initialize agent
agent = ScheduleValidationAgent(
    db_connection=db_conn,
    llm_model="claude-sonnet-4-20250514"
)

# Validate schedule
result = agent.validate(schedule_id="schedule-001")

# Check results
if result["validation_complete"]:
    critical_issues = [
        i for i in result["all_issues"]
        if i["severity"] == "critical"
    ]

    if critical_issues:
        print(f"❌ {len(critical_issues)} critical issues found")
        for issue in critical_issues:
            print(f"  - {issue['description']}")
            print(f"    Action: {issue['recommended_action']}")
    else:
        print("✓ No critical issues")

# Get analysis
analysis = result["analysis_result"]
print(f"\nSummary: {analysis['summary']}")

print("\nRecommendations:")
for rec in analysis["recommendations"]:
    print(f"  - {rec['title']} ({rec['priority']})")
```

### REST API (cURL)

```bash
# Validate schedule
curl -X POST http://localhost:8000/api/schedules/validation/validate \
  -H "Content-Type: application/json" \
  -d '{
    "schedule_id": "schedule-001",
    "airline_code": "CM"
  }'

# Get validation report (Markdown)
curl -X POST http://localhost:8000/api/schedules/validation/report \
  -H "Content-Type: application/json" \
  -d '{
    "schedule_id": "schedule-001",
    "format": "markdown"
  }' > validation_report.md

# Get critical issues only
curl "http://localhost:8000/api/schedules/validation/issues/schedule-001?severity=critical"
```

## Performance

- **Parallel Execution**: All 8 validators run concurrently
- **Typical Validation Time**: 2-5 seconds for 50 flights
- **LLM Analysis Time**: 3-8 seconds for complex issues
- **Total Time**: ~5-15 seconds end-to-end

## File Structure

```
backend/app/agents/schedule_validation/
├── __init__.py
├── agent.py                        # Main LangGraph agent
├── conflict_analyzer.py            # LLM-enhanced analysis
├── report_generator.py             # Report formatting
└── validators/
    ├── __init__.py
    ├── slot_validator.py           # Airport slot validation
    ├── aircraft_validator.py       # Aircraft availability
    ├── crew_validator.py           # Crew feasibility
    ├── mct_validator.py            # Minimum connect time
    ├── curfew_validator.py         # Airport hours/curfew
    ├── regulatory_validator.py     # Regulatory compliance
    ├── routing_validator.py        # Aircraft routing
    └── pattern_validator.py        # Schedule patterns
```

## Dependencies

- `langgraph>=0.2.45` - Multi-agent orchestration
- `langchain-anthropic>=0.3.7` - Claude LLM integration
- `psycopg2-binary>=2.9.10` - PostgreSQL database
- `pydantic>=2.10.3` - Data validation

## Future Enhancements

1. **Real-time Validation**
   - WebSocket support for live validation
   - Incremental validation as changes are made

2. **Auto-Fix Suggestions**
   - LLM-generated schedule adjustments
   - One-click issue resolution

3. **Historical Analytics**
   - Track validation trends over time
   - Identify recurring issues

4. **Custom Validation Rules**
   - Airline-specific validation rules
   - Configurable thresholds

5. **Integration with Conflict Resolution Agent**
   - Automatic conflict resolution
   - Optimization suggestions

## Support

For issues or questions, see backend/docs/TROUBLESHOOTING.md
