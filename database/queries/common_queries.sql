-- =====================================================
-- Common Query Examples
-- Airline Schedule Management System
-- =====================================================
-- Purpose: Frequently used queries for operations,
--          reporting, and troubleshooting
-- =====================================================

-- =====================================================
-- 1. DAILY OPERATIONS QUERIES
-- =====================================================

-- Get today's flight schedule
SELECT
    f.carrier_code,
    f.flight_number,
    f.origin_airport,
    f.destination_airport,
    f.departure_time,
    f.arrival_time,
    f.aircraft_type,
    f.seats_total
FROM flights f
JOIN schedules s ON f.schedule_id = s.schedule_id
WHERE s.status = 'active'
  AND flight_operates_on_date(
      f.operating_days,
      CURRENT_DATE,
      f.effective_from,
      f.effective_to
  )
ORDER BY f.departure_time;

-- Get flights departing from a specific airport today
SELECT
    carrier_code,
    flight_number,
    destination_airport,
    departure_time,
    aircraft_type
FROM get_daily_schedule(CURRENT_DATE, NULL, 'PTY')
ORDER BY departure_time;

-- Find flights operating on a specific date range
SELECT
    f.flight_number,
    f.origin_airport,
    f.destination_airport,
    od.operating_date,
    f.departure_time
FROM flights f
CROSS JOIN LATERAL get_operating_dates(
    f.operating_days,
    f.effective_from,
    f.effective_to,
    '2025-01-15',
    '2025-01-21'
) as od
WHERE f.carrier_code = 'CM'
ORDER BY od.operating_date, f.departure_time;

-- =====================================================
-- 2. SCHEDULE ANALYSIS QUERIES
-- =====================================================

-- Get schedule summary by airline
SELECT
    f.carrier_code,
    COUNT(DISTINCT f.flight_id) as total_flights,
    COUNT(DISTINCT f.origin_airport || '-' || f.destination_airport) as unique_routes,
    SUM(f.frequency_per_week) as weekly_departures,
    COUNT(DISTINCT f.aircraft_type) as aircraft_types_used
FROM flights f
JOIN schedules s ON f.schedule_id = s.schedule_id
WHERE s.status = 'active'
GROUP BY f.carrier_code
ORDER BY weekly_departures DESC;

-- Find most frequent routes
SELECT
    origin_airport,
    destination_airport,
    COUNT(*) as flight_count,
    SUM(frequency_per_week) as weekly_frequency,
    array_agg(DISTINCT carrier_code) as operating_carriers
FROM flights
WHERE schedule_id IN (SELECT schedule_id FROM schedules WHERE status = 'active')
GROUP BY origin_airport, destination_airport
ORDER BY weekly_frequency DESC
LIMIT 20;

-- Analyze aircraft utilization
SELECT
    aircraft_type,
    COUNT(*) as flights_count,
    SUM(frequency_per_week) as weekly_operations,
    AVG(seats_total) as avg_capacity
FROM flights
WHERE schedule_id IN (SELECT schedule_id FROM schedules WHERE status = 'active')
GROUP BY aircraft_type
ORDER BY weekly_operations DESC;

-- =====================================================
-- 3. CONNECTION QUERIES
-- =====================================================

-- Find possible connections between two cities
SELECT * FROM find_connecting_flights('MIA', 'LAX', '2025-01-15', 1)
ORDER BY total_journey_time;

-- Find all flights connecting through a hub
SELECT
    f1.flight_number as inbound_flight,
    f1.origin_airport as from_airport,
    f1.arrival_time as inbound_arrival,
    f2.flight_number as outbound_flight,
    f2.destination_airport as to_airport,
    f2.departure_time as outbound_departure,
    EXTRACT(EPOCH FROM (f2.departure_time - f1.arrival_time))::INTEGER / 60 as connection_time_minutes
FROM flights f1
JOIN flights f2 ON f1.destination_airport = f2.origin_airport
WHERE f1.destination_airport = 'PTY'  -- Panama City hub
  AND f2.departure_time > f1.arrival_time
  AND (f2.departure_time - f1.arrival_time) BETWEEN INTERVAL '45 minutes' AND INTERVAL '6 hours'
  AND f1.carrier_code = 'CM'
  AND f2.carrier_code = 'CM'
ORDER BY f1.origin_airport, f2.destination_airport;

-- =====================================================
-- 4. CONFLICT DETECTION QUERIES
-- =====================================================

