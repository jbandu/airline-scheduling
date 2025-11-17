# Airline Schedule Management System - Database Documentation

## Overview

Production-ready PostgreSQL database schema for airline schedule management with IATA SSM/SSIM compliance and multi-agent workflow orchestration.

## Architecture

- **Database**: PostgreSQL 15+
- **Migration Tool**: Alembic
- **Standards**: IATA SSM, SSIM, WSG (Worldwide Slot Guidelines)
- **Pattern**: Multi-agent orchestration with LangGraph

## Quick Start

### 1. Setup Database

```bash
# Create database
createdb airline_scheduling

# Set connection string
export DATABASE_URL="postgresql://user:password@localhost:5432/airline_scheduling"
```

### 2. Run Migrations

```bash
cd database

# Install Alembic
pip install alembic psycopg2-binary

# Run migrations
alembic upgrade head
```

### 3. Load Sample Data

```bash
psql $DATABASE_URL -f seeds/001_sample_schedules.sql
```

## Schema Structure

### Core Tables (4 groups, 20+ tables)

#### 1. Core Schedule Management
- `schedules` - Seasonal schedule containers (W25, S25)
- `flights` - Individual flight operations
- `flight_legs` - Multi-segment flight details
- `ssm_messages` - IATA SSM message log
- `schedule_changes` - Complete audit trail

#### 2. Constraints & Validation
- `airport_slots` - IATA WSG slot allocations
- `airport_constraints` - Curfews, capacity limits
- `aircraft_availability` - Fleet availability tracking
- `minimum_connect_times` - MCT requirements
- `crew_bases` - Crew base locations
- `regulatory_requirements` - Compliance tracking

#### 3. Multi-Agent Workflow
- `schedule_workflows` - Workflow orchestration
- `agent_executions` - Agent execution logs (7 agents)
- `schedule_conflicts` - Conflict detection/resolution
- `agent_communications` - Inter-agent messaging
- `workflow_approvals` - Human-in-the-loop

#### 4. Distribution & Publishing
- `distribution_channels` - GDS/OTA configurations
- `schedule_publications` - Publication tracking
- `publication_flights` - Flight-level tracking
- `distribution_subscriptions` - Partner subscriptions
- `publication_confirmations` - ACK/NAK tracking

## Key Features

### IATA Standards Compliance

**SSM (Standard Schedule Message)**
- Message types: NEW, CNL, TIM, EQT, ACK, REJ
- Action codes: ADD, MOD, DEL, RPL
- Full message parsing and validation

**SSIM (Standard Schedules Information Manual)**
- Schedule distribution format
- GDS/OTA compatibility
- IATA day pattern: `1234567` (1=Mon, 7=Sun, X=Not operating)

**WSG (Worldwide Slot Guidelines)**
- Slot coordination levels (1, 2, 3)
- Historical rights (grandfather rights)
- 80/20 usage rule compliance

### Multi-Agent System (7 Agents)

1. **SSMParserAgent** - Ingest and validate SSM/SSIM messages
2. **ScheduleValidationAgent** - Validate against constraints
3. **ConflictResolutionAgent** - Detect/resolve conflicts
4. **FleetAssignmentAgent** - Optimize aircraft assignments
5. **CrewFeasibilityAgent** - Ensure crew availability
6. **SlotComplianceAgent** - Validate airport slots
7. **DistributionAgent** - Publish to GDS/OTA channels

### Advanced Functions

**SSM Parsing**
```sql
-- Parse operating days pattern
SELECT parse_ssm_operating_days('1234567');  -- Daily
SELECT parse_ssm_operating_days('X2X4X6X');  -- Tue/Thu/Sat

-- Check if flight operates on date
SELECT flight_operates_on_date('1234567', '2025-01-15', '2025-01-01', '2025-03-31');

-- Get all operating dates
SELECT * FROM get_operating_dates('123456X', '2025-01-01', '2025-01-31');
```

**Schedule Analysis**
```sql
-- Get daily schedule
SELECT * FROM get_daily_schedule('2025-01-15', 'CM', 'PTY');

-- Find connections
SELECT * FROM find_connecting_flights('MIA', 'LAX', '2025-01-15', 1);

-- Detect aircraft conflicts
SELECT * FROM detect_aircraft_conflicts('schedule-uuid');

-- Validate schedule quality
SELECT * FROM validate_schedule_data_quality('schedule-uuid');
```

