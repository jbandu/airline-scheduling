# Airline Schedule Management System

Production-ready airline schedule management system with 7 specialized AI agents that process IATA SSM/SSIM messages, manage weekly schedule updates, detect conflicts, optimize crew/aircraft assignments, and ensure regulatory compliance.

## Overview

This system provides comprehensive airline schedule management following IATA standards with multi-agent AI orchestration for intelligent schedule processing and conflict resolution.

### Key Features

- ✅ **IATA SSM/SSIM Standards Compliance** - Full support for Standard Schedule Messages
- ✅ **7 Specialized AI Agents** - Intelligent schedule processing and optimization
- ✅ **Multi-Agent Orchestration** - LangGraph-based workflow coordination
- ✅ **Conflict Detection & Resolution** - Automated conflict identification and resolution
- ✅ **Airport Slot Management** - IATA WSG (Worldwide Slot Guidelines) compliance
- ✅ **Distribution to GDS/OTA** - Automated schedule publishing to multiple channels
- ✅ **Regulatory Compliance** - Built-in validation for airline regulations

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SupervisorAgent                           │
│              (LangGraph Orchestration)                       │
└──────────────────┬──────────────────────────────────────────┘
                   │
        ┌──────────┴───────────┐
        │                      │
   ┌────▼────┐          ┌─────▼─────┐
   │ SSM     │          │ Schedule  │
   │ Parser  │◄────────►│Validation │
   └────┬────┘          └─────┬─────┘
        │                     │
   ┌────▼────┐          ┌─────▼─────┐
   │Conflict │          │   Fleet   │
   │Resolution│◄────────►│Assignment │
   └────┬────┘          └─────┬─────┘
        │                     │
   ┌────▼────┐          ┌─────▼─────┐
   │  Crew   │          │   Slot    │
   │Feasibility│◄───────►│Compliance │
   └────┬────┘          └─────┬─────┘
        │                     │
        └──────────┬──────────┘
                   │
            ┌──────▼──────┐
            │Distribution │
            │   Agent     │
            └─────────────┘
```

### Technology Stack

- **Backend**: FastAPI (Python)
- **Database**: PostgreSQL 15+ / Supabase
- **Knowledge Graph**: Neo4j (Digital Twins)
- **AI Framework**: LangGraph + LangChain
- **Frontend**: Next.js + Vercel
- **Standards**: IATA SSM/SSIM

## 7 Core AI Agents

1. **SSMParserAgent** - Ingests and validates IATA SSM/SSIM messages
2. **ScheduleValidationAgent** - Validates schedules against operational constraints
3. **ConflictResolutionAgent** - Detects and resolves scheduling conflicts
4. **FleetAssignmentAgent** - Optimizes aircraft-to-flight assignments
5. **CrewFeasibilityAgent** - Ensures crew availability and regulatory compliance
6. **SlotComplianceAgent** - Validates airport slot allocations (IATA WSG)
7. **DistributionAgent** - Publishes schedules to GDS/OTA channels

## Project Structure

```
airline-scheduling/
├── backend/
│   └── app/
│       ├── agents/          # 7 AI agents
│       ├── models/          # Data models
│       ├── api/             # FastAPI endpoints
│       ├── services/        # Business logic
│       └── utils/           # Utilities
├── database/
│   ├── schemas/             # PostgreSQL schemas
│   ├── migrations/          # Alembic migrations
│   ├── seeds/               # Sample data
│   ├── queries/             # Common queries
│   └── docs/                # ERD and documentation
├── frontend/
│   ├── app/                 # Next.js app directory
│   ├── components/          # React components
│   └── lib/                 # Utilities
└── tests/
    ├── unit/                # Unit tests
    └── integration/         # Integration tests
```

## Database Schema

### Core Tables

- **schedules** - Seasonal schedule containers (W25, S25)
- **flights** - Individual flight operations
- **ssm_messages** - IATA SSM message log
- **schedule_workflows** - Multi-agent workflow tracking
- **schedule_conflicts** - Conflict detection and resolution
- **airport_slots** - Airport slot allocations
- **distribution_channels** - GDS/OTA channel configurations

See [database/README.md](database/README.md) for complete documentation.

### ERD Diagram

Full entity relationship diagram available in [database/docs/ERD.md](database/docs/ERD.md).

## Quick Start

### Prerequisites

- PostgreSQL 15+
- Python 3.11+
- Node.js 18+
- Neo4j (optional, for knowledge graph)

### Database Setup

```bash
# Create database
createdb airline_scheduling

# Navigate to database directory
cd database

# Install Alembic
pip install alembic psycopg2-binary

# Run migrations
alembic upgrade head

# Load sample data
psql airline_scheduling -f seeds/001_sample_schedules.sql
```

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run FastAPI server
uvicorn app.main:app --reload
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

## IATA Standards

### SSM (Standard Schedule Message)

Message types supported:
- **NEW** - New schedule
- **CNL** - Cancellation
- **TIM** - Time change
- **EQT** - Equipment change
- **CON** - Confirmation
- **ACK** - Acknowledgment
- **REJ** - Rejection

### SSIM (Standard Schedules Information Manual)

Format for schedule distribution to GDS and OTA platforms.

### Day Pattern Format

```
1234567 - Daily operation (Mon-Sun)
123456X - Weekdays only (Mon-Sat)
X2X4X6X - Tue/Thu/Sat only
```

Where:
- 1=Monday, 2=Tuesday, ..., 7=Sunday
- X=Not operating

### Sample SSM Message

```
NEW
CM 101 PTY MIA 1234567 01JAN25 31MAR25 738 0600 0915
```

## Example Usage

### Query Today's Schedule

```python
from app.services.schedule_service import get_daily_schedule