-- Detect potential aircraft conflicts
SELECT * FROM detect_aircraft_conflicts(
    '550e8400-e29b-41d4-a716-446655440001'  -- W25 schedule
)
ORDER BY conflict_date, conflict_time;

-- Find flights with insufficient turnaround time
WITH flight_pairs AS (
    SELECT
        f1.flight_id as flight_1_id,
        f1.flight_number as flight_1,
        f1.destination_airport as airport,
        f1.arrival_time as arrival,
        f2.flight_id as flight_2_id,
        f2.flight_number as flight_2,
        f2.departure_time as departure,
        f2.departure_time - f1.arrival_time as turnaround_time,
        f1.aircraft_registration
    FROM flights f1
    JOIN flights f2 ON
        f1.destination_airport = f2.origin_airport
        AND f1.aircraft_registration = f2.aircraft_registration
        AND f2.departure_time > f1.arrival_time
    WHERE f1.aircraft_registration IS NOT NULL
)
SELECT *
FROM flight_pairs
WHERE turnaround_time < INTERVAL '45 minutes'
ORDER BY turnaround_time;

-- Check for slot conflicts at an airport
SELECT
    slot_time,
    slot_type,
    COUNT(*) as allocations,
    array_agg(allocated_to_airline) as airlines
FROM airport_slots
WHERE airport_code = 'PTY'
  AND slot_time::date = '2025-01-15'
  AND confirmed = true
GROUP BY slot_time, slot_type
HAVING COUNT(*) > 1;

-- =====================================================
-- 5. WORKFLOW & AGENT QUERIES
-- =====================================================

-- Get active workflows with progress
SELECT * FROM v_active_workflows
ORDER BY initiated_at DESC;

-- View workflow execution details
SELECT
    w.workflow_name,
    ae.agent_name,
    ae.status,
    ae.started_at,
    ae.completed_at,
    ae.execution_time_ms,
    ae.tokens_used
FROM schedule_workflows w
JOIN agent_executions ae ON w.workflow_id = ae.workflow_id
WHERE w.workflow_id = 'd50e8400-e29b-41d4-a716-446655440001'
ORDER BY ae.execution_sequence;

-- Get unresolved conflicts
SELECT * FROM v_unresolved_conflicts
ORDER BY severity DESC, resolution_priority DESC;

-- Agent performance summary
SELECT * FROM v_agent_performance
ORDER BY total_executions DESC;

-- Find failed agent executions
SELECT
    ae.agent_name,
    ae.started_at,
    ae.error_message,
    w.workflow_name
FROM agent_executions ae
JOIN schedule_workflows w ON ae.workflow_id = w.workflow_id
WHERE ae.status = 'failed'
  AND ae.started_at >= NOW() - INTERVAL '24 hours'
ORDER BY ae.started_at DESC;

-- =====================================================
-- 6. DISTRIBUTION & PUBLISHING QUERIES
-- =====================================================

-- Get publication status by channel
SELECT
    dc.channel_name,
    sp.status,
    COUNT(*) as publication_count
FROM schedule_publications sp
JOIN distribution_channels dc ON sp.channel_id = dc.channel_id
WHERE sp.created_at >= NOW() - INTERVAL '7 days'
GROUP BY dc.channel_name, sp.status
ORDER BY dc.channel_name, sp.status;

-- View channel health
SELECT * FROM v_channel_health
ORDER BY consecutive_failures DESC, channel_name;

-- Find failed publications
SELECT
    sp.publication_id,
    dc.channel_name,
    sp.publication_type,
    sp.created_at,
    sp.status_message,
    sp.retry_count
FROM schedule_publications sp
JOIN distribution_channels dc ON sp.channel_id = dc.channel_id
WHERE sp.status = 'failed'
  AND sp.created_at >= NOW() - INTERVAL '24 hours'
ORDER BY sp.created_at DESC;

-- Get publication statistics for a schedule
SELECT * FROM get_publication_stats('550e8400-e29b-41d4-a716-446655440001');

-- =====================================================
-- 7. COMPLIANCE & VALIDATION QUERIES
-- =====================================================

-- Check curfew compliance
SELECT
    f.flight_number,
    f.origin_airport,
    f.destination_airport,
    f.departure_time,
    f.arrival_time,
    check_curfew_violation(f.destination_airport, f.arrival_time, CURRENT_DATE) as has_violation