**Workflow Management**
```sql
-- Get workflow summary
SELECT * FROM get_workflow_summary('workflow-uuid');

-- View active workflows
SELECT * FROM v_active_workflows;

-- Check unresolved conflicts
SELECT * FROM v_unresolved_conflicts;
```

## Data Model

See [ERD.md](docs/ERD.md) for complete entity relationship diagram.

### Sample Flight Record

```sql
{
  "flight_id": "uuid",
  "flight_number": "CM101",
  "carrier_code": "CM",
  "route": "PTY-MIA",
  "departure_time": "06:00",
  "arrival_time": "09:15",
  "operating_days": "1234567",  -- Daily
  "aircraft_type": "738",        -- Boeing 737-800
  "effective_from": "2025-01-01",
  "effective_to": "2025-03-31",
  "frequency_per_week": 7
}
```

### Sample SSM Message

```
NEW
CM 101 PTY MIA 1234567 01JAN25 31MAR25 738 0600 0915
```

## Database Files

```
database/
├── README.md                    # This file
├── alembic.ini                  # Alembic configuration
├── schemas/
│   ├── 001_core_schedule_tables.sql
│   ├── 002_constraint_validation_tables.sql
│   ├── 003_workflow_agent_tables.sql
│   ├── 004_distribution_publishing_tables.sql
│   └── 005_functions_utilities.sql
├── migrations/
│   ├── env.py
│   └── versions/
│       ├── 001_create_core_schedule_tables.py
│       ├── 002_create_constraint_validation_tables.py
│       ├── 003_create_workflow_agent_tables.py
│       ├── 004_create_distribution_publishing_tables.py
│       └── 005_create_functions_utilities.py
├── seeds/
│   └── 001_sample_schedules.sql
├── queries/
│   └── common_queries.sql
└── docs/
    └── ERD.md
```

## Common Operations

### Query Today's Schedule

```sql
SELECT
    carrier_code,
    flight_number,
    origin_airport,
    destination_airport,
    departure_time,
    aircraft_type
FROM flights f
JOIN schedules s ON f.schedule_id = s.schedule_id
WHERE s.status = 'active'
  AND flight_operates_on_date(
      operating_days,
      CURRENT_DATE,
      effective_from,
      effective_to
  )
ORDER BY departure_time;
```

### Create New Schedule

```sql
-- 1. Create schedule
INSERT INTO schedules (season_code, effective_from, effective_to, status, created_by)
VALUES ('W25', '2025-01-01', '2025-03-31', 'draft', 'system');

-- 2. Add flights
INSERT INTO flights (schedule_id, flight_number, carrier_code, ...)
VALUES (...);

-- 3. Validate
SELECT * FROM validate_schedule_data_quality('schedule-uuid');

-- 4. Publish schedule
UPDATE schedules SET status = 'active' WHERE schedule_id = 'schedule-uuid';
```

### Process SSM Message

```sql
-- 1. Insert SSM message
INSERT INTO ssm_messages (message_type, raw_message, sender_airline, ...)
VALUES ('NEW', 'SSM message text...', 'CM', ...);

-- 2. Create workflow
INSERT INTO schedule_workflows (workflow_type, initiated_by, ...)
VALUES ('ad_hoc_change', 'SSMParserAgent', ...);

-- 3. Process through agents
INSERT INTO agent_executions (workflow_id, agent_name, status, ...)
VALUES ('workflow-uuid', 'SSMParserAgent', 'running', ...);
```

### Detect Conflicts

```sql
-- Aircraft conflicts
SELECT * FROM detect_aircraft_conflicts('schedule-uuid');

-- Slot conflicts
SELECT
    slot_time,
    COUNT(*) as conflicts
FROM airport_slots
WHERE airport_code = 'PTY'
  AND confirmed = true
GROUP BY slot_time
HAVING COUNT(*) > 1;

-- MCT violations
WITH connections AS (...)
SELECT * FROM connections
WHERE actual_connect_time < required_mct;
```

## Performance Optimization

### Indexes

All tables have optimized indexes:
- B-tree indexes on foreign keys
- Composite indexes on common query patterns
- GIN indexes on JSONB columns
- GIN indexes on array columns