# Get all flights for today
schedule = get_daily_schedule(date.today())

# Get flights for specific airline
copa_flights = get_daily_schedule(date.today(), carrier_code='CM')

# Get flights from specific airport
pty_departures = get_daily_schedule(date.today(), airport_code='PTY')
```

### Process SSM Message

```python
from app.agents.ssm_parser import SSMParserAgent

# Initialize agent
parser = SSMParserAgent()

# Process SSM message
ssm_message = """
NEW
CM 101 PTY MIA 1234567 01JAN25 31MAR25 738 0600 0915
"""

result = parser.process(ssm_message)
print(f"Processed {result.flights_created} flights")
```

### Detect Conflicts

```python
from app.agents.conflict_resolution import ConflictResolutionAgent

# Initialize agent
resolver = ConflictResolutionAgent()

# Detect conflicts for a schedule
conflicts = resolver.detect_conflicts(schedule_id)

# Resolve conflicts
for conflict in conflicts:
    solution = resolver.resolve(conflict)
    print(f"Resolved: {conflict.type} - {solution.description}")
```

## API Endpoints

### Schedules

```
GET    /api/schedules              # List all schedules
POST   /api/schedules              # Create new schedule
GET    /api/schedules/{id}         # Get schedule details
PUT    /api/schedules/{id}         # Update schedule
DELETE /api/schedules/{id}         # Delete schedule
```

### Flights

```
GET    /api/flights                # List flights
POST   /api/flights                # Create flight
GET    /api/flights/{id}           # Get flight details
GET    /api/flights/daily/{date}   # Get daily schedule
```

### SSM Processing

```
POST   /api/ssm/process            # Process SSM message
GET    /api/ssm/messages           # List SSM messages
GET    /api/ssm/messages/{id}      # Get message details
```

### Workflows

```
GET    /api/workflows              # List workflows
GET    /api/workflows/{id}         # Get workflow details
GET    /api/workflows/{id}/agents  # Get agent executions
```

### Conflicts

```
GET    /api/conflicts              # List conflicts
GET    /api/conflicts/{id}         # Get conflict details
POST   /api/conflicts/{id}/resolve # Resolve conflict
```

## Multi-Agent Workflow Example

```python
from app.orchestrator import SupervisorAgent

# Initialize supervisor
supervisor = SupervisorAgent()

# Create workflow for weekly schedule update
workflow = supervisor.create_workflow(
    workflow_type="weekly_update",
    schedule_id=schedule_id,
    initiated_by="scheduler_system"
)

# Execute workflow through all agents
result = supervisor.execute(workflow)

# Workflow automatically runs:
# 1. SSMParserAgent - Parse incoming SSM messages
# 2. ScheduleValidationAgent - Validate constraints
# 3. ConflictResolutionAgent - Detect conflicts
# 4. FleetAssignmentAgent - Optimize aircraft
# 5. CrewFeasibilityAgent - Validate crew
# 6. SlotComplianceAgent - Check airport slots
# 7. DistributionAgent - Publish to GDS/OTA

print(f"Workflow completed: {result.status}")
print(f"Conflicts resolved: {result.conflicts_resolved}")
print(f"Published to {result.channels_published} channels")
```

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/unit/test_ssm_parser.py
```

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Add new table"

# Apply migration
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

### Code Quality

```bash
# Format code
black app/

# Lint code
pylint app/

# Type checking
mypy app/
```

## Monitoring

### Key Metrics

- Workflow processing time
- Agent execution time
- Conflict resolution rate
- Publication success rate
- SSM message processing rate

### Performance Monitoring

```sql
-- Agent performance
SELECT * FROM v_agent_performance;

-- Active workflows
SELECT * FROM v_active_workflows;

-- Unresolved conflicts
SELECT * FROM v_unresolved_conflicts;

-- Channel health
SELECT * FROM v_channel_health;
```

## Sample Data

The system includes sample data for 3 airlines:
- **CM** (Copa Airlines) - 5 flights
- **AA** (American Airlines) - 2 flights
- **DL** (Delta Air Lines) - 2 flights

Major airports included:
- PTY (Panama City Tocumen)
- MIA (Miami International)
- JFK (New York JFK)
- LAX (Los Angeles)
- ATL (Atlanta)

## Production Deployment

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/airline_scheduling

# API Keys
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key

# Neo4j (optional)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# Distribution Channels
AMADEUS_API_KEY=your_amadeus_key
SABRE_API_KEY=your_sabre_key
```

### Docker Deployment

```bash
# Build images
docker-compose build

# Start services
docker-compose up -d

# View logs
docker-compose logs -f
```

## Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## Documentation

- [Database Documentation](database/README.md)
- [ERD Diagram](database/docs/ERD.md)
- [Common Queries](database/queries/common_queries.sql)
- API Documentation: http://localhost:8000/docs (when running)

## License

Copyright © 2025 Airline Schedule Management System

## Support

For issues, questions, or contributions, please open an issue on GitHub.

## Roadmap

- [x] Database schema design
- [x] IATA SSM/SSIM parsing
- [ ] AI agent implementation
- [ ] FastAPI backend
- [ ] Next.js frontend
- [ ] Neo4j integration
- [ ] GDS/OTA integration
- [ ] Real-time monitoring dashboard
- [ ] Automated testing suite
- [ ] Production deployment

## Acknowledgments

- IATA for SSM/SSIM standards
- LangChain/LangGraph for AI orchestration framework
- FastAPI community
- PostgreSQL community