FROM flights f
WHERE f.schedule_id IN (SELECT schedule_id FROM schedules WHERE status = 'active')
  AND check_curfew_violation(f.destination_airport, f.arrival_time, CURRENT_DATE) = true;

-- Validate schedule data quality
SELECT * FROM validate_schedule_data_quality('550e8400-e29b-41d4-a716-446655440001')
WHERE status = 'FAIL';

-- Check MCT compliance for connections
WITH connections AS (
    SELECT
        f1.destination_airport as connect_airport,
        f2.departure_time - f1.arrival_time as actual_connect_time,
        get_minimum_connect_time(
            f1.destination_airport,
            NULL,
            NULL,
            'international_international'::connection_type
        ) as required_mct
    FROM flights f1
    JOIN flights f2 ON f1.destination_airport = f2.origin_airport
    WHERE f1.carrier_code = 'CM'
      AND f2.carrier_code = 'CM'
      AND f2.departure_time > f1.arrival_time
)
SELECT *
FROM connections
WHERE EXTRACT(EPOCH FROM actual_connect_time) / 60 < required_mct;

-- =====================================================
-- 8. REPORTING QUERIES
-- =====================================================

-- Daily departure summary by airport
SELECT
    f.origin_airport,
    COUNT(*) as total_departures,
    COUNT(DISTINCT f.carrier_code) as airlines,
    MIN(f.departure_time) as first_departure,
    MAX(f.departure_time) as last_departure
FROM flights f
WHERE flight_operates_on_date(
    f.operating_days,
    CURRENT_DATE,
    f.effective_from,
    f.effective_to
)
GROUP BY f.origin_airport
ORDER BY total_departures DESC;

-- Weekly capacity report
SELECT
    f.carrier_code,
    SUM(f.seats_total * f.frequency_per_week) as weekly_seat_capacity,
    SUM(f.seats_business * f.frequency_per_week) as weekly_business_seats,
    SUM(f.seats_economy * f.frequency_per_week) as weekly_economy_seats
FROM flights f
JOIN schedules s ON f.schedule_id = s.schedule_id
WHERE s.status = 'active'
GROUP BY f.carrier_code
ORDER BY weekly_seat_capacity DESC;

-- Route network analysis
SELECT
    origin_airport,
    COUNT(DISTINCT destination_airport) as destinations_served,
    SUM(frequency_per_week) as weekly_departures
FROM flights
WHERE schedule_id IN (SELECT schedule_id FROM schedules WHERE status = 'active')
GROUP BY origin_airport
ORDER BY destinations_served DESC;

-- SSM message processing metrics
SELECT
    message_type,
    processing_status,
    COUNT(*) as message_count,
    AVG(EXTRACT(EPOCH FROM (processed_at - received_at)))::INTEGER as avg_processing_seconds
FROM ssm_messages
WHERE received_at >= NOW() - INTERVAL '7 days'
GROUP BY message_type, processing_status
ORDER BY message_type, processing_status;

-- =====================================================
-- 9. AUDIT & CHANGE TRACKING QUERIES
-- =====================================================

-- Recent schedule changes
SELECT
    sc.changed_at,
    f.flight_number,
    sc.change_type,
    sc.field_name,
    sc.old_value,
    sc.new_value,
    sc.changed_by,
    sc.reason
FROM schedule_changes sc
JOIN flights f ON sc.flight_id = f.flight_id
WHERE sc.changed_at >= NOW() - INTERVAL '24 hours'
ORDER BY sc.changed_at DESC;

-- Change frequency by flight
SELECT
    f.carrier_code,
    f.flight_number,
    COUNT(sc.change_id) as total_changes,
    array_agg(DISTINCT sc.change_type) as change_types
FROM flights f
LEFT JOIN schedule_changes sc ON f.flight_id = sc.flight_id
WHERE f.schedule_id IN (SELECT schedule_id FROM schedules WHERE status = 'active')
GROUP BY f.carrier_code, f.flight_number
HAVING COUNT(sc.change_id) > 0
ORDER BY total_changes DESC;

-- =====================================================
-- 10. MAINTENANCE & MONITORING QUERIES
-- =====================================================

-- Database table sizes
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as total_size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Active connections by application
SELECT
    application_name,
    state,
    COUNT(*) as connection_count
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY application_name, state;

-- Recent table modifications
SELECT
    schemaname,
    tablename,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY last_autoanalyze DESC NULLS LAST;

-- =====================================================
-- END OF COMMON QUERIES
-- =====================================================
