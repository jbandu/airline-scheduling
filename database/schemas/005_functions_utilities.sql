-- =====================================================
-- Airline Schedule Management System
-- Functions & Utilities Schema
-- =====================================================
-- Purpose: Helper functions for SSM parsing, schedule
--          management, and operational queries
-- =====================================================

-- =====================================================
-- SSM PARSING FUNCTIONS
-- =====================================================

-- Function to parse IATA operating days pattern
-- Input: '1234567' (1=Mon, 7=Sun), 'X' = not operating
-- Output: Array of integers [1,2,3,4,5,6,7] or [1,3,5] etc.
CREATE OR REPLACE FUNCTION parse_ssm_operating_days(pattern VARCHAR(7))
RETURNS INTEGER[] AS $$
DECLARE
    result INTEGER[] := '{}';
    i INTEGER;
BEGIN
    IF pattern IS NULL OR LENGTH(pattern) != 7 THEN
        RAISE EXCEPTION 'Invalid operating days pattern: %', pattern;
    END IF;

    FOR i IN 1..7 LOOP
        IF SUBSTRING(pattern FROM i FOR 1) = i::TEXT THEN
            result := array_append(result, i);
        END IF;
    END LOOP;

    RETURN result;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

COMMENT ON FUNCTION parse_ssm_operating_days IS 'Parse IATA day pattern to array of operating days';

-- Function to check if flight operates on a specific date
CREATE OR REPLACE FUNCTION flight_operates_on_date(
    p_operating_days VARCHAR(7),
    p_check_date DATE,
    p_effective_from DATE,
    p_effective_to DATE
)
RETURNS BOOLEAN AS $$
DECLARE
    v_day_of_week INTEGER;
    v_day_char VARCHAR(1);
BEGIN
    -- Check if date is within effective range
    IF p_check_date < p_effective_from OR p_check_date > p_effective_to THEN
        RETURN false;
    END IF;

    -- Get day of week (1=Monday, 7=Sunday per ISO)
    v_day_of_week := EXTRACT(ISODOW FROM p_check_date);

    -- Get character at that position
    v_day_char := SUBSTRING(p_operating_days FROM v_day_of_week FOR 1);

    -- Check if it matches the day number
    RETURN v_day_char = v_day_of_week::TEXT;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

COMMENT ON FUNCTION flight_operates_on_date IS 'Check if flight operates on specific date';

-- Function to calculate next occurrence of a flight
CREATE OR REPLACE FUNCTION calculate_next_occurrence(
    p_operating_days VARCHAR(7),
    p_reference_date DATE,
    p_effective_from DATE,
    p_effective_to DATE
)
RETURNS DATE AS $$
DECLARE
    v_current_date DATE := p_reference_date;
    v_max_iterations INTEGER := 14; -- Look ahead max 2 weeks
    i INTEGER := 0;
BEGIN
    -- Ensure we start from effective_from if reference is before it
    IF v_current_date < p_effective_from THEN
        v_current_date := p_effective_from;
    END IF;

    -- Check if already past effective_to
    IF v_current_date > p_effective_to THEN
        RETURN NULL;
    END IF;

    -- Find next operating date
    WHILE i < v_max_iterations LOOP
        IF flight_operates_on_date(p_operating_days, v_current_date, p_effective_from, p_effective_to) THEN
            RETURN v_current_date;
        END IF;

        v_current_date := v_current_date + 1;
        i := i + 1;

        -- Stop if past effective_to
        IF v_current_date > p_effective_to THEN
            RETURN NULL;
        END IF;
    END LOOP;

    RETURN NULL;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

COMMENT ON FUNCTION calculate_next_occurrence IS 'Calculate next operating date for a flight';