### Partitioning Recommendations

For high-volume tables:

```sql
-- Partition ssm_messages by month
CREATE TABLE ssm_messages_2025_01 PARTITION OF ssm_messages
FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

-- Partition agent_executions by week
CREATE TABLE agent_executions_2025_w01 PARTITION OF agent_executions
FOR VALUES FROM ('2025-01-01') TO ('2025-01-08');
```

### Materialized Views

```sql
-- Daily schedule cache
CREATE MATERIALIZED VIEW mv_daily_schedule AS
SELECT * FROM get_daily_schedule(CURRENT_DATE, NULL, NULL);

-- Refresh hourly
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_schedule;
```

## Monitoring

### Key Metrics to Track

```sql
-- Workflow processing time
SELECT
    workflow_type,
    AVG(EXTRACT(EPOCH FROM (completed_at - initiated_at))) as avg_duration_seconds
FROM schedule_workflows
WHERE completed_at IS NOT NULL
GROUP BY workflow_type;

-- Agent performance
SELECT * FROM v_agent_performance;

-- Conflict resolution rate
SELECT
    conflict_type,
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE resolution_status = 'resolved') as resolved,
    ROUND(100.0 * COUNT(*) FILTER (WHERE resolution_status = 'resolved') / COUNT(*), 2) as resolution_rate
FROM schedule_conflicts
GROUP BY conflict_type;

-- Publication success rate
SELECT
    dc.channel_name,
    COUNT(*) as total_publications,
    COUNT(*) FILTER (WHERE sp.status = 'published') as successful,
    ROUND(100.0 * COUNT(*) FILTER (WHERE sp.status = 'published') / COUNT(*), 2) as success_rate
FROM schedule_publications sp
JOIN distribution_channels dc ON sp.channel_id = dc.channel_id
WHERE sp.created_at >= NOW() - INTERVAL '7 days'
GROUP BY dc.channel_name;
```

## Backup & Recovery

```bash
# Full backup
pg_dump airline_scheduling > backup_$(date +%Y%m%d).sql

# Schema only
pg_dump --schema-only airline_scheduling > schema_backup.sql

# Data only
pg_dump --data-only airline_scheduling > data_backup.sql

# Restore
psql airline_scheduling < backup.sql
```

## Security Considerations

### Row-Level Security (RLS)

```sql
-- Enable RLS on sensitive tables
ALTER TABLE flights ENABLE ROW LEVEL SECURITY;

-- Airline can only see their flights
CREATE POLICY airline_flights_policy ON flights
FOR SELECT
USING (carrier_code = current_setting('app.airline_code'));
```

### Encryption

```sql
-- Enable pgcrypto for credential encryption
CREATE EXTENSION pgcrypto;

-- Encrypt distribution channel credentials
UPDATE distribution_channels
SET credentials_encrypted = pgp_sym_encrypt(credentials, 'encryption_key');
```

## Troubleshooting

### Common Issues

**Slow queries**
```sql
-- Check query plan
EXPLAIN ANALYZE SELECT ...;

-- Missing indexes
SELECT * FROM pg_stat_user_tables WHERE idx_scan = 0;
```

**Workflow stuck**
```sql
-- Find stuck workflows
SELECT * FROM schedule_workflows
WHERE status = 'in_progress'
  AND started_at < NOW() - INTERVAL '1 hour';

-- Check agent executions
SELECT * FROM agent_executions
WHERE status = 'running'
  AND started_at < NOW() - INTERVAL '30 minutes';
```

**Conflicts not resolving**
```sql
-- View unresolved conflicts
SELECT * FROM v_unresolved_conflicts
ORDER BY severity DESC;

-- Check conflict details
SELECT conflict_description, proposed_solutions
FROM schedule_conflicts
WHERE resolution_status = 'pending';
```

## Contributing

When modifying the schema:

1. Create new migration file
2. Update ERD diagram
3. Add example queries
4. Update this README
5. Test with sample data

## Support

For issues or questions:
- Check [common_queries.sql](queries/common_queries.sql) for examples
- Review [ERD.md](docs/ERD.md) for relationships
- See schema files for detailed comments

## License

Copyright © 2025 Airline Schedule Management System
