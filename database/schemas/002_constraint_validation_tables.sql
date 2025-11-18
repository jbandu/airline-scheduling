-- =====================================================
-- Airline Schedule Management System
-- Constraint & Validation Tables Schema
-- =====================================================
-- Purpose: Airport slots, constraints, aircraft
--          availability, and regulatory compliance
-- Standards: IATA Worldwide Slot Guidelines (WSG)
-- =====================================================

-- =====================================================
-- ENUMS
-- =====================================================

-- Slot types
CREATE TYPE slot_type AS ENUM (
    'arrival',
    'departure'
);

-- Airport constraint types
CREATE TYPE constraint_type AS ENUM (
    'curfew',              -- Night flight restrictions
    'capacity',            -- Hourly/daily capacity limits
    'slot_coordination',   -- Level 1, 2, 3 coordination
    'mct',                 -- Minimum Connect Time
    'noise',               -- Noise abatement procedures
    'environmental',       -- Environmental restrictions
    'infrastructure'       -- Runway/terminal limitations
);

-- Aircraft status
CREATE TYPE aircraft_status AS ENUM (
    'available',
    'maintenance',
    'grounded',
    'in_flight',
    'reserved'
);

-- Slot coordination levels (IATA WSG)
CREATE TYPE coordination_level AS ENUM (
    'level_1',  -- Non-coordinated, sufficient capacity
    'level_2',  -- Schedules facilitated
    'level_3'   -- Fully coordinated, slot allocation required
);

-- Connection types for MCT
CREATE TYPE connection_type AS ENUM (
    'domestic_domestic',
    'domestic_international',
    'international_domestic',
    'international_international',
    'online',   -- Same airline
    'interline' -- Different airlines
);

-- =====================================================
-- CONSTRAINT TABLES
-- =====================================================

-- -----------------------------------------------------
-- airport_slots: Airport slot allocations
-- -----------------------------------------------------
-- Description: Manages airport slots per IATA WSG
-- Supports historical rights and series allocation
-- Critical for Level 3 coordinated airports
-- -----------------------------------------------------
CREATE TABLE airport_slots (
    slot_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Airport and timing
    airport_code VARCHAR(3) NOT NULL CHECK (airport_code ~ '^[A-Z]{3}$'),
    slot_time TIMESTAMP WITH TIME ZONE NOT NULL,
    slot_type slot_type NOT NULL,

    -- Tolerance window (typically ±5 or ±15 minutes)
    tolerance_before_minutes INTEGER DEFAULT 5,
    tolerance_after_minutes INTEGER DEFAULT 5,

    -- Allocation
    allocated_to_airline VARCHAR(3) CHECK (allocated_to_airline ~ '^[A-Z0-9]{2,3}$'),
    allocated_to_flight UUID REFERENCES flights(flight_id) ON DELETE SET NULL,

    -- Season and series
    slot_season VARCHAR(3),  -- W25, S25, etc.
    slot_series VARCHAR(50), -- Series identifier for recurring slots

    -- Historical rights (grandfather rights)
    historical_rights BOOLEAN DEFAULT false,
    usage_history JSONB DEFAULT '[]'::jsonb,  -- Track slot usage

    -- Confirmation and coordination
    confirmed BOOLEAN DEFAULT false,
    coordinator_reference VARCHAR(50),
    coordinator_name VARCHAR(100),

    -- Temporary vs permanent
    temporary BOOLEAN DEFAULT false,
    temporary_reason TEXT,

    -- Restrictions
    restrictions JSONB DEFAULT '{}'::jsonb,  -- Aircraft size, type restrictions

    -- Audit fields
    allocated_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Metadata
    notes TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Constraints
    CONSTRAINT valid_tolerance CHECK (
        tolerance_before_minutes >= 0 AND
        tolerance_after_minutes >= 0
    )
);

-- Add comments
COMMENT ON TABLE airport_slots IS 'IATA WSG-compliant airport slot allocations';
COMMENT ON COLUMN airport_slots.historical_rights IS 'Grandfather rights per IATA 80/20 rule';
COMMENT ON COLUMN airport_slots.slot_series IS 'Series identifier for recurring seasonal slots';

