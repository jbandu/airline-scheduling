-- =====================================================
-- Airline Schedule Management System
-- Core Schedule Tables Schema
-- =====================================================
-- Purpose: Core tables for managing airline schedules,
--          flights, SSM messages, and change tracking
-- Standards: IATA SSM/SSIM compliance
-- PostgreSQL Version: 15+
-- =====================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- =====================================================
-- ENUMS
-- =====================================================

-- Schedule status lifecycle
CREATE TYPE schedule_status AS ENUM (
    'draft',        -- Initial creation
    'published',    -- Published to internal systems
    'active',       -- Currently operational
    'superseded',   -- Replaced by newer version
    'cancelled'     -- Cancelled schedule
);

-- SSM message types per IATA standard
CREATE TYPE ssm_message_type AS ENUM (
    'NEW',  -- New schedule
    'CNL',  -- Cancellation
    'CON',  -- Confirmation
    'TIM',  -- Time change
    'EQT',  -- Equipment change
    'ACK',  -- Acknowledgment
    'REJ',  -- Rejection
    'SKD',  -- Complete schedule
    'RPL',  -- Replace
    'ADM'   -- Administrative message
);

-- Message format standards
CREATE TYPE message_format AS ENUM (
    'SSM',   -- IATA Standard Schedule Message
    'SSIM',  -- IATA Standard Schedules Information Manual
    'JSON',  -- JSON format
    'XML'    -- XML format
);

-- Processing status for async operations
CREATE TYPE processing_status AS ENUM (
    'pending',
    'processing',
    'completed',
    'failed',
    'rejected'
);

-- Change types for audit trail
CREATE TYPE change_type AS ENUM (
    'create',
    'update',
    'cancel',
    'reinstate'
);

-- Service types per IATA standards
CREATE TYPE service_type AS ENUM (
    'J',  -- Passenger jet
    'F',  -- Cargo
    'C',  -- Combi (passenger/cargo)
    'H'   -- Charter
);

-- =====================================================
-- CORE TABLES
-- =====================================================

-- -----------------------------------------------------
-- schedules: Master schedule container
-- -----------------------------------------------------
-- Description: Contains seasonal schedules (IATA seasons)
-- IATA Seasons: W25=Winter 2025, S25=Summer 2025
-- Version control for schedule iterations
-- -----------------------------------------------------
CREATE TABLE schedules (
    schedule_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- IATA season code (format: W25, S25)
    season_code VARCHAR(3) NOT NULL CHECK (season_code ~ '^[WS]\d{2}$'),

    -- Effective date range for this schedule
    effective_from DATE NOT NULL,
    effective_to DATE NOT NULL,

    -- Version control
    version_number INTEGER NOT NULL DEFAULT 1,

    -- Status lifecycle
    status schedule_status NOT NULL DEFAULT 'draft',

    -- Audit fields
    created_by VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Metadata
    notes TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Constraints
    CONSTRAINT valid_date_range CHECK (effective_to > effective_from),
    CONSTRAINT unique_season_version UNIQUE (season_code, version_number)
);

-- Add comments for documentation
COMMENT ON TABLE schedules IS 'Master schedule container for IATA seasonal schedules';
COMMENT ON COLUMN schedules.season_code IS 'IATA season code: W25=Winter 2025, S25=Summer 2025';
COMMENT ON COLUMN schedules.operating_days IS 'IATA day pattern: 1234567 (Mon-Sun), where X=not operating';