-- Function to get all operating dates for a flight in a date range
CREATE OR REPLACE FUNCTION get_operating_dates(
    p_operating_days VARCHAR(7),
    p_effective_from DATE,
    p_effective_to DATE,
    p_start_date DATE DEFAULT NULL,
    p_end_date DATE DEFAULT NULL
)
RETURNS TABLE(operating_date DATE) AS $$
DECLARE
    v_start_date DATE := COALESCE(p_start_date, p_effective_from);
    v_end_date DATE := COALESCE(p_end_date, p_effective_to);
    v_current_date DATE := v_start_date;
BEGIN
    -- Ensure start date is not before effective_from
    IF v_start_date < p_effective_from THEN
        v_start_date := p_effective_from;
        v_current_date := v_start_date;
    END IF;

    -- Ensure end date is not after effective_to
    IF v_end_date > p_effective_to THEN
        v_end_date := p_effective_to;
    END IF;

    -- Generate all operating dates
    WHILE v_current_date <= v_end_date LOOP
        IF flight_operates_on_date(p_operating_days, v_current_date, p_effective_from, p_effective_to) THEN
            operating_date := v_current_date;
            RETURN NEXT;
        END IF;

        v_current_date := v_current_date + 1;
    END LOOP;

    RETURN;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

COMMENT ON FUNCTION get_operating_dates IS 'Get all operating dates for a flight within date range';

-- =====================================================
-- SCHEDULE ANALYSIS FUNCTIONS
-- =====================================================