-- Indexes
CREATE INDEX idx_slots_airport_time ON airport_slots(airport_code, slot_time);
CREATE INDEX idx_slots_airline ON airport_slots(allocated_to_airline);
CREATE INDEX idx_slots_flight ON airport_slots(allocated_to_flight);
CREATE INDEX idx_slots_season ON airport_slots(slot_season);
CREATE INDEX idx_slots_confirmed ON airport_slots(confirmed, airport_code);
CREATE INDEX idx_slots_usage_history ON airport_slots USING GIN(usage_history);

-- -----------------------------------------------------
-- airport_constraints: Airport operational constraints
-- -----------------------------------------------------
-- Description: Regulatory and operational constraints
-- Includes curfews, capacity limits, noise abatement
-- -----------------------------------------------------
CREATE TABLE airport_constraints (
    constraint_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Airport
    airport_code VARCHAR(3) NOT NULL CHECK (airport_code ~ '^[A-Z]{3}$'),

    -- Constraint classification
    constraint_type constraint_type NOT NULL,
    constraint_name VARCHAR(200) NOT NULL,
    description TEXT,

    -- Constraint specifics (flexible JSON structure)
    -- Examples:
    -- Curfew: {"start_time": "23:00", "end_time": "06:00", "exceptions": [...]}
    -- Capacity: {"max_movements_per_hour": 60, "peak_hours": [...]}
    constraint_data JSONB NOT NULL,

    -- Effective date range
    effective_from DATE NOT NULL,
    effective_to DATE,

    -- Severity and enforcement
    is_mandatory BOOLEAN DEFAULT true,
    severity VARCHAR(20) DEFAULT 'high', -- high, medium, low

    -- Coordination level
    coordination_level coordination_level,

    -- Contact information
    regulatory_authority VARCHAR(200),
    contact_info JSONB,

    -- Audit fields
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Add comments
COMMENT ON TABLE airport_constraints IS 'Airport operational constraints and regulatory requirements';
COMMENT ON COLUMN airport_constraints.constraint_data IS 'Flexible JSONB structure for constraint-specific rules';

-- Indexes
CREATE INDEX idx_constraints_airport ON airport_constraints(airport_code);
CREATE INDEX idx_constraints_type ON airport_constraints(constraint_type);
CREATE INDEX idx_constraints_dates ON airport_constraints(effective_from, effective_to);
CREATE INDEX idx_constraints_coordination ON airport_constraints(coordination_level);
CREATE INDEX idx_constraints_data ON airport_constraints USING GIN(constraint_data);

-- -----------------------------------------------------
-- aircraft_availability: Aircraft fleet availability
-- -----------------------------------------------------
-- Description: Tracks aircraft availability for scheduling
-- Supports maintenance planning and fleet assignment
-- -----------------------------------------------------
CREATE TABLE aircraft_availability (
    availability_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Aircraft identification
    aircraft_registration VARCHAR(10) NOT NULL,  -- Tail number
    aircraft_type VARCHAR(3) NOT NULL,           -- IATA code: 738, 32N, etc.

    -- Aircraft details
    aircraft_subtype VARCHAR(20),  -- Variant: 737-8MAX, A320-271N
    manufacture_year INTEGER,
    seat_configuration VARCHAR(20), -- e.g., "Y180", "C20Y150"

    -- Ownership and operation
    owner_airline VARCHAR(3) CHECK (owner_airline ~ '^[A-Z0-9]{2,3}$'),
    operating_airline VARCHAR(3) CHECK (operating_airline ~ '^[A-Z0-9]{2,3}$'),
    lease_type VARCHAR(20), -- owned, wet_lease, dry_lease, charter

    -- Base and routing
    home_base VARCHAR(3),  -- Airport code
    current_location VARCHAR(3),  -- Current airport

    -- Availability window
    available_from TIMESTAMP WITH TIME ZONE NOT NULL,
    available_to TIMESTAMP WITH TIME ZONE,

    -- Status
    status aircraft_status NOT NULL DEFAULT 'available',

    -- Maintenance tracking
    maintenance_type VARCHAR(50),  -- A-check, B-check, C-check, D-check
    next_maintenance_date DATE,
    next_maintenance_type VARCHAR(50),
    maintenance_base VARCHAR(3),  -- Where maintenance performed

    -- Operational limits
    max_flight_hours_remaining DECIMAL(10,2),
    max_cycles_remaining INTEGER,
    range_nm INTEGER,  -- Maximum range in nautical miles

    -- Certifications and capabilities
    etops_certified BOOLEAN DEFAULT false,
    etops_minutes INTEGER,  -- 120, 180, 240
    cat_ii_iii_certified BOOLEAN DEFAULT false,
    rnav_certified BOOLEAN DEFAULT false,

    -- Restrictions
    route_restrictions JSONB DEFAULT '[]'::jsonb,  -- Specific route limitations
    airport_restrictions JSONB DEFAULT '[]'::jsonb,  -- Airports cannot serve

    -- Audit fields
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Metadata
    notes TEXT,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Add comments
COMMENT ON TABLE aircraft_availability IS 'Aircraft fleet availability and maintenance tracking';
COMMENT ON COLUMN aircraft_availability.etops_minutes IS 'ETOPS certification: 120, 180, or 240 minutes';
COMMENT ON COLUMN aircraft_availability.maintenance_type IS 'A-check, B-check, C-check, or D-check';

-- Indexes
CREATE INDEX idx_aircraft_registration ON aircraft_availability(aircraft_registration);
CREATE INDEX idx_aircraft_type ON aircraft_availability(aircraft_type);
CREATE INDEX idx_aircraft_status ON aircraft_availability(status);
CREATE INDEX idx_aircraft_availability ON aircraft_availability(available_from, available_to);
CREATE INDEX idx_aircraft_airline ON aircraft_availability(operating_airline);
CREATE INDEX idx_aircraft_base ON aircraft_availability(home_base);
CREATE INDEX idx_aircraft_location ON aircraft_availability(current_location);
CREATE UNIQUE INDEX idx_unique_aircraft_registration ON aircraft_availability(aircraft_registration, available_from);

-- -----------------------------------------------------
-- minimum_connect_times: MCT requirements
-- -----------------------------------------------------
-- Description: Minimum connection times per IATA standards
-- Varies by airport, terminals, and connection type
-- -----------------------------------------------------
CREATE TABLE minimum_connect_times (
    mct_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Airport
    airport_code VARCHAR(3) NOT NULL CHECK (airport_code ~ '^[A-Z]{3}$'),

    -- Terminal information
    from_terminal VARCHAR(10),
    to_terminal VARCHAR(10),

    -- Connection type
    connection_type connection_type NOT NULL,

    -- MCT in minutes
    mct_minutes INTEGER NOT NULL CHECK (mct_minutes > 0),

    -- Additional factors
    requires_security_recheck BOOLEAN DEFAULT false,
    requires_customs BOOLEAN DEFAULT false,
    requires_immigration BOOLEAN DEFAULT false,
    baggage_recheck_required BOOLEAN DEFAULT false,

    -- Terminal transfer
    terminal_transfer_method VARCHAR(50),  -- walk, bus, train, airside
    terminal_transfer_time_minutes INTEGER,

    -- Effective date range
    effective_from DATE NOT NULL,
    effective_to DATE,

    -- Airline-specific overrides
    airline_code VARCHAR(3),  -- NULL for general, specific airline for override

    -- Audit fields
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Metadata
    notes TEXT,
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Add comments
COMMENT ON TABLE minimum_connect_times IS 'IATA-compliant minimum connection time requirements';
COMMENT ON COLUMN minimum_connect_times.connection_type IS 'Type of connection affecting MCT requirements';

-- Indexes
CREATE INDEX idx_mct_airport ON minimum_connect_times(airport_code);
CREATE INDEX idx_mct_terminals ON minimum_connect_times(from_terminal, to_terminal);
CREATE INDEX idx_mct_type ON minimum_connect_times(connection_type);
CREATE INDEX idx_mct_airline ON minimum_connect_times(airline_code);
CREATE INDEX idx_mct_dates ON minimum_connect_times(effective_from, effective_to);

-- -----------------------------------------------------
-- crew_bases: Crew base locations
-- -----------------------------------------------------
-- Description: Crew base stations for crew assignment
-- Supports legality and duty time calculations
-- -----------------------------------------------------
CREATE TABLE crew_bases (
    base_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Base information
    base_code VARCHAR(10) NOT NULL UNIQUE,
    base_name VARCHAR(200) NOT NULL,
    airport_code VARCHAR(3) NOT NULL,

    -- Airline
    airline_code VARCHAR(3) NOT NULL,

    -- Crew types at base
    has_pilots BOOLEAN DEFAULT true,
    has_cabin_crew BOOLEAN DEFAULT true,
    has_maintenance BOOLEAN DEFAULT false,

    -- Capacity
    pilot_capacity INTEGER,
    cabin_crew_capacity INTEGER,

    -- Time zone
    timezone VARCHAR(50),

    -- Status
    is_active BOOLEAN DEFAULT true,

    -- Audit fields
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Add comments
COMMENT ON TABLE crew_bases IS 'Crew base locations for crew assignment optimization';

-- Indexes
CREATE INDEX idx_crew_bases_airport ON crew_bases(airport_code);
CREATE INDEX idx_crew_bases_airline ON crew_bases(airline_code);
CREATE INDEX idx_crew_bases_active ON crew_bases(is_active);

-- -----------------------------------------------------
-- regulatory_requirements: Compliance tracking
-- -----------------------------------------------------
-- Description: Regulatory requirements by region/country
-- Tracks permits, authorizations, bilateral agreements
-- -----------------------------------------------------
CREATE TABLE regulatory_requirements (
    requirement_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Jurisdiction
    country_code VARCHAR(2) NOT NULL,  -- ISO 3166-1 alpha-2
    region_code VARCHAR(10),           -- State/province if applicable

    -- Requirement details
    requirement_type VARCHAR(100) NOT NULL,
    requirement_name VARCHAR(200) NOT NULL,
    description TEXT,

    -- Affected operations
    applies_to_airlines VARCHAR(3)[],  -- Specific airlines or NULL for all
    applies_to_routes JSONB,           -- Specific routes affected

    -- Compliance details
    compliance_data JSONB NOT NULL,

    -- Effective date range
    effective_from DATE NOT NULL,
    effective_to DATE,

    -- Authority
    regulatory_authority VARCHAR(200),
    authority_contact JSONB,

    -- Audit fields
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Add comments
COMMENT ON TABLE regulatory_requirements IS 'Regional and national regulatory compliance requirements';

-- Indexes
CREATE INDEX idx_regulatory_country ON regulatory_requirements(country_code);
CREATE INDEX idx_regulatory_type ON regulatory_requirements(requirement_type);
CREATE INDEX idx_regulatory_dates ON regulatory_requirements(effective_from, effective_to);
CREATE INDEX idx_regulatory_airlines ON regulatory_requirements USING GIN(applies_to_airlines);

-- =====================================================
-- VALIDATION FUNCTIONS
-- =====================================================

-- Function to check if a flight violates airport curfew
CREATE OR REPLACE FUNCTION check_curfew_violation(
    p_airport_code VARCHAR(3),
    p_operation_time TIME,
    p_operation_date DATE
)
RETURNS BOOLEAN AS $$
DECLARE
    v_has_violation BOOLEAN := false;
    v_constraint RECORD;
BEGIN
    FOR v_constraint IN
        SELECT constraint_data
        FROM airport_constraints
        WHERE airport_code = p_airport_code
          AND constraint_type = 'curfew'
          AND effective_from <= p_operation_date
          AND (effective_to IS NULL OR effective_to >= p_operation_date)
    LOOP
        -- Check if operation time falls within curfew window
        -- This is simplified; actual implementation would parse constraint_data
        -- and check time ranges including timezone considerations
        IF p_operation_time >= (v_constraint.constraint_data->>'start_time')::TIME
           AND p_operation_time <= (v_constraint.constraint_data->>'end_time')::TIME
        THEN
            v_has_violation := true;
            EXIT;
        END IF;
    END LOOP;

    RETURN v_has_violation;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION check_curfew_violation IS 'Check if flight operation violates airport curfew';

-- Function to get MCT for a connection
CREATE OR REPLACE FUNCTION get_minimum_connect_time(
    p_airport_code VARCHAR(3),
    p_from_terminal VARCHAR(10),
    p_to_terminal VARCHAR(10),
    p_connection_type connection_type,
    p_airline_code VARCHAR(3) DEFAULT NULL
)
RETURNS INTEGER AS $$
DECLARE
    v_mct INTEGER;
BEGIN
    -- Try to find airline-specific MCT first
    SELECT mct_minutes INTO v_mct
    FROM minimum_connect_times
    WHERE airport_code = p_airport_code
      AND (from_terminal = p_from_terminal OR from_terminal IS NULL)
      AND (to_terminal = p_to_terminal OR to_terminal IS NULL)
      AND connection_type = p_connection_type
      AND airline_code = p_airline_code
      AND effective_from <= CURRENT_DATE
      AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
    ORDER BY airline_code DESC NULLS LAST  -- Prefer airline-specific
    LIMIT 1;

    -- If not found, try general MCT
    IF v_mct IS NULL THEN
        SELECT mct_minutes INTO v_mct
        FROM minimum_connect_times
        WHERE airport_code = p_airport_code
          AND (from_terminal = p_from_terminal OR from_terminal IS NULL)
          AND (to_terminal = p_to_terminal OR to_terminal IS NULL)
          AND connection_type = p_connection_type
          AND airline_code IS NULL
          AND effective_from <= CURRENT_DATE
          AND (effective_to IS NULL OR effective_to >= CURRENT_DATE)
        LIMIT 1;
    END IF;

    -- Return MCT or default 45 minutes if not found
    RETURN COALESCE(v_mct, 45);
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_minimum_connect_time IS 'Get MCT for airport connection with airline override support';

-- Function to check aircraft availability for a time window
CREATE OR REPLACE FUNCTION is_aircraft_available(
    p_aircraft_registration VARCHAR(10),
    p_from_time TIMESTAMP WITH TIME ZONE,
    p_to_time TIMESTAMP WITH TIME ZONE
)
RETURNS BOOLEAN AS $$
DECLARE
    v_is_available BOOLEAN;
BEGIN
    SELECT EXISTS(
        SELECT 1
        FROM aircraft_availability
        WHERE aircraft_registration = p_aircraft_registration
          AND status = 'available'
          AND available_from <= p_from_time
          AND (available_to IS NULL OR available_to >= p_to_time)
    ) INTO v_is_available;

    RETURN v_is_available;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION is_aircraft_available IS 'Check if aircraft is available for specified time window';

-- =====================================================
-- TRIGGERS
-- =====================================================

-- Update timestamp trigger for airport_slots
CREATE TRIGGER update_airport_slots_updated_at
    BEFORE UPDATE ON airport_slots
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Update timestamp trigger for airport_constraints
CREATE TRIGGER update_airport_constraints_updated_at
    BEFORE UPDATE ON airport_constraints
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Update timestamp trigger for aircraft_availability
CREATE TRIGGER update_aircraft_availability_updated_at
    BEFORE UPDATE ON aircraft_availability
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Update timestamp trigger for minimum_connect_times
CREATE TRIGGER update_minimum_connect_times_updated_at
    BEFORE UPDATE ON minimum_connect_times
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =====================================================
-- VIEWS
-- =====================================================

-- View of current slot allocations
CREATE OR REPLACE VIEW v_current_slot_allocations AS
SELECT
    s.slot_id,
    s.airport_code,
    s.slot_time,
    s.slot_type,
    s.allocated_to_airline,
    f.flight_number,
    f.origin_airport,
    f.destination_airport,
    s.confirmed,
    s.historical_rights
FROM airport_slots s
LEFT JOIN flights f ON s.allocated_to_flight = f.flight_id
WHERE s.slot_season = (
    SELECT season_code
    FROM schedules
    WHERE status = 'active'
    LIMIT 1
);

COMMENT ON VIEW v_current_slot_allocations IS 'Current season slot allocations with flight details';

-- View of available aircraft
CREATE OR REPLACE VIEW v_available_aircraft AS
SELECT
    aircraft_registration,
    aircraft_type,
    aircraft_subtype,
    operating_airline,
    home_base,
    current_location,
    available_from,
    available_to,
    etops_certified,
    etops_minutes
FROM aircraft_availability
WHERE status = 'available'
  AND available_from <= NOW()
  AND (available_to IS NULL OR available_to >= NOW());

COMMENT ON VIEW v_available_aircraft IS 'Currently available aircraft fleet';

-- =====================================================
-- END OF CONSTRAINT & VALIDATION TABLES SCHEMA
-- =====================================================