-- -----------------------------------------------------
-- flights: Operational flight schedules
-- -----------------------------------------------------
-- Description: Individual flights within a schedule
-- Supports multi-leg operations and through flights
-- IATA day patterns: 1=Mon, 2=Tue...7=Sun, X=Not operating
-- -----------------------------------------------------
CREATE TABLE flights (
    flight_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Schedule relationship
    schedule_id UUID NOT NULL REFERENCES schedules(schedule_id) ON DELETE CASCADE,

    -- Flight identification
    flight_number VARCHAR(10) NOT NULL,  -- e.g., 'CM101', 'AA1234'
    carrier_code VARCHAR(3) NOT NULL,    -- IATA airline code

    -- Route information
    origin_airport VARCHAR(3) NOT NULL,      -- IATA airport code
    destination_airport VARCHAR(3) NOT NULL, -- IATA airport code

    -- Timing (all in local times)
    departure_time TIME NOT NULL,
    arrival_time TIME NOT NULL,
    departure_day_offset INTEGER DEFAULT 0,  -- For overnight flights
    arrival_day_offset INTEGER DEFAULT 0,    -- Arrival next day: +1, +2, etc.

    -- Operating pattern
    -- Format: 1234567 where 1=Mon, 2=Tue...7=Sun, X=Not operating
    -- Examples: '1234567'=Daily, 'X2X4X6X'=Tue/Thu/Sat, '12345XX'=Weekdays
    operating_days VARCHAR(7) NOT NULL CHECK (operating_days ~ '^[1-7X]{7}$'),

    -- Effective date range
    effective_from DATE NOT NULL,
    effective_to DATE NOT NULL,

    -- Aircraft information
    aircraft_type VARCHAR(3) NOT NULL,  -- IATA aircraft code: 738, 32N, 77W, etc.
    aircraft_config_version VARCHAR(10),
    aircraft_registration VARCHAR(10),  -- Tail number if assigned

    -- Service details
    service_type service_type NOT NULL DEFAULT 'J',
    frequency_per_week INTEGER,

    -- Multi-leg support
    leg_sequence INTEGER DEFAULT 1,
    onward_flight_number VARCHAR(10),  -- For through flights

    -- Operational details
    meal_service VARCHAR(10),  -- M=Meal, S=Snack, B=Breakfast, etc.
    secure_flight_required BOOLEAN DEFAULT true,
    eta_indicator VARCHAR(1),  -- E=Estimated time of arrival

    -- Capacity (optional)
    seats_total INTEGER,
    seats_business INTEGER,
    seats_economy INTEGER,
    cargo_capacity_kg INTEGER,

    -- Codeshare information
    operating_carrier VARCHAR(3),  -- If different from marketing carrier
    codeshare_partners VARCHAR(50)[],  -- Array of codeshare airlines

    -- Audit fields
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Additional metadata
    remarks TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Constraints
    CONSTRAINT valid_flight_dates CHECK (effective_to >= effective_from),
    CONSTRAINT valid_airports CHECK (origin_airport != destination_airport),
    CONSTRAINT valid_carrier_code CHECK (carrier_code ~ '^[A-Z0-9]{2,3}$'),
    CONSTRAINT valid_airport_codes CHECK (
        origin_airport ~ '^[A-Z]{3}$' AND
        destination_airport ~ '^[A-Z]{3}$'
    )
);

-- Add comments
COMMENT ON TABLE flights IS 'Operational flight schedules with IATA SSM compliance';
COMMENT ON COLUMN flights.operating_days IS 'IATA day pattern: 1234567=Daily, X=Not operating, 12345XX=Weekdays';
COMMENT ON COLUMN flights.aircraft_type IS 'IATA aircraft code: 738=Boeing 737-800, 32N=Airbus A320neo, 77W=Boeing 777-300ER';
COMMENT ON COLUMN flights.leg_sequence IS 'For multi-leg flights: 1, 2, 3, etc.';

-- -----------------------------------------------------
-- ssm_messages: Raw SSM/SSIM message log
-- -----------------------------------------------------
-- Description: Stores all incoming/outgoing SSM messages
-- Used for audit trail and reprocessing
-- IATA SSM Standard compliance
-- -----------------------------------------------------
CREATE TABLE ssm_messages (
    message_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Message classification
    message_type ssm_message_type NOT NULL,
    message_format message_format NOT NULL DEFAULT 'SSM',

    -- Message content
    raw_message TEXT NOT NULL,  -- Original message
    parsed_data JSONB,          -- Structured parsed data

    -- Sender/Receiver
    sender_airline VARCHAR(3) NOT NULL,
    receiver_airline VARCHAR(3),

    -- SSM action code
    action_code VARCHAR(3),  -- ADD, MOD, DEL, RPL

    -- Timing
    received_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE,

    -- Processing status
    processing_status processing_status NOT NULL DEFAULT 'pending',
    validation_errors JSONB DEFAULT '[]'::jsonb,

    -- Impact tracking
    affected_flight_ids UUID[],  -- Array of flight IDs affected

    -- Agent tracking
    created_by_agent VARCHAR(100),
    processed_by_agent VARCHAR(100),

    -- Reference fields from SSM
    ssm_reference_number VARCHAR(50),
    season_reference VARCHAR(3),

    -- Retry tracking for failed messages
    retry_count INTEGER DEFAULT 0,
    last_retry_at TIMESTAMP WITH TIME ZONE,

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Constraints
    CONSTRAINT valid_sender_code CHECK (sender_airline ~ '^[A-Z0-9]{2,3}$')
);