-- Function to get schedule by season
CREATE OR REPLACE FUNCTION get_schedule_by_season(p_season_code VARCHAR(3))
RETURNS TABLE (
    schedule_id UUID,
    season_code VARCHAR,
    effective_from DATE,
    effective_to DATE,
    version_number INTEGER,
    status schedule_status,
    total_flights BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        s.schedule_id,
        s.season_code,
        s.effective_from,
        s.effective_to,
        s.version_number,
        s.status,
        COUNT(f.flight_id) as total_flights
    FROM schedules s
    LEFT JOIN flights f ON s.schedule_id = f.schedule_id
    WHERE s.season_code = p_season_code
    GROUP BY s.schedule_id, s.season_code, s.effective_from, s.effective_to,
             s.version_number, s.status
    ORDER BY s.version_number DESC;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_schedule_by_season IS 'Get schedule details and flight count by season';

-- Function to detect schedule gaps (routes without coverage)
CREATE OR REPLACE FUNCTION detect_schedule_gaps(
    p_schedule_id UUID,
    p_min_frequency INTEGER DEFAULT 7
)
RETURNS TABLE (
    route VARCHAR,
    current_frequency INTEGER,
    gap_severity VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    WITH route_frequencies AS (
        SELECT
            origin_airport || '-' || destination_airport as route_key,
            COUNT(*) as flight_count,
            SUM(frequency_per_week) as total_frequency
        FROM flights
        WHERE schedule_id = p_schedule_id
        GROUP BY origin_airport, destination_airport
    )
    SELECT
        route_key,
        COALESCE(total_frequency::INTEGER, 0) as current_frequency,
        CASE
            WHEN total_frequency IS NULL THEN 'no_service'
            WHEN total_frequency < p_min_frequency THEN 'low_frequency'
            ELSE 'adequate'
        END as gap_severity
    FROM route_frequencies
    WHERE COALESCE(total_frequency, 0) < p_min_frequency
    ORDER BY total_frequency NULLS FIRST;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION detect_schedule_gaps IS 'Detect routes with insufficient frequency';

-- Function to validate flight continuity (aircraft routing)
CREATE OR REPLACE FUNCTION validate_flight_continuity(p_flight_id UUID)
RETURNS TABLE (
    is_valid BOOLEAN,
    validation_message TEXT
) AS $$
DECLARE
    v_flight RECORD;
    v_previous_flight RECORD;
    v_next_flight RECORD;
BEGIN
    -- Get flight details
    SELECT * INTO v_flight
    FROM flights
    WHERE flight_id = p_flight_id;

    IF NOT FOUND THEN
        RETURN QUERY SELECT false, 'Flight not found'::TEXT;
        RETURN;
    END IF;

    -- Check if there's a previous flight ending at origin
    -- This is a simplified check - production would consider timing, aircraft type, etc.
    SELECT * INTO v_previous_flight
    FROM flights
    WHERE schedule_id = v_flight.schedule_id
      AND destination_airport = v_flight.origin_airport
      AND arrival_time <= v_flight.departure_time
      AND aircraft_type = v_flight.aircraft_type
    ORDER BY arrival_time DESC
    LIMIT 1;

    -- Check if there's a next flight starting from destination
    SELECT * INTO v_next_flight
    FROM flights
    WHERE schedule_id = v_flight.schedule_id
      AND origin_airport = v_flight.destination_airport
      AND departure_time >= v_flight.arrival_time
      AND aircraft_type = v_flight.aircraft_type
    ORDER BY departure_time ASC
    LIMIT 1;

    -- Return validation result
    IF v_previous_flight IS NULL AND v_next_flight IS NULL THEN
        RETURN QUERY SELECT true, 'Standalone flight - no continuity check needed'::TEXT;
    ELSIF v_previous_flight IS NOT NULL AND v_next_flight IS NOT NULL THEN
        RETURN QUERY SELECT true, 'Flight has valid continuity'::TEXT;
    ELSE
        RETURN QUERY SELECT false, 'Potential continuity issue - flight may leave aircraft stranded'::TEXT;
    END IF;

    RETURN;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION validate_flight_continuity IS 'Validate aircraft routing continuity for a flight';

-- =====================================================
-- OPERATIONAL QUERY FUNCTIONS
-- =====================================================

-- Function to get daily flight schedule
CREATE OR REPLACE FUNCTION get_daily_schedule(
    p_date DATE,
    p_carrier_code VARCHAR(3) DEFAULT NULL,
    p_airport_code VARCHAR(3) DEFAULT NULL
)
RETURNS TABLE (
    flight_id UUID,
    carrier_code VARCHAR,
    flight_number VARCHAR,
    origin_airport VARCHAR,
    destination_airport VARCHAR,
    departure_time TIME,
    arrival_time TIME,
    aircraft_type VARCHAR,
    status VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        f.flight_id,
        f.carrier_code,
        f.flight_number,
        f.origin_airport,
        f.destination_airport,
        f.departure_time,
        f.arrival_time,
        f.aircraft_type,
        s.status::VARCHAR as status
    FROM flights f
    JOIN schedules s ON f.schedule_id = s.schedule_id
    WHERE s.status = 'active'
      AND flight_operates_on_date(f.operating_days, p_date, f.effective_from, f.effective_to)
      AND (p_carrier_code IS NULL OR f.carrier_code = p_carrier_code)
      AND (p_airport_code IS NULL OR f.origin_airport = p_airport_code OR f.destination_airport = p_airport_code)
    ORDER BY f.departure_time;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_daily_schedule IS 'Get all flights operating on a specific date';

-- Function to find connecting flights
CREATE OR REPLACE FUNCTION find_connecting_flights(
    p_origin VARCHAR(3),
    p_destination VARCHAR(3),
    p_date DATE,
    p_max_connections INTEGER DEFAULT 1
)
RETURNS TABLE (
    route_type VARCHAR,
    flight_1_id UUID,
    flight_1_number VARCHAR,
    flight_1_departure TIME,
    flight_1_arrival TIME,
    connection_airport VARCHAR,
    connection_time_minutes INTEGER,
    flight_2_id UUID,
    flight_2_number VARCHAR,
    flight_2_departure TIME,
    flight_2_arrival TIME,
    total_journey_time INTERVAL
) AS $$
BEGIN
    -- Direct flights
    IF p_max_connections >= 0 THEN
        RETURN QUERY
        SELECT
            'DIRECT'::VARCHAR as route_type,
            f.flight_id as flight_1_id,
            f.flight_number as flight_1_number,
            f.departure_time as flight_1_departure,
            f.arrival_time as flight_1_arrival,
            NULL::VARCHAR as connection_airport,
            NULL::INTEGER as connection_time_minutes,
            NULL::UUID as flight_2_id,
            NULL::VARCHAR as flight_2_number,
            NULL::TIME as flight_2_departure,
            NULL::TIME as flight_2_arrival,
            (f.arrival_time - f.departure_time) as total_journey_time
        FROM flights f
        JOIN schedules s ON f.schedule_id = s.schedule_id
        WHERE f.origin_airport = p_origin
          AND f.destination_airport = p_destination
          AND s.status = 'active'
          AND flight_operates_on_date(f.operating_days, p_date, f.effective_from, f.effective_to);
    END IF;

    -- One-stop connections
    IF p_max_connections >= 1 THEN
        RETURN QUERY
        SELECT
            'ONE_STOP'::VARCHAR as route_type,
            f1.flight_id as flight_1_id,
            f1.flight_number as flight_1_number,
            f1.departure_time as flight_1_departure,
            f1.arrival_time as flight_1_arrival,
            f1.destination_airport as connection_airport,
            EXTRACT(EPOCH FROM (f2.departure_time - f1.arrival_time))::INTEGER / 60 as connection_time_minutes,
            f2.flight_id as flight_2_id,
            f2.flight_number as flight_2_number,
            f2.departure_time as flight_2_departure,
            f2.arrival_time as flight_2_arrival,
            (f2.arrival_time - f1.departure_time) as total_journey_time
        FROM flights f1
        JOIN schedules s1 ON f1.schedule_id = s1.schedule_id
        JOIN flights f2 ON f1.destination_airport = f2.origin_airport
        JOIN schedules s2 ON f2.schedule_id = s2.schedule_id
        WHERE f1.origin_airport = p_origin
          AND f2.destination_airport = p_destination
          AND s1.status = 'active'
          AND s2.status = 'active'
          AND flight_operates_on_date(f1.operating_days, p_date, f1.effective_from, f1.effective_to)
          AND flight_operates_on_date(f2.operating_days, p_date, f2.effective_from, f2.effective_to)
          AND f2.departure_time > f1.arrival_time
          AND (f2.departure_time - f1.arrival_time) >= INTERVAL '45 minutes'  -- Minimum connect time
          AND (f2.departure_time - f1.arrival_time) <= INTERVAL '6 hours';    -- Maximum connection time
    END IF;

    RETURN;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION find_connecting_flights IS 'Find direct and connecting flight options between airports';

-- =====================================================
-- CONFLICT DETECTION FUNCTIONS
-- =====================================================

-- Function to detect aircraft double-booking
CREATE OR REPLACE FUNCTION detect_aircraft_conflicts(
    p_schedule_id UUID
)
RETURNS TABLE (
    aircraft_registration VARCHAR,
    conflict_date DATE,
    conflict_time TIME,
    flight_1_id UUID,
    flight_2_id UUID,
    overlap_type VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    WITH flight_instances AS (
        SELECT
            f.flight_id,
            f.aircraft_registration,
            f.origin_airport,
            f.destination_airport,
            f.departure_time,
            f.arrival_time,
            od.operating_date
        FROM flights f
        CROSS JOIN LATERAL get_operating_dates(
            f.operating_days,
            f.effective_from,
            f.effective_to
        ) as od
        WHERE f.schedule_id = p_schedule_id
          AND f.aircraft_registration IS NOT NULL
    )
    SELECT
        f1.aircraft_registration,
        f1.operating_date as conflict_date,
        f1.departure_time as conflict_time,
        f1.flight_id as flight_1_id,
        f2.flight_id as flight_2_id,
        CASE
            WHEN f1.departure_time = f2.departure_time THEN 'SIMULTANEOUS_DEPARTURE'
            WHEN f1.departure_time < f2.departure_time AND f1.arrival_time > f2.departure_time THEN 'OVERLAPPING_TIMES'
            WHEN f1.destination_airport != f2.origin_airport THEN 'ROUTING_MISMATCH'
            ELSE 'OTHER'
        END as overlap_type
    FROM flight_instances f1
    JOIN flight_instances f2 ON
        f1.aircraft_registration = f2.aircraft_registration
        AND f1.operating_date = f2.operating_date
        AND f1.flight_id < f2.flight_id  -- Avoid duplicates
        AND (
            -- Overlapping times
            (f1.departure_time <= f2.arrival_time AND f1.arrival_time >= f2.departure_time)
            OR
            -- Wrong routing (aircraft at wrong airport)
            (f1.arrival_time < f2.departure_time AND f1.destination_airport != f2.origin_airport)
        );
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION detect_aircraft_conflicts IS 'Detect aircraft double-booking and routing conflicts';

-- Function to check slot availability
CREATE OR REPLACE FUNCTION check_slot_availability(
    p_airport_code VARCHAR(3),
    p_slot_time TIMESTAMP WITH TIME ZONE,
    p_slot_type slot_type,
    p_tolerance_minutes INTEGER DEFAULT 5
)
RETURNS BOOLEAN AS $$
DECLARE
    v_available BOOLEAN;
BEGIN
    SELECT NOT EXISTS (
        SELECT 1
        FROM airport_slots
        WHERE airport_code = p_airport_code
          AND slot_type = p_slot_type
          AND slot_time BETWEEN
              p_slot_time - (p_tolerance_minutes || ' minutes')::INTERVAL AND
              p_slot_time + (p_tolerance_minutes || ' minutes')::INTERVAL
          AND allocated_to_flight IS NOT NULL
          AND confirmed = true
    ) INTO v_available;

    RETURN v_available;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION check_slot_availability IS 'Check if airport slot is available within tolerance window';

-- =====================================================
-- ANALYTICS FUNCTIONS
-- =====================================================

-- Function to calculate schedule utilization metrics
CREATE OR REPLACE FUNCTION calculate_schedule_utilization(
    p_schedule_id UUID
)
RETURNS TABLE (
    total_flights INTEGER,
    total_departures INTEGER,
    unique_routes INTEGER,
    unique_airports INTEGER,
    avg_frequency_per_route DECIMAL,
    aircraft_utilization_pct DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    WITH schedule_stats AS (
        SELECT
            COUNT(DISTINCT flight_id)::INTEGER as flight_count,
            COUNT(DISTINCT (origin_airport || '-' || destination_airport))::INTEGER as route_count,
            COUNT(DISTINCT origin_airport) + COUNT(DISTINCT destination_airport)::INTEGER as airport_count,
            AVG(frequency_per_week) as avg_freq
        FROM flights
        WHERE schedule_id = p_schedule_id
    )
    SELECT
        flight_count as total_flights,
        flight_count * 7 as total_departures,  -- Assuming weekly frequency
        route_count as unique_routes,
        airport_count as unique_airports,
        avg_freq as avg_frequency_per_route,
        NULL::DECIMAL as aircraft_utilization_pct  -- Placeholder for complex calculation
    FROM schedule_stats;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION calculate_schedule_utilization IS 'Calculate schedule utilization and coverage metrics';

-- =====================================================
-- SSM MESSAGE PROCESSING FUNCTIONS
-- =====================================================

-- Function to extract flight info from SSM message (simplified)
CREATE OR REPLACE FUNCTION parse_ssm_basic(
    p_raw_message TEXT
)
RETURNS JSONB AS $$
DECLARE
    v_result JSONB := '{}'::jsonb;
    v_lines TEXT[];
    v_action_code VARCHAR(3);
BEGIN
    -- This is a simplified parser - production would use more sophisticated parsing
    -- SSM Format example:
    -- NEW
    -- CM 101 PTY MIA 1234567 01JAN25 31MAR25 738 0800 1200

    v_lines := string_to_array(p_raw_message, E'\n');

    -- Extract action code (first line)
    IF array_length(v_lines, 1) >= 1 THEN
        v_action_code := TRIM(v_lines[1]);
        v_result := v_result || jsonb_build_object('action_code', v_action_code);
    END IF;

    -- Note: Full SSM parsing would be much more complex
    -- This is a placeholder for actual implementation
    v_result := v_result || jsonb_build_object(
        'parsed', true,
        'message_lines', array_length(v_lines, 1)
    );

    RETURN v_result;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

COMMENT ON FUNCTION parse_ssm_basic IS 'Basic SSM message parser (simplified)';

-- =====================================================
-- UTILITY FUNCTIONS
-- =====================================================

-- Function to convert IATA time to timestamp on specific date
CREATE OR REPLACE FUNCTION iata_time_to_timestamp(
    p_date DATE,
    p_time TIME,
    p_day_offset INTEGER DEFAULT 0,
    p_timezone TEXT DEFAULT 'UTC'
)
RETURNS TIMESTAMP WITH TIME ZONE AS $$
BEGIN
    RETURN (p_date + p_day_offset + p_time) AT TIME ZONE p_timezone;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

COMMENT ON FUNCTION iata_time_to_timestamp IS 'Convert IATA local time to timestamp with timezone';

-- Function to calculate block time
CREATE OR REPLACE FUNCTION calculate_block_time(
    p_departure_time TIME,
    p_arrival_time TIME,
    p_arrival_day_offset INTEGER DEFAULT 0
)
RETURNS INTERVAL AS $$
BEGIN
    RETURN (p_arrival_time + (p_arrival_day_offset || ' days')::INTERVAL) - p_departure_time;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

COMMENT ON FUNCTION calculate_block_time IS 'Calculate block time considering day offset';

-- =====================================================
-- DATA QUALITY FUNCTIONS
-- =====================================================

-- Function to validate schedule data quality
CREATE OR REPLACE FUNCTION validate_schedule_data_quality(
    p_schedule_id UUID
)
RETURNS TABLE (
    check_name VARCHAR,
    status VARCHAR,
    issue_count INTEGER,
    severity VARCHAR
) AS $$
BEGIN
    -- Check for flights with invalid airports
    RETURN QUERY
    SELECT
        'Invalid Airports'::VARCHAR as check_name,
        CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END::VARCHAR as status,
        COUNT(*)::INTEGER as issue_count,
        'HIGH'::VARCHAR as severity
    FROM flights
    WHERE schedule_id = p_schedule_id
      AND (origin_airport !~ '^[A-Z]{3}$' OR destination_airport !~ '^[A-Z]{3}$');

    -- Check for flights with same origin and destination
    RETURN QUERY
    SELECT
        'Same Origin-Destination'::VARCHAR,
        CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END::VARCHAR,
        COUNT(*)::INTEGER,
        'HIGH'::VARCHAR
    FROM flights
    WHERE schedule_id = p_schedule_id
      AND origin_airport = destination_airport;

    -- Check for flights with invalid time ranges
    RETURN QUERY
    SELECT
        'Invalid Time Range'::VARCHAR,
        CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END::VARCHAR,
        COUNT(*)::INTEGER,
        'MEDIUM'::VARCHAR
    FROM flights
    WHERE schedule_id = p_schedule_id
      AND arrival_time = departure_time;

    -- Check for flights with invalid date ranges
    RETURN QUERY
    SELECT
        'Invalid Date Range'::VARCHAR,
        CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END::VARCHAR,
        COUNT(*)::INTEGER,
        'HIGH'::VARCHAR
    FROM flights
    WHERE schedule_id = p_schedule_id
      AND effective_to < effective_from;

    RETURN;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION validate_schedule_data_quality IS 'Run data quality checks on schedule';

-- =====================================================
-- END OF FUNCTIONS & UTILITIES SCHEMA
-- =====================================================