-- Add comments
COMMENT ON TABLE ssm_messages IS 'IATA SSM/SSIM message log for audit and reprocessing';
COMMENT ON COLUMN ssm_messages.action_code IS 'SSM action: ADD, MOD, DEL, RPL';
COMMENT ON COLUMN ssm_messages.parsed_data IS 'Structured JSONB representation of parsed SSM message';

-- -----------------------------------------------------
-- schedule_changes: Audit trail for all changes
-- -----------------------------------------------------
-- Description: Tracks all modifications to flight schedules
-- Enables rollback and change history analysis
-- -----------------------------------------------------
CREATE TABLE schedule_changes (
    change_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Flight reference
    flight_id UUID NOT NULL REFERENCES flights(flight_id) ON DELETE CASCADE,

    -- Change details
    change_type change_type NOT NULL,
    field_name VARCHAR(100),      -- Which field changed
    old_value TEXT,               -- Previous value
    new_value TEXT,               -- New value

    -- Change reason and context
    reason TEXT,
    change_context JSONB DEFAULT '{}'::jsonb,

    -- Actor tracking
    changed_by VARCHAR(255) NOT NULL,  -- Agent name or user ID
    changed_by_type VARCHAR(50),       -- 'agent', 'user', 'system'

    -- Timing
    changed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- SSM reference
    ssm_message_id UUID REFERENCES ssm_messages(message_id),

    -- Approval tracking
    requires_approval BOOLEAN DEFAULT false,
    approved_by VARCHAR(255),
    approved_at TIMESTAMP WITH TIME ZONE,

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Add comments
COMMENT ON TABLE schedule_changes IS 'Complete audit trail of all schedule modifications';
COMMENT ON COLUMN schedule_changes.changed_by_type IS 'Source of change: agent, user, system';

-- -----------------------------------------------------
-- flight_legs: Multi-segment flight operations
-- -----------------------------------------------------
-- Description: Individual legs for multi-segment flights
-- Supports complex routing and aircraft utilization
-- -----------------------------------------------------
CREATE TABLE flight_legs (
    leg_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Parent flight reference
    flight_id UUID NOT NULL REFERENCES flights(flight_id) ON DELETE CASCADE,

    -- Leg sequence
    leg_sequence INTEGER NOT NULL,  -- 1, 2, 3, etc.

    -- Route for this leg
    departure_airport VARCHAR(3) NOT NULL,
    arrival_airport VARCHAR(3) NOT NULL,

    -- Timing (local times)
    departure_time TIME NOT NULL,
    arrival_time TIME NOT NULL,
    departure_day_offset INTEGER DEFAULT 0,
    arrival_day_offset INTEGER DEFAULT 0,

    -- Flight time
    block_time INTERVAL,  -- Scheduled block time
    distance_nm INTEGER,  -- Distance in nautical miles

    -- Aircraft assignment
    aircraft_registration VARCHAR(10),
    aircraft_type VARCHAR(3),

    -- Terminal information
    departure_terminal VARCHAR(5),
    arrival_terminal VARCHAR(5),

    -- Gate information (if known)
    departure_gate VARCHAR(10),
    arrival_gate VARCHAR(10),

    -- Operational details
    ground_time INTERVAL,  -- Time on ground before next leg
    fuel_required_kg INTEGER,

    -- Metadata
    remarks TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Constraints
    CONSTRAINT valid_leg_airports CHECK (departure_airport != arrival_airport),
    CONSTRAINT valid_leg_sequence CHECK (leg_sequence > 0),
    CONSTRAINT unique_flight_leg UNIQUE (flight_id, leg_sequence)
);

-- Add comments
COMMENT ON TABLE flight_legs IS 'Individual legs for multi-segment flight operations';
COMMENT ON COLUMN flight_legs.block_time IS 'Scheduled block time (wheels off to wheels on)';
COMMENT ON COLUMN flight_legs.distance_nm IS 'Distance in nautical miles';

-- =====================================================
-- INDEXES FOR PERFORMANCE
-- =====================================================

-- schedules indexes
CREATE INDEX idx_schedules_season ON schedules(season_code, status);
CREATE INDEX idx_schedules_dates ON schedules(effective_from, effective_to);
CREATE INDEX idx_schedules_status ON schedules(status);

-- flights indexes
CREATE INDEX idx_flights_schedule ON flights(schedule_id);
CREATE INDEX idx_flights_carrier_number ON flights(carrier_code, flight_number);
CREATE INDEX idx_flights_route ON flights(origin_airport, destination_airport);
CREATE INDEX idx_flights_departure ON flights(origin_airport, departure_time);
CREATE INDEX idx_flights_dates ON flights(effective_from, effective_to);
CREATE INDEX idx_flights_aircraft ON flights(aircraft_type);
CREATE INDEX idx_flights_operating_pattern ON flights(operating_days);
CREATE INDEX idx_flights_composite ON flights(carrier_code, flight_number, effective_from, effective_to);

-- ssm_messages indexes
CREATE INDEX idx_ssm_status ON ssm_messages(processing_status, received_at);
CREATE INDEX idx_ssm_sender ON ssm_messages(sender_airline, message_type);
CREATE INDEX idx_ssm_received ON ssm_messages(received_at DESC);
CREATE INDEX idx_ssm_type ON ssm_messages(message_type);
CREATE INDEX idx_ssm_affected_flights ON ssm_messages USING GIN(affected_flight_ids);
CREATE INDEX idx_ssm_parsed_data ON ssm_messages USING GIN(parsed_data);

-- schedule_changes indexes
CREATE INDEX idx_changes_flight ON schedule_changes(flight_id, changed_at DESC);
CREATE INDEX idx_changes_type ON schedule_changes(change_type);
CREATE INDEX idx_changes_by ON schedule_changes(changed_by);
CREATE INDEX idx_changes_ssm ON schedule_changes(ssm_message_id);
CREATE INDEX idx_changes_date ON schedule_changes(changed_at DESC);

-- flight_legs indexes
CREATE INDEX idx_legs_flight ON flight_legs(flight_id, leg_sequence);
CREATE INDEX idx_legs_departure ON flight_legs(departure_airport);
CREATE INDEX idx_legs_arrival ON flight_legs(arrival_airport);
CREATE INDEX idx_legs_aircraft ON flight_legs(aircraft_registration);

-- =====================================================
-- HELPER FUNCTIONS
-- =====================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply updated_at trigger to schedules
CREATE TRIGGER update_schedules_updated_at
    BEFORE UPDATE ON schedules
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Apply updated_at trigger to flights
CREATE TRIGGER update_flights_updated_at
    BEFORE UPDATE ON flights
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- VIEWS FOR COMMON QUERIES
-- =====================================================

-- Active flights view
CREATE OR REPLACE VIEW v_active_flights AS
SELECT
    f.*,
    s.season_code,
    s.version_number,
    CASE
        WHEN f.operating_carrier IS NOT NULL
        THEN f.operating_carrier
        ELSE f.carrier_code
    END as actual_operating_carrier
FROM flights f
JOIN schedules s ON f.schedule_id = s.schedule_id
WHERE s.status = 'active'
  AND f.effective_from <= CURRENT_DATE
  AND f.effective_to >= CURRENT_DATE;

COMMENT ON VIEW v_active_flights IS 'Currently active flights with schedule metadata';

-- Daily operations view
CREATE OR REPLACE VIEW v_daily_operations AS
SELECT
    f.flight_id,
    f.carrier_code,
    f.flight_number,
    f.origin_airport,
    f.destination_airport,
    f.departure_time,
    f.arrival_time,
    f.aircraft_type,
    f.operating_days,
    s.season_code
FROM flights f
JOIN schedules s ON f.schedule_id = s.schedule_id
WHERE s.status = 'active'
  AND f.effective_from <= CURRENT_DATE
  AND f.effective_to >= CURRENT_DATE
  AND f.operating_days LIKE '%' || EXTRACT(ISODOW FROM CURRENT_DATE)::TEXT || '%';

COMMENT ON VIEW v_daily_operations IS 'Flights operating today based on day pattern';

-- =====================================================
-- GRANTS (adjust based on your role structure)
-- =====================================================

-- Grant permissions to application role
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO airline_app_role;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO airline_app_role;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO airline_app_role;

-- =====================================================
-- SAMPLE DATA COMMENTS
-- =====================================================

-- To insert sample data, see: /database/seeds/001_sample_schedules.sql

-- =====================================================
-- END OF CORE SCHEDULE TABLES SCHEMA
-- =====================================================
